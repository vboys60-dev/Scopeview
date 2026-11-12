"""離線量測自檢，執行時才由 measure 載入。"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis import edge
from scope_tool.analysis.measure import (MEASUREMENTS, THRESHOLDS, levels,
                                         measure, measure_all, stats, uniform_dt, unit_of)
from scope_tool.contracts import ScopeError


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
    # 2.5 週期：整段含尾端半週期，整數週期僅取首末同向緣之間。
    ct = np.arange(250, dtype=float) * 1e-9
    cv = np.tile(np.r_[0., np.ones(50), np.zeros(49)], 3)[:250]
    helpers = {"Vavg": np.mean, "Vrms(DC)": lambda x: np.sqrt(np.mean(x*x)), "Vrms(AC)": np.std}
    for name, helper in helpers.items():
        assert np.isclose(measure(name, ct, cv)[0], helper(cv))
        assert np.isclose(measure(name, ct, cv, mode="full")[0], helper(cv))
        for rising, start, stop in ((True, 1, 201), (False, 51, 151)):
            assert np.isclose(measure(name, ct, cv, rising=rising, mode="cycles")[0], helper(cv[start:stop]))
        for times, signal, reason in ((ct[:100], cv[:100], "No edges：範圍內不足一個完整週期"),
                                      (ct, np.ones_like(cv), "TOP_EQ_BASE：波形沒有振幅（top = base）。")):
            try:
                measure(name, times, signal, mode="cycles")
                raise AssertionError("不足一週期不可退回整段")
            except ScopeError as exc:
                assert str(exc) == reason
    assert measure("Vavg", ct, cv, mode="cycles")[0] == 0.5
    assert measure("Vavg", ct, cv)[0] == 149 / 250
    # 相位、中閾、方向與時間平移：以首末同向緣的獨立樣本切片驗證。
    for pct in THRESHOLDS.values():
        for phase in (0., 0.1, 0.5, 0.999999):
            signal = np.interp((np.arange(t.size) - phase) % 1000,
                               [0, 10, 255, 265, 1000], [0, 2, 2, 0, 0])
            signal += np.repeat(np.arange(5) * 0.02, 1000)
            _, _, top, base = levels(signal)
            for rising in (True, False):
                # 每點斜率 ±0.2 V；第 k 週期偏移 0.02k V，中閾由平台推算。
                mid = (top + base) / 2
                crossing = (mid - np.array([0., 0.08])) / 0.2
                bounds = phase + np.array([0, 4000]) + (crossing if rising else 265 - crossing)
                bounds = np.where(abs(bounds - np.rint(bounds)) < 1e-10, np.rint(bounds), bounds)
                start, stop = np.ceil(bounds).astype(int)
                expected = signal[start:stop].mean()
                for offset in (0., -5e-3, 123.):
                    assert abs(measure("Vavg", t+offset, signal, pct, rising, "cycles")[0] - expected) < 1e-12
    # 遠端樣本不可放寬局部 ULP 吸附；首末上升交越落在索引 5～6、4004～4005。
    pt = np.arange(5000) * 1e-12
    pv = np.interp((np.arange(5000) + 0.1) % 1000,
                   [0, 10, 250, 270, 1000], [0, 2, 2, 0, 0]) + np.repeat(np.arange(5) * 0.02, 1000)
    expected = pv[6:4005].mean()
    for last in (4.999e-9, 100., 1000.):
        pt[-1] = last
        assert abs(measure("Vavg", pt, pv, mode="cycles")[0] - expected) < 1e-12
    # 1.6 ps 取樣平移 1000 s 後仍採相同樣本，不以絕對時間 ULP 吸附。
    tiny_t = np.arange(5000) * 1.6e-12
    for offset in (0., 1000.):
        assert abs(measure("Vavg", tiny_t + offset, pv, mode="cycles")[0] - expected) < 1e-12
    assert measure("Vavg", t, np.full_like(t, 3))[0] == 3
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
            for name, expected, tol in (("週期", 1e-3, 1e-12), ("頻率", 1000, 1e-6), ("工作週期", 25, 1e-8), ("-工作週期", 75, 1e-8)):
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
    # 邊緣不足四點：時間上界／上升斜率下界；下降斜率真值更負。
    for signal in (np.array([0., 1.]), np.array([0., 0.5, 1.])):
        for name, samples in (("上升時間", signal), ("下降時間", 1 - signal),
                              ("上升斜率", signal), ("下降斜率", 1 - signal)):
            got = measure(name, t[:len(samples)], samples)
            slope = name.endswith("斜率")
            assert isinstance(got, np.ndarray) and got.bound == (">" if slope and name.startswith("上升") else "<")
            assert got[:1].bound is None
            reason = measure_all([(name, t[:len(samples)], samples, True)], (10, 50, 90))[0]
            assert reason == f"點數不足，僅得{'下界' if got.bound == '>' else '上界'} {got.bound}"
            expected = (len(samples)-1)*dt
            if slope:
                expected = (0.8 if name.startswith("上升") else -0.8) / expected
            assert np.isclose(got[0], expected)
        # 重複短邊緣仍能量週期；兩點／三點案例的週期分別是 2／4 µs。
        samples = np.tile(np.r_[signal, signal[-2:0:-1]], 3)
        for direction in (True, False):
            assert np.allclose(measure("週期", t[:len(samples)], samples, rising=direction),
                               2 * (len(signal) - 1) * dt, rtol=0, atol=1e-12)
    # 混合品質只採可信緣；沒有完整同方向緣仍失敗。
    mt = np.arange(11, dtype=float)
    mv = np.array([0., 1., 1., 0., 0., 0.25, 0.5, 0.75, 1., 1., 0.])
    mixed = measure("上升時間", mt, mv)
    assert not getattr(mixed, "bound", None) and len(mixed) == 1 and np.isclose(mixed[0], 3.2)
    try:
        measure("上升時間", np.arange(4, dtype=float), np.array([1., 1., 0., 0.]))
    except ScopeError:
        pass
    else:
        raise AssertionError("不完整邊緣應失敗")
    fast_t = np.arange(4000) * 2.5e-9
    fast_v = np.interp(np.arange(4000) % 40, [0, 1.3, 20, 21.3, 40], [0, 1, 1, 0, 0])
    fast = measure("上升時間", fast_t, fast_v)
    assert fast.bound == "<" and np.allclose(fast, 5e-9, rtol=0, atol=1e-20)
    print(f"10 MHz / 2.5 ns synthetic: {fast.bound} {fast[0]*1e9:g} ns")
    assert stats(np.array([3.0, 1.0, 2.0])) == (3.0, 2.0, 1.0, 3.0, 2.0, float(np.std([3, 1, 2])), 3)
    flat = np.ones_like(t)
    assert measure("Vp-p", t, flat)[0] == 0
    res = measure_all([("頻率", t, flat, True), ("Vmax", t, v, True)], (10, 50, 90))
    assert isinstance(res[0], str) and "振幅" in res[0] and res[1][0] == 2
    _new_checks()
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
    from scope_tool.analysis.measure_current_check import _self_check as current_check
    current_check()
    _dual_check()
    _other_regression()
    _rms_public_check()
    print("analysis.measure self-check OK")


def _other_regression() -> None:
    from unittest.mock import patch
    from scope_tool.analysis import measure as module

    def old_dc(v: np.ndarray) -> float:
        return float(np.sqrt(np.mean(v ** 2)))

    def old_ac(v: np.ndarray) -> float:
        return float(np.sqrt(np.mean((v - v.mean()) ** 2)))

    def outcomes(t: np.ndarray, v: np.ndarray) -> list:
        out = []
        for name in MEASUREMENTS:
            if name.startswith("Vrms"):
                continue
            try:
                out.append(module.measure(name, t, v).view(np.uint64).tolist())
            except ScopeError as exc:
                out.append((type(exc), str(exc)))
        return out

    rng = np.random.default_rng(20261024)
    for i in range(1000):
        n, scale = int(rng.integers(2, 10001)), 10.0 ** rng.uniform(-6, 6)
        t = np.arange(n, dtype=float)
        x = t / n
        signals = (np.full(n, -scale), scale * np.sin(2 * np.pi * x * 7),
                   scale * np.where(x % 0.1 < 0.025, 1., -0.5), scale * (2 + rng.normal(size=n)))
        v = signals[i % 4]
        got = outcomes(t, v)
        with patch.object(module, "rms_dc", old_dc), patch.object(module, "rms_ac", old_ac):
            assert got == outcomes(t, v), i
    print("RMS other measurements: 1000 groups, uint64 outputs/exceptions unchanged")


def _rms_public_check() -> None:
    # 前置直方圖失敗如實列出；不可用 helper 通過替代公開入口結果。
    from scope_tool.analysis.rms import rms_ac, rms_dc

    for name, helper in (("Vrms(DC)", rms_dc), ("Vrms(AC)", rms_ac)):
        for a in (1e200, 1e-200, np.finfo(np.float64).max):
            for label, v in (("constant", np.array([a, a])), ("bipolar", np.array([-a, a]))):
                try:
                    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                        got = measure(name, np.arange(v.size, dtype=float), v)[0]
                except (ValueError, IndexError, OverflowError) as exc:
                    # 僅 finfo.max 雙極被前置直方圖擋下屬已知限制，其餘失敗一律算錯。
                    assert label == "bipolar" and a == np.finfo(np.float64).max and "Too many bins" in str(exc), (name, label, a, exc)
                    print(f"RMS public {name} {label} {a:g}: FAILED {type(exc).__name__}: {exc}")
                else:
                    assert np.float64(got).view(np.uint64) == np.float64(helper(v)).view(np.uint64)
                    print(f"RMS public {name} {label} {a:g}: OK {got:.17g}")


def _dual_check() -> None:
    from time import perf_counter
    from scope_tool.analysis.measure import DUAL, measure2

    t = np.arange(4000, dtype=float) / 1000
    v = np.tile(np.r_[np.zeros(100), np.ones(100)], 20)
    for shift in (0.05, -0.05):
        delay = measure2("延遲", t, v, t + shift, v)
        phase = measure2("相位", t, v, t + shift, v)
        assert len(delay) == 20 and len(phase) == 19
        assert np.allclose(delay, shift, rtol=0, atol=1e-14)
        assert np.allclose(phase, shift / .2 * 360, rtol=0, atol=1e-10)
    # 反向邊緣、缺省方向與不包裹（來源 2 僅一個較晚的事件）。
    assert np.allclose(measure2("延遲", t, v, t + .05, 1-v, rising2=False), .05)
    assert np.array_equal(measure2("延遲", t, v, t, v, rising=False),
                          measure2("延遲", t, v, t, v, rising=False, rising2=False))
    assert measure2("相位", t, v, t, np.r_[np.zeros(3500), np.ones(500)])[0] > 360
    # 不等長範圍只統計交集內事件；首尾範圍外事件不能進入配對。
    for name, count, expected in (("延遲", 5, .05), ("相位", 4, 90)):
        got = measure2(name, t, v, t[1000:2000] + .05, v[1000:2000])
        assert got.size == count and np.allclose(got, expected)
        try:
            measure2(name, t, v, t + 10, v)
            raise AssertionError("完全不重疊應失敗")
        except ScopeError as exc:
            assert str(exc) == "兩來源時間範圍沒有重疊"
    for offset in (0, 7):
        ratio = measure2("電壓比", t, v*2+offset, t, v-13)
        assert ratio.size == 1 and np.isclose(ratio[0], 6.020599913279624)
    for name, a, b, reason in (("延遲", v, np.ones_like(v), "來源 2"),
                               ("延遲", np.ones_like(v), v, "來源 1"),
                               ("電壓比", v, np.ones_like(v), "AC RMS 為 0"),
                               ("電壓比", np.ones_like(v), v, "AC RMS 為 0")):
        try:
            measure2(name, t, a, t, b)
            raise AssertionError("應回報雙來源量測失敗")
        except ScopeError as exc:
            assert reason in str(exc)
    assert not set(DUAL) & set(MEASUREMENTS)  # Qt 分類清單維持單來源。
    # 十萬來源 1 事件，包含共用 edges 與最近配對的公開入口效能。
    big = np.tile(np.array([0., 1., 1., 0.]), 100000)
    times = np.arange(big.size, dtype=float) * 1e-6
    start = perf_counter()
    result = measure2("延遲", times, big, times + 1e-7, big)
    elapsed = perf_counter() - start
    assert result.size == 100000 and np.allclose(result, 1e-7, rtol=0, atol=1e-16)
    assert elapsed < 1, elapsed
    print(f"measure2: 100000 events {elapsed:.3f} s; Delay ±0.05 s, Phase ±90°, Ratio 6.0206 dB OK")




def _new_checks() -> None:
    from unittest.mock import patch
    from scope_tool.analysis import measure as module
    from scope_tool.analysis.measure import measure2

    t = np.arange(11, dtype=float)
    v = np.array([0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 0], dtype=float)
    for name, expected in (("Vavg", .2), ("Vrms(DC)", np.sqrt(.2)), ("Vrms(AC)", .4)):
        assert np.isclose(measure(name, t, v, mode="cycle", ref_time=0)[0], expected)
    assert np.isclose(measure("Vavg", t, v, mode="cycles")[0], 2 / 7)
    for mode in ("all_cycles", "ALL_CYCLES", "CYCLE", "unknown"):
        try:
            measure("Vavg", t, v, mode=mode)
            assert False
        except ScopeError as exc:
            assert "未知的量測模式" in str(exc)
    try:
        measure("Vavg", t, v, mode="cycle", ref_time=9.5)
        assert False
    except ScopeError as exc:
        assert "EDGE" in str(exc)
    near = np.array([1., np.nextafter(1., 2.)])
    with patch.object(module.np, "histogram", side_effect=AssertionError("不應呼叫直方圖")):
        assert levels(near)[2] == levels(near)[3]
    for ulps in (9, 255, 256):
        signal = np.array([1., 1. + ulps * np.spacing(1.)])
        assert levels(signal)[2] == levels(signal)[3]
    for name in ("Vtop", "Vbase", "Vamp"):
        try:
            measure(name, t[:2], near)
            assert False
        except ScopeError as exc:
            assert "TOP_EQ_BASE" in str(exc)
    assert measure("Vmax", t[:2], near)[0] == near.max()
    assert measure("Vmin", t[:2], near)[0] == near.min()
    assert measure("Vp-p", t[:2], near)[0] == near[1] - near[0]
    for pct in ((90, 50, 10), (10, 150, 90), (-1, 50, 90), (10, 50, 101)):
        for fn in (lambda: measure("週期", t, v, pct), lambda: measure2("延遲", t, v, t, v, pct)):
            try:
                fn()
                assert False
            except ScopeError as exc:
                assert "THRESHOLDS" in str(exc)
    with patch.object(module, "measure", side_effect=[ValueError("測試例外"), np.array([3.])]):
        result = measure_all([("Vmax", t, v, True)] * 2, (10, 50, 90))
        assert result[0] == "測試例外" and result[1][0] == 3
    events = edge.timed(np.array([1., 2.]), [1., 4.])
    assert stats(events, 1, False) == (1., 1., 1., 1., 0., 0., 1)
    assert stats(events, 1, True)[-1] == 2
    result = measure_all([("週期", t, v, True)], (10, 50, 90), ref_time=2.4, meas_all_edges=False)[0]
    assert result[-1] == 1 and result[0] == 5 and result[1] == 5
    result = measure_all([("週期", t, v, True)], (10, 50, 90), ref_time=6.5, meas_all_edges=False)[0]
    assert result[0] == 3 and result[-1] == 1
    result = measure_all([("週期", t, v, True)], (10, 50, 90), ref_time=1.5)[0]
    assert result[-1] == 2 and result[1] == 3.5


if __name__ == "__main__":
    _self_check()
