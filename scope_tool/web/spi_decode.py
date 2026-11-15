from __future__ import annotations

"""SPI 單線或雙線取樣解碼；待實機驗證。"""
import numpy as np
from scope_tool.web.logic import Edges, levels_at
from scope_tool.web.i3c_fields import frame
from scope_tool.web.i3c_ccc import reason

ROLES = {'sclk': True, 'mosi': False, 'miso': False, 'cs': False}
BASE = 'sclk'
ADDR_TABLE = False
REQUIRE_EDGES = False


def options(options: dict, channels: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {'mode', 'bits', 'lsb', 'cs_active', 'idle'}:
        raise ValueError('SPI 參數不合法')
    o = dict(mode=0, bits=8, lsb=False, cs_active='low', idle=None)
    o.update(options)
    idle = o['idle']
    if (type(o['mode']) is not int or o['mode'] not in range(4) or type(o['bits']) is not int
            or not 4 <= o['bits'] <= 32 or type(o['lsb']) is not bool
            or o['cs_active'] not in ('low', 'high') or (idle is not None and
            (isinstance(idle, bool) or not isinstance(idle, (int, float)) or not np.isfinite(idle) or idle <= 0))):
        raise ValueError('SPI 模式、字長、位序、CS 極性或閒置時間不合法')
    if not any(k in channels for k in ('mosi', 'miso')):
        raise ValueError('SPI 至少需要 MOSI 或 MISO')
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
    clk = edges['sclk']
    mask = (clk.time <= end) & ~clk.resync & (clk.value >= 0)
    ct, cv = clk.time[mask], clk.value[mask]
    cpol, cpha = o['mode'] >> 1, o['mode'] & 1
    rising = (cpol == cpha)
    sample = ct[cv == int(rising)]
    spans = []
    if 'cs' in edges:
        cs = edges['cs']
        active = int(o['cs_active'] == 'high')
        start, first = None, False
        for i, (tm, value) in enumerate(zip(cs.time, cs.value)):
            if tm > end:
                break
            if value == active and start is None:
                start, first = float(tm), bool(cs.resync[i])
            elif value != active and start is not None:
                spans.append((start, float(tm), first, False, False, value < 0))
                start = None
        if start is not None:
            spans.append((start, end, first, True, False, False))
    elif len(ct):
        indexes = np.flatnonzero(np.diff(ct) > o['idle']) + 1 if o['idle'] is not None else np.array([], dtype=int)
        for group in np.split(ct, indexes):
            if len(group):
                spans.append((float(group[0]), float(group[-1]), False, False, True, False))
    frames, bits_t, bits_v, warnings = [], [], [], []
    truncated = bool(cuts)
    count = 0
    halted = False
    for a, b, first, last, no_cs, cut in spans:
        st = sample[(sample >= a) & (sample <= b if no_cs or last else sample < b)]
        if no_cs and not len(st):
            continue
        f = frame(float(st[0]) if no_cs else a, 'txn')
        f['t1'] = float(st[-1]) if no_cs else b
        if no_cs:
            reason(f, 'no_cs', 'ok')
            f['label'] = '無 CS：字組對齊未驗證'
            prior = levels_at(clk, np.array([np.nextafter(a, -np.inf)]), end)[0]
            if prior != cpol:
                reason(f, 'clk_phase', 'warn')
        else:
            if first or last or cut:
                reason(f, 'truncated', 'warn')
                f['label'] = ('CS 進入未知區段，交易可能未結束' if cut else
                              ('擷取開始時 CS 已有效，對齊未知' if a == cs.time[0] else 'CS 未知區段後恢復有效，對齊未知') if first else '擷取結束時 CS 仍有效')
                truncated = True
            if levels_at(clk, np.array([a]), end)[0] != cpol:
                reason(f, 'clk_phase', 'warn')
        values = {lane: levels_at(edges[lane], st, end) for lane in ('mosi', 'miso') if lane in edges}
        primary = 'mosi' if 'mosi' in values else 'miso'
        gaps = [g0 for g0, g1 in clk.unknown if g0 < b and g1 > a]
        bounds = [0, *np.searchsorted(st,gaps), len(st)]
        words = [(p, min(p+o['bits'], hi)) for lo, hi in zip(bounds, bounds[1:]) for p in range(lo, hi, o['bits'])]
        if gaps:
            reason(f, 'unknown_bit', 'warn')
        for p, q in words:
            ts = st[p:q]
            if len(frames) >= max_frames or count + len(values) > max_fields:
                truncated = True
                halted = True
                reason(f, 'truncated', 'warn')
                f['t1'] = float(ts[0])
                end = min(end, f['t1'])
                break
            if len(ts) < o['bits']:
                reason(f, 'incomplete', 'warn')
            for lane, vals in values.items():
                v = vals[p:q]
                unknown = bool(np.any(v < 0))
                if unknown:
                    reason(f, 'unknown_bit', 'warn')
                value = None if unknown else sum(int(bit) << (j if o['lsb'] else len(v)-1-j) for j, bit in enumerate(v))
                # ponytail: 未知半位元組以問號表示，保留已知半位元組。
                ordered = list(reversed(v)) if o['lsb'] else list(v)
                ordered = [0] * ((-len(ordered)) % 4) + ordered
                label = '0x' + ''.join('?' if min(ordered[i:i+4]) < 0 else format(sum(int(x) << (3-j) for j, x in enumerate(ordered[i:i+4])), 'X') for i in range(0, len(ordered), 4))
                f['fields'].append(dict(t0=float(ts[0]), t1=float(ts[-1]), kind=lane, addr=None,
                                        value=value, nbits=len(ts), ninth=None, ninth_kind=None,
                                        ok=not unknown and len(ts) == o['bits'], label=label))
                count += 1
            bits_t.extend(map(float, ts))
            bits_v.extend(map(int, values[primary][p:q]))
        if len(frames) >= max_frames:
            truncated = True
            end = min(end, a)
            break
        f['i'] = len(frames)
        frames.append(f)
        if halted:
            break
    if 'cs' in edges:
        inside = np.zeros(len(ct), dtype=bool)
        for a, b, _, last, _, _ in spans:
            inside |= (ct >= a) & ((ct <= b) if last else (ct < b))
        for g0, g1 in cs.unknown:
            inside |= (ct >= g0) & (ct < g1)
        outside = int(np.sum(~inside))
        if outside:
            warnings.append(f'CS 外時脈 {outside} 個')
    if cuts or end < (t1 if t1 is not None else end):
        warnings.append(f'事件或邊沿超過上限，只解到 t={end:.12g}')
    return dict(frames=frames, bits_t=np.array(bits_t), bits_v=np.array(bits_v, dtype=np.int8),
                addresses=[], warnings=warnings, truncated=truncated, t1=end)


if __name__ == '__main__':
    assert options({}, {'mosi': 'x'})['bits'] == 8
    print('web.spi_decode self-check OK')
