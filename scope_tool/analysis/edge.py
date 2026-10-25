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


def edges(t: np.ndarray, v: np.ndarray, lo: float, mid: float, hi: float) -> list[Edge]:
    state = np.where(v < lo, 0, np.where(v > hi, 2, 1)).astype(np.int8)
    idx = np.flatnonzero(state != 1)
    st = state[idx]
    k = np.flatnonzero(st[1:] != st[:-1])
    a, b, rising = idx[k], idx[k + 1], st[k] == 0
    times = []
    # 各閾值的第一次交越用二分搜尋批次取得，保留三閾狀態機與線性內插。
    for thr in (lo, mid, hi):
        cross = np.empty(k.size)
        for up in (True, False):
            sel = rising == up
            hits = np.flatnonzero((v[:-1] < thr) & (v[1:] >= thr) if up else
                                  (v[:-1] > thr) & (v[1:] <= thr)) + 1
            j = hits[np.searchsorted(hits, a[sel] + 1)]
            cross[sel] = t[j - 1] + (thr - v[j - 1]) / (v[j] - v[j - 1]) * (t[j] - t[j - 1])
        times.append(cross)
    return [Edge(bool(up), float(l), float(m), float(h), int(x), int(y))
            for up, l, m, h, x, y in zip(rising, *times, a, b)]


def _need(values: list[float], reason: str) -> np.ndarray:
    if not values:
        raise ScopeError(reason)
    return np.array(values, dtype=np.float64)


class BoundedValues(np.ndarray):
    """保留 ndarray 介面，額外標示整組事件的界限。"""
    bound: str | None = None


def transition(es: list[Edge], rising: bool, lo: float, hi: float, slope: bool,
               t: np.ndarray) -> np.ndarray:
    """優先用至少 4 點的邊緣；皆不足時以括住樣本給時間上界、上升斜率下界／下降斜率上界。"""
    selected = [e for e in es if e.rising == rising]
    good = [e for e in selected if e.b - e.a + 1 >= 4]
    bounded = not good
    if bounded:
        d = [float(t[e.b] - t[e.a]) for e in selected]
    else:
        d = [e.t_hi - e.t_lo if rising else e.t_lo - e.t_hi for e in good]
    name = "上升緣" if rising else "下降緣"
    out = _need(d, f"範圍內沒有完整{name}")
    if slope:
        out = ((hi - lo) if rising else (lo - hi)) / out
    if bounded:
        out = out.view(BoundedValues)
        out.bound = ">" if slope and rising else "<"
    return out


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


def shoot(t: np.ndarray, v: np.ndarray, es: list[Edge], rising: bool,
          top: float, base: float, pre: bool) -> np.ndarray:
    """過衝（pre=False）：越過遠端閾值後到平台中點的局部極值；
    前衝（pre=True）：平台中點到越過近端閾值前的局部極值。皆以 top−base 的百分比表示。"""
    amp = top - base
    out = []
    for k, e in enumerate(es):
        if e.rising != rising:
            continue
        if pre:
            end = e.t_lo if rising else e.t_hi
            prev = es[k - 1] if k else None
            if prev is None:
                continue  # 缺前鄰緣，無法定出平台中心。
            start = ((prev.t_lo if rising else prev.t_hi) + end) / 2
        else:
            start = e.t_hi if rising else e.t_lo
            nxt = es[k + 1] if k + 1 < len(es) else None
            if nxt is None:
                continue  # 缺後鄰緣，無法定出平台中心。
            end = (start + (nxt.t_hi if rising else nxt.t_lo)) / 2
        # 平台中心依閾值交越時間計算是本程式假設，手冊未載明中心算法。
        a, b = np.searchsorted(t, start), np.searchsorted(t, end, side="right")
        # 將內插端點納入極值搜尋，手冊未載明，保留現法。
        seg = np.r_[np.interp(start, t, v), v[a:b], np.interp(end, t, v)]
        # 上升緣：過衝看高於 top、前衝看低於 base；下降緣相反。
        # 負值截零規則手冊未載明，保留公式原值。
        high_side = rising != pre
        out.append((seg.max() - top if high_side else base - seg.min()) / amp * 100)
    return _need(out, "範圍內沒有前後都有鄰緣的" + ("上升緣" if rising else "下降緣") + "（無法定平台中心）")


def _self_check() -> None:
    dt = 1e-6
    t = np.arange(5000) * dt
    v = np.interp(t % 1e-3, [0, 10e-6, 500e-6, 510e-6, 1e-3], [0, 2, 2, 0, 0])
    es = edges(t, v, 0.2, 1.0, 1.8)
    assert all(a.rising != b.rising for a, b in zip(es, es[1:]))
    assert np.allclose(transition(es, True, 0.2, 1.8, False, t), 8e-6)
    assert np.allclose(transition(es, False, 0.2, 1.8, False, t), 8e-6)
    assert np.allclose(transition(es, True, 0.2, 1.8, True, t), 2e5)
    assert np.allclose(transition(es, False, 0.2, 1.8, True, t), -2e5)
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
    ov = shoot(t, w, es2, True, 2.0, 0.0, False)
    assert np.isclose(ov[1], 10) and np.isclose(ov[0], 0) and np.isclose(ov[2], 0)
    pre = shoot(t, w, es2, True, 2.0, 0.0, True)
    assert np.isclose(pre[0], 5) and np.isclose(pre[1], 0)
    assert np.allclose(shoot(t, w, es2, False, 2.0, 0.0, False), 0)
    # 從下降緣中途切入，前一緣的 15% 下衝振鈴不能算成第一個上升緣的前衝。
    ring = v.copy()
    ring[520:550] -= 0.3
    ct, cv = t[505:], ring[505:]
    ce = edges(ct, cv, 0.2, 1.0, 1.8)
    assert ce[0].rising
    pre = shoot(ct, cv, ce, True, 2.0, 0.0, True)
    assert len(pre) == 3 and np.allclose(pre, 0, rtol=0, atol=1e-10)
    # 時間反轉後同樣驗證缺後鄰緣的過衝；僅剩單一邊緣時須回報量測失敗。
    rt, rv = ct[-1] - ct[::-1], cv[::-1]
    re = edges(rt, rv, 0.2, 1.0, 1.8)
    ov = shoot(rt, rv, re, False, 2.0, 0.0, False)
    assert len(ov) == 3 and np.allclose(ov, 0, rtol=0, atol=1e-10)
    for pre, times, signal, single in ((True, ct, cv, ce[:1]), (False, rt, rv, re[-1:])):
        for invert in (False, True):
            es_single = [single[0]._replace(rising=not single[0].rising)] if invert else single
            try:
                shoot(times, 2 - signal if invert else signal, es_single,
                      es_single[0].rising, 2.0, 0.0, pre)
                raise AssertionError("缺鄰緣應該丟出 ScopeError")
            except ScopeError as exc:
                assert str(exc) == "範圍內沒有前後都有鄰緣的" + ("上升緣" if es_single[0].rising else "下降緣") + "（無法定平台中心）"
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
