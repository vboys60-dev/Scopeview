"""固定頻率時脈還原（依 Infiniium 手冊 Clock_Recovery_Constant_Frequency、Clock_Recovery_TIE_Measurements）。
時脈與 NRZ 資料共用同一套：每個中閾值邊緣配一個整數 UI 格號（相鄰邊緣間隔 ÷ UI 四捨五入後累加，
單一邊緣位移造成的錯格不往後傳），再最小平方擬合 UI 與起點 t0，重複到格號不變。
相鄰兩邊緣的位移差超過 0.5 UI（高隨機 jitter）仍可能使格號永久漂移；聯合診斷只標滑格疑慮。
TIE＝邊緣時間 − (t0 + 格號 × UI)，平均為 0。
單邊時脈 UI＝週期；兩邊時脈 UI＝半週期（保留 DCD）；資料一律用兩種邊緣。
不做 PLL／SSC 追蹤：長記錄的 TIE 會含低頻漂移（手冊 dlg_ClockRecoverySetup_Jitter_Considerations）。
# 待真機驗證：與 EZJIT 數值比對。
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from scope_tool.analysis import edge, rate_seed, slip, status as st
from scope_tool.analysis.measure import levels, validate
from scope_tool.contracts import ScopeError

KINDS = ("時脈", "NRZ 資料")
EDGES = ("上升", "下降", "兩者")
MODES = ("全自動", "半自動", "手動")
_MAX_ITER = 10
# 待校準的產品門檻，非物理界線。
_COLLISION_MIN, _COLLISION_FRACTION = 3, 0.001
_LOW_EDGE_COUNT = 1000
_HALF_UI_RADIUS, _HALF_LIMITED, _HALF_INVALID = 0.1, 0.01, 0.05


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
    status: str = st.VALID
    reasons: tuple[str, ...] = ()
    diagnostics: dict | None = None


def _units(times: np.ndarray, ui: float, odd: bool) -> np.ndarray:
    """四捨五入前的間隔。odd（兩邊時脈）：相鄰邊緣極性相反，跨度必為奇數 UI，回傳 (間隔/UI − 1)/2。"""
    x = np.diff(times) / ui
    return (x - 1) / 2 if odd else x


def _grid(times: np.ndarray, ui: float, odd: bool) -> np.ndarray:
    k = np.rint(_units(times, ui, odd))
    span = (2 * k + 1 if odd else k).astype(np.int64)
    n = np.concatenate(([0], np.cumsum(span)))
    if not np.any(n != n[0]):
        raise ScopeError("格號全部相同，無法還原時脈：標稱速率可能遠低於實際（UI 設太大），請提高速率或改用全自動。")
    return n


def _seed(spec: ClockSpec, es: list[edge.Edge], times: np.ndarray, step: int, diagnostics: dict) -> float:
    if spec.mode != "全自動":
        if spec.rate <= 0:
            raise ScopeError("標稱速率必須大於 0。")
        return 1 / spec.rate / (step if spec.kind == "時脈" else 1)
    if spec.kind != "時脈":
        ui, info = rate_seed.seed_ui(times)
        diagnostics.update(info)
        return ui
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
    diagnostics = {}
    ui = _seed(spec, es, times, step, diagnostics)
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
    result = _assess(times, n, ui, spec)
    result.diagnostics.update(diagnostics)
    return Clock(spec, es, times, rising, n, ui, t0, tie, step, mid,
                 _warnings(t, times, n, ui, tie, spec, result.diagnostics["half_ui_fraction"]), *result)


def _assess(times: np.ndarray, n: np.ndarray, ui: float, spec: ClockSpec) -> st.Result:
    span = np.diff(n)
    c = int(np.sum(span <= 0))
    threshold = max(_COLLISION_MIN, int(np.ceil(_COLLISION_FRACTION * span.size)))
    positive = span[span > 0]
    g = int(np.gcd.reduce(positive)) if positive.size else 0
    odd = spec.kind == "時脈" and spec.edges == "兩者"
    units = _units(times, ui, odd)
    half = float(np.mean(np.abs(units % 1 - 0.5) <= _HALF_UI_RADIUS))
    result = st.Result(st.VALID, (), {"grid_collisions": c, "collision_threshold": threshold, "g": g,
                                   "half_ui_fraction": half, "half_ui_radius": _HALF_UI_RADIUS,
                                   "edge_count": int(times.size), "low_edge_threshold": _LOW_EDGE_COUNT})
    for condition, state, reason in (
        (c > 0, st.INVALID if c >= threshold else st.LIMITED,
         st.GRID_COLLISION_MANY if c >= threshold else st.GRID_COLLISION),
        (g > 1, st.LIMITED, st.RATE_AMBIGUOUS),
        (spec.kind != "時脈" and spec.mode == "全自動", st.LIMITED, st.RATE_INFERRED),
        (half >= _HALF_LIMITED, st.INVALID if half > _HALF_INVALID else st.LIMITED, st.HALF_UI_AMBIGUOUS),
        (times.size < _LOW_EDGE_COUNT, st.LIMITED, st.LOW_EDGE_COUNT),
    ):
        if condition:
            result = st.worst(result, st.Result(state, (reason,), {}))
    return st.worst(result, slip.assess(n, (times - times[0]) / ui - n, units))


def _warnings(t: np.ndarray, times: np.ndarray, n: np.ndarray, ui: float, tie: np.ndarray,
              spec: ClockSpec, half: float) -> list[str]:
    out = []
    span = np.diff(n)
    conflicts = int(np.sum(span <= 0))
    if conflicts:
        out.append(f"{conflicts} 處格號衝突（相鄰邊緣被配到同一格）：可能有大幅位移、標稱速率偏低（UI 過大）或配對歧義")
    if half >= _HALF_LIMITED:
        out.append(f"{half:.0%} 的邊緣間隔落在半個 UI 附近：速率可能不對、有 SSC、jitter 或 DCD 很大")
    if spec.kind == "時脈" and np.any(span > 1):
        out.append(f"缺邊 {int(np.sum(span > 1))} 處（N 週期與寬度差不跨缺口）")
    if spec.kind != "時脈":
        positive = span[span > 0]
        g = int(np.gcd.reduce(positive)) if positive.size else 0
        if g > 1:
            out.append(f"所有間隔都是 {g} 的整數倍（{g} UI）：還原速率可能是實際的 {g} 倍")
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
        assert ck.status == (st.LIMITED if mode == "全自動" else st.VALID)
        assert (st.RATE_INFERRED in ck.reasons) == (mode == "全自動")
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
    # 兩邊時脈：工作週期偏離 50% 仍無奇數格配對歧義。
    for high in (4, 5, 6, 14, 15, 16):
        td, vd = nrz(np.tile(np.r_[np.ones(high), np.zeros(20 - high)], 600), ui, 10)
        for mode in MODES:
            ck = recover(td, vd, (10, 50, 90), ClockSpec(edges="兩者", mode=mode, rate=0.05e9))
            assert ck.status == st.VALID and ck.reasons == (), (high, mode, ck)
            assert abs(rate(ck) - 0.05e9) < 1 and set(np.diff(ck.n)) == {1} and not any("缺邊" in w for w in ck.warnings)
    # 連續碼 2／3／4 UI：手動與半自動提示正確倍數，全自動不另提示。
    for g in (2, 3, 4):
        tp, vp = nrz(np.repeat(clk[:2000], g), ui, 10)
        for mode in MODES:
            ck = recover(tp, vp, (10, 50, 90), ClockSpec("NRZ 資料", mode=mode, rate=1e9))
            assert (st.RATE_AMBIGUOUS in ck.reasons) == (mode != "全自動")
            assert ck.status == st.LIMITED and ck.diagnostics["g"] == (1 if mode == "全自動" else g)
            ambiguity = [w for w in ck.warnings if "所有間隔" in w]
            assert ambiguity == ([] if mode == "全自動" else
                                 [f"所有間隔都是 {g} 的整數倍（{g} UI）：還原速率可能是實際的 {g} 倍"])
    # 單緣晚 0.6 UI：只錯該格，下一個跨度為 0；舊夾值會讓後半段全錯。
    mids = np.arange(1, 4000) * ui
    mids[1999] += 0.6 * ui
    knots = np.column_stack((mids - 0.05 * ui, mids + 0.05 * ui)).ravel()
    volts = np.column_stack((np.arange(3999) % 2, 1 - np.arange(3999) % 2)).ravel()
    ts = np.arange(4000 * 20) * ui / 20
    vs = np.interp(ts, knots, volts)
    ck = recover(ts, vs, (10, 50, 90), ClockSpec("NRZ 資料", mode="半自動", rate=1e9))
    expected = np.arange(3999)
    assert np.count_nonzero(ck.n != expected) == 1
    assert np.sum(np.diff(ck.n) <= 0) == 1 and any("1 處格號衝突（相鄰邊緣被配到同一格）" in w for w in ck.warnings)
    assert ck.tie.std() < 10e-12
    assert ck.status == st.LIMITED and ck.reasons == (st.GRID_COLLISION,)
    mids = np.arange(1, 4000) * ui
    mids[200::500] += 0.6 * ui
    knots = np.column_stack((mids - 0.05 * ui, mids + 0.05 * ui)).ravel()
    many = recover(ts, np.interp(ts, knots, volts), (10, 50, 90), ck.spec)
    assert many.status == st.INVALID and many.reasons == (st.GRID_COLLISION_MANY,)
    for size, collisions, state in ((1001, 2, st.LIMITED), (1001, 3, st.INVALID),
                                    (2501, 2, st.LIMITED), (2501, 3, st.INVALID),
                                    (2502, 2, st.LIMITED), (2502, 3, st.INVALID),
                                    (3001, 3, st.INVALID), (3002, 3, st.LIMITED),
                                    (3002, 4, st.INVALID), (5001, 4, st.LIMITED), (5001, 5, st.INVALID)):
        grid = np.arange(size); grid[1:1 + collisions] = 0
        check = _assess(np.arange(size) * ui, grid, ui, ck.spec)
        assert check.status == state
        assert check.diagnostics["collision_threshold"] == (4 if size == 3002 else 5 if size == 5001 else 3)
    crowded = np.arange(2000); crowded[100:110] = crowded[99]
    check = _assess(np.arange(2000) * ui, crowded, ui, ck.spec)
    assert check.status == st.INVALID and st.GRID_COLLISION_MANY in check.reasons
    for count, state in ((0, st.VALID), (9, st.VALID), (10, st.LIMITED), (50, st.LIMITED), (51, st.INVALID)):
        intervals = np.ones(1000); intervals[:count] = 1.5
        times = np.r_[0, np.cumsum(intervals)] * ui
        check = _assess(times, np.arange(1001), ui, ck.spec)
        assert check.status == state and (st.HALF_UI_AMBIGUOUS in check.reasons) == (count >= 10)
        messages = _warnings(np.arange(20000) * ui / 10, times, np.arange(1001), ui,
                             np.zeros(1001), ck.spec, check.diagnostics["half_ui_fraction"])
        assert any("半個 UI" in message for message in messages) == (count >= 10)
    for size in (999, 1000):
        check = _assess(np.arange(size) * ui, np.arange(size), ui, ck.spec)
        assert check.status == (st.LIMITED if size == 999 else st.VALID)
        assert check.reasons == ((st.LOW_EDGE_COUNT,) if size == 999 else ())
    # 全部跨度為 0：手動與迭代擬合都要報錯，不可回傳 NaN。
    ta, va = nrz(clk, ui, 10)
    for mode in ("手動", "半自動"):
        try:
            recover(ta, va, (10, 50, 90), ClockSpec("NRZ 資料", mode=mode, rate=0.4e9))
            raise AssertionError("格號相同應該丟出 ScopeError")
        except ScopeError as exc:
            assert "標稱速率可能遠低於實際（UI 設太大），請提高速率或改用全自動" in str(exc)
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
