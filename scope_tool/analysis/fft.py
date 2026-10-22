"""FFT 頻譜（依 Infiniium 手冊 FFT_Magnitude、FFT_Magnitude_Vertical_Units、FFT_Theory）。

原始資料加窗後前後補零至 2 的冪次；CG = Σw/n，振幅除以 Σw。
手冊未載明，採標準定義：週期餘弦窗、ENBW 與保留 DC，不減平均值。
加窗與補零的先後、奇數補零多一點放右側是本工具做法，待真機驗證。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis.measure import uniform_dt, validate
from scope_tool.contracts import ScopeError
from scope_tool.analysis.peaks import peaks  # 保留既有呼叫介面

MAX_POINTS = 2 ** 24
# 手冊未載明，採標準定義：週期餘弦窗，w[n] = Σ (-1)^k a_k cos(2πkn/N)。
# Hanning 即 Hann；Flattop 用 MATLAB flattopwin 五項係數，BH 用四項最小旁瓣版本。
WINDOWS: dict[str, tuple[float, ...]] = {
    "Hanning": (0.5, 0.5),
    "Flattop": (0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368),
    "Rectangular": (1.0,),
    "Hamming": (0.54, 0.46),
    "Blackman-Harris": (0.35875, 0.48829, 0.14128, 0.01168),
}
UNITS = ("dBm", "Vrms", "dBV", "dBmV", "dBµV", "W", "Watt", "Phase")
_FLOOR = 1e-20  # 避免 log(0)


def window(name: str, n: int) -> np.ndarray:
    x = 2 * np.pi * np.arange(n) / n
    return sum((-1) ** k * a * np.cos(k * x) for k, a in enumerate(WINDOWS[name]))


def reference_impedance(manual: float | None = None, source_kind: str = "other", *,
                        channel_mode: str | None = None, probe_kind: str = "single-ended",
                        high_impedance: bool = False) -> float:
    """Auto：通道設定優先於探棒；其他來源（含 math／memory）假設 50 Ω。"""
    if manual is not None:
        if not np.isfinite(manual) or not 10 <= manual <= 200:
            raise ScopeError("手動參考阻抗必須介於 10–200 Ω。")
        return float(manual)
    if source_kind != "analog":
        return 50.0
    mode = channel_mode or probe_kind
    if mode == "common-mode" and high_impedance:
        raise ScopeError("高阻抗探棒不支援共模。")
    if mode not in ("single-ended", "differential", "common-mode"):
        raise ScopeError("未知來源型態。")
    return {"single-ended": 50.0, "differential": 100.0, "common-mode": 25.0}[mode]


def magnitude(rms: np.ndarray, unit: str, r_ohm: float) -> np.ndarray:
    """A-17：dBm=10 log10(Vrms²/R/1mW)，dBV=20 log10(Vrms/1V)。"""
    safe = np.maximum(rms, _FLOOR)
    return {"Vrms": lambda: rms, "dBV": lambda: 20 * np.log10(safe),
            "dBmV": lambda: 20 * np.log10(safe / 1e-3), "dBµV": lambda: 20 * np.log10(safe / 1e-6),
            "W": lambda: rms ** 2 / r_ohm, "Watt": lambda: rms ** 2 / r_ohm,
            "dBm": lambda: 20 * np.log10(safe) - 10 * np.log10(r_ohm * 1e-3)}[unit]()


def spectrum(t: np.ndarray, v: np.ndarray, window_name: str = "Hanning", unit: str = "dBm",
             r_ohm: float | None = None, source_unit: str = "V", *, source_kind: str = "other",
             channel_mode: str | None = None, probe_kind: str = "single-ended",
             high_impedance: bool = False, reference_time: float = 0.0,
             delay: float = 0.0, unwrap: bool = False) -> dict:
    """df=Fs/Effective Memory Depth；rbw=df×標準窗 ENBW 倍率。

    補零只增加頻格密度，實際雜訊頻寬 enbw=Fs×Σw²/(Σw)² 不會縮小。
    RBW 分母用原始 n 或補零後 M 手冊未載明；本工具取 Fs/M×原始窗 ENBW 倍率，
    與實際窗 ENBW（Hz）分開顯示，待真機比對。
    手冊未載明，採標準定義：Phase 以餘弦為零相位、參考時刻加 delay，
    預設包裹於 ±180°；可選 numpy.unwrap，再換成度。零振幅相位沒有物理意義。
    """
    validate(t, v)
    if len(v) > MAX_POINTS:
        raise ScopeError(f"FFT 點數 {len(v):,} 超過上限 {MAX_POINTS:,}，請縮小游標區間。")
    if window_name not in WINDOWS or unit not in UNITS:
        raise ScopeError("未知 FFT 視窗或單位。")
    if not np.isfinite([reference_time, delay]).all():
        raise ScopeError("相位參考時間必須有限。")
    resistance = reference_impedance(r_ohm, source_kind, channel_mode=channel_mode,
                                    probe_kind=probe_kind, high_impedance=high_impedance)
    dt, n = uniform_dt(t), len(v)
    effective_n = 1 << (n - 1).bit_length()
    w = window(window_name, n)
    left = (effective_n - n) // 2
    z = np.fft.rfft(np.pad(v * w, (left, effective_n - n - left))) / w.sum()
    freq = np.fft.rfftfreq(effective_n, dt)
    rms = np.abs(z) * np.sqrt(2)
    rms[0], rms[-1] = abs(z[0]), abs(z[-1])  # DC 與 Nyquist 不成對，不乘 √2
    factor = n * float(np.sum(w ** 2)) / float(w.sum()) ** 2
    df = 1 / (effective_n * dt)
    if unit == "Phase":
        angle = np.angle(z * np.exp(-2j * np.pi * freq * (t[0] - left * dt - reference_time - delay)))
        mag = np.rad2deg(np.unwrap(angle) if unwrap else angle)
        out_unit = "°"
    else:
        if source_unit != "V":
            unit = "Vrms"  # 衍生波形沒有電壓功率意義，只給來源有效值
        mag = magnitude(rms, unit, resistance)
        out_unit = source_unit + " rms" if unit == "Vrms" and source_unit != "V" else unit
    # 主瓣略過範圍沿用本工具的窗項數估計，補零時等比例放大；非手冊峰定義。
    return {"freq": freq, "mag": mag, "rms": rms, "unit": out_unit, "df": df,
            "lobe": int(np.ceil(len(WINDOWS[window_name]) * effective_n / n)),
            "enbw_bins": factor, "enbw": factor / (n * dt), "rbw": df * factor,
            "cg": float(w.mean()), "n": n, "effective_n": effective_n, "r_ohm": resistance,
            "power": rms ** 2 / resistance,
            "power_correction": effective_n / n * factor}


def _self_check() -> None:
    t = np.arange(16384) / 16384
    # 手冊未載明，採標準定義；允差是本工具驗證規格，非真機保證。
    # 五項 Flattop（原有 MATLAB 係數）ENBW≈3.77025；四項 BH≈2.00435。
    expected = {"Rectangular": 1., "Hanning": 1.5, "Hamming": 1.362826,
                "Blackman-Harris": 2.004353, "Flattop": 3.770246}
    # 半格 scalloping 上限（dB）：矩形 3.93、Hann 1.43、Hamming 1.76、BH 0.83、Flattop 0.02。
    loss = {"Rectangular": 3.93, "Hanning": 1.43, "Hamming": 1.76,
            "Blackman-Harris": 0.83, "Flattop": 0.02}
    for name in WINDOWS:
        for offset in (0., 0.5):
            s = spectrum(t, np.sqrt(2) * np.sin(2 * np.pi * (1000 + offset) * t), name, "Vrms")
            i = int(np.argmax(s['mag']))
            assert abs(s['freq'][i] - 1000 - offset) <= 0.501 * s['df']
            assert abs(20 * np.log10(s['mag'][i])) < (1e-6 if offset == 0 else loss[name])
            assert abs(s['enbw_bins'] - expected[name]) < 1e-5  # 解析值允差 0.00001 bin
            assert np.isclose(s['rbw'], s['df'] * expected[name], atol=1e-5)
        v = np.random.default_rng(7).normal(size=len(t)) + 0.5
        for count in (len(t), 10000):
            s = spectrum(t[:count], v[:count], name, "Watt")
            w = window(name, count)
            # Parseval：CG 校正譜平方和再除 power_correction = 加窗加權均方功率。
            assert np.isclose(sum(s['power']) / s['power_correction'],
                              sum((v[:count] * w) ** 2) / sum(w ** 2) / 50, rtol=1e-12)
    s = spectrum(t, np.sqrt(2) * np.sin(2 * np.pi * 1000 * t), "Rectangular")
    i = 1000
    assert abs(s['mag'][i] - 13.0102999566) < 1e-9
    for unit, value in (("dBV", 0.), ("dBmV", 60.), ("dBµV", 120.), ("Vrms", 1.), ("Watt", .02)):
        assert abs(magnitude(s['rms'], unit, 50)[i] - value) < 1e-9
    assert np.isclose(s['mag'][i] - magnitude(s['rms'], "dBV", 50)[i], 13.0102999566)
    levels = [magnitude(np.ones(1), "dBm", r)[0] for r in (25, 50, 100)]
    assert np.allclose(np.diff(levels), -10 * np.log10(2), atol=1e-12)
    for mode, r in (("single-ended", 50), ("differential", 100), ("common-mode", 25)):
        assert reference_impedance(None, "analog", channel_mode=mode) == r
    assert reference_impedance(None, "other", channel_mode="differential") == 50
    assert reference_impedance(None, "analog", channel_mode="single-ended", probe_kind="differential") == 50
    try:
        reference_impedance(None, "analog", channel_mode="common-mode", high_impedance=True)
        raise AssertionError("高阻抗探棒應拒絕共模")
    except ScopeError:
        pass
    for r in (10, 25, 50, 100, 200):
        assert reference_impedance(r) == r
    for r in (0, 9, 201, np.nan):
        try:
            reference_impedance(r)
            raise AssertionError("應拒絕錯誤阻抗")
        except ScopeError:
            pass
    v = .5 + np.sqrt(2) * np.sin(2 * np.pi * 1000 * t)
    s = spectrum(t, v, "Rectangular", "Watt")
    assert np.isclose(sum(s['power']), np.mean(v ** 2) / 50, rtol=1e-12)
    for name in WINDOWS:
        assert np.isclose(spectrum(t, np.ones(len(t)) * 2, name, "Vrms")['mag'][0], 2)
    dc = spectrum(t, np.ones(len(t)) * 2, "Rectangular", "Vrms")
    assert dc['mag'][0] == 2 and np.max(dc['mag'][1:]) == 0
    ny = spectrum(t, np.tile([1., -1.], len(t) // 2), "Rectangular", "Vrms")
    assert ny['mag'][-1] == 1
    p = spectrum(t[:10000], np.ones(10000), "Rectangular", "Vrms")
    assert p['effective_n'] == 16384 and p['mag'][0] == 1 and p['n'] == 10000
    # 非 2 冪次：明確鎖定補零頻格、RBW 與原始窗 ENBW 的不同分母。
    p = spectrum(np.arange(10000) / 1e6, np.ones(10000))
    assert p['effective_n'] == 16384 and np.isclose(p['df'], 61.03515625, rtol=1e-12)
    assert np.isclose(p['rbw'], 91.552734375, rtol=1e-12)
    assert np.isclose(p['enbw'], 150., rtol=1e-12) and np.isclose(p['enbw_bins'], 1.5)
    assert p['lobe'] == 4  # ceil(2×16384/10000)，不可沿用未補零的 2 格。
    for r, watts in ((50, .02), (100, .01)):
        assert magnitude(np.ones(1), "W", r)[0] == magnitude(np.ones(1), "Watt", r)[0] == watts
    assert spectrum(t, t, source_unit="V/s")['unit'] == "V/s rms"
    # 原長度非整數週期，左補零相位不能恰好繞整圈而漏測正負號。
    for count in (16384, 1001, 1023):
        times = t[:count] - .231
        phase = spectrum(times, np.cos(2 * np.pi * 1968 * times + .3), unit="Phase")
        k = int(np.argmin(abs(phase['freq'] - 1968)))
        assert phase['unit'] == "°" and abs(phase['mag'][k] - np.rad2deg(.3)) < 1e-4
    phase = spectrum(t, np.cos(2 * np.pi * 1024 * t + .3), "Rectangular", "Phase",
                     reference_time=1 / (8 * 1024), delay=1 / (8 * 1024))
    assert abs(phase['mag'][1024] - np.rad2deg(.3) - 90) < 1e-7
    unwrapped = spectrum(t, v, unit="Phase", unwrap=True)['mag']
    assert np.max(abs(np.diff(unwrapped))) <= 180 + 1e-8
    # 暫縮上限，避免自我檢查配置 16M 點；只超一點且來源仍有效，確實走點數限制。
    from unittest.mock import patch
    with patch(__name__ + ".MAX_POINTS", 1024):
        try:
            spectrum(t[:1025], v[:1025])
            raise AssertionError("應拒絕超過 FFT 點數上限")
        except ScopeError as exc:
            assert "超過上限" in str(exc)
    for bad in (lambda: spectrum(t, v, unit="Phase", reference_time=np.nan),
                lambda: spectrum(t[:1], t[:1]),
                lambda: spectrum(np.r_[t[:5], t[6:]], np.r_[v[:5], v[6:]])):
        try:
            bad()
            raise AssertionError("應拒絕不足點數／不等距來源")
        except ScopeError:
            pass
    print("analysis.fft self-check OK")


if __name__ == "__main__":
    _self_check()
