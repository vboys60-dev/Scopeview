"""離線自動量測（依 Keysight Infiniium Offline 手冊）：輸入驗證、top/base、電壓量測、量測分派與統計。

手冊定義：top/base 取自直方圖（上／下各 40% 找最多次數，次數 < 5% 退回最大／最小）；
閾值為 top−base 的百分比（10/50/90 或 20/50/80）。時間類量測在 edge.py。
# 待真機驗證：與示波器面板數值比對。
"""
from __future__ import annotations

import math

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
    "-工作週期": ("時間", "%"),
    "Vmax": ("電壓", "{u}"), "Vmin": ("電壓", "{u}"), "Vp-p": ("電壓", "{u}"),
    "Vtop": ("電壓", "{u}"), "Vbase": ("電壓", "{u}"), "Vamp": ("電壓", "{u}"),
    "Vavg": ("電壓", "{u}"), "Vrms(DC)": ("電壓", "{u}"), "Vrms(AC)": ("電壓", "{u}"),
    "過衝": ("電壓", "%"), "前衝": ("電壓", "%"),
}
# 雙來源獨立列出，避免 Qt 固定分類迭代出現無法使用的項目。
DUAL = {"延遲": ("雙來源", "s"), "相位": ("雙來源", "°"), "電壓比": ("雙來源", "dB")}
# 支援整段／整數週期模式的量測。
INTERVAL = {"Vavg", "Vrms(DC)", "Vrms(AC)"}
# 需要選邊緣方向的量測；上升／下降時間、斜率與正／負寬度已由名稱指定方向。
SLOPED = {"週期", "頻率", "工作週期", "-工作週期", "過衝", "前衝"}
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
    if vmax - vmin <= _BINS * math.ulp(max(abs(vmin), abs(vmax))):
        return vmin, vmax, vmin, vmin
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
    if top <= base:
        top = base
    return vmin, vmax, top, base


def unit_of(name: str, source_unit: str) -> str:
    return (DUAL if name in DUAL else MEASUREMENTS)[name][1].replace("{u}", source_unit)


def _sample_index(t: np.ndarray, endpoint: float) -> int:
    """相對時間端點僅在 8 ULP 內吸附樣本，回傳左閉右開的切片索引。"""
    i = int(np.searchsorted(t, endpoint))
    near = min((j for j in (i - 1, i) if 0 <= j < t.size), key=lambda j: abs(t[j] - endpoint))
    return near if abs(t[near] - endpoint) <= 8 * np.spacing(abs(endpoint)) else i


def _validate_pct(pct: tuple[float, float, float]) -> None:
    try:
        lower, mid, upper = pct
        valid = 0 <= lower <= mid <= upper <= 100 and lower < upper
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ScopeError("THRESHOLDS：百分比須符合 0 ≤ lower ≤ mid ≤ upper ≤ 100，且 lower < upper。")


def measure(name: str, t: np.ndarray, v: np.ndarray, pct: tuple[float, float, float] = (10, 50, 90),
            rising: bool = True, mode: str = "full", ref_time: float = 0.0) -> np.ndarray:
    """回傳該量測在範圍內每個事件的值（整段量測長度 1）；量測不出來丟 ScopeError（訊息即原因）。"""
    if mode not in ("full", "cycles", "cycle"):
        raise ScopeError(f"未知的量測模式：{mode}（可用 full、cycles、cycle）")
    _validate_pct(pct)
    validate(t, v)
    vmin, vmax = float(v.min()), float(v.max())
    if name in ("Vmax", "Vmin", "Vp-p"):
        return np.array([{"Vmax": vmax, "Vmin": vmin, "Vp-p": vmax - vmin}[name]])
    interval = name in INTERVAL
    if not interval or mode in ("cycles", "cycle"):
        _, _, top, base = levels(v)
        if top <= base:
            raise ScopeError("TOP_EQ_BASE：波形沒有振幅（top = base）。")
    if interval and mode in ("cycles", "cycle"):
        # 相對時間避免遠離原點時 ULP 吸附過寬；右端不重複計入。
        et = t - t[0]
        es = edge.edges(et, v, *(base + (top - base) * p / 100 for p in pct))
        if mode == "cycle":
            if not es:
                raise ScopeError("EDGE：範圍內不足一個完整週期")
            e0 = min(es, key=lambda e: (abs(e.t_mid - (ref_time - t[0])), e.t_mid))
            mids = [e.t_mid for e in es if e.rising == e0.rising and e.t_mid >= e0.t_mid][:2]
        else:
            mids = [e.t_mid for e in es if e.rising == rising]
        if len(mids) < 2:
            reason = "EDGE" if mode == "cycle" else "No edges"
            raise ScopeError(f"{reason}：範圍內不足一個完整週期")
        v = v[_sample_index(et, mids[0]):_sample_index(et, mids[-1])]
        if not v.size:
            raise ScopeError("EDGE：週期內沒有取樣點")
    if interval:
        # 均勻次取樣比例手冊未載明，保留所選區間全部樣本。
        # RMS_Voltage：AC RMS 使用同段平均。
        value = float(v.mean()) if name == "Vavg" else (rms_dc(v) if name == "Vrms(DC)" else rms_ac(v))
        return np.array([value])
    single = {"Vmax": vmax, "Vmin": vmin, "Vp-p": vmax - vmin, "Vtop": top, "Vbase": base,
              "Vamp": top - base}
    if name in single:
        if name == "Vamp" and top <= base:
            raise ScopeError("TOP_EQ_BASE：波形沒有振幅（top = base）。")
        return np.array([single[name]])
    amp = top - base
    if amp <= 0:
        raise ScopeError("波形沒有振幅（top = base），找不到邊緣。")
    lo, mid, hi = (base + amp * p / 100 for p in pct)
    es = edge.edges(t, v, lo, mid, hi)
    if name in ("上升時間", "下降時間", "上升斜率", "下降斜率"):
        return edge.transition(es, name.startswith("上升"), lo, hi, name.endswith("斜率"), t)
    if name == "週期":
        return edge.periods(es, rising)
    if name == "頻率":
        periods = edge.periods(es, rising)
        return edge.timed(1 / periods, periods.at)
    if name in ("+寬度", "-寬度"):
        return edge.widths(es, name == "+寬度")
    if name in ("工作週期", "-工作週期"):
        duty = edge.duty(es, rising)
        return edge.timed(100 - duty, duty.at) if name == "-工作週期" else duty
    if name in ("過衝", "前衝"):
        return edge.shoot(t, v, es, rising, top, base, name == "前衝")
    raise ScopeError(f"未知的量測：{name}")


def measure2(name: str, t1: np.ndarray, v1: np.ndarray, t2: np.ndarray, v2: np.ndarray,
             pct: tuple[float, float, float] = (10, 50, 90), rising: bool = True,
             rising2: bool | None = None) -> np.ndarray:
    """3000G 雙來源量測；時間軸須為各自已套 dx 的顯示時間。"""
    _validate_pct(pct)
    for i, (t, v) in enumerate(((t1, v1), (t2, v2)), 1):
        try:
            validate(t, v)
        except ScopeError as exc:
            raise ScopeError(f"來源 {i}：{exc}") from exc
    if name == "電壓比":
        a, b = rms_ac(v1), rms_ac(v2)
        if a == 0 or b == 0:
            raise ScopeError(f"來源 {1 if a == 0 else 2} 的 AC RMS 為 0，無法計算電壓比。")
        return np.array([20 * (np.log10(a) - np.log10(b))])
    if name not in DUAL:
        raise ScopeError(f"未知的雙來源量測：{name}")
    mids = []
    for i, (t, v, up) in enumerate(((t1, v1, rising), (t2, v2, rising if rising2 is None else rising2)), 1):
        try:
            _, _, top, base = levels(v)
        except ScopeError as exc:
            raise ScopeError(f"來源 {i}：{exc}") from exc
        es = edge.edges(t, v, *(base + (top - base) * p / 100 for p in pct)) if top > base else []
        m = np.array([e.t_mid for e in es if e.rising == up])
        if not m.size:
            raise ScopeError(f"來源 {i}：找不到指定方向的邊緣。")
        mids.append(m)
    a, b = mids
    a = a[(a >= max(t1[0], t2[0])) & (a <= min(t1[-1], t2[-1]))]
    if not a.size:
        raise ScopeError("兩來源時間範圍沒有重疊")
    # 每個來源 1 事件只比較來源 2 插入點的左右鄰居；同距取較早者。
    j = np.searchsorted(b, a)
    left, right = np.clip(j - 1, 0, b.size - 1), np.clip(j, 0, b.size - 1)
    delay = b[np.where(abs(b[left] - a) <= abs(b[right] - a), left, right)] - a
    if name == "相位":
        if a.size < 2:
            raise ScopeError("來源 1：找不到完整週期（需要兩個同方向邊緣）。")
        return edge.timed(delay[:-1] / np.diff(a) * 360, a[:-1])
    return edge.timed(delay, a)


def stats(values: np.ndarray, ref: float | None = None, meas_all_edges: bool = True) -> tuple[float, float, float, float, float, float, int]:
    """目前取距參考最近的事件，同距取較早；未給參考／事件時間時沿用首事件。"""
    at = getattr(values, "at", None)
    i = 0
    if ref is not None and at is not None:
        distance = abs(at - ref)
        candidates = np.flatnonzero(distance == distance.min())
        i = candidates[at[candidates].argmin()]
    if not meas_all_edges:
        values = values[i:i + 1]
        i = 0
    lo, hi = float(values.min()), float(values.max())
    return (float(values[i]), float(values.mean()), lo, hi, hi - lo, float(values.std()), len(values))


def measure_all(tasks: list[tuple[str, np.ndarray, np.ndarray, bool]],
                pct: tuple[float, float, float], ref_time: float = 0.0,
                meas_all_edges: bool = True) -> list[tuple | str]:
    """背景執行用：每筆回傳 stats 結果，失敗回傳原因字串（一筆失敗不影響其他筆）。"""
    out: list[tuple | str] = []
    for name, t, v, rising in tasks:
        try:
            try:
                values = measure(name, t, v, pct, rising)
            except ScopeError:
                if meas_all_edges or name not in SLOPED:
                    raise
                values = measure(name, t, v, pct, not rising)
                rising = not rising
            if not meas_all_edges and name in SLOPED:
                try:
                    other = measure(name, t, v, pct, not rising)
                except ScopeError:
                    other = None
                if other is not None:
                    values = edge.timed(np.concatenate((values, other)), np.concatenate((values.at, other.at)))
            bound = getattr(values, "bound", None)
            out.append(f"點數不足，僅得{'下界' if bound == '>' else '上界'} {bound}" if bound else stats(values, ref_time, meas_all_edges))
        except Exception as exc:
            out.append(str(exc))
    return out


def _self_check() -> None:
    from scope_tool.analysis.measure_check import _self_check as check
    check()


if __name__ == "__main__":
    _self_check()
