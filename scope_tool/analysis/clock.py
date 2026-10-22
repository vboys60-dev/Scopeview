"""固定頻率時脈還原（依 Infiniium 手冊 Clock_Recovery_Constant_Frequency、Clock_Recovery_TIE_Measurements）。

時脈與 NRZ 資料共用同一套：每個中閾值邊緣配一個整數 UI 格號（相鄰邊緣間隔 ÷ UI 四捨五入後累加，
錯一格不會往後傳），再最小平方擬合 UI 與起點 t0，重複到格號不變。TIE＝邊緣時間 − (t0 + 格號 × UI)，平均為 0。
單邊時脈 UI＝週期；兩邊時脈 UI＝半週期（保留 DCD）；資料一律用兩種邊緣。
不做 PLL／SSC 追蹤：長記錄的 TIE 會含低頻漂移（手冊 dlg_ClockRecoverySetup_Jitter_Considerations）。
# 待真機驗證：與 EZJIT 數值比對。
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from scope_tool.analysis import edge
from scope_tool.analysis.measure import levels, validate
from scope_tool.contracts import ScopeError

KINDS = ("時脈", "NRZ 資料")
EDGES = ("上升", "下降", "兩者")
MODES = ("全自動", "半自動", "手動")
_MAX_ITER = 10


class ClockSpec(NamedTuple):
    kind: str = "時脈"
    edges: str = "上升"   # 資料型忽略，一律兩者
    mode: str = "全自動"  # 全自動＝自己找速率；半自動＝標稱速率當起點再擬合；手動＝UI 固定只估相位
    rate: float = 1e6     # 標稱速率：時脈＝頻率 Hz，資料＝位元率 b/s
    n: int = 1            # N 週期／Period-Period 的 N（1–20）


class Clock(NamedTuple):
    spec: ClockSpec
    es: list[edge.Edge]   # 全部邊緣（寬度差用）
    times: np.ndarray     # 參與還原的邊緣中閾值時間
    rising: np.ndarray
    n: np.ndarray         # 各邊緣的 UI 格號（從 0 起）
    ui: float
    t0: float
    tie: np.ndarray
    step: int             # 一個週期幾個 UI：兩邊時脈 2，其他 1
    mid: float            # 中閾值電壓
    warnings: list[str]


def _units(times: np.ndarray, ui: float, odd: bool) -> np.ndarray:
    """四捨五入前的間隔。odd（兩邊時脈）：相鄰邊緣極性相反，跨度必為奇數 UI，回傳 (間隔/UI − 1)/2。"""
    x = np.diff(times) / ui
    return (x - 1) / 2 if odd else x


def _grid(times: np.ndarray, ui: float, odd: bool) -> np.ndarray:
    k = np.rint(_units(times, ui, odd))
    span = np.maximum(2 * k + 1 if odd else k, 1).astype(np.int64)
    return np.concatenate(([0], np.cumsum(span)))


def _seed(spec: ClockSpec, es: list[edge.Edge], times: np.ndarray, step: int) -> float:
    if spec.mode != "全自動":
        if spec.rate <= 0:
            raise ScopeError("標稱速率必須大於 0。")
        return 1 / spec.rate / (step if spec.kind == "時脈" else 1)
    if spec.kind != "時脈":
        return float(np.diff(times).min())  # 手冊：最窄的資料脈衝當作 1 UI
    for rising in (True, False):  # 同方向邊緣的週期中位數，不受工作週期影響
        same = [e.t_mid for e in es if e.rising == rising]
        if len(same) >= 2:
            return float(np.median(np.diff(same))) / step
    raise ScopeError("範圍內沒有完整週期，無法還原時脈。")


def recover(t: np.ndarray, v: np.ndarray, pct: tuple[float, float, float], spec: ClockSpec) -> Clock:
    validate(t, v)
    _, _, top, base = levels(v)
    amp = top - base
    if amp <= 0:
        raise ScopeError("波形沒有振幅（top = base），找不到邊緣。")
    lo, mid, hi = (base + amp * p / 100 for p in pct)
    es = edge.edges(t, v, lo, mid, hi)
    both = spec.kind != "時脈" or spec.edges == "兩者"
    used = [e for e in es if both or e.rising == (spec.edges == "上升")]
    if len(used) < 3:
        raise ScopeError("範圍內邊緣少於 3 個，無法還原時脈。")
    times = np.array([e.t_mid for e in used])
    rising = np.array([e.rising for e in used])
    step = 2 if spec.kind == "時脈" and both else 1
    ui = _seed(spec, es, times, step)
    if not ui > 0:
        raise ScopeError("找不到有效的 UI（邊緣時間重疊）。")
    odd = step == 2
    rel = times - times[0]  # 減掉起點，避免大時間值的相減誤差
    n = _grid(times, ui, odd)
    for _ in range(_MAX_ITER):
        if spec.mode == "手動":
            break
        nc = n - n.mean()
        ui = float(nc @ (rel - rel.mean()) / (nc @ nc))
        new = _grid(times, ui, odd)
        if np.array_equal(new, n):
            break
        n = new
    else:
        raise ScopeError(f"時脈還原 {_MAX_ITER} 次仍未收斂：速率可能不對或訊號不是固定頻率。")
    t0 = times[0] + float(np.mean(rel - n * ui))
    tie = times - (t0 + n * ui)
    return Clock(spec, es, times, rising, n, ui, t0, tie, step, mid, _warnings(t, times, n, ui, tie, spec, odd))


def _warnings(t: np.ndarray, times: np.ndarray, n: np.ndarray, ui: float, tie: np.ndarray,
              spec: ClockSpec, odd: bool) -> list[str]:
    out = []
    span = np.diff(n)
    half = np.mean(np.abs(_units(times, ui, odd) % 1 - 0.5) < 0.15)
    if half > 0.01:
        out.append(f"{half:.0%} 的邊緣間隔落在半個 UI 附近：速率可能不對、有 SSC、jitter 或 DCD 很大")
    if spec.kind == "時脈" and np.any(span > 1):
        out.append(f"缺邊 {int(np.sum(span > 1))} 處（N 週期與寬度差不跨缺口）")
    if spec.kind != "時脈" and span.size and np.all(span % 2 == 0):
        out.append("所有間隔都是偶數 UI：還原速率可能是實際的 2 倍")
    if np.ptp(tie) > 0.5 * ui:
        out.append("TIE 峰對峰超過 0.5 UI：可能有 SSC、低頻漂移或還原錯誤")
    spu = ui / float(np.median(np.diff(t)))
    if spu < 4:
        out.append(f"每 UI 只有 {spu:.1f} 個取樣點（建議 ≥ 4）")
    if times.size < 1000:
        out.append(f"只有 {times.size} 個邊緣，統計不穩（建議 ≥ 1000）")
    return out


def rate(ck: Clock) -> float:
    """還原速率：時脈＝頻率，資料＝位元率。"""
    return 1 / (ck.ui * ck.step)


def nrz(bits: np.ndarray, ui: float, spu: int, rise: int = 2, jitter: np.ndarray | None = None,
        start: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """自我檢查用：每 UI spu 點、線性邊緣 rise 點的 0/1 V NRZ；jitter 為各 UI 邊界的時間偏移。"""
    t = start + np.arange(len(bits) * spu) * ui / spu
    edges_t = np.arange(len(bits) + 1) * ui + start + (0 if jitter is None else jitter[:len(bits) + 1])
    before, after = np.r_[bits[0], bits].astype(float), np.r_[bits, bits[-1]].astype(float)
    k = np.clip(np.rint((t - start) / ui).astype(np.int64), 0, len(bits))  # 最近的 UI 邊界
    w = rise * ui / spu
    frac = np.clip((t - edges_t[k] + w / 2) / w, 0, 1)
    return t, before[k] + (after[k] - before[k]) * frac


def _self_check() -> None:
    rng = np.random.default_rng(1)
    ui = 1e-9
    bits = rng.integers(0, 2, 4000)
    bits[:4] = (0, 1, 0, 1)
    t, v = nrz(bits, ui, 20)
    for mode in MODES:
        ck = recover(t, v, (10, 50, 90), ClockSpec("NRZ 資料", mode=mode, rate=1e9))
        assert abs(ck.ui - ui) < 1e-15 and np.max(np.abs(ck.tie)) < 1e-14, mode
        assert abs(rate(ck) - 1e9) < 1 and not ck.warnings, (mode, ck.warnings)
    # 半自動：標稱速率偏 2 % 仍收斂；手動：UI 固定不變，偏差出現在 TIE 斜率
    assert abs(recover(t, v, (10, 50, 90), ClockSpec("NRZ 資料", mode="半自動", rate=1.02e9)).ui - ui) < 1e-15
    assert recover(t, v, (10, 50, 90), ClockSpec("NRZ 資料", mode="手動", rate=1.001e9)).ui == 1 / 1.001e9
    # 時脈：漏一個邊緣跨度為 2，且發出缺邊警告
    clk = np.tile([0, 1], 3000)
    tc, vc = nrz(clk, ui, 10)
    hole = (tc > 2000.95 * ui) & (tc < 2002.5 * ui)  # 拿掉一個完整脈衝
    vc[hole] = 0
    ck = recover(tc, vc, (10, 50, 90), ClockSpec())
    assert abs(ck.ui - 2 * ui) < 1e-15 and int(np.max(np.diff(ck.n))) == 2 and "缺邊 1 處" in ck.warnings[0]
    both = recover(tc, vc, (10, 50, 90), ClockSpec(edges="兩者"))
    assert both.step == 2 and abs(both.ui - ui) < 1e-15 and abs(rate(both) - 0.5e9) < 1
    # 兩邊時脈、20% 工作週期：跨度限奇數，不會還原成 1.5 倍頻率
    t20, v20 = nrz(np.tile([1, 0, 0, 0, 0], 600), ui, 10)
    for mode in ("全自動", "手動"):
        ck = recover(t20, v20, (10, 50, 90), ClockSpec(edges="兩者", mode=mode, rate=0.2e9))
        assert abs(rate(ck) - 0.2e9) < 1 and set(np.diff(ck.n)) == {1} and not any("缺邊" in w for w in ck.warnings)
    # 全部間隔都是 2 UI 的資料（其實是時脈）：提示速率歧義
    pair = np.repeat(clk[:2000], 2)
    tp, vp = nrz(pair, ui, 10)
    assert any("2 倍" in w for w in recover(tp, vp, (10, 50, 90), ClockSpec("NRZ 資料", mode="半自動", rate=1e9))
               .warnings)
    # 平移起點：TIE 平均為 0；加入正弦 jitter 後 TIE 還原得出
    jit = 20e-12 * np.sin(np.arange(4001) * 2 * np.pi / 97)
    tj, vj = nrz(bits, ui, 20, jitter=jit, start=3.3e-3)
    ck = recover(tj, vj, (10, 50, 90), ClockSpec("NRZ 資料"))
    assert abs(ck.tie.mean()) < 1e-16 and abs(ck.tie.std() - jit.std()) < 1.5e-12
    try:
        recover(t[:40], v[:40], (10, 50, 90), ClockSpec())
        raise AssertionError("邊緣太少應該丟出 ScopeError")
    except ScopeError:
        pass
    print("analysis.clock self-check OK")


if __name__ == "__main__":
    _self_check()
