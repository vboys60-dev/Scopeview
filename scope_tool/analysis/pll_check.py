"""pll.py 事件層合成驗收（R=1 Gb/s、seed=20261024；傳遞函數、頻偏、長碼、滑格、捕獲邊界）。"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis import pll

R = 1e9


def edges(runs: np.ndarray, ppm: float = 0.0, sj: tuple[float, float] | None = None,
          step: tuple[int, float] | None = None) -> np.ndarray:
    """runs＝各轉態間的 UI 數；sj＝(振幅 UI, 頻率 Hz)；step＝(第幾緣起, 相位階躍 UI)。"""
    pos = np.cumsum(runs).astype(float)
    t = pos / (R * (1 + ppm * 1e-6))
    if sj:
        t = t + sj[0] / R * np.sin(2 * np.pi * sj[1] * t)
    if step:
        t[step[0]:] += step[1] / R
    return t


def prbs_runs(rng: np.random.Generator, n: int, longest: int = 7) -> np.ndarray:
    return np.minimum(rng.geometric(0.5, n), longest)


def lsq(t: np.ndarray, y: np.ndarray, f: float) -> complex:
    """y ≈ Re(c·e^{j2πft}) 的最小平方複振幅（y 為 UI）。"""
    m = np.c_[np.cos(2 * np.pi * f * t), -np.sin(2 * np.pi * f * t)]
    a, b = np.linalg.lstsq(m, y, rcond=None)[0]
    return a + 1j * b


def run() -> None:
    rng = np.random.default_rng(20261024)
    wn = pll.omega_n(R)
    bw = R / pll.BW_DIVISOR
    # 頻寬定義：JTF 在 B 的 −3 dB（相對 DC），預設 B≈599.88 kHz
    assert abs(abs(pll.transfer(bw, wn)[0]) - 10 ** (-3 / 20)) < 5e-3 and abs(bw - 599.88e3) < 10
    assert abs(abs(pll.transfer(0.1 * bw, wn)[1]) - 0.0423) < 5e-4
    # 無 jitter、頻偏 ±1000 ppm：殘餘 <1e−6 UI、速率誤差 <10 ppm、零滑格
    for ppm in (-1000, 0, 1000):
        r = pll.track(edges(prbs_runs(rng, 60000), ppm), R)
        assert r.ok and r.valid.sum() > 20000 and r.diag["relocks"] == 0, (ppm, r.reason)
        assert np.sqrt(np.mean((r.tie[r.valid] * R) ** 2)) < 1e-6, ppm
        assert abs(r.w[-1] / (R * (1 + ppm * 1e-6)) - 1) < 10e-6, ppm
    # SJ 掃頻：A=0.02 UI；殘餘 TIE 的振幅比與相位對 OJTF E(f)（0.1B 約吸收 96%）
    for ratio, nt in ((0.1, 190000), (1, 60000), (10, 60000)):
        f, a = ratio * bw, 0.02
        t = edges(prbs_runs(rng, nt), 0, (a, f))
        r = pll.track(t, R)
        assert r.ok and r.diag["relocks"] == 0
        tv = r.times[r.valid]
        if ratio == 0.1:
            assert (tv[-1] - tv[0]) * f >= 20
        got = lsq(tv, r.tie[r.valid] * R, f)       # TIE>0＝邊緣晚於預測
        want = a * pll.transfer(f, wn)[1] * -1j     # 輸入 A·sin → 複振幅 −jA
        assert abs(abs(got) / abs(want) - 1) <= 0.05, (ratio, abs(got) / abs(want))
        assert abs(np.degrees(np.angle(got / want))) <= 5, (ratio, np.degrees(np.angle(got / want)))
    # 轉態密度：交替碼、PRBS7（最長 7）、8b10b（最長 5）的 E(10B) 同樣符合
    f, a = 10 * bw, 0.02
    for runs in (np.ones(60000, int), prbs_runs(rng, 60000, 7), prbs_runs(rng, 60000, 5)):
        r = pll.track(edges(runs, 0, (a, f)), R)
        assert r.ok and r.diag["relocks"] == 0 and r.valid.sum() > 5000
        got = abs(lsq(r.times[r.valid], r.tie[r.valid] * R, f))
        assert abs(got / (a * abs(pll.transfer(f, wn)[1])) - 1) <= 0.05
    # 長碼：≤32 UI 保持鎖定且不重鎖；33 UI 失鎖並重新取得
    for gap, relock in ((4, 0), (5, 0), (7, 0), (32, 0), (33, 1)):
        runs = prbs_runs(rng, 60000, 7)
        runs[30000] = gap
        r = pll.track(edges(runs), R)
        assert r.ok and r.diag["relocks"] == relock, (gap, r.diag["relocks"])
        assert r.valid[:29000].sum() > 5000 and r.valid[-1]
        if relock:
            assert not r.valid[30000:32000].any() and r.diag["long_gaps"] == 1
            assert r.seg[-1] == 1
    # 階躍：0.2 UI 為暫態不重鎖；0.6 UI 排除並重鎖，不輸出一串小 TIE
    r = pll.track(edges(prbs_runs(rng, 60000), step=(30000, 0.2)), R)
    assert r.ok and r.diag["relocks"] == 0 and abs(r.tie_all[30000] * R - 0.2) < 1e-3
    r = pll.track(edges(prbs_runs(rng, 60000), step=(30000, 0.6)), R)
    assert r.diag["relocks"] >= 1 and not r.valid[30000] and r.seg[-1] >= 1
    # 捕獲邊界：±1000 ppm 可鎖；2000 ppm、1% 不納入保證（不得宣稱有效鎖定）
    for ppm in (1400, 2000, 10000):
        r = pll.track(edges(prbs_runs(rng, 60000), ppm), R)
        assert not r.ok or ppm <= 1400, (ppm, r.reason)
    # 失敗狀態：短記錄、全未鎖皆無假零
    r = pll.track(edges(prbs_runs(rng, 3000)), R)
    assert not r.ok and r.reason == "PLL_NOT_LOCKED" and not r.valid.any() and np.isnan(r.tie).all()
    for bad in (0, R / 999):
        try:
            pll.omega_n(R, bad)
        except Exception as ex:
            assert "PLL" in str(ex)
        else:
            raise AssertionError(bad)
    print("pll self-check OK")


if __name__ == "__main__":
    run()
