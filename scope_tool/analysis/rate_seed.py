"""資料型全自動 UI 種子：正間隔對數直方圖的第一個顯著峰；不取最窄脈衝。"""
from __future__ import annotations

import warnings

import numpy as np

from scope_tool.contracts import ScopeError

# 待校準的產品常數；對數 bin 約為 8% 相對寬度，峰簇門檻為最大平滑計數的 8%。
_MIN_INTERVALS, _LOG_WIDTH, _PEAK_FRACTION = 16, 0.08, 0.08
_OUTLIER_RATIO, _OUTLIER_FRACTION, _OUTLIER_COUNT = 0.6, 0.005, 3
# 待校準：峰位比上限避開 exp(0.45) 離散鏈；兩窗計數至少為對方的 60%。
_DCD_RATIO, _DCD_BALANCE = 1.55, 0.6
_CHAIN_WIDTH = 0.08  # 待校準：倍頻併鏈檢查的相對半窗。
_MAX_BINS = 4096  # 待校準：極端動態範圍的記憶體上限。


def seed_ui(times: np.ndarray) -> tuple[float, dict]:
    """忽略非有限／非正間隔；不足 16 個正間隔才退回舊 min 行為。"""
    t = np.asarray(times, dtype=float)
    if t.ndim != 1:
        raise ScopeError("UI 種子需要一維邊緣時間。")
    # 先篩端點，避免 Inf 相減的 RuntimeWarning；不跨過缺失時間重接間隔。
    finite = np.isfinite(t[:-1]) & np.isfinite(t[1:])
    with np.errstate(over='ignore'):
        d = t[1:][finite] - t[:-1][finite]
    d = d[np.isfinite(d) & (d > 0)]
    if not d.size:
        raise ScopeError("找不到有效的 UI（沒有有限正間隔）。")
    method, fraction = "first_local_histogram_peak", 1.0
    if d.size < _MIN_INTERVALS:
        ui, method = float(d.min()), "min_short_record"
        fraction = float(np.mean(d == ui))  # 退回 min 時揭露該間隔占比，不冒稱整組皆屬同峰。
    else:
        logs = np.log(d)
        low, high = float(logs.min()), float(logs.max())
        bins = min(_MAX_BINS, max(1, int(np.ceil((high - low) / _LOG_WIDTH))))
        counts, edges = np.histogram(logs, bins=bins, range=(low, high))
        # 補零保留兩端的峰；每簇所有真正局部極大值皆交給短峰篩選。
        smooth = np.convolve(np.pad(counts, 2), [1, 2, 3, 2, 1], mode='valid')
        active = smooth >= max(1, float(smooth.max()) * _PEAK_FRACTION)
        starts = np.flatnonzero(active & ~np.r_[False, active[:-1]])
        ends = np.flatnonzero(active & ~np.r_[active[1:], False]) + 1
        maxima = _maxima(smooth)
        peaks = [int(p) for a, b in zip(starts, ends) for p in maxima if a <= p < b]
        # 已有序的間隔直接沿用；未排序時只排序一次，峰窗僅保存起訖索引。
        if np.any(d[1:] < d[:-1]):
            d.sort()
        logs = np.log(d)
        windows = []
        for peak in peaks:
            left, right = max(0, peak - 2), min(counts.size, peak + 3)
            windows.append((int(np.searchsorted(logs, edges[left], side='left')),
                            int(np.searchsorted(logs, edges[right], side='right'))))
        centers = [float(np.median(d[a:b])) for a, b in windows]
        pairs = []
        for k, (first, second) in enumerate(zip(windows, windows[1:])):
            ratio = float(np.log(centers[k + 1]) - np.log(centers[k]))
            pairs.append(_dcd_pair(ratio, first[1] - first[0], second[1] - second[0]))
        clusters = []
        for k, (a, b) in enumerate(windows):
            center, count = centers[k], b - a
            if k + 1 < len(windows):
                other = k + 1
                c, e = windows[other]
                harmonic = _harmonic(logs, center, centers[other], count, e - c)
                if pairs[k] and not harmonic:
                    # 各窗中位數取幾何中點；聯集計數扣除重疊，避免占比超過 1。
                    center = float(np.exp((np.log(center) + np.log(centers[other])) / 2))
                    count += e - c - max(0, min(b, e) - max(a, c))
            if count:
                clusters.append((center, count))
        ui, count = _first_peak(clusters, d.size)
        fraction = count / d.size
    return ui, {"seed_method": method, "seed_peak_ui": ui, "seed_peak_fraction": fraction,
                "seed_interval_count": int(d.size), "seed_peak_threshold": _PEAK_FRACTION,
                "seed_log_width": _LOG_WIDTH}


def _harmonic(logs: np.ndarray, m1: float, m2: float, first: int, second: int) -> bool:
    """2 倍頻達 60% 且多於 DCD 預測的 2UI 短脈衝，才排除合併。"""
    support = min(first, second) * _DCD_BALANCE
    lower, upper = np.log1p(-_CHAIN_WIDTH), np.log1p(_CHAIN_WIDTH)

    def count(position: float) -> int:
        return int(np.searchsorted(logs, position + upper, side='left')
                   - np.searchsorted(logs, position + lower, side='right'))

    # 兩位置皆留在 log 域，避免 2*m1 或 (3*m1+m2)/2 溢位。
    first_log = np.log(m1)
    harmonic = count(first_log + np.log(2))
    predicted = np.logaddexp(first_log + np.log(1.5), np.log(m2) - np.log(2))
    return harmonic >= support and harmonic > count(predicted)


def _maxima(smooth: np.ndarray) -> np.ndarray:
    """平台僅在整段高於兩側時取左端；上升肩部 3,5,5,7 不算峰。"""
    starts = np.flatnonzero(np.r_[True, np.diff(smooth) != 0])
    ends = np.r_[starts[1:] - 1, smooth.size - 1]
    return starts[(smooth[starts] > np.r_[-1, smooth[ends[:-1]]])
                  & (smooth[ends] > np.r_[smooth[starts[1:]], -1])]


def _dcd_pair(ratio: float, first: int, second: int) -> bool:
    """相鄰且計數相近的兩峰才合併，避免把 1 UI 與 2 UI 接在一起。"""
    return ratio < np.log(_DCD_RATIO) and min(first, second) >= _DCD_BALANCE * max(first, second)


def _first_peak(clusters: list[tuple[float, int]], size: int) -> tuple[float, int]:
    """連鎖略過孤立極短峰；峰高門檻由直方圖流程先處理。"""
    k = 0
    while (k + 1 < len(clusters) and clusters[k][0] < _OUTLIER_RATIO * clusters[k + 1][0]
           and clusters[k][1] <= max(_OUTLIER_COUNT, _OUTLIER_FRACTION * size)):
        k += 1
    return clusters[k]


def _rule_checks() -> None:
    """固定數值邊界；也供突變檢查使用。"""
    def check(d: np.ndarray, target: float, tolerance: float = 0.02) -> None:
        ui, diag = seed_ui(np.r_[0, np.cumsum(d)])
        assert abs(ui / target - 1) < tolerance, (ui, target)
        assert 0 < diag['seed_peak_fraction'] <= 1
        assert diag['seed_peak_ui'] == ui and diag['seed_interval_count'] == d.size

    # 孤立比值 0.6、計數 3／0.5% 的上下界，以及連鎖跳過均獨立固定。
    for ratio, expected in ((0.5999, 1), (0.6, 0.6), (0.6001, 0.6001)):
        assert _first_peak([(ratio, 3), (1, 100)], 103)[0] == expected
    for count, size, expected in ((3, 100, 1), (4, 100, 0.3), (5, 1000, 1), (6, 1000, 0.3)):
        assert _first_peak([(0.3, count), (1, size - count)], size)[0] == expected
    assert _first_peak([(0.1, 3), (0.3, 3), (1, 100)], 106)[0] == 1
    # 恰 16 個間隔須用峰；15 個才用 min。兩端 bin 必須包含原始最大值。
    check(np.r_[0.25, np.ones(15)], 1)
    ui, diag = seed_ui(np.arange(17.0))
    assert ui == 1 and diag['seed_method'] == 'first_local_histogram_peak'
    # 7.9%、8%、8.1% 的孤立峰；門檻為含等號的平滑峰高比較。
    for count, target in ((79, 2), (80, 1), (81, 1)):
        check(np.r_[np.ones(count), np.full(1000, 2.0)], target)
    _, diag = seed_ui(np.r_[0, np.cumsum(np.r_[np.ones(80), np.full(1000, 2.0)])])
    assert abs(diag['seed_peak_fraction'] - 80 / 1080) < 1e-12
    # 右端恰位於直方圖邊界：以非對稱分布區分中位數、平均及 min/max。
    check(np.r_[np.ones(80), np.full(15, 1.0625), np.full(5, 1.125)], 1, 1e-10)
    # 相鄰離散峰被平滑核連起來時，種子仍來自第一峰，不能落在兩峰之間。
    check(np.repeat(np.exp(np.arange(6) * 0.45), 100), 1, 1e-10)
    # log 距 0.3 的鏈因窗重疊、計數不平衡而保留第一峰。
    check(np.repeat(np.exp(np.arange(6) * 0.3), 100), 1, 1e-10)
    assert np.array_equal(_maxima(np.array([3, 5, 5, 7, 4])), [3])
    assert np.array_equal(_maxima(np.array([3, 5, 5, 3])), [1])
    for ratio, expected in ((1.3, True), (1.5499, True), (1.55, False), (1.56, False), (2, False)):
        assert _dcd_pair(np.log(ratio), 100, 100) == expected
    for count, expected in ((59, False), (60, True), (61, True)):
        assert _dcd_pair(np.log(1.5), count, 100) == expected
        assert _dcd_pair(np.log(1.5), 100, count) == expected
    # 兩窗幾何中點不隨計數偏向大群；60% 邊界兩側各自固定。
    for count in (100, 80, 61, 60, 59):
        target = np.sqrt(.8 * 1.2) if count >= 60 else .8
        check(np.r_[np.full(100, .8), np.full(count, 1.2), np.full(10, 3.)], target, 1e-10)
    check(np.r_[.4, np.full(100, .85), np.full(100, 1.15), np.full(10, 3.)],
          np.sqrt(.85 * 1.15), 1e-10)
    # 長碼真 DCD 應合併；少數 1 UI 的 {2,3,4} 仍保留 2 UI。
    check(np.repeat([.8, 1.2, 1.8, 2.2, 2.8, 3.2], [100, 100, 70, 70, 70, 70]), .980, .01)
    check(np.repeat([1., 2., 3., 4.], [6, 100, 100, 100]), 2, 1e-10)
    for offset, expected in ((-.081, False), (-.079, True), (.079, True), (.081, False)):
        assert _harmonic(np.log(np.full(60, 2 * (1 + offset))), 1., 5., 100, 100) == expected
    for offset in (-.08, .08):
        logs = np.full(60, np.log(2) + np.log1p(offset))
        assert not _harmonic(logs, 1., 5., 100, 100)  # 恰在半窗端點不計入。
    # 較小峰 60 的門檻是 36；預測位置計數相等時不得排除。
    # 第二窗較小：2 倍頻 35 點合併、36 點不合併，固定呼叫端計數。
    for count, target in ((35, np.sqrt(1.5)), (36, 1.)):
        check(np.repeat([1., 1.5, 2., 3.], [100, 60, count, 10]), target, 1e-10)
    for count, expected in ((35, False), (36, True)):
        assert _harmonic(np.log(np.full(count, 2.)), 1., 1.5, 100, 60) == expected
        assert _harmonic(np.log(np.full(count, 2.)), 1., 1.5, 60, 100) == expected
    for count, expected in ((59, True), (60, False), (61, False)):
        logs = np.log(np.repeat([2., 2.25], [60, count]))
        assert _harmonic(logs, 1., 1.5, 100, 100) == expected
    assert not _harmonic(np.log(np.full(60, 4.)), 1., 1.5, 100, 100)
    assert _harmonic(np.log(np.full(60, 1e308)), 5e307, 7e307, 100, 100)
    assert not _harmonic(np.log(np.full(60, 1e308)), np.float64(1e308), 1.5e308, 100, 100)
    # 固定重疊窗：1000、1090 點，交集 109 點；聯集占比須扣重疊。
    rng_overlap = np.random.default_rng(0)
    t = np.arange(2001.) + np.where(np.arange(2001) % 2, .075, -.075)
    t += rng_overlap.normal(0, .05, t.size)
    _, diag = seed_ui(t)
    assert 0 < diag['seed_peak_fraction'] <= 1
    assert diag['seed_peak_fraction'] == (1000 + 1090 - 109) / 2000
    # 峰位比緊鄰上限、非對稱窗與上升平台：固定端到端的候選選取。
    check(np.repeat([.8, 1.23999, 3.], [100, 100, 10]), np.sqrt(.8 * 1.23999), 1e-10)
    check(np.repeat([.1, .8, 1.2], [3, 10, 10]), np.sqrt(.8 * 1.2), 1e-10)
    for counts, exponent in (
            ([0, 11, 0, 78, 88, 0, 0, 67, 0, 119, 29, 0, 0, 0, 46, 0], 3),
            ([24, 110, 1, 114, 6, 99, 0, 0, 68, 115, 76, 0, 0, 77, 79, 0], 1),
            ([42, 0, 0, 0, 54, 63, 0, 0, 0, 0, 104, 5, 20, 0, 0, 12], 7.5),
            ([0, 0, 38, 32, 0, 40, 33, 0, 0, 0, 3, 81, 57, 9, 23, 0], 5)):
        check(np.repeat(np.exp(np.arange(16) * .079), counts), np.exp(exponent * .079), 1e-10)
    # 稀疏簇左緣孤立樣本不可令後面的真正峰整簇消失。
    for size in (16, 20, 30, 50):
        rng_short = np.random.default_rng(6)
        bits_short = rng_short.integers(0, 2, 6000)
        x = np.flatnonzero(np.diff(bits_short)) + 1
        t = (x + rng_short.normal(0, .12, x.size))[:size + 1]
        assert abs(seed_ui(t)[0] - 1) < .15
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, 6000)
    indices = np.flatnonzero(np.diff(bits)) + 1
    times = indices + rng.normal(0, 0.12, indices.size)
    assert abs(seed_ui(times)[0] - 1) < 0.1
    runs = np.where(rng.random(3000) < 0.02, 1, rng.integers(2, 7, 3000))
    times = np.r_[0, np.cumsum(runs)] + rng.normal(0, 0.03, runs.size + 1)
    assert abs(seed_ui(times)[0] - 2) < 0.02
    # 少數 1 UI、眾數 2 UI：不能把最大峰當第一峰。
    check(np.r_[np.ones(80), np.full(600, 2.0), np.full(300, 3.0)], 1)
    # 不足顯著門檻、但超過孤立計數上限的小峰；門檻改成零會誤選。
    check(np.r_[np.full(10, 0.3), np.ones(1000)], 1)
    # 三點尖峰對寬峰仍可顯著：單靠計數門檻不足，須另排除孤立極短峰。
    broad = np.exp(np.linspace(np.log(0.8), np.log(1.2), 64))
    check(np.r_[np.full(3, 0.3), broad], float(np.median(broad)), 0.04)
    check(np.full(100, 2.0), 2)
    short, diag = seed_ui(np.r_[0, np.cumsum([0.3] + [1.0] * 14)])
    assert short == 0.3 and diag['seed_method'] == 'min_short_record'
    ui, diag = seed_ui(np.r_[np.arange(40.0), np.nan, np.inf, np.inf, 0, 0, -1])
    assert ui == 1 and diag['seed_interval_count'] == 39
    for bad in ([], [np.nan, np.inf], [2, 1, 0], [0, 0]):
        try:
            seed_ui(np.array(bad))
            raise AssertionError("無正間隔應報錯")
        except ScopeError:
            pass


def _self_check() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        _checks()


def _checks() -> None:
    from scope_tool.analysis import clock

    _rule_checks()
    size, ui = 6000, 1e-9
    register, prbs = 127, []
    for _ in range(size):
        prbs.append(register & 1)
        register = (register >> 1) | (((register ^ (register >> 1)) & 1) << 6)
    for sigma in (0, 0.02, 0.07):
        maximum = 0.0
        for seed in range(8):
            rng = np.random.default_rng(seed)
            for bits in (np.array(prbs), rng.integers(0, 2, size)):
                indices = np.flatnonzero(np.diff(bits)) + 1
                times = (indices + rng.normal(0, sigma, indices.size)) * ui
                value, _ = seed_ui(times)
                maximum = max(maximum, abs(value / ui - 1))
                assert abs(value / ui - 1) < 0.02, (sigma, seed, value)
        print(f"PRBS／隨機 NRZ σ={sigma}，8 seed：種子最大誤差 {maximum:.3%}")
    for count in (1, 2, 3):
        times = np.r_[0, np.cumsum(np.r_[np.ones(200), np.full(200, 2.0)])]
        times = np.sort(np.r_[times, times[10:10 + count] + 0.2 + count * 0.05])
        d = np.diff(times)
        value, _ = seed_ui(times)
        assert abs(value - 1) < 0.1 and abs(d.min() - 1) > 0.1
        print(f"glitch {count}：min={d.min():.3f} UI，第一峰={value:.3f} UI")
    # 使用真正 recover，只替換舊種子以作相同波形的配對比較；保留原擬合流程。
    original = clock._seed
    for sigma in (0.07, 0.09):
        old_wrong = new_wrong = failures = all_new_wrong = 0
        for seed in range(12):
            rng = np.random.default_rng(seed)
            bits = rng.integers(0, 2, size)
            t, v = clock.nrz(bits, ui, 32, jitter=rng.normal(0, sigma * ui, size + 1))
            spec = clock.ClockSpec("NRZ 資料")
            new = clock.recover(t, v, (10, 50, 90), spec)
            truth = np.flatnonzero(np.diff(bits)) + 1
            truth -= truth[0]
            b = int(np.count_nonzero(new.n != truth))
            all_new_wrong += b
            try:
                clock._seed = lambda spec, es, times, step, diagnostics: float(np.diff(times).min())
                old = clock.recover(t, v, (10, 50, 90), spec)
            except ScopeError:
                failures += 1
                continue  # 舊法未收斂另列，不把無格號的案例虛列為錯格數。
            finally:
                clock._seed = original
            a = int(np.count_nonzero(old.n != truth))
            assert b <= a, (sigma, seed, a, b)
            old_wrong += a
            new_wrong += b
        print(f"recover σ={sigma}，12 seed：配對錯格 min={old_wrong}／第一峰={new_wrong}，舊法未收斂={failures}")
        print(f"第一峰全部 12 seed 錯格={all_new_wrong}，未收斂=0")
    print("analysis.rate_seed self-check OK")


if __name__ == "__main__":
    _self_check()
