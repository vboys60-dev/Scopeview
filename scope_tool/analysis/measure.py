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

    # 同高峰的選擇手冊未載明，保留 argmax 選較低電壓格。
    top = mode(_BINS - cut + int(counts[-cut:].argmax()), vmax)
    base = mode(int(counts[:cut].argmax()), vmin)
    return vmin, vmax, top, base


def unit_of(name: str, source_unit: str) -> str:
    return MEASUREMENTS[name][1].replace("{u}", source_unit)


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
    es = edge.edges(t, v, lo, mid, hi)
    if name == "Vavg":
        # 手冊單週期模式從觸發參考點邊緣起算，也允許整個螢幕模式。
        # 離線無觸發參考，改取最左完整邊緣（偏離手冊）至下一同向邊緣的中閾交越。
        # 平均式與次取樣比例手冊未載明，保留樣本算術平均；右端不重複計入。
        for a, b in zip(es, es[2:]):
            if a.rising == b.rising:
                return np.array([float(v[(t >= a.t_mid) & (t < b.t_mid)].mean())])
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
    assert np.allclose(m["上升時間"], 8e-6) and np.allclose(m["下降時間"], 8e-6)
    assert np.allclose(m["頻率"], 1000) and np.allclose(m["週期"], 1e-3)
    assert np.allclose(m["+寬度"], 500e-6) and np.allclose(m["工作週期"], 50)
    assert np.allclose(m["上升斜率"], 2e5) and np.allclose(m["過衝"], 0)
    assert np.allclose(measure("上升時間", t, v, THRESHOLDS["20/50/80 %"]), 6e-6)
    assert np.allclose(measure("週期", t, v, rising=False), 1e-3)
    sine = np.sin(2 * np.pi * 1e3 * t)
    assert abs(measure("Vrms(AC)", t, sine)[0] - 1 / np.sqrt(2)) < 1e-3
    # 三角波：直方圖平均分布，top/base 退回 max/min
    tri = np.abs((t % 1e-3) / 1e-3 - 0.5)
    _, vmax, top, base = levels(tri)
    assert top == vmax and base == tri.min()
    # 非整數週期：Vavg 只用第一個完整週期；RMS 仍用整段及該段平均。
    # 方波／正弦／三角波平均誤差分別 < 1e-9／1e-9／1e-6 V。
    short_t = t[:2300]
    for signal, expected, tol in ((v[:2300], 1.0, 1e-9),
                                  (sine[:2300], 0.0, 1e-9), (tri[:2300], 0.25, 1e-6)):
        assert abs(measure("Vavg", short_t, signal)[0] - expected) < tol
    short_v = v[:2300] + 3
    assert abs(measure("Vrms(DC)", short_t, short_v)[0] - np.sqrt(np.mean(short_v ** 2))) < 1e-12
    assert abs(measure("Vrms(AC)", short_t, short_v)[0] - np.std(short_v)) < 1e-12
    assert abs(measure("Vavg", t[200:2300], v[200:2300])[0] - 1) < 1e-9  # 首緣下降
    assert measure("Vavg", t[:200], v[:200])[0] == v[:200].mean()  # 無完整週期保留整段
    assert measure("Vavg", t, np.full_like(t, 3))[0] == 3
    # 每個週期使用不同 DC 偏移，避免誤取第二個週期仍通過檢查。
    shifted = v + np.repeat(np.arange(5) * 0.02, 1000)
    _, _, top, base = levels(shifted)
    se = edge.edges(t, shifted, base + (top - base) * 0.1,
                    (top + base) / 2, base + (top - base) * 0.9)
    cycle_avgs = [shifted[(t >= se[k].t_mid) & (t < se[k + 2].t_mid)].mean()
                  for k in (0, 2, 4, 6)]
    assert np.all(np.diff(cycle_avgs) > 0.01)
    assert abs(measure("Vavg", t, shifted)[0] - cycle_avgs[0]) < 1e-12
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
    # 非等距方波：平台中心須用時間，40 µs 過衝、50 µs 前衝分屬中心兩側。
    # 上升過衝 20%、下降前衝 30%；反相驗證另外兩式，容許 1e-10 百分點。
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
            assert np.allclose(measure("週期", t, v25, pct, direction), 1e-3, rtol=0, atol=1e-12)
            assert np.allclose(measure("頻率", t, v25, pct, direction), 1000, rtol=0, atol=1e-6)
            assert np.allclose(measure("工作週期", t, v25, pct, direction), 25, rtol=0, atol=1e-8)
        for name, expected in (("+寬度", 250e-6), ("-寬度", 750e-6),
                               ("上升時間", (pct[2] - pct[0]) * 1e-7),
                               ("下降時間", (pct[2] - pct[0]) * 1e-7)):
            assert np.allclose(measure(name, t, v25, pct), expected, rtol=0, atol=1e-12)
    # 相鄰點線性內插（非等距、閾值不落在樣本上），時間誤差 < 1 ps。
    rt, rv = np.array([0., 1., 2., 4., 5., 6.]) * dt, np.array([0., 0.3, 0.7, 1., 1., 1.])
    re = edge.edges(rt, rv, 0.1, 0.5, 0.9)[0]
    assert np.allclose([re.t_lo, re.t_mid, re.t_hi], np.array([1 / 3, 1.5, 10 / 3]) * dt,
                       rtol=0, atol=1e-12)
    assert abs(measure("上升時間", rt, rv)[0] - 3 * dt) < 1e-12
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
    for bad_t, bad_v in ((t[:1], v[:1]), (t[::-1], v), (t, np.r_[v[:-1], np.nan]), (t[:-1], v)):
        try:
            measure("Vmax", bad_t, bad_v)
            raise AssertionError("應該丟出 ScopeError")
        except ScopeError:
            pass
    assert unit_of("上升斜率", "V²") == "V²/s" and unit_of("頻率", "V") == "Hz"
    assert uniform_dt(t) == dt
    print("analysis.measure self-check OK")


if __name__ == "__main__":
    _self_check()
