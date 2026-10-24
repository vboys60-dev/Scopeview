"""離線自動量測（依 Keysight Infiniium Offline 手冊）：輸入驗證、top/base、電壓量測、量測分派與統計。

手冊定義：top/base 取自直方圖（上／下各 40% 找最多次數，次數 < 5% 退回最大／最小）；
閾值為 top−base 的百分比（10/50/90 或 20/50/80）。時間類量測在 edge.py。
# 待真機驗證：與示波器面板數值比對。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis import edge
from scope_tool.analysis.rms import rms_ac, rms_dc
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
              "Vamp": top - base, "Vrms(DC)": rms_dc(v),
              "Vrms(AC)": rms_ac(v)}
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
    from scope_tool.analysis.measure_check import _self_check as check
    check()


if __name__ == "__main__":
    _self_check()
