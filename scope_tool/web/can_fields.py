from __future__ import annotations

"""CAN 位元層：CRC-15、顯性區間表、逐位取樣（含重對齊）與去填充。# 待真機驗證。"""
import numpy as np
from scope_tool.web.logic import Edges, levels_at

POLY = 0x4599


def crc15(bits) -> int:
    """CRC-15/CAN：多項式 0x4599、初值 0、MSB first；輸入為去填充後 SOF..DATA。"""
    crc = 0
    for b in bits:
        top = ((crc >> 14) ^ b) & 1
        crc = (crc << 1) & 0x7FFF
        if top:
            crc ^= POLY
    return crc


class Stop(Exception):
    """框內提前結束：code 為原因，t 為該 frame 的結束時間（不回溯）。"""

    def __init__(self, code: str, t: float) -> None:
        super().__init__(code)
        self.code, self.t = code, t


class Bus:
    """把邊沿表轉成「顯性區間」陣列；取樣一律走 levels_at，與共用層一致。"""

    def __init__(self, e: Edges, end: float, T: float, sp: float, dom_high: bool) -> None:
        self.e, self.end, self.T, self.sp, self.dom_high = e, end, T, sp, dom_high
        v, n = e.value, len(e.value)
        idx = np.flatnonzero((v >= 0) & ((v == 1) == dom_high) & (e.time <= end))
        nxt = idx + 1
        last = nxt >= n
        self.ds = e.time[idx]
        self.de = np.minimum(np.where(last, end, e.time[np.minimum(nxt, n - 1)]), end)
        self.dreal = ~e.resync[idx]          # 起點是真正的 recessive→dominant 轉態
        self.dopen = last | (self.de >= end)  # 終點是擷取結束，不是真邊沿

    def dominant(self, t: float) -> int:
        lv = int(levels_at(self.e, np.array([t]), self.end)[0])
        return -1 if lv < 0 else int((lv == 1) == self.dom_high)


class Reader:
    """從 SOF 邊沿起逐位取樣：有效 r→d 邊沿重對齊、動態填充位移除。

    ponytail: 重對齊不受 SJW 限制（離線工程近似），|誤差|>0.25 T 只標 timing。
    """

    def __init__(self, b: Bus, t_sync: float) -> None:
        self.b, self.sync, self.k, self.last_k = b, t_sync, 0, 0
        self.ri = int(np.searchsorted(b.ds, t_sync, 'right'))
        self.rv, self.rl, self.stuffing, self.timing = None, 0, True, False
        self.wire: list[tuple[float, int]] = []  # (取樣時間, 0/1；2＝填充位)

    def edge_time(self) -> float:
        return self.sync + self.k * self.b.T

    def raw(self) -> tuple[float, float, int]:
        """讀一個線上位元：(起點, 取樣點, 值；0＝顯性)。"""
        b, T = self.b, self.b.T
        while True:
            samp = self.sync + (self.k + b.sp) * T
            moved = False
            while self.ri < len(b.ds) and b.ds[self.ri] <= samp:
                i, self.ri = self.ri, self.ri + 1
                # 邊沿之後的顯性段須持續 ≥0.5 T 才算有效；較短者視為雜訊，不重對齊。
                if not b.dreal[i] or (b.de[i] - b.ds[i] < .5 * T and not b.dopen[i]):
                    continue
                r = (float(b.ds[i]) - self.sync) / T
                n = round(r)
                if n <= self.last_k:
                    continue
                self.last_k = n
                if abs(r - n) > .25:
                    self.timing = True
                self.sync += (r - n) * T
                moved = True
            if not moved:
                break
        start = self.sync + self.k * T
        if samp > b.end:
            raise Stop('truncated', b.end)
        d = b.dominant(samp)
        if d < 0:
            raise Stop('unknown_bit', start)
        self.k += 1
        return start, samp, 0 if d else 1

    def take(self, n: int) -> list[tuple[float, float, int]]:
        """讀 n 個「欄位位元」（自動吃掉填充位）；連續 6 個相同 → Stop('stuff')。"""
        out = []
        while len(out) < n:
            st, sm, v = self.raw()
            if self.stuffing and self.rl == 5:
                if v == self.rv:
                    raise Stop('stuff', st)
                self.rv, self.rl = v, 1
                self.wire.append((sm, 2))
                continue
            self.rl = self.rl + 1 if v == self.rv else 1
            self.rv = v
            self.wire.append((sm, v))
            out.append((st, sm, v))
        return out

    def flush(self) -> None:
        """CRC 末位之後若恰為 5 個同值，還有一個填充位（之後才是 CRC delimiter）。"""
        if self.rl == 5:
            st, sm, v = self.raw()
            if v == self.rv:
                raise Stop('stuff', st)
            self.wire.append((sm, 2))
        self.stuffing = False


def field(kind: str, bits: list, T: float, label: str = '', ok: bool = True) -> dict:
    v = 0
    for *_, b in bits:
        v = (v << 1) | b
    return dict(t0=bits[0][0], t1=bits[-1][0] + T, kind=kind, addr=None, value=v, nbits=len(bits),
                ninth=None, ninth_kind=None, ok=ok, label=label)


if __name__ == '__main__':
    def bits_of(data: bytes) -> list[int]:
        return [(x >> i) & 1 for x in data for i in range(7, -1, -1)]
    assert crc15(bits_of(b'123456789')) == 0x059E
    h1 = [int(c) for c in '00010010001100000100001001000110100']
    assert crc15(h1) == 0x36B7
    print('web.can_fields self-check OK')
