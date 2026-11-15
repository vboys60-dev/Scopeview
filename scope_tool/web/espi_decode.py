from __future__ import annotations

"""eSPI 單線交易解碼；待實機驗證。"""
import numpy as np
from scope_tool.web.logic import Edges, levels_at
from scope_tool.web.i3c_fields import frame
from scope_tool.web.i3c_ccc import reason
from scope_tool.web.espi_table import command, crc8

ROLES = {'cs': True, 'clk': True, 'io0': True, 'io1': True, 'io2': False, 'io3': False}
BASE = 'clk'
ADDR_TABLE = False
REQUIRE_EDGES = False


def options(options: dict, channels: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {'io_mode', 'crc'}:
        raise ValueError('eSPI 參數不合法')
    o = dict(io_mode='single', crc=True)
    o.update(options)
    if o['io_mode'] != 'single' or type(o['crc']) is not bool:
        raise ValueError('eSPI 第一版只支援單線模式；CRC 須為布林值')
    return o


def run(edges: dict[str, Edges], *, t1: float | None = None, max_frames: int = 100_000,
        max_fields: int = 100_000, **opts: object) -> dict:
    o = options(opts, edges)
    if any(type(n) is not int or n < 1 for n in (max_frames, max_fields)):
        raise ValueError('事件上限須為正整數')
    end = float(t1 if t1 is not None else max(e.time[-1] for e in edges.values()))
    cuts = [float(e.time[-1]) for e in edges.values() if e.truncated]
    if cuts:
        end = min(end, *cuts)
    cs, clk = edges['cs'], edges['clk']
    spans, start = [], None
    for tm, value in zip(cs.time, cs.value):
        if tm > end:
            break
        if value == 0 and start is None:
            start = float(tm)
        elif value != 0 and start is not None:
            spans.append((start, float(tm), start == float(cs.time[0]), False))
            start = None
    if start is not None:
        spans.append((start, end, start == float(cs.time[0]), True))
    sample = clk.time[(clk.time <= end) & ~clk.resync & (clk.value == 1)]
    frames, bits_t, bits_v, warnings = [], [], [], []
    truncated, count, halt = bool(cuts), 0, False
    for a, b, first, last in spans:
        if len(frames) >= max_frames:
            truncated, end = True, a
            break
        ts = sample[(sample >= a) & ((sample <= b) if last else (sample < b))]
        v0, v1 = (levels_at(edges[k], ts, end) for k in ('io0', 'io1'))
        f = frame(a, 'cmd')
        f['t1'], f['i'] = b, len(frames)
        if first or last:
            reason(f, 'truncated', 'warn')
            truncated = True
        pos = 0
        def take(kind: str, n: int, vals: np.ndarray) -> int | None:
            nonlocal pos, count, truncated, end, halt
            if pos >= len(ts):
                reason(f, 'incomplete', 'warn')
                return None
            if count >= max_fields:
                truncated, halt, end = True, True, min(end, float(ts[pos]))
                f['t1'] = end
                reason(f, 'truncated', 'warn')
                return None
            stop = min(pos+n, len(ts))
            part = vals[pos:stop]
            unknown = bool(np.any(part < 0))
            if unknown:
                reason(f, 'unknown_bit', 'warn')
            if stop-pos < n:
                reason(f, 'incomplete', 'warn')
            value = None if unknown or stop-pos < n else sum(int(x) << (n-1-i) for i, x in enumerate(part))
            f['fields'].append(dict(t0=float(ts[pos]), t1=float(ts[stop-1]), kind=kind, addr=None,
                                    value=value, nbits=stop-pos, ninth=None, ninth_kind=None,
                                    ok=value is not None, label='' if value is not None else '資料不完整或未知'))
            bits_t.extend(map(float, ts[pos:stop]))
            bits_v.extend(map(int, part))
            count += 1
            pos = stop
            return value
        op = take('opcode', 8, v0)
        if op is None:
            f['kind'] = 'partial'
        elif op == 0xff:
            x = take('hdr', 8, v0)
            if x == 0xff:
                f['kind'], f['label'] = 'reset', 'RESET'
            else:
                f['kind'] = 'partial'
                reason(f, 'incomplete', 'warn')
        else:
            cmd = [op]
            name, length = command(cmd)
            while name and length is None and pos+8 <= len(ts):
                x = take('hdr', 8, v0)
                if x is None:
                    break
                cmd.append(x)
                name, length = command(cmd)
            f['label'] = name or '未知命令'
            if not name:
                reason(f, 'unknown_opcode', 'warn')
                while pos < len(ts) and not halt:
                    take('data', 8, v0)
            elif length is None:
                reason(f, 'incomplete', 'warn')
            else:
                while len(cmd) < length and pos < len(ts) and not halt:
                    index = len(cmd)
                    kind = 'crc' if index == length-1 else ('addr' if op in (0x21, 0x22) and index < 3 else 'hdr' if op == 4 and index == 1 else 'data')
                    x = take(kind, 8, v0)
                    if x is None:
                        break
                    cmd.append(x)
                if len(cmd) < length:
                    reason(f, 'incomplete', 'warn')
                else:
                    if o['crc'] and crc8(cmd[:-1]) != cmd[-1]:
                        reason(f, 'crc_cmd')
                    pos += 2
                    resp = take('resp', 8, v1)
                    while resp == 0x0f and not halt:
                        f['fields'][-1]['kind'] = 'wait'
                        resp = take('resp', 8, v1)
                    if resp == 0xff:
                        reason(f, 'no_response', 'warn')
                    elif resp is not None:
                        if resp & 15 == 1:
                            reason(f, 'defer', 'warn')
                        elif resp & 15 == 3:
                            reason(f, 'fatal')
                        # ponytail: 附加通道封包尚未細解，無法可靠推定回應長度。
                        if resp & 0xf0:
                            reason(f, 'incomplete', 'warn')
                        else:
                            response = [resp]
                            ndata = 4 if op == 0x21 and resp & 15 == 8 else 0
                            for kind in ['data']*ndata + ['status', 'status', 'crc']:
                                x = take(kind, 8, v1)
                                if x is None:
                                    break
                                response.append(x)
                            if len(response) == ndata + 4:
                                status = response[-3] | response[-2] << 8
                                if status & 0xcc00:
                                    reason(f, 'reserved_bit', 'warn')
                                if o['crc'] and crc8(response[:-1]) != response[-1]:
                                    reason(f, 'crc_resp')
        frames.append(f)
        if halt:
            break
    if cuts:
        warnings.append(f'邊沿超過上限，只解到 t={end:.12g}')
    return dict(frames=frames, bits_t=np.array(bits_t), bits_v=np.array(bits_v, dtype=np.int8),
                addresses=[], warnings=warnings, truncated=truncated, t1=end)


if __name__ == '__main__':
    assert options({}, {}) == {'io_mode': 'single', 'crc': True}
    print('web.espi_decode self-check OK')
