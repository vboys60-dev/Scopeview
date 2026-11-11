from __future__ import annotations

"""eSPI 單線合成波形；待實機驗證。"""
from pathlib import Path
from scope_tool.web.spi_synth import spi_bus, edges as spi_edges
from scope_tool.web.synth import render, write_csv
from scope_tool.web.espi_table import crc8


def bus(cmd: list[int], response: list[int], waits: int = 0, reset: bool = False) -> dict:
    command = cmd if reset else cmd + [crc8(cmd)]
    reply = [0x0f]*waits + response
    if response and response != [0xff]:
        reply += [crc8(response)]
    def bits(data: list[int]) -> list[int]:
        return [(b >> i) & 1 for b in data for i in range(7, -1, -1)]
    a = bits(command) + [1]*2 + [1]*(8*len(reply))
    b = [1]*(8*len(command)+2) + bits(reply)
    raw = spi_bus(list(zip(a, b)), bits=1)
    raw['trans'] = [(t, {'sclk':'clk', 'mosi':'io0', 'miso':'io1'}.get(k, k), v) for t, k, v in raw['trans']]
    return raw


def edges(b: dict) -> dict:
    raw = dict(b)
    raw['trans'] = [(t, {'clk':'sclk', 'io0':'mosi', 'io1':'miso'}.get(k, k), v) for t, k, v in b['trans']]
    return {{'sclk':'clk', 'mosi':'io0', 'miso':'io1'}.get(k, k): v for k, v in spi_edges(raw).items()}


def fixture(path: Path) -> dict:
    cases = [bus([0x25], [8, 15, 3]), bus([0x21, 0, 4], [8, 1, 2, 3, 4, 15, 3]),
             bus([4, 0, 2, 0x55], [8, 15, 3]), bus([0x25], [8, 15, 3], waits=2)]
    trans, now = [], 0.
    for b in cases:
        trans.extend((t+now, k, v) for t, k, v in b['trans'])
        now += b['end'] + 3e-6
    waves = render(trans, 32e6, lines=('cs', 'clk', 'io0', 'io1'), noise=.005, end=now)
    write_csv(path, waves)
    return dict(channels=dict(cs='CHAN1', clk='CHAN2', io0='CHAN3', io1='CHAN4'), options={}, expect_kinds=['cmd'])


if __name__ == '__main__':
    assert len(edges(bus([0x25], [8, 15, 3]))) == 4
    print('web.espi_synth self-check OK')
