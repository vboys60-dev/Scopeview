from __future__ import annotations

"""解碼結果建構與 DAA 欄位切割。# 待真機驗證。"""
from collections.abc import Callable
from scope_tool.web.i3c_ccc import active, assign, entry, reason


def frame(tm: float, kind: str = 'partial', start: str | None = None) -> dict:
    return dict(i=0, t0=tm, t1=tm, kind=kind, start=start, addr=None, rw=None,
                ack=None, ccc=None, ccc_name=None, label='', status='ok', reasons=[], fields=[])


def field(bits: list[tuple[float, int]], kind: str, ninth_kind: str | None = None,
          addr: int | None = None, label: str = '') -> dict:
    data = bits[:-1] if ninth_kind else bits
    value = 0
    for _, v in data:
        value = (value << 1) | v
    return dict(t0=bits[0][0], t1=bits[-1][0], kind=kind, addr=addr, value=value,
                nbits=len(bits), ninth=bits[-1][1] if ninth_kind else None,
                ninth_kind=ninth_kind, ok=True, label=label)


def header(f: dict, bits: list[tuple[float, int]], i2c: set[int], addresses: list[dict],
           start: str, direct: bool, daa: bool) -> tuple[int, int, bool]:
    h = field(bits, 'addr', 'ack')
    da, rw, ack = h['value'] >> 1, h['value'] & 1, h['ninth'] == 0
    h['addr'] = da if direct else None
    f['fields'].append(h)
    if direct or daa:
        if not ack and not daa:
            reason(f, 'nack', 'warn')
        if daa and not ack:
            f['label'] = 'DAA 結束'
        return da, rw, ack
    kind = ('error' if da == 0x7E and rw else 'ccc_broadcast' if da == 0x7E
            else 'hotjoin' if da == 2 and rw == 0 and start == 'S' else 'i2c' if da in i2c
            else 'ibi' if rw and start == 'S' else 'private_read' if rw else 'private_write')
    f.update(kind=kind, addr=da, rw=rw, ack=ack)
    if kind == 'error':
        reason(f, 'addr_7e_read')
    if not ack:
        reason(f, 'nack', 'warn')
    if da not in (2, 0x7E) and kind != 'i2c':
        a = active(addresses, da)
        if a is None or a['how'] == 'observed':
            reason(f, 'type_unknown', 'ok')
            f['label'] = '位址類型未確認；若為 I2C 裝置請加入 I2C 位址清單'
            if a is None:
                addresses.append(entry(da))
    if kind == 'ibi':
        f['label'] += ' IBI（亦可能為 Controller 直接讀）' if ack else ' IBI 被拒／延後'
    return da, rw, ack


def daa_fields(f: dict, bits: list[tuple[float, int]], addresses: list[dict],
               parity: Callable[[int], int]) -> None:
    p, b, d = field(bits[:48], 'pid'), field(bits[48:56], 'bcr'), field(bits[56:64], 'dcr')
    a = field(bits[64:72], 'da', 'parity')
    a['nbits'], a['t1'] = 9, bits[72][0]
    a['ok'] = a['ninth'] == parity(a['value']) and bits[72][1] == 0
    f['fields'].extend([p, b, d, a])
    if a['ninth'] != parity(a['value']):
        reason(f, 'addr_parity')
    if bits[72][1]:
        reason(f, 'nack')
    if a['ok']:
        assign(addresses, entry(a['value'], 'ENTDAA', bits[72][0],
                                pid=p['value'], bcr=b['value'], dcr=d['value']), f)


if __name__ == '__main__':
    f = field([(0., 1), (1., 0)], 'data', 'parity')
    assert f['value'] == 1 and f['ninth'] == 0 and f['nbits'] == 2
    assert frame(1.)['status'] == 'ok'
    print('web.i3c_fields self-check OK')
