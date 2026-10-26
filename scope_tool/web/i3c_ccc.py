from __future__ import annotations

"""I3C Basic v1.2 常用 CCC 子集；版本不確定的 payload 僅保留 raw。# 待真機驗證。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    form: str
    defining: str = 'none'
    defvals: tuple[int, ...] | None = None
    payload: tuple[int, ...] | None = (0,)
    parse: bool = True
    note: str | None = None


def _commands() -> dict[int, Command]:
    table = {}
    for code, name, lengths in [(0, 'ENEC', (1,)), (1, 'DISEC', (1,)),
                                (6, 'RSTDAA', (0,)), (7, 'ENTDAA', (0,)),
                                (8, 'DEFTGTS', None), (9, 'SETMWL', (2,)),
                                (10, 'SETMRL', (2, 3)), (18, 'ENDXFER', None)]:
        table[code] = Command(name, 'broadcast', payload=lengths, parse=code != 18)
    for code in range(2, 6):
        table[code] = Command(f'ENTAS{code - 2}', 'broadcast')
    for code in (0, 1, 2, 3, 4, 5, 9, 10, 18):
        c = table[code]
        table[code | 128] = Command(c.name, 'direct', payload=c.payload, parse=c.parse)
    for code, name, lengths in [(0x87, 'SETDASA', (1,)), (0x88, 'SETNEWDA', (1,)),
                                (0x8B, 'GETMWL', (2,)), (0x8C, 'GETMRL', (2, 3)),
                                (0x8D, 'GETPID', (6,)), (0x8E, 'GETBCR', (1,)),
                                (0x8F, 'GETDCR', (1,)), (0x90, 'GETSTATUS', (2,))]:
        table[code] = Command(name, 'direct', payload=lengths)
    table[0x86] = Command('RSTDAA', 'direct', note='v1.1 起不得使用')
    for code, name in [(0x94, 'GETMXDS'), (0x95, 'GETCAPS')]:
        table[code] = Command(name, 'direct', defining='optional', payload=None, parse=False)
    for code in range(0x20, 0x28):
        table[code] = Command(f'ENTHDR{code - 0x20}', 'broadcast',
                              note='非 Basic' if code in (0x21, 0x22) else None)
    for code in (0x2A, 0x9A):
        table[code] = Command('RSTACT', 'direct' if code & 128 else 'broadcast',
                              defining='required', defvals=(0, 1, 2))
    return table


COMMANDS = _commands()
RESET_ACTION = {0: '不重設', 1: '周邊重設', 2: '整個 Target 重設'}


def reason(frame: dict, code: str, severity: str = 'error') -> None:
    if code not in frame['reasons']:
        frame['reasons'].append(code)
    if {'ok': 0, 'warn': 1, 'error': 2}[severity] > {'ok': 0, 'warn': 1, 'error': 2}[frame['status']]:
        frame['status'] = severity


def active(addresses: list[dict], da: int) -> dict | None:
    return next((a for a in reversed(addresses) if a['da'] == da and a['t_to'] is None), None)


def entry(da: int, how: str = 'observed', tm: float | None = None, **values: int) -> dict:
    return dict(da=da, pid=None, bcr=None, dcr=None, static=None, t_from=tm,
                t_to=None, how=how, note=None) | values


def invalidate(addresses: list[dict], tm: float, note: str) -> None:
    for a in addresses:
        if a['t_to'] is None:
            a.update(t_to=tm, note=note)


def assign(addresses: list[dict], a: dict, frame: dict) -> None:
    old = active(addresses, a['da'])
    if old and old['how'] != 'observed':
        reason(frame, 'addr_conflict')
        return
    if old:
        old['t_to'] = a['t_from']
    addresses.append(a)


def finish_ccc(frame: dict, addresses: list[dict]) -> None:
    """逐段驗證格式；每一段只有在 ACK、T 及長度皆正確才更新表。"""
    code = frame['ccc']
    cmd = COMMANDS.get(code)
    if cmd is None:
        frame['label'] = f'CCC 0x{code:02X}'
        reason(frame, 'ccc_unknown', 'ok')
        return
    frame['ccc_name'] = cmd.name
    frame['label'] = cmd.name + (f'（{cmd.note}）' if cmd.note else '')
    if code == 0x86:
        reason(frame, 'ccc_invalid', 'warn')
        return
    fields = frame['fields']
    ci = next(i for i, f in enumerate(fields) if f['kind'] == 'ccc')
    rest = fields[ci + 1:]
    first = next((i for i, f in enumerate(rest) if f['kind'] == 'addr'), len(rest))
    pre = rest[:first]
    # Broadcast RSTACT 的一個資料 byte 也是 action 定義。
    uses_def = cmd.form == 'direct' or cmd.name == 'RSTACT'
    if uses_def:
        bad = ((cmd.defining == 'none' and len(pre) != 0) or
               (cmd.defining == 'required' and len(pre) != 1) or
               (cmd.defining == 'optional' and len(pre) > 1))
        if cmd.defvals is not None and any(f['value'] not in cmd.defvals for f in pre):
            bad = True
        if bad:
            reason(frame, 'ccc_format')
        for f in pre:
            f['kind'] = 'def' if cmd.defining != 'none' else 'data'
            f['label'] = RESET_ACTION.get(f['value'], 'Defining Byte') if cmd.name == 'RSTACT' else 'Defining Byte'
    segments = []
    if cmd.form == 'broadcast':
        segments.append((fields[0], [] if uses_def else pre))
    else:
        for f in rest[first:]:
            if f['kind'] == 'addr':
                segments.append((f, []))
            elif segments:
                segments[-1][1].append(f)
    for header, data in segments:
        if header['ninth'] != 0:
            continue
        if cmd.payload is not None and len(data) not in cmd.payload:
            reason(frame, 'ccc_format')
            continue
        if not all(f['ok'] for f in data) or frame['status'] == 'error' or not cmd.parse:
            continue
        v = [f['value'] for f in data]
        tm, da = (data[-1]['t1'] if data else frame['t1']), header['value'] >> 1
        if cmd.name in ('SETDASA', 'SETNEWDA') and v:
            if v[0] & 1 or header['value'] & 1:
                reason(frame, 'ccc_format')
                continue
            destination = active(addresses, v[0] >> 1)
            if destination and destination['how'] != 'observed':
                reason(frame, 'addr_conflict')
                continue
            old = active(addresses, da)
            new = entry(v[0] >> 1, cmd.name, tm, static=da if cmd.name == 'SETDASA' else None)
            if cmd.name == 'SETNEWDA' and old:
                new.update({k: old[k] for k in ('pid', 'bcr', 'dcr', 'static')})
                old['t_to'] = tm
            assign(addresses, new, frame)
        elif cmd.name in ('GETPID', 'GETBCR', 'GETDCR') and v:
            if not header['value'] & 1:
                reason(frame, 'ccc_format')
                continue
            a = active(addresses, da)
            if a is None:
                a = entry(da)
                addresses.append(a)
            key = cmd.name[3:].lower()
            value = int.from_bytes(bytes(v), 'big')
            if a[key] is not None and a[key] != value:
                reason(frame, 'addr_conflict')
            else:
                a[key] = value
        elif cmd.name == 'RSTDAA' and cmd.form == 'broadcast':
            invalidate(addresses, tm, 'RSTDAA')
        if v and cmd.name in ('ENEC', 'DISEC', 'SETMWL', 'SETMRL', 'GETMWL', 'GETMRL', 'GETSTATUS'):
            value = v[0] if len(v) == 1 else int.from_bytes(bytes(v[:2]), 'big')
            data[0]['label'] = f'{cmd.name}={value}' + (f' IBI長度={v[2]}' if len(v) == 3 else '')


if __name__ == '__main__':
    assert COMMANDS[0x8D].name == 'GETPID' and COMMANDS[0x86].note
    assert all(i in COMMANDS for i in range(0x20, 0x28))
    assert COMMANDS[0x9A].defining == 'required' and 0x5A not in COMMANDS
    a = [entry(8, 'ENTDAA', 1.)]
    invalidate(a, 2., 'RSTDAA')
    assert a[0]['t_to'] == 2.
    print('web.i3c_ccc self-check OK')
