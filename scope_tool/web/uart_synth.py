from __future__ import annotations

"""UART 符號與類比合成；真值保留發送端起點，不由接收器反推。"""
from pathlib import Path
import numpy as np
from scope_tool.web.logic import Edges


def uart_line(chars: list[int], baud: float = 9600, bits: int = 8, parity: str = 'N',
              stop: int = 1, eps: float = 0, gaps: float | list[float] = 0,
              idle_level: int = 1, breaks: tuple = ()) -> dict:
    """gaps 與 breaks 長度以發送端位元為單位；breaks 為（字元索引、低、mark）。"""
    period = 1 / (baud * (1 + eps))
    trans, truth, now = [(0., 1)], [], 2 * period
    def put(tm: float, value: int) -> None:
        if trans[-1][1] != value:
            trans.append((tm, value))
    for i, value in enumerate(chars):
        for index, low, mark in breaks:
            if index == i:
                put(now, 0)
                now += low * period
                put(now, 1)
                now += mark * period
        start = now
        data = [(value >> k) & 1 for k in range(bits)]
        symbol = [0] + data
        if parity != 'N':
            symbol.append({'E': sum(data) % 2, 'O': 1 - sum(data) % 2, 'M': 1, 'S': 0}[parity])
        symbol += [1] * stop
        for b in symbol:
            put(now, b)
            now += period
        truth.append(dict(start=start, value=value, symbol=symbol))
        gap = gaps[i] if isinstance(gaps, list) else gaps
        now += gap * period
    if idle_level == 0:
        trans = [(tm, 1 - v) for tm, v in trans]
    return dict(trans=trans, truth=truth, end=now + 2 * period)


def edge(line: dict) -> Edges:
    trans = line['trans']
    return Edges(np.array([x[0] for x in trans]), np.array([x[1] for x in trans], dtype=np.int8),
                 np.array([i == 0 for i in range(len(trans))]), [], 32, 0, False)


def render(tx: dict, rx: dict | None = None, *, fs: float = 9600 * 64,
           levels: tuple[float, float] = (0., 3.3), noise: float = 0,
           seed: int = 0, end: float | None = None, nan: tuple = ()) -> tuple:
    """levels 的索引是邏輯 0／1，可直接給 (+12,-12) 或差動 (-1.2,+1.2)。"""
    end = max(tx['end'], rx['end'] if rx else 0) if end is None else end
    t = np.arange(int(np.ceil(end * fs)) + 1) / fs
    waves, rng = [], np.random.default_rng(seed)
    for lane, line in (('tx', tx), ('rx', rx)):
        if line is None:
            continue
        e = edge(line)
        values = e.value[np.searchsorted(e.time, t, side='right') - 1]
        v = np.array(levels)[np.maximum(values, 0)] + rng.normal(0, noise, len(t))
        v[values < 0] = np.nan
        for name, a, b in nan:
            if name == lane:
                v[(t >= a) & (t < b)] = np.nan
        waves.append(v)
    return (t, *waves)


def fixture(path: Path) -> dict:
    """雙通道五組原生格式；sections 保留各段格式與裁切時間。"""
    bad = uart_line([0x55, 0x41])
    bad['trans'] = [(t, v) for t, v in bad['trans'] if abs(t - 21 / 9600) > 1e-12]
    bad['trans'].append((22 / 9600, 1))
    bad['trans'].sort()
    cases = [('U01', uart_line([0x55]), None, 'N'),
             ('U02', uart_line([0x41], parity='E'), None, 'E'),
             ('U04', bad, None, 'N'),
             ('U05', uart_line([0x41], breaks=((0, 11.52, 2),)), None, 'N'),
             ('U17', uart_line([0x41]), uart_line([0x42]), 'N')]
    tx, rx = dict(trans=[(0., 1)], end=0.), dict(trans=[(0., 1)], end=0.)
    sections, now = [], 0.
    for name, a, b, parity in cases:
        duration = max(a['end'], b['end'] if b else 0)
        for target, line in ((tx, a), (rx, b)):
            if line:
                target['trans'].extend((t + now, v) for t, v in line['trans'] if t > 0)
        sections.append(dict(case=name, t0=now, t1=now + duration,
                             options=dict(baud=9600, parity=parity)))
        now += duration + 40 / 9600  # 超過 GROUP_GAP（2 字元），各案例才分成獨立 frame
    tx['end'] = rx['end'] = now
    t, a, b = render(tx, rx)
    with path.open('x', encoding='utf-8', newline='') as stream:
        stream.write('Time(s),CH1(V),CH2(V)\n')
        np.savetxt(stream, np.column_stack((t, a, b)), delimiter=',', fmt='%.12e')
    return dict(channels={'tx': 'CHAN1', 'rx': 'CHAN2'}, options=dict(baud=9600),
                expect_kinds=['chars'], sections=sections)


if __name__ == '__main__':
    assert uart_line([0x55])['truth'][0]['symbol'] == [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    print('web.uart_synth self-check OK')
