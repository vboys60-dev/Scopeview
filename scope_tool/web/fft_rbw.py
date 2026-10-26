"""Web FFT 的 Welch／VBW 模擬；本工具做法，待真機驗證。"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis.fft import WINDOWS, MAX_POINTS, window, magnitude, reference_impedance
from scope_tool.analysis.measure import uniform_dt, validate
from scope_tool.contracts import ScopeError

L_MIN = 64
BLOCK = 2 ** 22


def welch(t: np.ndarray, v: np.ndarray, window_name: str, unit: str,
          r_ohm: float | None, source_unit: str, rbw: float) -> dict:
    """50% 重疊、CG 校正後功率平均；尾端不足一個 hop 的樣本捨棄。"""
    validate(t, v)
    n = len(v)
    if n > MAX_POINTS:
        raise ScopeError(f"FFT 點數 {n:,} 超過上限 {MAX_POINTS:,}，請縮小游標區間。")
    if window_name not in WINDOWS or unit == "Phase" or not np.isfinite(rbw) or rbw <= 0:
        raise ScopeError("Welch 視窗／單位／RBW 無效。")
    resistance = reference_impedance(r_ohm)
    dt = uniform_dt(t)
    # 週期餘弦窗在 L≥64 時等於解析倍率；先算倍率再決定段長。
    probe = window(window_name, L_MIN)
    factor = L_MIN * float(np.sum(probe ** 2)) / float(probe.sum()) ** 2
    minimum = min(L_MIN, n)
    # 先夾 Hz 範圍，避免極小 RBW 使除法溢位或轉整數失敗。
    length = (n if rbw <= factor / (n * dt) else minimum if rbw >= factor / (minimum * dt)
              else max(minimum, min(n, round(factor / dt / rbw))))
    w = window(window_name, length)
    total = float(w.sum())
    factor = length * float(np.sum(w ** 2)) / total ** 2
    m = 1 << (length - 1).bit_length()
    hop = length // 2
    count = 1 + (n - length) // hop
    left = (m - length) // 2
    segments = np.lib.stride_tricks.sliding_window_view(v, length)[::hop]
    power = np.zeros(m // 2 + 1)
    per_block = max(1, BLOCK // length)
    for start in range(0, count, per_block):
        block = segments[start:start + per_block] * w
        z = np.fft.rfft(np.pad(block, ((0, 0), (left, m - length - left))), axis=1) / total
        power += np.sum(z.real ** 2 + z.imag ** 2, axis=0)
        del block, z  # 下一塊開始前釋放本塊暫存
    power /= count
    rms = np.sqrt(2 * power)
    rms[0], rms[-1] = np.sqrt(power[0]), np.sqrt(power[-1])
    out_unit = unit if source_unit == "V" else source_unit + " rms"
    mag = magnitude(rms, unit if source_unit == "V" else "Vrms", resistance)
    actual = factor / (length * dt)
    return {"freq": np.fft.rfftfreq(m, dt), "mag": mag, "rms": rms, "unit": out_unit,
            "df": 1 / (m * dt), "lobe": int(np.ceil(len(WINDOWS[window_name]) * m / length)),
            "enbw_bins": factor, "enbw": actual, "rbw": actual, "cg": float(w.mean()),
            "n": n, "effective_n": m, "r_ohm": resistance, "segments": count,
            "power": rms ** 2 / resistance if source_unit == "V" else None,
            "power_correction": m / length * factor}


def video_smooth(mag: np.ndarray, rbw: float, vbw: float | None,
                 df: float) -> tuple[np.ndarray, float | None]:
    """輸出單位域方框平均；RBW²/VBW 是本工具模擬，非儀器等效公式。"""
    if vbw is None or vbw >= rbw or not len(mag):
        return mag, None
    n = len(mag)
    # 以比例先判斷是否超過上限，避免 RBW² 或極小 VBW 造成溢位。
    cap = n if n % 2 else n - 1
    width = rbw / df * (rbw / vbw)
    k = cap if width >= cap else min(cap, max(1, round(width)) | 1)
    half = k // 2
    idx = np.arange(n)
    lo, hi = np.maximum(0, idx - half), np.minimum(n, idx + half + 1)
    sums = np.r_[0., np.cumsum(mag, dtype=np.float64)]
    return (sums[hi] - sums[lo]) / (hi - lo), vbw


def _self_check() -> None:
    from scope_tool.analysis import fft as fftmod
    from unittest.mock import patch

    t = np.arange(10000) / 1e6
    v = np.random.default_rng(7).normal(size=len(t))
    for name in WINDOWS:
        for unit in ("dBm", "dBV", "dBmV", "dBµV", "Vrms", "W", "Watt"):
            s = welch(t, v, name, unit, 50., "V", 1e-300)
            original = fftmod.spectrum(t, v, name, unit, 50.)
            assert np.allclose(s["mag"], original["mag"])
            assert s["segments"] == 1 and np.isclose(s["rbw"], s["enbw_bins"] * 1e6 / len(t))
    loss = {"Rectangular": 3.93, "Hanning": 1.43, "Hamming": 1.76,
            "Blackman-Harris": 0.83, "Flattop": 0.02}
    length, n = 4096, 32768
    t = np.arange(n, dtype=float)
    for name in WINDOWS:
        w = window(name, length)
        rbw = np.sum(w ** 2) / w.sum() ** 2
        for offset in (0., .5):
            v = np.sqrt(2) * np.sin(2 * np.pi * (500 + offset) * t / length)
            s = welch(t, v, name, "dBV", 50., "V", rbw)
            assert s["segments"] >= 8
            assert abs(max(s["mag"])) < (.01 if offset == 0 else loss[name])
    t = np.arange(2 ** 20, dtype=float)
    noise = np.random.default_rng(42).normal(size=len(t))
    results = [welch(t, noise, "Hanning", "Vrms", 50., "V", 1.5 / l) for l in (256, 4096)]
    floors = [np.mean(s["rms"][1:-1] ** 2) for s in results]
    for s, floor in zip(results, floors):
        assert abs(floor / (2 * s["rbw"]) - 1) < .05
    assert abs(10 * np.log10(floors[0] / floors[1]) -
               10 * np.log10(results[0]["rbw"] / results[1]["rbw"])) < .5
    s = welch(t, noise, "Hanning", "Vrms", 50., "V", 1e300)
    assert s["effective_n"] == 64 and s["segments"] == 32767 and s["n"] == len(t)
    # 縮小分塊仍須產出相同結果，確實跨多塊累加。
    with patch(__name__ + ".BLOCK", 1024):
        small = welch(t[:8192], noise[:8192], "Hanning", "Vrms", 50., "V", 1e300)
    regular = welch(t[:8192], noise[:8192], "Hanning", "Vrms", 50., "V", 1e300)
    assert np.allclose(small["mag"], regular["mag"])
    short = welch(t[:50], noise[:50], "Hanning", "Vrms", 50., "V", 1e300)
    assert short["segments"] == 1 and short["n"] == 50 and short["effective_n"] == 64
    for n in (100, 101):
        a = np.ones(n)
        for vbw in (None, 2., 3.):
            out, applied = video_smooth(a, 2., vbw, 1.)
            assert out is a and applied is None
        assert np.allclose(video_smooth(a, 2., .1, 1.)[0], a)
        pulse = np.zeros(n)
        pulse[n // 2] = 1
        out, applied = video_smooth(pulse, 2., 1., 1.)  # round(4) 強制奇數＝5
        assert applied == 1. and np.count_nonzero(out) == 5 and np.isclose(out.sum(), 1.)
        ramp = np.arange(n, dtype=float)
        out, _ = video_smooth(ramp, 2., 1., 1.)
        assert out[0] == 1. and out[-1] == n - 2
        out, _ = video_smooth(ramp, 2., 1e-300, 1.)
        half = (n if n % 2 else n - 1) // 2
        assert out[0] == np.mean(ramp[:half + 1])
    print("web.fft_rbw self-check OK")


if __name__ == "__main__":
    _self_check()
