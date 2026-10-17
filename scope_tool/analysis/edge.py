"""邊緣與時間量測（依 Infiniium 手冊 Determining_Rising_and_Falling_Edges、Period、Duty_Cycle、
Rise_Time、Slew_Rate、Overshoot、Preshoot）。

邊緣須依序穿越下／中／上閾值，交點與前一點線性內插；沒走完三個閾值的半截邊緣與毛刺忽略，
因此回傳的邊緣一定是上升、下降交替。
# 待真機驗證：與示波器面板數值比對。
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from scope_tool.contracts import ScopeError


class Edge(NamedTuple):
    rising: bool
    t_lo: float   # 越過下閾值的時間
    t_mid: float
    t_hi: float   # 越過上閾值的時間
    a: int        # 邊緣開始前最後一個在原狀態的取樣點
    b: int        # 邊緣結束後第一個在新狀態的取樣點


def _cross(t: np.ndarray, v: np.ndarray, a: int, b: int, thr: float, rising: bool) -> float:
    """在 [a,b] 內第一個越過 thr 的取樣點，與前一點線性內插出時間。"""
    seg = v[a:b + 1]
    j = max(int(np.argmax(seg >= thr if rising else seg <= thr)), 1)
    i0, i1 = a + j - 1, a + j
    dv = v[i1] - v[i0]
    return float(t[i0]) if dv == 0 else float(t[i0] + (thr - v[i0]) / dv * (t[i1] - t[i0]))


def edges(t: np.ndarray, v: np.ndarray, lo: float, mid: float, hi: float) -> list[Edge]:
    state = np.where(v < lo, 0, np.where(v > hi, 2, 1)).astype(np.int8)
    idx = np.flatnonzero(state != 1)
    st = state[idx]
    out = []
    for k in np.flatnonzero(st[1:] != st[:-1]):
        a, b, rising = int(idx[k]), int(idx[k + 1]), bool(st[k] == 0)
        first, last = (lo, hi) if rising else (hi, lo)
        t_first, t_last = _cross(t, v, a, b, first, rising), _cross(t, v, a, b, last, rising)
        t_lo, t_hi = (t_first, t_last) if rising else (t_last, t_first)
        out.append(Edge(rising, t_lo, _cross(t, v, a, b, mid, rising), t_hi, a, b))
    return out


def _need(values: list[float], reason: str) -> np.ndarray:
    if not values:
        raise ScopeError(reason)
    return np.array(values, dtype=np.float64)


def transition(es: list[Edge], rising: bool, lo: float, hi: float, slope: bool) -> np.ndarray:
    """上升／下降時間（slope=False）或斜率 ΔV/ΔT（slope=True）；邊緣至少 4 個取樣點。"""
    d = [e.t_hi - e.t_lo if rising else e.t_lo - e.t_hi
         for e in es if e.rising == rising and e.b - e.a + 1 >= 4]
    name = "上升緣" if rising else "下降緣"
    out = _need(d, f"範圍內沒有至少 4 個取樣點的完整{name}")
    return ((hi - lo) if rising else (lo - hi)) / out if slope else out


def periods(es: list[Edge], rising: bool) -> np.ndarray:
    mids = [e.t_mid for e in es if e.rising == rising]
    return _need(list(np.diff(mids)), "範圍內沒有完整週期（需要兩個同方向邊緣）")


def widths(es: list[Edge], positive: bool) -> np.ndarray:
    """+寬度＝上升中點到下一個下降中點；-寬度反之。"""
    d = [b.t_mid - a.t_mid for a, b in zip(es, es[1:]) if a.rising == positive]
    return _need(d, "範圍內沒有完整脈衝")


def duty(es: list[Edge], rising: bool) -> np.ndarray:
    """每個完整週期（同方向相鄰兩邊緣）內的 +寬度 / 週期 × 100。"""
    d = []
    for e0, e1, e2 in zip(es, es[1:], es[2:]):
        if e0.rising == rising:
            pos = e1.t_mid - e0.t_mid if rising else e2.t_mid - e1.t_mid
            d.append(pos / (e2.t_mid - e0.t_mid) * 100)
    return _need(d, "範圍內沒有完整週期")


def shoot(v: np.ndarray, es: list[Edge], rising: bool, top: float, base: float, pre: bool) -> np.ndarray:
    """過衝（pre=False）：越過遠端閾值後到平台中點的局部極值；
    前衝（pre=True）：平台中點到越過近端閾值前的局部極值。皆以 top−base 的百分比表示。"""
    amp = top - base
    out = []
    for k, e in enumerate(es):
        if e.rising != rising:
            continue
        if pre:
            start = (es[k - 1].b + e.a) // 2 if k else 0
            seg = v[start:e.a + 1]
        else:
            end = (e.b + es[k + 1].a) // 2 if k + 1 < len(es) else len(v) - 1
            seg = v[e.b:end + 1]
        # 上升緣：過衝看高於 top、前衝看低於 base；下降緣相反。
        high_side = rising != pre
        out.append((seg.max() - top if high_side else base - seg.min()) / amp * 100)
    return _need(out, "範圍內沒有" + ("上升緣" if rising else "下降緣"))


def _self_check() -> None:
    dt = 1e-6
    t = np.arange(5000) * dt
    v = np.interp(t % 1e-3, [0, 10e-6, 500e-6, 510e-6, 1e-3], [0, 2, 2, 0, 0])
    es = edges(t, v, 0.2, 1.0, 1.8)
    assert all(a.rising != b.rising for a, b in zip(es, es[1:]))
    assert np.allclose(transition(es, True, 0.2, 1.8, False), 8e-6)
    assert np.allclose(transition(es, False, 0.2, 1.8, False), 8e-6)
    assert np.allclose(transition(es, True, 0.2, 1.8, True), 2e5)
    assert np.allclose(transition(es, False, 0.2, 1.8, True), -2e5)
    p = periods(es, True)
    assert np.allclose(p, 1e-3) and len(p) == 4  # 只用上升緣，不和下降緣混算
    assert np.allclose(widths(es, True), 500e-6) and np.allclose(widths(es, False), 500e-6)
    assert np.allclose(duty(es, True), 50) and np.allclose(duty(es, False), 50)
    # 25% 工作週期，逐週期計算
    v25 = np.interp(t % 1e-3, [0, 10e-6, 250e-6, 260e-6, 1e-3], [0, 2, 2, 0, 0])
    e25 = edges(t, v25, 0.2, 1.0, 1.8)
    assert np.allclose(duty(e25, True), 25) and np.allclose(duty(e25, False), 25)
    # 只在第 2 個上升緣後加 0.2 V 過衝，前 1 個上升緣前加 0.1 V 下凹
    w = v.copy()
    w[1012] += 0.2
    w[995] -= 0.1
    es2 = edges(t, w, 0.2, 1.0, 1.8)
    ov = shoot(w, es2, True, 2.0, 0.0, False)
    assert np.isclose(ov[1], 10) and np.isclose(ov[0], 0) and np.isclose(ov[2], 0)
    pre = shoot(w, es2, True, 2.0, 0.0, True)
    assert np.isclose(pre[1], 5) and np.isclose(pre[0], 0)
    assert np.allclose(shoot(w, es2, False, 2.0, 0.0, False), 0)
    # 毛刺（沒過上閾值）不算邊緣；沒有邊緣時丟出原因
    g = np.zeros(100)
    g[50] = 1.0
    assert edges(t[:100], g, 0.2, 1.0, 1.8) == []
    try:
        periods([], True)
        raise AssertionError("應該丟出 ScopeError")
    except ScopeError as exc:
        assert "完整週期" in str(exc)
    print("analysis.edge self-check OK")


if __name__ == "__main__":
    _self_check()
