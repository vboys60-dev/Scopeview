"""即時眼圖與眼圖量測（依 Infiniium 手冊 dlg_RealTimeEyeSetup、Eye_Height、Eye_Width、Eye_Crossing、
Eye_Jitter、Eye_Q-Factor、Eye_Duty_Cycle_Distortion）。

即時眼圖＝把單次擷取依還原時脈折疊：相位 0／1 是理想轉態、眼中心在 0.5 UI，顯示 −0.5～1.5 UI。
以下都是近似，與 Infiniium 的色階資料庫算法不同（畫面要標明）：
- Vtop／Vbase：UI 40–60% 的原始樣本以中閾值分上下兩群，取平均與 σ。
- 交叉點：中閾值邊緣的 TIE 分布，迭代縮窄到 ±3σ 求中心與 σ；眼 Jitter RMS＝σ、p-p＝6σ。
- 眼高＝(Vtop−3σtop)−(Vbase+3σbase)、眼寬＝UI−6σ（3σ 外插；固定頻率還原下兩個交叉點分布相同）。
- Vcross：每個 UI 在交叉時間內插出的電壓，取中段直方圖眾數。
色階圖相鄰取樣之間線性補點只供顯示，量測一律用原始取樣。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis.clock import Clock
from scope_tool.contracts import ScopeError

NAMES = ("眼高", "眼寬", "Q 值", "Crossing %", "眼 Jitter RMS", "眼 Jitter p-p", "DCD")
X_RANGE = (-0.5, 1.5)
_X_BINS, _Y_BINS = 400, 256
_LIMIT = 50_000_000  # 補點後總點數上限：超過就少補點（不截掉記錄）
_CHUNK = 2_000_000


def phase(t: np.ndarray, ck: Clock) -> np.ndarray:
    return (t - ck.t0) / ck.ui


def rails(t: np.ndarray, v: np.ndarray, ck: Clock) -> tuple[float, float, float, float]:
    """(Vtop, σtop, Vbase, σbase)：UI 40–60% 的樣本以中閾值分兩群。"""
    f = np.mod(phase(t, ck), 1.0)
    center = v[(f >= 0.4) & (f <= 0.6)]
    hi, lo = center[center >= ck.mid], center[center < ck.mid]
    if min(hi.size, lo.size) < 10:
        raise ScopeError("眼中央（40–60% UI）的高、低準位樣本不足")
    return float(hi.mean()), float(hi.std()), float(lo.mean()), float(lo.std())


def crossing(ck: Clock) -> tuple[float, float, float]:
    """(交叉中心 UI, σ UI, 保留比例)：TIE 迭代縮窄到 ±3σ；保留比例低表示有離群或多峰。"""
    x = ck.tie / ck.ui
    keep = np.ones(x.size, bool)
    c, s = float(np.median(x)), float(x.std())
    for _ in range(20):
        new = np.abs(x - c) <= 3 * s
        if s == 0 or np.array_equal(new, keep):
            break
        keep = new
        c, s = float(x[keep].mean()), float(x[keep].std())
    return c, s, float(keep.mean())


def v_cross(t: np.ndarray, v: np.ndarray, ck: Clock, c: float, top: float, base: float) -> float:
    k = np.arange(np.ceil(phase(t[0], ck) - c), np.floor(phase(t[-1], ck) - c) + 1)
    vc = np.interp(ck.t0 + (k + c) * ck.ui, t, v)
    amp = top - base
    band = vc[(vc > base + 0.1 * amp) & (vc < top - 0.1 * amp)]  # 去掉沒有轉態的 UI（停在上下準位）
    if band.size < 10:
        raise ScopeError("交叉點附近的樣本不足，無法判定 Crossing %")
    counts, bins = np.histogram(band, 50)
    if counts.max() < 2 * counts.mean():
        raise ScopeError("交叉電壓沒有明顯的峰，無法判定 Crossing %")
    k = int(counts.argmax())
    return float(band[(band >= bins[k]) & (band <= bins[k + 1])].mean())


def notes(name: str, ck: Clock) -> list[str]:
    """量測表要附的提示：以交叉點 σ 為準的量測，裁掉太多就提醒。"""
    if name not in ("眼寬", "眼 Jitter RMS", "眼 Jitter p-p", "Crossing %"):
        return []
    kept = crossing(ck)[2]
    return [f"交叉點只保留 {kept:.0%}（有離群或多峰，σ 偏小、眼寬偏大）"] if kept < 0.95 else []


def measure(name: str, t: np.ndarray, v: np.ndarray, ck: Clock) -> np.ndarray:
    if name in ("眼寬", "眼 Jitter RMS", "眼 Jitter p-p"):
        _, s, _ = crossing(ck)
        return np.array([{"眼寬": 1 - 6 * s, "眼 Jitter RMS": s, "眼 Jitter p-p": 6 * s}[name] * ck.ui])
    if name == "DCD":
        if ck.rising.all() or not ck.rising.any():
            raise ScopeError("DCD 需要上升與下降緣（時脈請把邊緣設為「兩者」）")
        return np.array([abs(np.median(ck.tie[ck.rising]) - np.median(ck.tie[~ck.rising]))])
    top, s_top, base, s_base = rails(t, v, ck)
    if name == "眼高":
        return np.array([(top - 3 * s_top) - (base + 3 * s_base)])
    if name == "Q 值":
        return np.array([(top - base) / (s_top + s_base) if s_top + s_base > 0 else np.inf])
    if name == "Crossing %":
        return np.array([(v_cross(t, v, ck, crossing(ck)[0], top, base) - base) / (top - base) * 100])
    raise ScopeError(f"未知的量測：{name}")


def density(t: np.ndarray, v: np.ndarray, ck: Clock) -> tuple[np.ndarray, tuple[float, float]]:
    """色階圖：回傳 (次數 [x, y], 電壓範圍)。x 範圍 X_RANGE（UI），每個點畫兩次補滿 2 UI。"""
    dt = float(np.median(np.diff(t)))
    m = int(np.clip(np.ceil(_X_BINS / 2 * dt / ck.ui), 1, max(1, _LIMIT // t.size)))
    lo, hi = float(v.min()), float(v.max())
    pad = 0.1 * (hi - lo) or 1.0
    ylim = (lo - pad, hi + pad)
    counts = np.zeros((_X_BINS, _Y_BINS))
    frac = np.arange(m) / m
    step = max(_CHUNK // m, 1)
    for a in range(0, t.size - 1, step):
        b = min(a + step, t.size - 1)
        tt = (t[a:b, None] + np.diff(t[a:b + 1])[:, None] * frac).ravel()
        vv = (v[a:b, None] + np.diff(v[a:b + 1])[:, None] * frac).ravel()
        x = np.mod(phase(tt, ck), 1.0)
        x = np.concatenate((x, np.where(x < 0.5, x + 1, x - 1)))
        counts += np.histogram2d(x, np.concatenate((vv, vv)), bins=(_X_BINS, _Y_BINS),
                                 range=(X_RANGE, ylim))[0]
    return counts, ylim


def _self_check() -> None:
    from scope_tool.analysis.clock import ClockSpec, nrz, recover

    rng = np.random.default_rng(7)
    ui, n = 1e-9, 6000
    bits = rng.integers(0, 2, n)
    bits[:3] = (0, 1, 0)
    t, v = nrz(bits, ui, 20, rise=4, jitter=rng.normal(0, 10e-12, n + 1))
    v = v + rng.normal(0, 0.01, v.size)
    ck = recover(t, v, (10, 50, 90), ClockSpec("NRZ 資料"))
    m = {name: measure(name, t, v, ck)[0] for name in NAMES}
    assert abs(m["眼 Jitter RMS"] - 10.2e-12) < 0.8e-12, m  # √(10² + 2²) ps：雜訊 0.01 V ÷ 斜率 5 V/ns
    assert abs(m["眼 Jitter p-p"] - 6 * m["眼 Jitter RMS"]) < 1e-18 and abs(m["眼寬"] - 939e-12) < 5e-12
    assert abs(m["眼高"] - 0.94) < 0.01 and abs(m["Q 值"] - 50) < 3 and abs(m["Crossing %"] - 50) < 2
    assert m["DCD"] < 2e-12
    # 下降緣晚 30 ps → DCD 30 ps
    falls = np.r_[0, (bits[:-1] == 1) & (bits[1:] == 0), 0][:n + 1] * 30e-12
    t2, v2 = nrz(bits, ui, 20, rise=4, jitter=falls)
    assert abs(measure("DCD", t2, v2, recover(t2, v2, (10, 50, 90), ClockSpec("NRZ 資料")))[0] - 30e-12) < 1e-13
    assert crossing(ck)[2] > 0.98 and notes("眼寬", ck) == []
    # 約 6% 邊緣晚 0.2 UI：尾峰被裁掉 → 提示
    late = np.where(rng.random(n + 1) < 0.06, 0.2e-9, 0.0)
    t3, v3 = nrz(bits, ui, 20, rise=4, jitter=late)
    ck3 = recover(t3, v3, (10, 50, 90), ClockSpec("NRZ 資料", mode="半自動", rate=1e9))  # 全自動的最窄脈衝會被拉偏
    assert "交叉點只保留" in notes("眼 Jitter RMS", ck3)[0] and notes("眼高", ck3) == []
    # 色階圖：每個補點畫兩次；眼中心沒有中間電壓的點、交叉處有
    counts, ylim = density(t, v, ck)
    assert counts.sum() > 1.99 * t.size and ylim[0] < -0.05
    xs, ys = counts.shape
    assert counts[xs // 2, ys // 2] == 0 and counts[xs // 4, ys // 2] > 0
    single = ck._replace(rising=np.ones(ck.rising.size, bool))
    try:
        measure("DCD", t, v, single)
        raise AssertionError("單邊應該丟出 ScopeError")
    except ScopeError:
        pass
    print("analysis.eye self-check OK")


if __name__ == "__main__":
    _self_check()
