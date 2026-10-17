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
# 需要選邊緣方向的量測（手冊 Measure All Edges 時要指定 Rising／Falling）。
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
    """回傳 (vmin, vmax, top, base)。眾數取該直方圖格內的平均值，避免格中心偏差。"""
    vmin, vmax = float(v.min()), float(v.max())
    if vmax == vmin:
        return vmin, vmax, vmax, vmin
    counts, bins = np.histogram(v, bins=_BINS, range=(vmin, vmax))
    cut = int(_BINS * 0.4)

    def mode(k: int, fallback: float) -> float:
        if counts[k] < 0.05 * v.size:
            return fallback
        sel = v[(v >= bins[k]) & (v <= bins[k + 1])]
        return float(sel.mean())

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
    avg = float(v.mean())
    single = {"Vmax": vmax, "Vmin": vmin, "Vp-p": vmax - vmin, "Vtop": top, "Vbase": base,
              "Vamp": top - base, "Vavg": avg, "Vrms(DC)": float(np.sqrt(np.mean(v ** 2))),
              "Vrms(AC)": float(np.sqrt(np.mean((v - avg) ** 2)))}
    if name in single:
        return np.array([single[name]])
    amp = top - base
    if amp <= 0:
        raise ScopeError("波形沒有振幅（top = base），找不到邊緣。")
    lo, mid, hi = (base + amp * p / 100 for p in pct)
    es = edge.edges(t, v, lo, mid, hi)
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
        return edge.shoot(v, es, rising, top, base, name == "前衝")
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
