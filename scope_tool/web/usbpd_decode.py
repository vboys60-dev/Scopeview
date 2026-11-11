from __future__ import annotations

"""USB PD CC 線 BMC 與封包解碼；待實機驗證。"""
import zlib
import numpy as np
from scope_tool.web.logic import Edges
from scope_tool.web.i3c_fields import frame
from scope_tool.web.i3c_ccc import reason
from scope_tool.web.usbpd_fields import DATA_CODES, ORDERED, EOP, header

ROLES = {'cc': True}
BASE = 'cc'
REQUIRE_EDGES = True
ADDR_TABLE = False


def options(options: dict, channels: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {'bitrate'}:
        raise ValueError('USB PD 參數不合法')
    rate = options.get('bitrate')
    if rate is not None and (isinstance(rate, bool) or not isinstance(rate, (int, float))
                             or not np.isfinite(rate) or rate <= 0):
        raise ValueError('位元率須為有限正數或空白')
    return dict(bitrate=rate)


def _field(kind: str, ts: list, a: int, b: int, value: int | None, label: str = '', ok: bool = True) -> dict:
    return dict(t0=ts[a], t1=ts[b], kind=kind, addr=None, value=value, nbits=b-a,
                ninth=None, ninth_kind=None, ok=ok, label=label)


def _packet(times: np.ndarray, end: float, rate: float | None) -> tuple[dict, list, float]:
    ds = np.diff(times)
    # ponytail: 前 48 個間隔取中位數；前導碼至少提供足夠交替位元。
    ui = 1 / rate if rate else float(np.median(ds[:min(48, len(ds))]))
    if not rate:
        # 交替前導碼的短間隔占三分之二。
        ui *= 2
    f = frame(float(times[0]), 'partial')
    bits, ts, i, failed = [], [], 0, False
    while i < len(ds):
        d = float(ds[i])
        if d >= .75 * ui:
            if d > 1.35 * ui:
                failed = True
                break
            bit, duration, step = 0, d, 1
        elif i + 1 < len(ds) and ds[i + 1] < .75 * ui:
            bit, duration, step = 1, d + float(ds[i+1]), 2
            if not .65 * ui <= duration <= 1.35 * ui:
                failed = True
                break
        else:
            failed = True
            break
        ts.append(float(times[i])); bits.append(bit)
        ui = .9 * ui + .1 * duration
        i += step
    ts.append(min(end, float(times[min(i, len(times)-1)])))
    f['t1'] = ts[-1]
    if failed:
        reason(f, 'sampler', 'error')
    def code(pos: int) -> int:
        return sum(bits[pos+j] << j for j in range(5))
    # ponytail: ordered set 四個 K 碼須全部正確，暫不接受四中三。
    found = None
    for pos in range(16, max(16, len(bits)-19)):
        if all(bits[j] != bits[j-1] for j in range(pos-15, pos)):
            key = tuple(code(pos+5*j) for j in range(4))
            if key in ORDERED:
                found = (pos, ORDERED[key]); break
    if found is None:
        reason(f, 'preamble' if len(bits) < 36 else 'bad_sop', 'error')
        return f, list(zip(ts, bits)), ui
    pos, sop = found
    f['fields'].append(_field('sop', ts, pos, pos+20, None, sop))
    pos += 20
    if sop in ('Hard Reset', 'Cable Reset'):
        f.update(kind='hard_reset' if sop == 'Hard Reset' else 'cable_reset', label=sop, t1=ts[pos])
        return f, list(zip(ts[:pos], bits[:pos])), ui
    nibbles, spans, eop_pos = [], [], None
    while pos + 5 <= len(bits):
        c = code(pos)
        if c == EOP:
            eop_pos = pos
            f['fields'].append(_field('eop', ts, pos, pos+5, None, 'EOP'))
            pos += 5
            break
        if c not in DATA_CODES:
            reason(f, 'invalid_5b', 'error'); break
        nibbles.append(DATA_CODES.index(c)); spans.append(pos); pos += 5
    raw = bytes(nibbles[j] | (nibbles[j+1] << 4) for j in range(0, len(nibbles)-1, 2))
    if len(raw) >= 2:
        h = int.from_bytes(raw[:2], 'little'); info = header(h)
        f.update(kind=info['kind'], label=sop + ' ' + info['name'])
        f['fields'].append(_field('header', ts, spans[0], spans[3]+5, h, info['name']))
        for j in range(info['count']):
            offset = 2 + 4*j
            if len(raw) < offset+4: break
            f['fields'].append(_field('obj', ts, spans[offset*2], spans[(offset+4)*2-1]+5,
                                      int.from_bytes(raw[offset:offset+4], 'little')))
        needed = 2 + 4*info['count'] + 4
        if len(raw) >= needed:
            offset = needed-4; got = int.from_bytes(raw[offset:needed], 'little')
            good = zlib.crc32(raw[:offset]) == got
            f['fields'].append(_field('crc', ts, spans[offset*2], spans[needed*2-1]+5, got, '', good))
            if not good: reason(f, 'crc', 'error')
        else:
            reason(f, 'truncated', 'warn')
        if info['name'].startswith('Reserved') or info['spec_rev'] == 3:
            reason(f, 'reserved', 'warn')
        if len(raw) > needed or len(nibbles) % 2:
            reason(f, 'bad_eop', 'error')
    else:
        reason(f, 'truncated', 'warn')
    if eop_pos is None:
        reason(f, 'bad_eop', 'error')
    f['fields'].sort(key=lambda x: x['t0'])
    f['t1'] = max(f['t1'], ts[pos] if pos < len(ts) else ts[-1])
    return f, list(zip(ts[:pos], bits[:pos])), ui


def run(edges: dict[str, Edges], *, t1: float | None = None, max_frames: int = 100000,
        max_fields: int = 100000, **opts: object) -> dict:
    rate = options(opts, edges)['bitrate']
    if any(type(x) is not int or x < 1 for x in (max_frames, max_fields)):
        raise ValueError('事件上限須為正整數')
    e = edges['cc']; end = float(t1 if t1 is not None else e.time[-1])
    times = e.time[(e.value >= 0) & ~e.resync]
    groups = np.split(times, np.flatnonzero(np.diff(times) > 3 / 300000) + 1)
    frames, wire, warnings, count, halted = [], [], [], 0, False
    for group in groups:
        if len(group) < 2: continue
        f, bits, ui = _packet(group, end, rate)
        if len(frames) >= max_frames or count + len(f['fields']) > max_fields:
            end = f['t0']; halted = True; break
        if not 1/360000 <= ui <= 1/240000 and '位元率超出預期範圍' not in warnings:
            warnings.append('位元率超出預期範圍')
        f['i'] = len(frames); frames.append(f); wire.extend(bits); count += len(f['fields'])
    truncated = halted or e.truncated or any('truncated' in f['reasons'] for f in frames)
    if halted or e.truncated: warnings.append(f'事件或邊沿超過上限，只解到 t={end:.12g}')
    return dict(frames=frames, bits_t=np.array([x[0] for x in wire]),
                bits_v=np.array([x[1] for x in wire], dtype=np.int8), addresses=[],
                warnings=warnings, truncated=truncated, t1=end)


if __name__ == '__main__':
    assert options({}, {}) == {'bitrate': None}
    assert options({'bitrate': 300000}, {})['bitrate'] == 300000
    print('web.usbpd_decode self-check OK')
