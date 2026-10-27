from __future__ import annotations

"""獨立的 I3C 線上符號與類比合成器；不匯入解碼器。# 待真機驗證。"""
from pathlib import Path
import numpy as np
from scope_tool.web.synth import render, write_csv


class Bus:
    def __init__(self, f_pp: float = 12.5e6, f_od: float = 2.5e6) -> None:
        self.f_pp, self.f_od = f_pp, f_od
        self.now = 1e-6
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
        self.set('sda', 0)
        self.idle(40e-9)
        self.set('scl', 0)
        return self

    def rstart(self) -> Bus:
        self.set('scl', 0)
        self.idle(20e-9)
        self.set('sda', 1)
        self.idle(20e-9)
        self.set('scl', 1)
        self.idle(40e-9)
        return self.start()

    def stop(self) -> Bus:
        self.set('scl', 0)
        self.idle(20e-9)
        self.set('sda', 0)
        self.idle(20e-9)
        self.set('scl', 1)
        self.idle(40e-9)
        self.set('sda', 1)
        self.idle(200e-9)
        return self

    def bit(self, value: int, od: bool = False, finish_low: bool = True) -> Bus:
        period = 1 / (self.f_od if od else self.f_pp)
        self.set('scl', 0)
        self.idle(period / 4)
        self.set('sda', value)
        self.idle(period / 4)
        self.set('scl', 1)
        self.idle(period / 2)
        if finish_low:
            self.set('scl', 0)
        return self

    def word(self, value: int, width: int = 8, od: bool = False) -> Bus:
        for shift in range(width - 1, -1, -1):
            self.bit((value >> shift) & 1, od)
        return self

    def header(self, addr: int, rw: int = 0, ack: bool = True, od: bool = False) -> Bus:
        period = 1 / (self.f_od if od else self.f_pp)
        self.truth.append(('header', self.now + period / 2, addr, rw, ack, self.now + 8.5 * period))
        return self.word((addr << 1) | rw, od=od).bit(0 if ack else 1, od)

    def byte_w(self, v: int, t: int | None = None) -> Bus:
        ninth = (1 ^ (v.bit_count() % 2)) if t is None else t
        self.truth.append(('write', self.now + .5 / self.f_pp, v, ninth, self.now + 8.5 / self.f_pp))
        return self.word(v).bit(ninth)

    def byte_r(self, v: int, t: int, abort: bool = False) -> Bus:
        self.truth.append(('read', self.now + .5 / self.f_pp, v, t, self.now + 8.5 / self.f_pp))
        self.word(v).bit(t, finish_low=not abort)
        if abort:
            if t != 1:
                raise ValueError('Controller 提前結束必須先有 T=1')
            self.set('sda', 0)
            self.idle(20e-9)
            self.set('scl', 0)
        return self

    def ccc(self, code: int, defbyte: int | None = None, payload: tuple = (),
            targets: tuple = ()) -> Bus:
        """targets 每項為 (位址, 方向, ACK, 資料序列)。"""
        self.start().header(0x7E, od=True).byte_w(code)
        if defbyte is not None:
            self.byte_w(defbyte)
        for v in payload:
            self.byte_w(v)
        for addr, rw, ack, data in targets:
            self.rstart().header(addr, rw, ack)
            if ack:
                for i, v in enumerate(data):
                    self.byte_r(v, int(i < len(data) - 1)) if rw else self.byte_w(v)
        return self.stop()

    def entdaa(self, rounds: list[tuple[int, int, int]], das: tuple = (),
               bad_parity: bool = False) -> Bus:
        """每輪逐 bit 淘汰送 1 讀 0 的 Target；落敗者下輪再競爭。"""
        self.start().header(0x7E, od=True).byte_w(7)
        pending = list(rounds)
        index = 0
        while pending:
            self.rstart().header(0x7E, 1, od=True)
            live = list(range(len(pending)))
            words = [(p << 16) | (b << 8) | d for p, b, d in pending]
            for shift in range(63, -1, -1):
                val = min((words[j] >> shift) & 1 for j in live)
                self.bit(val, od=True)
                live = [j for j in live if ((words[j] >> shift) & 1) == val]
            winner = live[0]
            pid, bcr, dcr = pending.pop(winner)
            da = das[index] if index < len(das) else 8 + index
            self.truth.append(('winner', pid, bcr, dcr, da))
            par = (1 ^ (da.bit_count() % 2)) ^ int(bad_parity)
            self.word(da, 7, True).bit(par, True).bit(int(bad_parity), True)
            index += 1
        return self.rstart().header(0x7E, 1, False, od=True).stop()

    def ibi(self, da: int, payload: tuple = (), ack: bool = True) -> Bus:
        self.start().header(da, 1, ack, od=True)
        if ack:
            for i, v in enumerate(payload):
                self.byte_r(v, int(i < len(payload) - 1))
        return self.stop()

    def hotjoin(self, ack: bool = True) -> Bus:
        return self.start().header(2, 0, ack, od=True).stop()

    def pattern(self, n: int, sr: bool = False, stop: bool = True,
                end_high: bool | None = None, raise_scl: bool = True) -> Bus:
        self.set('scl', 0)
        self.idle(40e-9)
        self.set('sda', 1)
        self.idle(40e-9)
        for _ in range(n):
            self.set('sda', 1 - self.level['sda'])
            self.idle(40e-9)
        if end_high is not None:
            self.set('sda', int(end_high))
            self.idle(40e-9)
        if raise_scl:
            self.set('scl', 1)
            self.idle(40e-9)
            if sr:
                self.set('sda', 0)
                self.idle(40e-9)
            if stop:
                self.set('sda', 1)
                self.idle(200e-9)
        return self

    def hdr_exit(self, stop: bool = True) -> Bus:
        return self.pattern(7, stop=stop)

    def target_reset(self, sr: bool = True, stop: bool = True) -> Bus:
        return self.pattern(14, sr=sr, stop=stop)

    def hdr(self, mode: int = 0, n_toggles: int = 100, seed: int = 0) -> Bus:
        self.start().header(0x7E, od=True).byte_w(0x20 + mode)
        rng = np.random.default_rng(seed)
        for _ in range(n_toggles):
            self.bit(int(rng.integers(0, 2)))
        return self.hdr_exit()

    def i2c(self, addr: int, rw: int, data: tuple, acks: tuple) -> Bus:
        self.truth.append(('i2c', addr, rw, data, acks))
        self.start().header(addr, rw, od=True)
        for v, ack in zip(data, acks):
            self.word(v, od=True).bit(0 if ack else 1, od=True)
        return self.stop()

    def raw(self, transitions: list[tuple[float, str, int]]) -> Bus:
        for tm, line, value in transitions:
            if tm < self.now:
                raise ValueError('raw 時間不可倒退')
            self.now = tm
            self.set(line, value)
        return self

    def render(self, fs: float = 1e9, **kwargs: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return render(self.trans, fs, end=self.now + 200e-9, **kwargs)


if __name__ == '__main__':
    b = Bus().entdaa([(0x800000000000, 2, 1), (0x0123456789AB, 6, 0x44)])
    assert [x[1] for x in b.truth if x[0] == 'winner'] == [0x0123456789AB, 0x800000000000]
    t, c, d = b.render(noise=0)
    assert len(t) == len(c) == len(d) and np.isfinite(c).all()
    print('web.i3c_synth self-check OK')
