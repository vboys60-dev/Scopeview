from __future__ import annotations

"""I2C 符號產生器；控制條件依週期縮放，渲染與 CSV 沿用既有純函式。"""
from pathlib import Path
import numpy as np
from scope_tool.web.i3c_synth import render, write_csv


class Bus:
    def __init__(self, frequency: float = 100_000) -> None:
        self.period = 1 / frequency
        self.now = self.period
        self.level = {'scl': 1, 'sda': 1}
        self.trans = [(0., 'scl', 1), (0., 'sda', 1)]
        self.truth = []

    def set(self, line: str, value: int) -> None:
        if self.level[line] != value:
            self.trans.append((self.now, line, value))
            self.level[line] = value

    def idle(self, sec: float) -> Bus:
        self.now += sec
        return self

    def start(self) -> Bus:
        self.truth.append(('S', self.now))
        self.set('sda', 0)
        self.idle(self.period / 2)
        self.set('scl', 0)
        return self

    def rstart(self) -> Bus:
        self.set('scl', 0)
        self.idle(self.period / 4)
        self.set('sda', 1)
        self.idle(self.period / 4)
        self.set('scl', 1)
        self.idle(self.period / 2)
        self.truth.append(('Sr', self.now))
        self.set('sda', 0)
        self.idle(self.period / 2)
        self.set('scl', 0)
        return self

    def stop(self) -> Bus:
        self.set('scl', 0)
        self.idle(self.period / 4)
        self.set('sda', 0)
        self.idle(self.period / 4)
        self.set('scl', 1)
        self.idle(self.period / 2)
        self.truth.append(('P', self.now))
        self.set('sda', 1)
        return self.idle(self.period)

    def bit(self, value: int) -> Bus:
        self.set('scl', 0)
        self.idle(self.period / 4)
        self.set('sda', value)
        self.idle(self.period / 4)
        self.set('scl', 1)
        self.idle(self.period / 2)
        self.set('scl', 0)
        return self

    def word(self, value: int, width: int = 8) -> Bus:
        for shift in range(width - 1, -1, -1):
            self.bit((value >> shift) & 1)
        return self

    def byte(self, v: int, ack: bool = True) -> Bus:
        self.truth.append(('byte', self.now + self.period / 2, v, ack))
        return self.word(v).bit(0 if ack else 1)

    def stretch(self, sec: float) -> Bus:
        self.set('scl', 0)
        return self.idle(sec)

    def raw(self, transitions: list[tuple[float, str, int]]) -> Bus:
        for tm, line, value in transitions:
            if tm < self.now:
                raise ValueError('raw 時間不可倒退')
            self.now = tm
            self.set(line, value)
        return self

    def render(self, fs: float = 20e6, **kw: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        kw.setdefault('tr', 300e-9)
        kw.setdefault('noise', 0)
        return render(self.trans, fs, end=self.now + self.period, **kw)


def fixture(path: Path) -> dict:
    """產生約二十萬點的八種代表交易；路徑須由呼叫端提供時間戳。"""
    b = Bus()
    b.start().byte(0xA0).byte(0x12).byte(0x34).stop()
    b.start().byte(0xA0).byte(0).rstart().byte(0xA1).byte(0xAB, False).stop()
    b.start().byte(0xD0, False).stop()
    b.start().byte(0xF4).byte(0xA5).byte(0x77).stop()
    b.start().byte(0xF4).byte(0xA5).rstart().byte(0xF5).byte(0x34, False).stop()
    b.start().byte(0).byte(6).stop()
    b.start().byte(1, False).rstart().byte(0xA0).stop()
    b.word(0xB, 4).stop().start().byte(0xA0).stop()
    b.idle(max(0, .01 - b.now))
    write_csv(path, b.render())
    return dict(channels={'scl': 'CHAN1', 'sda': 'CHAN2'}, options={},
                expect_kinds=['write', 'read', 'gc', 'start_byte', 'partial'])


def self_check() -> None:
    from scope_tool.web.logic import to_edges
    from scope_tool.web.i3c_events import events
    for frequency in (100_000, 400_000):
        b = Bus(frequency).start().byte(0xA0).byte(0).rstart().byte(0xA1).byte(0xAB, False).stop()
        t, c, d = b.render()
        tags = [e[0] for e in events(to_edges(t, c, .72, 1.08), to_edges(t, d, .72, 1.08), t[-1])]
        assert tags.count('start') == 2 and tags.count('stop') == 1, tags
        assert [x[0] for x in b.truth if x[0] != 'byte'] == ['S', 'Sr', 'P']


if __name__ == '__main__':
    self_check()
    print('web.i2c_synth self-check OK')
