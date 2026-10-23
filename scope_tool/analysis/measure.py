"""離線自動量測（依 Keysight Infiniium Offline 手冊）：輸入驗證、top/base、電壓量測、量測分派與統計。

手冊定義：top/base 取自直方圖（上／下各 40% 找最多次數，次數 < 5% 退回最大／最小）；
閾值為 top−base 的百分比（10/50/90 或 20/50/80）。時間類量測在 edge.py。
# 待真機驗證：與示波器面板數值比對。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis import edge
from scope_tool.contracts import ScopeError

_BINS = 256

# 量測名稱 → (分類, 單位樣板)；"{u}" 換成來源通道單位。
MEASUREMENTS: dict[str, tuple[str, str]] = {
    "上升時間": ("時間", "s"), "下降時間": ("時間", "s"),
    "上升斜率": ("時間", "{u}/s"), "下降斜率": ("時間", "{u}/s"),
    "週期": ("時間", "s"), "頻率": ("時間", "Hz"),
    "+寬度": ("時間", "s"), "-寬度": ("時間", "s"), "工作週期": ("時間", "%"),
    "Vmax": ("電壓", "{u}"), "Vmin": ("電壓", "{u}"), "Vp-p": ("電壓", "{u}"),
    "Vtop": ("電壓", "{u}"), "Vbase": ("電壓", "{u}"), "Vamp": ("電壓", "{u}"),
    "Vavg": ("電壓", "{u}"), "Vrms(DC)": ("電壓", "{u}"), "Vrms(AC)": ("電壓", "{u}"),
    "過衝": ("電壓", "%"), "前衝": ("電壓", "%"),
}
# 需要選邊緣方向的量測；上升／下降時間、斜率與正／負寬度已由名稱指定方向。
SLOPED = {"週期", "頻率", "工作週期", "過衝", "前衝"}
THRESHOLDS = {"10/50/90 %": (10.0, 50.0, 90.0), "20/50/80 %": (20.0, 50.0, 80.0)}
STAT_COLUMNS = ("目前", "平均", "最小", "最大", "範圍", "標準差", "次數")


def validate(t: np.ndarray, v: np.ndarray) -> None:
    if not (np.issubdtype(t.dtype, np.floating) and np.issubdtype(v.dtype, np.floating)):
        raise ScopeError("時間與電壓資料必須使用浮點型別。")
    if len(t) != len(v):
        raise ScopeError("時間與電壓點數不一致。")
    if len(v) < 2:
        raise ScopeError("範圍內至少要 2 個取樣點。")
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(v))):
        raise ScopeError("資料含 NaN 或無限大。")
    if np.any(np.diff(t) <= 0):
        raise ScopeError("時間軸必須遞增。")


def uniform_dt(t: np.ndarray) -> float:
    """等距取樣才能做 FFT／濾波；容許 CSV 來回造成的微小誤差。"""
    d = np.diff(t)
    dt = float(d.mean())
    if np.ptp(d) > 1e-3 * dt:
        raise ScopeError("取樣間隔不等距，無法做 FFT／濾波。")
    return dt


def levels(v: np.ndarray) -> tuple[float, float, float, float]:
    """回傳 (vmin, vmax, top, base)。格內代表值手冊未載明，保留格內平均。"""
    vmin, vmax = float(v.min()), float(v.max())
    if vmax == vmin:
        return vmin, vmax, vmax, vmin
    counts, bins = np.histogram(v, bins=_BINS, range=(vmin, vmax))
    cut = int(_BINS * 0.4)  # 40% 的格數取整方式手冊未載明，保留向下取整。

    def mode(k: int, fallback: float) -> float:
        if counts[k] < 0.05 * v.size:
            return fallback
        # 與 np.histogram 一致：左閉右開，只有最後一格包含右端點。
        sel = v[(v >= bins[k]) & ((v <= bins[k + 1]) if k == _BINS - 1 else (v < bins[k + 1]))]
        return float(sel.mean())

    # 同高峰取內側：Top 選較低格，Base 選較高格。
    top = mode(_BINS - cut + int(counts[-cut:].argmax()), vmax)
    base = mode(cut - 1 - int(counts[:cut][::-1].argmax()), vmin)
    return vmin, vmax, top, base


def unit_of(name: str, source_unit: str) -> str:
    return MEASUREMENTS[name][1].replace("{u}", source_unit)


def _sample_index(t: np.ndarray, endpoint: float) -> int:
    """相對時間端點僅在 8 ULP 內吸附樣本，回傳左閉右開的切片索引。"""
    i = int(np.searchsorted(t, endpoint))
    near = min((j for j in (i - 1, i) if 0 <= j < t.size), key=lambda j: abs(t[j] - endpoint))
    return near if abs(t[near] - endpoint) <= 8 * np.spacing(abs(endpoint)) else i


def measure(name: str, t: np.ndarray, v: np.ndarray, pct: tuple[float, float, float] = (10, 50, 90),
            rising: bool = True) -> np.ndarray:
    """回傳該量測在範圍內每個事件的值（整段量測長度 1）；量測不出來丟 ScopeError（訊息即原因）。"""
    validate(t, v)
    vmin, vmax, top, base = levels(v)
    # 均勻次取樣比例手冊未載明，保留全部樣本；AC RMS 使用同段平均。
    avg = float(v.mean())
    single = {"Vmax": vmax, "Vmin": vmin, "Vp-p": vmax - vmin, "Vtop": top, "Vbase": base,
              "Vamp": top - base, "Vrms(DC)": float(np.sqrt(np.mean(v ** 2))),
              "Vrms(AC)": float(np.sqrt(np.mean((v - avg) ** 2)))}
    if name in single:
        return np.array([single[name]])
    amp = top - base
    if amp <= 0:
        if name == "Vavg":
            return np.array([avg])
        raise ScopeError("波形沒有振幅（top = base），找不到邊緣。")
    lo, mid, hi = (base + amp * p / 100 for p in pct)
    et = t - t[0] if name == "Vavg" else t
    es = edge.edges(et, v, lo, mid, hi)
    if name == "Vavg":
        # 手冊單週期模式從觸發參考點邊緣起算，也允許整個螢幕模式。
        # 離線無觸發參考，改取最左完整邊緣（偏離手冊）至下一同向邊緣的中閾交越。
        # 平均式與次取樣比例手冊未載明，保留樣本算術平均；右端不重複計入。
        for a, b in zip(es, es[2:]):
            if a.rising == b.rising:
                start, stop = _sample_index(et, a.t_mid), _sample_index(et, b.t_mid)
                return np.array([float(v[start:stop].mean())])
        # 無完整週期時的處理手冊未載明，保留原本整段平均（含直流）。
        return np.array([avg])
    if name in ("上升時間", "下降時間", "上升斜率", "下降斜率"):
        return edge.transition(es, name.startswith("上升"), lo, hi, name.endswith("斜率"))
    if name == "週期":
        return edge.periods(es, rising)
    if name == "頻率":
        return 1 / edge.periods(es, rising)
    if name in ("+寬度", "-寬度"):
        return edge.widths(es, name == "+寬度")
    if name == "工作週期":
        return edge.duty(es, rising)
    if name in ("過衝", "前衝"):
        return edge.shoot(t, v, es, rising, top, base, name == "前衝")
    raise ScopeError(f"未知的量測：{name}")


def stats(values: np.ndarray) -> tuple[float, float, float, float, float, float, int]:
    """(目前, 平均, 最小, 最大, 範圍, 標準差, 次數)；目前＝範圍內最左邊的事件。"""
    lo, hi = float(values.min()), float(values.max())
    return (float(values[0]), float(values.mean()), lo, hi, hi - lo, float(values.std()), len(values))


def measure_all(tasks: list[tuple[str, np.ndarray, np.ndarray, bool]],
                pct: tuple[float, float, float]) -> list[tuple | str]:
    """背景執行用：每筆回傳 stats 結果，失敗回傳原因字串（一筆失敗不影響其他筆）。"""
    out: list[tuple | str] = []
    for name, t, v, rising in tasks:
        try:
            out.append(stats(measure(name, t, v, pct, rising)))
        except ScopeError as exc:
            out.append(str(exc))
    return out


def _self_check() -> None:
    # 1 kHz 方波 0~2 V，上升／下降各 10 µs 線性邊緣，每 1 µs 一點，5 個週期。
    dt = 1e-6
    t = np.arange(5000) * dt
    v = np.interp(t % 1e-3, [0, 10e-6, 500e-6, 510e-6, 1e-3], [0, 2, 2, 0, 0])
    m = {name: measure(name, t, v) for name in MEASUREMENTS}
    assert abs(m["Vtop"][0] - 2) < 1e-9 and abs(m["Vbase"][0]) < 1e-9
    assert abs(m["Vp-p"][0] - 2) < 1e-9 and abs(m["Vavg"][0] - 1.0) < 0.01
    for name, expected in (("上升時間", 8e-6), ("下降時間", 8e-6), ("頻率", 1000), ("週期", 1e-3),
                           ("+寬度", 500e-6), ("工作週期", 50), ("上升斜率", 2e5), ("過衝", 0)):
        assert np.allclose(m[name], expected)
    assert np.allclose(measure("上升時間", t, v, THRESHOLDS["20/50/80 %"]), 6e-6)
    assert np.allclose(measure("週期", t, v, rising=False), 1e-3)
    sine = np.sin(2 * np.pi * 1e3 * t)
    assert abs(measure("Vrms(AC)", t, sine)[0] - 1 / np.sqrt(2)) < 1e-3
    # 三角波：直方圖平均分布，top/base 退回 max/min
    tri = np.abs((t % 1e-3) / 1e-3 - 0.5)
    _, vmax, top, base = levels(tri)
    assert top == vmax and base == tri.min()
    # 非整數週期：Vavg 用首個完整週期；RMS 用整段，誤差見各案例。
    short_t = t[:2300]
    for signal, expected, tol in ((v[:2300], 1.0, 1e-9),
                                  (sine[:2300], 0.0, 1e-9), (tri[:2300], 0.25, 1e-6)):
        assert abs(measure("Vavg", short_t, signal)[0] - expected) < tol
    short_v = v[:2300] + 3
    for name, expected in (("Vrms(DC)", np.sqrt(np.mean(short_v ** 2))), ("Vrms(AC)", np.std(short_v))):
        assert abs(measure(name, short_t, short_v)[0] - expected) < 1e-12
    assert abs(measure("Vavg", t[200:2300], v[200:2300])[0] - 1) < 1e-9  # 首緣下降
    assert measure("Vavg", t[:200], v[:200])[0] == v[:200].mean()  # 無完整週期保留整段
    assert measure("Vavg", t, np.full_like(t, 3))[0] == 3
    shifted = v + np.repeat(np.arange(5) * 0.02, 1000)
    cycle_avgs = [shifted[k + 6:k + 1006].mean() for k in (0, 1000, 2000, 3000)]
    assert np.all(np.diff(cycle_avgs) > 0.01) and abs(measure("Vavg", t, shifted)[0] - cycle_avgs[0]) < 1e-12
    # 25.5% PWM：平移起點與閾值組合不影響樣本平均。
    pwm = np.interp(t % 1e-3, [0, 10e-6, 255e-6, 265e-6, 1e-3], [0, 2, 2, 0, 0])
    avgs = [measure("Vavg", t + offset, pwm, pct)[0]
            for offset in (0, -5e-3, 1e-3, 1.0, 3.3e-3, 123.0) for pct in THRESHOLDS.values()]
    assert np.ptp(avgs) < 1e-12 and np.max(np.abs(np.array(avgs) - 0.51)) < 1e-12
    # 交越掃過取樣間隔，以獨立切片驗證整數與樣本間端點。
    dc = np.repeat(np.arange(5) * 0.02, 1000)
    for pct in THRESHOLDS.values():
        for phase in np.r_[np.linspace(0, 1, 101), 1e-6, 1 - 1e-6]:
            signal = np.interp((np.arange(t.size) - phase) % 1000,
                               [0, 10, 255, 265, 1000], [0, 2, 2, 0, 0])
            start, stop = (5, 1005) if phase == 0 else (6, 1006)
            assert abs(measure("Vavg", t, signal, pct)[0] - signal[start:stop].mean()) < 1e-12
            assert abs(signal[start:stop].mean() - 0.51) < 1e-12
            # 每週期不同 DC；由線性斜率獨立推算索引，不依賴邊緣或吸附函式。
            signal = signal + dc
            _, _, top, base = levels(signal)
            if phase in (0, 1):
                # 固定中閾為 1 V，以不同 DC 的平均區分 [5:1005] 與 [6:1006]。
                fixed = (pct[0], (1 - base) / (top - base) * 100, pct[2])
                assert abs(measure("Vavg", t, signal, fixed)[0] - signal[start:stop].mean()) < 1e-12
            bounds = phase + (top + base) / 0.4 + np.array([0, 999.9])
            bounds = np.where(abs(bounds - np.rint(bounds)) < 1e-10, np.rint(bounds), bounds)
            start, stop = np.ceil(bounds).astype(int)
            assert abs(measure("Vavg", t, signal, pct)[0] - signal[start:stop].mean()) < 1e-12
    # 遠端時間不影響首週期吸附：局部交越不可使用整段 ULP。
    pt = np.arange(5000) * 1e-12
    pv = np.interp((np.arange(5000) + 0.1) % 1000,
                   [0, 10, 250, 270, 1000], [0, 2, 2, 0, 0]) + np.repeat(np.arange(5) * 0.02, 1000)
    _, _, top, base = levels(pv)
    for last in (4.999e-9, 100., 1000.):
        pt[-1] = last
        es = edge.edges(pt, pv, *(base + (top - base) * p / 100 for p in (10, 50, 90)))
        assert tuple(_sample_index(pt, es[k].t_mid) for k in (0, 2)) == (6, 1006)
        assert abs(pv[6:1006].mean() - 0.51012) < 1e-12 and abs(measure("Vavg", pt, pv)[0] - 0.51012) < 1e-12
    # 皮秒取樣平移 1000 s：Vavg 必須先轉相對時間，避免絕對時間 ULP 誤吸附。
    tiny_t = np.arange(5000) * 1.6e-12
    assert abs(measure("Vavg", tiny_t, pv)[0] - measure("Vavg", tiny_t + 1000, pv)[0]) < 1e-12
    # 直方圖左閉右開：相鄰格的邊界值不能混入峰值（誤差 < 1e-12 V）。
    hist = np.r_[np.zeros(50), 1, np.full(20, 0.75), np.full(19, 193 / 256)]
    assert abs(levels(hist)[2] - 0.75) < 1e-12
    hist = np.r_[0, np.ones(50), np.full(20, 0.25), np.full(19, 65 / 256)]
    assert abs(levels(hist)[3] - 0.25) < 1e-12
    # 峰恰為 5% 不回退；低於 5% 才回退。反相同時驗證 Base。
    hist = np.r_[np.zeros(199), np.arange(1, 181) / 256, np.full(20, 0.75), 1]
    assert levels(hist)[2] == 0.75 and levels(1 - hist)[3] == 0.25
    hist[-2] = 0.5
    assert levels(hist)[2] == 1 and levels(1 - hist)[3] == 0
    # 非等距平台以時間分過衝／前衝；反相驗證另外兩式。
    nt = np.sort(np.r_[np.arange(21), np.arange(30, 101, 10), 42, 48]) * dt
    nv = np.interp(nt / dt, [0, 4, 8, 80, 84, 100], [0, 0, 2, 2, 0, 0])
    nv[np.isclose(nt, 40 * dt, rtol=0, atol=1e-12)] = 2.4
    nv[np.isclose(nt, 50 * dt, rtol=0, atol=1e-12)] = 2.6
    for over, pre in ((0.4, 0.6), (0.6, 0.4)):
        # 對調尖峰高度，前衝若誤用全平台也必須失敗。
        nv[np.isclose(nt, 40 * dt, rtol=0, atol=1e-12)] = 2 + over
        nv[np.isclose(nt, 50 * dt, rtol=0, atol=1e-12)] = 2 + pre
        for signal, direction in ((nv, True), (2 - nv, False)):
            assert abs(measure("過衝", nt, signal, rising=direction)[0] - over * 50) < 1e-10
            assert abs(measure("前衝", nt, signal, rising=not direction)[0] - pre * 50) < 1e-10
            assert abs(measure("Vamp", nt, signal)[0] - 2) < 1e-12
            assert abs(measure("Vp-p", nt, signal)[0] - 2.6) < 1e-12
    # 已知 1 ms／25% 方波；兩個方向、兩組閾值都驗證，時間誤差 < 1 ps。
    v25 = np.interp(t % 1e-3, [0, 10e-6, 250e-6, 260e-6, 1e-3], [0, 2, 2, 0, 0])
    for pct in THRESHOLDS.values():
        for direction in (True, False):
            for name, expected, tol in (("週期", 1e-3, 1e-12), ("頻率", 1000, 1e-6), ("工作週期", 25, 1e-8)):
                assert np.allclose(measure(name, t, v25, pct, direction), expected, rtol=0, atol=tol)
        for name, expected in (("+寬度", 250e-6), ("-寬度", 750e-6),
                               *((name, (pct[2] - pct[0]) * 1e-7) for name in ("上升時間", "下降時間"))):
            assert np.allclose(measure(name, t, v25, pct), expected, rtol=0, atol=1e-12)
    rt, rv = np.array([0., 1., 2., 4., 5., 6.]) * dt, np.array([0., 0.3, 0.7, 1., 1., 1.])
    re = edge.edges(rt, rv, 0.1, 0.5, 0.9)[0]
    assert np.allclose([re.t_lo, re.t_mid, re.t_hi], np.array([1 / 3, 1.5, 10 / 3]) * dt,
                       rtol=0, atol=1e-12)
    _, _, top, base = levels(rv)
    _, _, inv_top, inv_base = levels(1 - rv)
    assert top == 1 and base == 0.3 and abs(top - (1 - inv_base)) < 1e-12 and abs(base - (1 - inv_top)) < 1e-12
    expected = (4 - (1 - 0.93) / 0.3 * 2 - 1) * dt
    for name, signal, pct in (("上升時間", rv, (0, 50, 90)), ("下降時間", 1 - rv, (10, 50, 100))):
        assert abs(measure(name, rt, signal, pct)[0] - expected) < 1e-12
    # 邊緣不足四點仍可量週期，但不能量上升／下降時間。
    for signal in (np.array([0., 1.]), np.array([0., 0.5, 1.])):
        for name, samples in (("上升時間", signal), ("下降時間", 1 - signal),
                              ("上升斜率", signal), ("下降斜率", 1 - signal)):
            try:
                measure(name, t[:len(samples)], samples)
                raise AssertionError("不足四點應該丟出 ScopeError")
            except ScopeError as exc:
                assert "4 個取樣點" in str(exc)
        # 重複短邊緣仍能量週期；兩點／三點案例的週期分別是 2／4 µs。
        samples = np.tile(np.r_[signal, signal[-2:0:-1]], 3)
        for direction in (True, False):
            assert np.allclose(measure("週期", t[:len(samples)], samples, rising=direction),
                               2 * (len(signal) - 1) * dt, rtol=0, atol=1e-12)
    assert stats(np.array([3.0, 1.0, 2.0])) == (3.0, 2.0, 1.0, 3.0, 2.0, float(np.std([3, 1, 2])), 3)
    flat = np.ones_like(t)
    assert measure("Vp-p", t, flat)[0] == 0
    res = measure_all([("頻率", t, flat, True), ("Vmax", t, v, True)], (10, 50, 90))
    assert isinstance(res[0], str) and "振幅" in res[0] and res[1][0] == 2
    def rejected(times: np.ndarray, values: np.ndarray, message: str = "") -> None:
        try:
            measure("Vmax", times, values)
            raise AssertionError("應該丟出 ScopeError")
        except ScopeError as exc:
            assert message in str(exc)

    for bad_t, bad_v in ((t[:1], v[:1]), (t[::-1], v), (t, np.r_[v[:-1], np.nan]), (t[:-1], v)):
        rejected(bad_t, bad_v)
    for dtype in (np.int64, np.bool_, object, np.complex128):
        for bad_t, bad_v in ((t.astype(dtype), v), (t, v.astype(dtype))):
            rejected(bad_t, bad_v, "浮點型別")
    assert unit_of("上升斜率", "V²") == "V²/s" and unit_of("頻率", "V") == "Hz" and uniform_dt(t) == dt
    print("analysis.measure self-check OK")


if __name__ == "__main__":
    _self_check()
