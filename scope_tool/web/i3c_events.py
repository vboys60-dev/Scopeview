from __future__ import annotations

"""合併兩線邊沿與保留整個 SCL 低期間；不推測缺失的轉換。"""
from collections.abc import Iterator
import numpy as np
from scope_tool.web.logic import Edges


def events(scl: Edges, sda: Edges, end: float) -> Iterator[tuple]:
    """產生 bit／start／stop／low／gap／pattern／ambiguous 事件。"""
    times = np.r_[scl.time, sda.time]
    lines = np.r_[np.zeros(len(scl.time), dtype=np.int8), np.ones(len(sda.time), dtype=np.int8)]
    vals, sync = np.r_[scl.value, sda.value], np.r_[scl.resync, sda.resync]
    order = np.argsort(times, kind='stable')
    order = order[times[order] <= end]
    times, lines, vals, sync = times[order], lines[order], vals[order], sync[order]
    c = d = -1
    k = n = 0
    low_start = end
    setup = False
    i = 0
    while i < len(times):
        tm, line, val, rs = float(times[i]), int(lines[i]), int(vals[i]), bool(sync[i])
        if i + 1 < len(times) and times[i + 1] == tm and lines[i + 1] != line:
            if not rs and not sync[i + 1]:
                yield ('ambiguous', tm)
        i += 1
        if val < 0 or rs:
            if val < 0:
                yield ('gap', tm)
            if line == 0:
                c = val
            else:
                d = val
            k = n = 0
            continue
        if line == 0:
            c = val
            if c == 0:
                yield ('low', tm)
                low_start, k, n, setup = tm, 0, 0, d == 1
            elif d >= 0:
                if k >= 2:
                    tail = []
                    j = i
                    while j < len(times) and lines[j] == 1 and not sync[j] and vals[j] >= 0:
                        tail.append((float(times[j]), int(vals[j])))
                        j += 1
                    stop = next((t for t, v in tail if v == 1), None)
                    sr = any(v == 0 for _, v in tail)
                    finish = stop if stop is not None else (float(times[j]) if j < len(times) else end)
                    yield ('pattern', low_start, finish, k, n, d, sr, stop is not None, False)
                    if tail:
                        d = tail[-1][1]
                    i = j
                else:
                    yield ('bit', tm, d)
                k = n = 0
        else:
            old, d = d, val
            if c == 0:
                yield ('activity', tm)
                if not setup and d == 1:
                    setup = True
                elif setup:
                    n += 1
                    k += d == 0
            elif c == 1 and old >= 0:
                yield ('start' if d == 0 else 'stop', tm)
    if c == 0 and k >= 2:
        yield ('pattern', low_start, end, k, n, d, False, False, True)


if __name__ == '__main__':
    e = Edges(np.array([0., 1., 2.]), np.array([1, 0, 1]),
              np.array([True, False, False]), [], 1, 0, False)
    a = list(events(e, e, 3.))
    assert any(x[0] == 'ambiguous' for x in a)
    print('web.i3c_events self-check OK')
