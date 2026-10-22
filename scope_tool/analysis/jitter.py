"""Jitter 量測（依 Infiniium 手冊 Jitter_Meas_Clock_TIE、Jitter_Meas_Clock_period-period、
Jitter_Meas_Clock_pos_width-pos_width、Jitter_Meas_Data_TIE）。統計沿用 measure.stats：標準差＝RMS、範圍＝p-p。

N 週期、Period-Period、寬度差只用時脈型，且不跨缺邊（格號必須剛好差 N 個週期）；
資料型 N-UI／UI-UI 延後。
# 待真機驗證：與 EZJIT 數值比對。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis import eye
from scope_tool.analysis.clock import Clock, ClockSpec, nrz, rate, recover
from scope_tool.contracts import ScopeError

NAMES = ("TIE", "N 週期", "Period-Period", "+寬度差", "-寬度差", "還原 UI", "還原速率")


def _pairs(n: np.ndarray, span: int) -> tuple[np.ndarray, np.ndarray]:
    """往後第 span 個事件剛好差 span 格（中間每一格都有事件，不跨缺口）：回傳 (起點索引, 終點索引)。"""
    if span >= n.size:
        return np.array([], int), np.array([], int)
    i = np.flatnonzero(n[span:] - n[:-span] == span)
    return i, i + span


def n_periods(ck: Clock) -> tuple[np.ndarray, np.ndarray]:
    """(起點格號, N 週期)：同方向邊緣相隔 N 個週期。"""
    i, j = _pairs(ck.n, ck.spec.n * ck.step)
    return ck.n[i], ck.times[j] - ck.times[i]


def period_period(ck: Clock) -> np.ndarray:
    """Pₖ＝N 週期，結果＝Pₖ₊ₙ − Pₖ，逐週期滑動（手冊圖：相鄰兩組 N 週期相減）。"""
    anchor, p = n_periods(ck)
    i, j = _pairs(anchor, ck.spec.n * ck.step)
    return p[j] - p[i]


def width_diffs(ck: Clock, positive: bool) -> np.ndarray:
    """下一個週期的脈寬 − 這個週期的脈寬；起點相隔超過 1.5 週期，或任一脈寬 ≥ 1 週期（中間缺邊）就不配對。"""
    es = ck.es
    pairs = [(a.t_mid, b.t_mid - a.t_mid) for a, b in zip(es, es[1:]) if a.rising == positive]
    if len(pairs) < 2:
        raise ScopeError("範圍內少於 2 個完整脈衝")
    start, width = np.array(pairs).T
    period = ck.ui * ck.step
    ok = (np.diff(start) < 1.5 * period) & (width[:-1] < period) & (width[1:] < period)
    return np.diff(width)[ok]


def measure(name: str, t: np.ndarray, v: np.ndarray, ck: Clock) -> np.ndarray:
    """Jitter 與眼圖量測：回傳每個事件的值；量測不出來丟 ScopeError。"""
    if name in eye.NAMES:
        return eye.measure(name, t, v, ck)
    if name == "TIE":
        out = ck.tie
    elif name == "還原 UI":
        out = np.array([ck.ui])
    elif name == "還原速率":
        out = np.array([rate(ck)])
    elif ck.spec.kind != "時脈":
        raise ScopeError("N 週期、Period-Period、寬度差只支援時脈型（資料型 N-UI／UI-UI 延後）")
    elif name == "N 週期":
        out = n_periods(ck)[1]
    elif name == "Period-Period":
        out = period_period(ck)
    elif name in ("+寬度差", "-寬度差"):
        out = width_diffs(ck, name == "+寬度差")
    else:
        raise ScopeError(f"未知的量測：{name}")
    if not out.size:
        raise ScopeError(f"範圍內沒有可配對的事件（N＝{ck.spec.n}，缺邊不跨）")
    return out


def _self_check() -> None:
    ns = 1e-9
    # 週期 10、11、12、13、14 ns；N=2 → N 週期 21、23、25、27，Period-Period 4、4
    edges_t = np.cumsum([0, 10, 11, 12, 13, 14]) * ns
    ck = Clock(ClockSpec(n=2), [], edges_t, np.ones(6, bool), np.arange(6), 12 * ns, 0.0, np.zeros(6), 1, 0.5, [])
    assert np.allclose(n_periods(ck)[1], [21 * ns, 23 * ns, 25 * ns, 27 * ns])
    assert np.allclose(period_period(ck), [4 * ns, 4 * ns])
    assert np.allclose(period_period(ck._replace(spec=ClockSpec(n=1))), [ns, ns, ns, ns])
    # 缺邊：格號 0,1,3,4 → N=1 的週期只有 0→1、3→4
    gap = ck._replace(n=np.array([0, 1, 3, 4, 5, 6]), spec=ClockSpec(n=1))
    assert np.array_equal(n_periods(gap)[0], [0, 3, 4, 5])
    assert np.array_equal(n_periods(gap._replace(spec=ClockSpec(n=2)))[0], [3, 4])  # 1→3 中間缺 2，不算
    # 寬度 4、5、3 ns（週期 10 ns）→ 寬度差 1、−2 ns
    tc = np.arange(800) * 0.05e-9
    vc = np.zeros_like(tc)
    for start, width in ((5, 4), (15, 5), (25, 3)):
        vc[start * 20:(start + width) * 20] = 1  # 每 ns 20 點
    real = recover(tc, vc, (10, 50, 90), ClockSpec())
    assert np.allclose(width_diffs(real, True), [1 * ns, -2 * ns], atol=1e-12)
    assert np.allclose(measure("-寬度差", tc, vc, real), [-1 * ns], atol=1e-12)  # 6→5 ns
    # 高低各 1 ns、拿掉一個高脈衝：跨缺口的 3 ns 負脈寬不參與
    clk = np.tile(np.r_[np.ones(20), np.zeros(20)], 40)
    clk[400:420] = 0
    tg = np.arange(clk.size) * 0.05e-9
    gck = recover(tg, clk, (10, 50, 90), ClockSpec())
    assert np.allclose(width_diffs(gck, False), 0, atol=1e-12) and np.allclose(width_diffs(gck, True), 0, atol=1e-12)
    # 資料型：TIE、還原速率可量，N 週期不支援
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, 3000)
    bits[:3] = (0, 1, 0)
    t, v = nrz(bits, 1e-9, 16)
    dck = recover(t, v, (10, 50, 90), ClockSpec("NRZ 資料"))
    assert abs(measure("還原速率", t, v, dck)[0] - 1e9) < 1 and np.max(np.abs(measure("TIE", t, v, dck))) < 1e-14
    for name in ("N 週期", "未知"):
        try:
            measure(name, t, v, dck)
            raise AssertionError("應該丟出 ScopeError")
        except ScopeError:
            pass
    print("analysis.jitter self-check OK")


if __name__ == "__main__":
    _self_check()
