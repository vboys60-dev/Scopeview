"""即時眼圖與眼圖量測（依 Infiniium 手冊 dlg_RealTimeEyeSetup、Eye_Height、Eye_Width、Eye_Crossing、
Eye_Jitter、Eye_Q-Factor、Eye_Duty_Cycle_Distortion）。

即時眼圖＝把單次擷取依還原時脈折疊：相位 0／1 是理想轉態、眼中心在 0.5 UI，顯示 −0.5～1.5 UI。
以下都是近似，與 Infiniium 的色階資料庫算法不同（畫面要標明）：
- Vtop／Vbase：UI 40–60% 的原始樣本以中閾值分上下兩群，取平均與 σ。
- 交叉點：中閾值邊緣的 TIE 分布，迭代縮窄到 ±3σ 求中心與 σ；分開揭露原始 σ、實測 p-p、裁切 σ 與 6σ 估計。
- 眼高＝(Vtop−3σtop)−(Vbase+3σbase)、眼寬＝UI−6σ（3σ 外插；固定頻率還原下兩個交叉點分布相同）。
- Vcross：每個 UI 在交叉時間內插出的電壓，取中段直方圖眾數。
色階圖相鄰取樣之間線性補點只供顯示，量測一律用原始取樣。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis.clock import Clock
from scope_tool.analysis import status as st
from scope_tool.contracts import ScopeError

NAMES = ("眼高", "眼寬", "Q 值", "Crossing %", "眼 Jitter 原始 σ", "眼 Jitter 實測 p-p", "眼 Jitter 裁切 σ", "眼 Jitter 6σ 估計", "DCD")
X_RANGE = (-0.5, 1.5)
_X_BINS, _Y_BINS = 400, 256
_LIMIT = 50_000_000  # 補點後總點數上限：超過就少補點（不截掉記錄）
_CHUNK = 2_000_000
_SIGMA_FLOOR_UI = 1e-12  # 相對 UI 的浮點下限；低於此值不裁切。
_TRIM_LIMITED_FRACTION = 0.01  # 待校準的產品門檻。
_TRIMMED_NAMES = ("眼寬", "眼 Jitter 裁切 σ", "眼 Jitter 6σ 估計")
_CROSSING_NAMES = _TRIMMED_NAMES + ("Crossing %",)


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


def crossing(ck: Clock) -> tuple[float, float, int]:
    """(交叉中心 UI, σ UI, 剔除點數)：TIE 迭代縮窄到 ±3σ。"""
    x = ck.tie / ck.ui
    keep = np.ones(x.size, bool)
    c, s = float(np.median(x)), float(x.std())
    for _ in range(20):
        new = np.abs(x - c) <= 3 * s
        if s < _SIGMA_FLOOR_UI or np.array_equal(new, keep) or not new.any():
            break
        keep = new
        c, s = float(x[keep].mean()), float(x[keep].std())
    return c, s, int(x.size - np.count_nonzero(keep))


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
    if name not in _TRIMMED_NAMES:
        return []
    removed = crossing(ck)[2]
    fraction = removed / ck.tie.size
    info = f"剔除 {removed} 點／{fraction:.3%}"
    return [info + ("（裁切 σ、6σ 估計與眼寬可能偏樂觀）" if fraction > _TRIM_LIMITED_FRACTION else "")]


def measure(name: str, t: np.ndarray, v: np.ndarray, ck: Clock) -> np.ndarray:
    name = "眼 Jitter 裁切 σ" if name == "眼 Jitter RMS" else name  # 舊量測呼叫端相容別名只留此處。
    if name in ("眼 Jitter 原始 σ", "眼 Jitter 實測 p-p", "眼 Jitter p-p"):
        value = ck.tie.std() if name == "眼 Jitter 原始 σ" else np.ptp(ck.tie)
        return np.array([value])
    if name in _CROSSING_NAMES and name != "Crossing %":
        _, s, _ = crossing(ck)
        width = (1 - 6 * s) * ck.ui
        value = width if name == "眼寬" else (6 * s if name == "眼 Jitter 6σ 估計" else s) * ck.ui
        return np.array([np.nan if name == "眼寬" and width <= 0 else value])
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


def assess(name: str, t: np.ndarray, v: np.ndarray, ck: Clock) -> st.Result:
    """單筆量測狀態；原始與裁切統計皆以秒揭露。"""
    measure(name, t, v, ck)  # 保留既有無法量測的例外。
    result = st.Result(ck.status, ck.reasons, dict(ck.diagnostics or {}))
    if name not in _CROSSING_NAMES + ("眼 Jitter 原始 σ", "眼 Jitter 實測 p-p", "眼 Jitter p-p"):
        return result
    _, sigma, removed = crossing(ck)
    signed_width = (1 - 6 * sigma) * ck.ui
    diagnostics = {"raw_sigma": float(ck.tie.std()), "measured_pp": float(np.ptp(ck.tie)),
                   "trimmed_sigma": sigma * ck.ui, "six_sigma_estimate": 6 * sigma * ck.ui,
                   "trimmed_count": removed, "trimmed_fraction": removed / ck.tie.size,
                   "trimmed_limited_fraction": _TRIM_LIMITED_FRACTION,
                   "sigma_floor_ui": _SIGMA_FLOOR_UI}
    if name in _TRIMMED_NAMES and removed / ck.tie.size > _TRIM_LIMITED_FRACTION:
        result = st.worst(result, st.Result(st.LIMITED, (st.CROSSING_TRIMMED,), {}))
    if name == "眼寬":
        diagnostics["signed_width"] = signed_width
        if signed_width <= 0:
            result = st.worst(result, st.Result(st.INVALID, (st.EYE_NO_POSITIVE_OPENING,), {}))
    return st.worst(result, st.Result(st.VALID, (), diagnostics))


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
    assert abs(m["眼 Jitter 裁切 σ"] - 10.2e-12) < 0.8e-12, m  # √(10² + 2²) ps：雜訊 0.01 V ÷ 斜率 5 V/ns
    assert abs(m["眼 Jitter 6σ 估計"] - 6 * m["眼 Jitter 裁切 σ"]) < 1e-18 and abs(m["眼寬"] - 939e-12) < 5e-12
    assert abs(m["眼高"] - 0.94) < 0.01 and abs(m["Q 值"] - 50) < 3 and abs(m["Crossing %"] - 50) < 2
    assert m["DCD"] < 2e-12
    # 下降緣晚 30 ps → DCD 30 ps
    falls = np.r_[0, (bits[:-1] == 1) & (bits[1:] == 0), 0][:n + 1] * 30e-12
    t2, v2 = nrz(bits, ui, 20, rise=4, jitter=falls)
    assert abs(measure("DCD", t2, v2, recover(t2, v2, (10, 50, 90), ClockSpec("NRZ 資料")))[0] - 30e-12) < 1e-13
    assert crossing(ck)[2] < 0.02 * ck.tie.size and "偏樂觀" not in notes("眼寬", ck)[0]
    # 約 6% 邊緣晚 0.2 UI：尾峰被裁掉 → 提示
    late = np.where(rng.random(n + 1) < 0.06, 0.2e-9, 0.0)
    t3, v3 = nrz(bits, ui, 20, rise=4, jitter=late)
    ck3 = recover(t3, v3, (10, 50, 90), ClockSpec("NRZ 資料", mode="半自動", rate=1e9))  # 全自動的最窄脈衝會被拉偏
    assert "偏樂觀" in notes("眼 Jitter 裁切 σ", ck3)[0] and notes("眼高", ck3) == []
    assert st.CROSSING_TRIMMED in assess("眼 Jitter 6σ 估計", t3, v3, ck3).reasons
    assert assess("眼寬", t3, v3, ck3).status == st.LIMITED
    trimmed = assess("眼寬", t3, v3, ck3)
    assert st.CROSSING_TRIMMED in trimmed.reasons and trimmed.diagnostics["trimmed_count"] > 0
    assert 0 < trimmed.diagnostics["trimmed_fraction"] < 1
    assert np.isclose(measure("眼 Jitter 實測 p-p", t, v, ck)[0], np.ptp(ck.tie), rtol=1e-12, atol=0)
    assert np.isclose(measure("眼 Jitter 原始 σ", t, v, ck)[0], ck.tie.std(), rtol=1e-12, atol=0)
    clean_t, clean_v = nrz(bits, ui, 20)
    for mode in ("手動", "半自動"):
        clean = recover(clean_t, clean_v, (10, 50, 90), ClockSpec("NRZ 資料", mode=mode, rate=1e9))
        assert assess("眼寬", clean_t, clean_v, clean).status == st.VALID
        assert crossing(clean)[2] == 0
    tiny = clean._replace(tie=np.r_[np.zeros(1999), 1e-14 * ui])
    assert crossing(tiny)[2] == 0 and st.CROSSING_TRIMMED not in assess("眼寬", t, v, tiny).reasons
    # 固定數值驗證下限，避免常數突變與斷言一起漂移。
    for sigma, removed in ((0.99e-12, 0), (1.01e-12, 1)):
        x = np.r_[np.zeros(99), 1.0]
        boundary = clean._replace(tie=x * (sigma / x.std()) * ui)
        assert crossing(boundary)[2] == removed
    wide = clean._replace(tie=np.tile([-0.2, 0.2], 1000) * ui)
    result = assess("眼寬", t, v, wide)
    assert np.isnan(measure("眼寬", t, v, wide)[0]) and result.status == st.INVALID
    assert st.EYE_NO_POSITIVE_OPENING in result.reasons and result.diagnostics["signed_width"] < 0
    inherited = clean._replace(status=st.INVALID, reasons=(st.GRID_COLLISION_MANY,))
    assert assess("眼寬", t, v, inherited).status == st.INVALID
    assert assess("眼高", clean_t, clean_v, inherited).reasons == inherited.reasons
    for name in ("眼 Jitter 原始 σ", "眼 Jitter 實測 p-p", "眼 Jitter p-p"):
        assert assess(name, t3, v3, ck3).status == st.VALID
    # 高斯尾端少量剔除只揭露；固定離群數驗證嚴格 >1% 的邊界。
    gaussian = clean._replace(tie=np.random.default_rng(30).normal(0, 10e-12, 10000))
    assert 0 < assess("眼寬", t, v, gaussian).diagnostics["trimmed_fraction"] < 0.01
    assert assess("眼寬", t, v, gaussian).status == st.VALID
    for count in (99, 100, 101):
        sample = clean._replace(tie=np.r_[np.tile([-0.01, 0.01], 5000)[:10000-count], np.full(count, 0.2)] * ui)
        for name in _TRIMMED_NAMES + ("眼 Jitter 原始 σ", "眼 Jitter 實測 p-p"):
            result = assess(name, t, v, sample)
            limited = count > 100 and name in _TRIMMED_NAMES
            assert result.status == (st.LIMITED if limited else st.VALID), (count, name, result)
            assert (st.CROSSING_TRIMMED in result.reasons) == limited
            assert result.diagnostics["trimmed_count"] == count
            assert np.isclose(result.diagnostics["trimmed_fraction"], count / 10000, rtol=0, atol=1e-15)
        assert ("偏樂觀" in notes("眼寬", sample)[0]) == (count > 100)
    sample = clean._replace(tie=np.r_[np.tile([-0.01, 0.01], 10000)[:19799], np.full(201, 0.2)] * ui)
    assert "201 點／1.005%" in notes("眼寬", sample)[0]
    assert wide.status == st.VALID  # 眼寬失效不回寫時脈層。
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
