from __future__ import annotations

"""SPI 符號轉換與四通道波形。"""
from pathlib import Path
import numpy as np
from scope_tool.web.logic import Edges
from scope_tool.web.synth import render, write_csv


def spi_bus(words: list[tuple[int, int]], mode: int = 0, bits: int = 8, lsb: bool = False,
            cs: bool = True, cs_active: str = 'low', gap: float = 0., t_bit: float = 1e-6) -> dict:
    cpol, cpha = mode >> 1, mode & 1
    active = int(cs_active == 'high')
    trans = [(0., 'sclk', cpol), (0., 'mosi', 0), (0., 'miso', 0), (0., 'cs', 1-active)]
    now = t_bit * 2
    if cs:
        trans.append((now, 'cs', active))
    now += t_bit
    for mosi, miso in words:
        for j in range(bits):
            shift = j if lsb else bits - 1 - j
            values = ((mosi >> shift) & 1, (miso >> shift) & 1)
            if not cpha:
                trans.extend((now, lane, v) for lane, v in zip(('mosi', 'miso'), values))
            now += t_bit / 4
            trans.append((now, 'sclk', 1-cpol))
            if cpha:
                trans.extend((now + t_bit / 16, lane, v) for lane, v in zip(('mosi', 'miso'), values))
            now += t_bit / 2
            trans.append((now, 'sclk', cpol))
            now += t_bit / 4
        now += gap
    if cs:
        trans.append((now, 'cs', 1-active))
    return dict(trans=trans, end=now + 2*t_bit, truth=words)


def edges(bus: dict) -> dict[str, Edges]:
    result = {}
    for lane in ('sclk', 'mosi', 'miso', 'cs'):
        pairs = [(t, v) for t, name, v in bus['trans'] if name == lane]
        filtered = [pairs[0]]
        for t, v in pairs[1:]:
            if v != filtered[-1][1]:
                filtered.append((t, v))
        result[lane] = Edges(np.array([x[0] for x in filtered]), np.array([x[1] for x in filtered], dtype=np.int8),
                             np.array([i == 0 for i in range(len(filtered))]), [], 32, 0, False)
    return result


def fixture(path: Path) -> dict:
    first = spi_bus([(0x96, 0x2d)])
    first['trans'] = [(t, lane, value) for t, lane, value in first['trans']
                      if not (lane == 'cs' and t == 2e-6)]
    first['trans'][3] = (0., 'cs', 0)
    incomplete = spi_bus([(0xa5, 0x5a), (0xf0, 0x0f)])
    stop = 15.5e-6
    incomplete['trans'] = [(t, lane, value) for t, lane, value in incomplete['trans']
                           if t < stop and not (lane == 'cs' and t > 2e-6)]
    incomplete['trans'].append((stop, 'cs', 1))
    incomplete['end'] = stop + 2e-6
    cases = [first, spi_bus([(0x96, 0x2d)]),
             spi_bus([(0x1234, 0xabcd), (0x5678, 0xef01)], bits=16), incomplete]
    trans, now = [], 0.
    for b in cases:
        trans.extend((t + now, lane, value) for t, lane, value in b['trans'])
        now += b['end'] + 3e-6
    waves = render(trans, 32e6, lines=('sclk', 'mosi', 'miso', 'cs'), noise=.005, end=now)
    write_csv(path, waves)
    return dict(channels=dict(sclk='CHAN1', mosi='CHAN2', miso='CHAN3', cs='CHAN4'),
                options={}, expect_kinds=['txn'])


if __name__ == '__main__':
    assert spi_bus([(0x96, 0x2d)])['truth'] == [(0x96, 0x2d)]
    print('web.spi_synth self-check OK')
