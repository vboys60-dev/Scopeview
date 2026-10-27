from __future__ import annotations

"""UART 離線中心取樣；狀態機與電氣反相分離，不估計鮑率。"""
import numpy as np
from scope_tool.web.logic import levels_at
from scope_tool.web.logic import Edges, auto_threshold, validate_time, to_edges
from scope_tool.web.i3c_fields import frame
from scope_tool.web.i3c_ccc import reason

ROLES = {'tx': True, 'rx': False}
BASE = 'tx'
ADDR_TABLE = False
REQUIRE_EDGES = False
GROUP_GAP = 2
_levels_at = levels_at  # 保留既有自檢的私有匯入點；實作統一使用共用函式。


def options(options: dict, channels: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {'baud', 'bits', 'parity', 'stop', 'invert'}:
        raise ValueError('UART 參數不合法')
    o = dict(bits=8, parity='N', stop=1, invert=False)
    o.update(options)
    try:
        valid = (not isinstance(o.get('baud'), bool) and np.isfinite(o['baud']) and o['baud'] > 0
                 and type(o['bits']) is int and 5 <= o['bits'] <= 9
                 and o['parity'] in ('N', 'E', 'O', 'M', 'S')
                 and not isinstance(o['stop'], bool) and o['stop'] in (1, 2)
                 and type(o['invert']) is bool)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('UART 需 baud>0、bits 5–9、parity N/E/O/M/S、stop 1/2 與布林 invert')
    return o


def _lane(e: Edges, lane: str, end: float, o: dict, limit: int) -> tuple:
    period, d, p, s = 1 / o['baud'], o['bits'], int(o['parity'] != 'N'), o['stop']
    pre, total = 1 + d + p, 1 + d + p + s
    keep = e.time <= end
    e = e._replace(time=e.time[keep], value=e.value[keep], resync=e.resync[keep])
    vals = np.where(e.value < 0, -1, 1 - e.value) if o['invert'] else e.value
    e = e._replace(value=vals)
    records, warnings = [], []
    if not len(e.time):
        return records, warnings, False
    last_rise = float(e.time[0]) if vals[0] == 1 else None
    synced, busy, false_starts = False, -np.inf, 0
    if vals[0] == 0:
        rises = e.time[vals == 1]
        stop = min(end, float(rises[0]) if len(rises) else end)
        records.append((float(e.time[0]), stop, None, ['unsynced'], []))
    for j, (tm, val) in enumerate(zip(e.time, vals)):
        if tm > end:
            break
        if val < 0:
            last_rise = None
        elif val == 1:
            last_rise = float(tm)
        if tm <= busy or j == 0 or val != 0 or vals[j - 1] == 0 or (synced and vals[j - 1] < 0):
            continue
        if not (synced or (last_rise is not None and tm - last_rise >= period * (1 - 1e-10))):
            continue
        times = tm + (np.arange(total) + .5) * period
        sampled = levels_at(e, times, end)
        if sampled[0] != 0:
            false_starts += 1
            synced, last_rise = False, None
            continue
        data, stops = sampled[1:1 + d], sampled[pre:]
        busy = float(times[-1])
        rs, item, bitlist = [], None, []
        next_j = j + 1
        low_end = float(e.time[next_j]) if next_j < len(vals) else end
        open_low = next_j >= len(vals) or low_end > end
        low_end = min(low_end, end)
        is_break = np.all(data == 0) and stops[0] == 0 and low_end - tm >= total * period * (1 - 1e-10)
        incomplete = times[-1] > end
        if is_break:
            rs = ['break'] + (['truncated'] if open_low else [])
            # busy 消耗整段低電位，相當於 BREAK_WAIT；結束上升緣重建 mark。
            busy, synced, last_rise = low_end, False, None
            item = dict(t0=float(tm), t1=low_end, kind=lane, addr=None, value=None,
                        nbits=0, ninth=None, ninth_kind=None, ok=True, label='BREAK')
        elif incomplete or synced or np.all(stops == 1):
            if incomplete:
                rs.append('truncated')
            elif not np.all(stops == 1):
                rs.append('framing')
            left = np.searchsorted(e.time, tm + pre * period, side='right')
            right = np.searchsorted(e.time, times[pre], side='left')
            if np.any(vals[left:right] == 0):
                rs.extend(x for x in ('framing', 'short_stop') if x not in rs)
            payload = sampled[1:1 + d + p]
            if np.any(payload < 0):
                rs.append('unknown_bit')
            value = None if incomplete or np.any(data < 0) or np.any(payload < 0) else sum(int(v) << k for k, v in enumerate(data))
            ninth = int(payload[-1]) if p else None
            if p and np.all(payload >= 0):
                expected = {'E': int(data.sum()) % 2, 'O': 1 - int(data.sum()) % 2, 'M': 1, 'S': 0}[o['parity']]
                if ninth != expected:
                    rs.append('parity')
            bitlist = [(float(t), int(v)) for t, v in zip(times[1:1 + d + p], payload) if t <= end]
            item = dict(t0=min(float(times[1]), end), t1=min(float(times[d + p]), end),
                        kind=lane, addr=None, value=value, nbits=len(bitlist), ninth=ninth,
                        ninth_kind='parity' if p else None, ok=not rs,
                        label='FE' if 'framing' in rs else 'PE' if 'parity' in rs else '')
            synced = not incomplete and np.all(stops == 1)
            if not synced:
                last_rise = None
        else:
            rs, last_rise = ['unsynced'], None
        records.append((float(tm), min(busy, end), item, rs, bitlist))
        if len(records) >= limit:
            return records, warnings, True
    if false_starts:
        warnings.append(f'{lane.upper()} false start {false_starts} 次')
    errors = sum('framing' in r[3] for r in records)
    if records and errors / len(records) > .1:
        warnings.append('framing 偏多，請確認鮑率與格式')
    durations = np.diff(np.r_[e.time, end])
    if errors and np.sum(durations[vals == 0]) > np.sum(durations[vals == 1]):
        warnings.append('可能需切換反相')
    return records, warnings, False


def run(edges: dict[str, Edges], *, t1: float | None = None, max_frames: int = 100_000,
        max_fields: int = 100_000, **opts: object) -> dict:
    o = options(opts, edges)
    if any(type(v) is not int or v < 1 for v in (max_frames, max_fields)):
        raise ValueError('事件上限須為正整數')
    end = float(t1 if t1 is not None else max(e.time[-1] for e in edges.values() if len(e.time)))
    cuts = [float(e.time[-1]) for e in edges.values() if e.truncated]
    if cuts:
        end = min(end, *cuts)
    groups, warnings, halted = [], [], False
    char_time = (1 + o['bits'] + (o['parity'] != 'N') + o['stop']) / o['baud']
    for lane in ('tx', 'rx'):
        if lane not in edges:
            continue
        records, ws, hit = _lane(edges[lane], lane, end, o, max_fields + max_frames + 1)
        warnings.extend(ws)
        if hit:
            cut = float(np.nextafter(records[-1][0], -np.inf))
            result = run(edges, t1=cut, max_frames=max_frames, max_fields=max_fields, **o)
            result['truncated'] = True
            result['warnings'].append(f'候選事件超過上限，只解到 t={result["t1"]:.12g}')
            return result
        group = None
        for start, stop, item, rs, bs in records:
            kind = 'unsynced' if item is None else 'chars'
            # 閒置從完整字元結束算起，不從最後 stop 中心算起。
            if group is None or group['kind'] != kind or start - group['t1'] > (GROUP_GAP * char_time + .5 / o['baud']) * (1 + 1e-10):
                group = frame(start, kind)
                group['_bits'] = []
                groups.append(group)
            group['t1'] = max(group['t1'], stop)
            if item is not None:
                item['_reasons'] = rs
                group['fields'].append(item)
                if lane == 'tx':
                    group['_bits'].extend(bs)
            for code in rs:
                reason(group, code, 'ok' if code == 'break' else 'warn' if code in ('unsynced', 'truncated') else 'error')
    merged = []
    for g in sorted(groups, key=lambda x: x['t0']):
        if merged and g['t0'] <= merged[-1]['t1']:
            f = merged[-1]
            f['t1'] = max(f['t1'], g['t1'])
            f['fields'].extend(g['fields'])
            f['_bits'].extend(g['_bits'])
            if g['kind'] == 'chars':
                f['kind'] = 'chars'
            for code in g['reasons']:
                reason(f, code, g['status'])
        else:
            merged.append(g)
    frames, bits, count = [], [], 0
    for f in merged:
        f['fields'].sort(key=lambda x: (x['t0'], x['kind'] == 'rx'))
        if len(frames) >= max_frames or count + len(f['fields']) > max_fields:
            halted = True
            available = max_fields - count if len(frames) < max_frames else 0
            if available:
                f['fields'] = f['fields'][:available]
                cut = max(x['t1'] for x in f['fields'])
                old_unsynced = 'unsynced' in f['reasons']
                f.update(reasons=[], status='ok')
                for code in dict.fromkeys((['unsynced'] if old_unsynced else []) + [c for x in f['fields'] for c in x['_reasons']]):
                    reason(f, code, 'ok' if code == 'break' else 'warn' if code in ('unsynced', 'truncated') else 'error')
                reason(f, 'truncated', 'warn')
                f['t1'] = min(f['t1'], cut)
                end = min(end, cut)
            else:
                end = min(end, f['t0'])
                break
        f['i'] = len(frames)
        f['label'] = ''.join(chr(x['value']) if 32 <= x['value'] < 127 else '.' for x in f['fields'][:24] if x['value'] is not None)
        for x in f['fields']:
            x.pop('_reasons')
        count += len(f['fields'])
        kept_bits = sum(x['nbits'] for x in f['fields'] if x['kind'] == 'tx')
        bits.extend(sorted(f.pop('_bits'))[:kept_bits])
        frames.append(f)
        if halted:
            break
    bits = sorted((t, v) for t, v in bits if t <= end)
    if cuts or halted:
        warnings.append(f'事件或邊沿超過上限，只解到 t={end:.12g}')
    return dict(frames=frames, bits_t=np.array([x[0] for x in bits]),
                bits_v=np.array([x[1] for x in bits], dtype=np.int8), addresses=[],
                warnings=warnings, truncated=bool(cuts) or halted or any('truncated' in f['reasons'] for f in frames), t1=end)


def decode_waveforms(t: np.ndarray, tx: np.ndarray, rx: np.ndarray | None = None, *,
                     thresholds: dict | None = None, max_edges: int = 10_000_000, **opts: object) -> dict:
    options({k: v for k, v in opts.items() if k not in ('t1', 'max_frames', 'max_fields')}, {})
    validate_time(t)
    edges, used = {}, {}
    for lane, v in (('tx', tx), ('rx', rx)):
        if v is None:
            continue
        th = (thresholds or {}).get(lane)
        if th is None:
            th = auto_threshold(v)
        used[lane] = th
        if th is None:
            return dict(ok=False, reason=f'{lane.upper()} 無有限高低平台；請改用手動門檻', thresholds=used)
        edges[lane] = to_edges(t, v, *th, max_edges=max_edges)
    opts.setdefault('t1', float(t[-1]))
    result = run(edges, **opts)
    if np.max(np.diff(t)) * opts['baud'] > 1 / 8:
        result['warnings'].append('取樣不足（每位元少於 8 點）')
    return dict(ok=True, reason=None, thresholds=used, **result)


if __name__ == '__main__':
    assert options({'baud': 9600}, {})['bits'] == 8
    print('web.uart_decode self-check OK')
