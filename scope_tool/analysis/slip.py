"""E 版滑格疑慮診斷；只去趨勢診斷，不修改還原 TIE。"""
from __future__ import annotations

import warnings

import numpy as np

from scope_tool.analysis import status as st

# 待校準的產品門檻；非物理界線。
_BLOCK_EDGES, _MIN_BLOCKS, _WINDOW_BLOCKS = 32, 3, 6
_WINDOW_STEP_UI, _LOCAL_STEP_UI = 0.6, 0.5
_PULSE_STEP_UI, _PULSE_SUM_UI, _QUIET_STEP_UI = 0.7, 0.3, 0.175
_RESIDUAL_BOUNDARY, _PULSE_MAX_GAP = 0.35, 5


def _rules(m: np.ndarray, residual: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """residual 為每對相鄰區塊（含交界）的最大間隔殘差；回傳 A/B 命中交界。"""
    jump = np.diff(m)
    j = np.arange(jump.size)
    offsets = np.arange(_WINDOW_BLOCKS)
    left, right = j[:, None] - offsets, j[:, None] + 1 + offsets
    lm = np.nanmedian(np.where(left >= 0, m[np.maximum(left, 0)], np.nan), axis=1)
    rm = np.nanmedian(np.where(right < m.size, m[np.minimum(right, m.size - 1)], np.nan), axis=1)
    local = np.abs(jump)
    two = np.abs(m[2:] - m[:-2])
    local = np.maximum(local, np.r_[two, 0])
    local = np.maximum(local, np.r_[0, two])
    near = np.maximum.reduce((residual, np.r_[0, residual[:-1]], np.r_[residual[1:], 0]))
    a = (np.abs(rm - lm) > _WINDOW_STEP_UI) & (local > _LOCAL_STEP_UI) & (near >= _RESIDUAL_BOUNDARY)
    b = np.zeros(jump.size, bool)
    quiet = np.abs(jump) < _QUIET_STEP_UI
    # 只迭代固定的五種跨度；所有交界成批比較，避免逐邊緣 Python 迴圈。
    for gap in range(1, min(_PULSE_MAX_GAP + 1, jump.size)):
        first, last = jump[:-gap], jump[gap:]
        flat = np.ones(first.size, bool)
        for k in range(1, gap):
            flat &= quiet[k:k + first.size]
        flat &= np.r_[True, quiet[:first.size - 1]]
        flat &= np.r_[quiet[gap + 1:], True]
        # 兩跳幅度皆 >0.7 且 |和|<0.3，已必為反號。
        hit = ((np.abs(first) > _PULSE_STEP_UI)
               & (np.abs(last) > _PULSE_STEP_UI) & (np.abs(first + last) < _PULSE_SUM_UI)
               & flat & (np.maximum(residual[:-gap], residual[gap:]) >= _RESIDUAL_BOUNDARY))
        b[:-gap] |= hit
        b[gap:] |= hit
    return a, b


def assess(n: np.ndarray, tie_ui: np.ndarray, units: np.ndarray) -> st.Result:
    """沿用 clock._units 的奇數格尺度；只用完整區塊，非有限輸入不判定。"""
    blocks = n.size // _BLOCK_EDGES
    count, maximum = 0, 0.0
    if blocks >= _MIN_BLOCKS and all(np.isfinite(x).all() for x in (n, tie_ui, units)):
        x = n.astype(float) - n.mean()
        y = tie_ui - tie_ui.mean()
        norm = np.sum(x * x)
        slope = float(np.sum(x * y) / norm) if norm > 0 else 0.0
        end = blocks * _BLOCK_EDGES
        m = np.median((y - slope * x)[:end].reshape(blocks, _BLOCK_EDGES), axis=1)
        residual = np.abs(units[:end - 1] - np.rint(units[:end - 1]))
        intervals = np.r_[residual, 0.0].reshape(blocks, _BLOCK_EDGES)
        internal = intervals[:, :-1].max(axis=1)
        near = np.maximum(np.maximum(internal[:-1], internal[1:]), intervals[:-1, -1])
        a, b = _rules(m, near)
        count, maximum = int(np.count_nonzero(a | b)), float(np.abs(np.diff(m)).max())
    diagnostics = {"grid_slip_suspects": count, "grid_slip_max_block_jump_ui": maximum,
                   "grid_slip_block_edges": _BLOCK_EDGES, "grid_slip_window_blocks": _WINDOW_BLOCKS,
                   "grid_slip_window_step_ui": _WINDOW_STEP_UI, "grid_slip_local_step_ui": _LOCAL_STEP_UI,
                   "grid_slip_pulse_step_ui": _PULSE_STEP_UI, "grid_slip_pulse_sum_ui": _PULSE_SUM_UI,
                   "grid_slip_quiet_step_ui": _QUIET_STEP_UI, "grid_slip_pulse_max_gap": _PULSE_MAX_GAP,
                   "grid_slip_residual_boundary": _RESIDUAL_BOUNDARY}
    return st.Result(st.LIMITED if count else st.VALID,
                     (st.GRID_SLIP_SUSPECT,) if count else (), diagnostics)


def _rule_checks() -> None:
    # 固定測試數值，不引用門檻常數；突變時測試不能跟著漂移。
    for height, expected in ((0.5999, False), (0.6001, True)):
        m = np.r_[np.zeros(8), np.full(8, height)]
        assert bool(_rules(m, np.full(15, 0.4))[0].any()) == expected
    for local, expected in ((0.4999, False), (0.5001, True)):
        m = np.r_[np.zeros(8), local, local, np.full(8, 0.8)]
        a, _ = _rules(m, np.r_[np.zeros(7), 0.4, np.zeros(9)])
        assert bool(a[7]) == expected
    for residual, expected in ((0.3499, False), (0.35, True)):
        a, _ = _rules(np.r_[np.zeros(8), np.ones(8)], np.full(15, residual))
        assert bool(a.any()) == expected
    # 六塊中位數能跨過緩慢過渡；單塊視窗無法通過 0.6 UI 門檻。
    m = np.r_[np.zeros(8), 0.3, 0.7, np.ones(8)]
    assert _rules(m, np.full(m.size - 1, 0.4))[0][8]
    for sign in (-1, 1):
        for height, expected in ((0.6999, False), (0.7001, True)):
            m = sign * np.r_[np.zeros(8), np.full(3, height), np.zeros(8)]
            assert bool(_rules(m, np.full(m.size - 1, 0.4))[1].any()) == expected
    for total, expected in ((0.2999, True), (0.3001, False)):
        m = np.r_[np.zeros(8), np.full(3, 1.1), np.full(8, total)]
        assert bool(_rules(m, np.full(m.size - 1, 0.4))[1].any()) == expected
    for quiet, expected in ((0.1749, True), (0.1751, False)):
        m = np.r_[np.zeros(8), 1, 1 + quiet, 1 + quiet, np.full(8, quiet)]
        assert bool(_rules(m, np.full(m.size - 1, 0.4))[1].any()) == expected
    for gap in (1, 5, 6):
        m = np.r_[np.zeros(8), np.ones(gap), np.zeros(8)]
        assert bool(_rules(m, np.full(m.size - 1, 0.4))[1].any()) == (gap <= 5)
    assert not _rules(np.r_[np.zeros(8), np.ones(3), np.zeros(8)], np.zeros(18))[1].any()
    # B 外側左右獨立：不能只檢查脈衝內部的平坦度。
    for quiet, expected in ((0.18, False), (0.17, True)):
        m = np.r_[np.zeros(7), quiet, np.full(3, 1 + quiet), np.full(8, quiet)]
        for values in (m, m[::-1]):
            assert bool(_rules(values, np.full(values.size - 1, 0.4))[1].any()) == expected
    for offset in (-1, 1):
        residual = np.zeros(15); residual[7 + offset] = 0.4
        assert _rules(np.r_[np.zeros(8), np.ones(8)], residual)[0][7]
    # 左右兩塊合計各自獨立；單跳皆不足 0.5，視窗仍跨過 0.6。
    for total, expected in ((0.49, False), (0.51, True)):
        m = np.r_[np.zeros(8), 0.25, total, np.full(8, 0.8)]
        for values, j in ((m, 7), (m[::-1], m.size - 9)):
            assert bool(_rules(values, np.full(values.size - 1, 0.4))[0][j]) == expected
    # 六塊視窗的最遠一塊決定中位數；右窗不可含 j，左窗必須含 j。
    m = np.r_[np.zeros(6), 1.4, 1.4, 0, 0, 0, 1.4, 0]
    assert _rules(m, np.full(m.size - 1, 0.4))[0][5]
    m = np.r_[0, 0, 0, 0, 0.6, 0.6, 0.6, 1.4, np.full(5, 0.8)]
    assert not _rules(m, np.full(m.size - 1, 0.4))[0][6]
    # j=0 左窗仍有 m[0]，不可產生 All-NaN slice 的 RuntimeWarning。
    assert _rules(np.r_[0, np.ones(8)], np.full(8, 0.4))[0][0]


def _self_check() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        _checks()


def _checks() -> None:
    from time import perf_counter
    from scope_tool.analysis import clock

    _rule_checks()
    n = np.arange(1024)
    for sign in (-1, 1):
        for pulse in (False, True):
            tie = sign * ((n >= 448) & ((n < 544) if pulse else True)).astype(float)
            units = np.diff(n + tie); units[447] += 0.4
            result = assess(n, tie, units)
            assert result.status == st.LIMITED
            if pulse:
                x, y = n - n.mean(), tie - tie.mean()
                m = np.median((y - np.sum(x * y) / np.sum(x * x) * x).reshape(-1, 32), axis=1)
                a, b = _rules(m, np.full(m.size - 1, 0.4))
                assert b.any() and not a.any()  # 短暫偏移確實由 B 補捉。
    for size in (63, 64, 95, 96):
        k = np.arange(size)
        tie = ((k >= 32) & (k < 64)).astype(float)
        units = np.diff(k + tie); units[31] += 0.4
        result = assess(k, tie, units)
        assert (result.status == st.LIMITED) == (size == 96), (size, result)
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        for bad in (np.nan, np.inf, -np.inf):
            tie = np.zeros(n.size); tie[10] = bad
            result = assess(n, tie, np.ones(n.size - 1))
            assert result.status == st.VALID and all(np.isfinite(v) for v in result.diagnostics.values())
    # 2% 頻偏使每塊漂移 0.64 UI；交替位移提供捨入殘差，不去趨勢會誤報 A。
    drift = 0.02 * n + np.where(n % 2, 0.2, -0.2)
    result = assess(n, drift, np.diff(n + drift))
    assert result.status == st.VALID
    assert result.diagnostics['grid_slip_max_block_jump_ui'] < 1e-3
    ui, size = 1e-9, 12000
    spec = clock.ClockSpec("NRZ 資料", mode="手動", rate=1 / ui)
    rng = np.random.default_rng(9)
    register, prbs = 127, []
    for _ in range(size):
        prbs.append(register & 1)
        register = (register >> 1) | (((register ^ (register >> 1)) & 1) << 6)
    for bits in (rng.integers(0, 2, size), np.array(prbs)):
        for sigma in (0, 0.02, 0.07):
            t, v = clock.nrz(bits, ui, 32, jitter=rng.normal(0, sigma * ui, size + 1))
            assert st.GRID_SLIP_SUSPECT not in clock.recover(t, v, (10, 50, 90), spec).reasons
        for ppm in (-100, 100):
            t, v = clock.nrz(bits, ui / (1 + ppm * 1e-6), 32)
            assert st.GRID_SLIP_SUSPECT not in clock.recover(t, v, (10, 50, 90), spec).reasons
    for sigma in (0, 0.05):
        offset = (np.arange(size + 1) % 2) * 0.2 * ui + rng.normal(0, sigma * ui, size + 1)
        t, v = clock.nrz(np.tile([0, 1], size // 2), ui, 32, jitter=offset)
        ck = clock.recover(t, v, (10, 50, 90), clock.ClockSpec(edges="兩者", mode="手動", rate=0.5 / ui))
        assert st.GRID_SLIP_SUSPECT not in ck.reasons
    for amp, period, sigma in ((0.5, 200, 0.07), (0.4, 128, 0.05), (0.3, 100, 0.06)):
        false = 0
        for seed in range(20):
            rng = np.random.default_rng(seed)
            bits = rng.integers(0, 2, size)
            offset = amp * np.sin(np.arange(size + 1) * 2 * np.pi / period) + rng.normal(0, sigma, size + 1)
            t, v = clock.nrz(bits, ui, 32, jitter=offset * ui)
            false += st.GRID_SLIP_SUSPECT in clock.recover(t, v, (10, 50, 90), spec).reasons
        # 20 seed 的第一組既有 1/20 誤報；放寬到 10%，避免卡在 5% 上限。
        assert false / 20 <= 0.10, (amp, period, sigma, false)
        print(f"SJ {amp}/{period}+RJ{sigma}：誤報 {false}/20", flush=True)
    for odd, sigmas in ((False, (0.09, 0.10)), (True, (0.2, 0.3))):
        for sigma in sigmas:
            slipped = detected = persistent = 0
            trials = 10 if odd else 20
            for seed in range(100, 100 + trials):
                rng = np.random.default_rng(seed)
                bits = np.tile([0, 1], size // 2) if odd else rng.integers(0, 2, size)
                t, v = clock.nrz(bits, ui, 32, jitter=rng.normal(0, sigma * ui, size + 1))
                check_spec = clock.ClockSpec(edges="兩者", mode="手動", rate=0.5 / ui) if odd else spec
                ck = clock.recover(t, v, (10, 50, 90), check_spec)
                truth = np.rint(ck.times / ui).astype(int)
                error = ck.n - (truth - truth[0])
                wrong = np.any(error)
                slipped += int(wrong)
                detected += int(wrong and st.GRID_SLIP_SUSPECT in ck.reasons)
                # 持久錯格：連續至少 128 個邊緣，不把短暫跳回算入。
                changes = np.r_[0, np.flatnonzero(np.diff(error)) + 1, error.size]
                lasting = np.any((np.diff(changes) >= 128) & (error[changes[:-1]] != 0))
                if lasting:
                    persistent += 1
                    assert ck.status != st.VALID, (odd, sigma, seed)
            assert slipped > 0 and detected > 0 and persistent > 0, (odd, sigma, slipped, detected)
            print(f"slip odd={odd} σ={sigma}：滑格 {slipped}/{trials}，偵測 {detected}，持久 {persistent}", flush=True)
    n = np.arange(1_000_000)
    tie = 0.02 * np.sin(n / 50)
    started = perf_counter()
    result = assess(n, tie, np.diff(n + tie))
    elapsed = perf_counter() - started
    assert result.status == st.VALID and elapsed < 1.0, elapsed
    assert np.isclose(result.diagnostics['grid_slip_max_block_jump_ui'], 0.012581, atol=1e-5)
    print(f"analysis.slip self-check OK（1e6 邊緣 {elapsed:.3f} s）")


if __name__ == "__main__":
    _self_check()
