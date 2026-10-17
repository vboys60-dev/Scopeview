"""FFT 頻譜（依 Infiniium 手冊 FFT_Magnitude、FFT_Magnitude_Vertical_Units、FFT_Theory）。

與 Infiniium 的差異（畫面要標明）：不補零到 2 的次方，直接用範圍內全部點數；
頻格 Δf = 1/(N·dt)，ENBW = Δf × N·Σw²/(Σw)²。振幅以 |rfft(v·w)|/Σw 換成弦波有效值。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis.measure import uniform_dt, validate
from scope_tool.contracts import ScopeError

MAX_POINTS = 2 ** 24
# 餘弦和視窗係數：w[n] = Σ (-1)^k a_k cos(2πkn/N)。Flattop 用 MATLAB flattopwin 係數。
WINDOWS: dict[str, tuple[float, ...]] = {
    "Hanning": (0.5, 0.5),
    "Flattop": (0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368),
    "Rectangular": (1.0,),
    "Hamming": (0.54, 0.46),
    "Blackman-Harris": (0.35875, 0.48829, 0.14128, 0.01168),
}
UNITS = ("dBm", "Vrms", "dBV", "dBmV", "dBµV", "W")
_FLOOR = 1e-20  # 避免 log(0)


def window(name: str, n: int) -> np.ndarray:
    x = 2 * np.pi * np.arange(n) / n
    return sum((-1) ** k * a * np.cos(k * x) for k, a in enumerate(WINDOWS[name]))


def spectrum(t: np.ndarray, v: np.ndarray, window_name: str = "Hanning", unit: str = "dBm",
             r_ohm: float = 50.0, source_unit: str = "V") -> dict:
    """回傳 {freq, mag, unit, df, enbw, n}；mag 已換成指定單位（非 V 來源只給線性有效值）。"""
    validate(t, v)
    if len(v) > MAX_POINTS:
        raise ScopeError(f"FFT 點數 {len(v):,} 超過上限 {MAX_POINTS:,}，請縮小游標區間。")
    if r_ohm <= 0:
        raise ScopeError("參考阻抗必須大於 0。")
    dt = uniform_dt(t)
    n = len(v)
    w = window(window_name, n)
    spec = np.abs(np.fft.rfft(v * w)) / w.sum()
    rms = spec * np.sqrt(2)
    rms[0] = spec[0]  # 直流的有效值就是本身
    if n % 2 == 0:
        rms[-1] = spec[-1]  # Nyquist 格同理
    rms = np.maximum(rms, _FLOOR)
    if source_unit != "V":
        unit = "Vrms"  # 衍生波形（V²、V/s…）沒有功率意義，只給有效值
    mag = {"Vrms": lambda: rms, "dBV": lambda: 20 * np.log10(rms),
           "dBmV": lambda: 20 * np.log10(rms / 1e-3), "dBµV": lambda: 20 * np.log10(rms / 1e-6),
           "W": lambda: rms ** 2 / r_ohm, "dBm": lambda: 10 * np.log10(rms ** 2 / r_ohm / 1e-3)}[unit]()
    df = 1 / (n * dt)
    out_unit = source_unit + " rms" if unit == "Vrms" and source_unit != "V" else unit
    # lobe：視窗主瓣半寬（格數），找峰值時跳過直流主瓣，避免直流洩漏被當成峰。
    return {"freq": np.fft.rfftfreq(n, dt), "mag": mag, "unit": out_unit, "df": df,
            "lobe": len(WINDOWS[window_name]), "enbw": df * n * float(np.sum(w ** 2)) / float(w.sum()) ** 2, "n": n}


def peaks(freq: np.ndarray, mag: np.ndarray, n: int = 5, start: int = 1) -> list[tuple[float, float]]:
    """從第 start 格起最大的 n 個局部峰，依大小排序。"""
    m = np.concatenate(([-np.inf], mag, [-np.inf]))  # 兩端補 -inf，Nyquist 端點也能當峰
    idx = np.flatnonzero((m[1:-1] > m[:-2]) & (m[1:-1] >= m[2:]))
    idx = idx[idx >= start]
    idx = idx[np.argsort(mag[idx])[::-1][:n]]
    return [(float(freq[i]), float(mag[i])) for i in idx]


def _self_check() -> None:
    dt = 1e-6
    t = np.arange(10000) * dt
    # 1 V 峰值、1.03 kHz（不落在頻格上）＋ 0.1 V、7 kHz ＋ 0.5 V 直流
    v = np.sin(2 * np.pi * 1030 * t) + 0.1 * np.sin(2 * np.pi * 7000 * t) + 0.5
    s = spectrum(t, v, "Flattop", "Vrms")
    assert abs(s["df"] - 100) < 1e-9 and s["n"] == 10000
    (f1, m1), (f2, m2) = peaks(s["freq"], s["mag"], 2, s["lobe"])
    assert abs(f1 - 1000) <= 100 and abs(m1 - 1 / np.sqrt(2)) < 0.01 * m1
    assert f2 == 7000 and abs(m2 - 0.1 / np.sqrt(2)) < 0.01 * m2
    assert abs(s["mag"][0] - 0.5) < 0.01
    h = spectrum(t, v, "Hanning", "dBV")
    assert peaks(h["freq"], h["mag"], 1)[0][0] == 1000
    assert abs(h["enbw"] / h["df"] - 1.5) < 1e-3  # Hanning ENBW = 1.5 格
    r = spectrum(t, np.sin(2 * np.pi * 1000 * t), "Rectangular", "dBm")
    i = int(np.argmax(r["mag"]))
    assert abs(r["mag"][i] - 10 * np.log10(0.5 / 50 / 1e-3)) < 1e-6  # 1 V 峰值弦波 = 10 dBm（50 Ω）
    assert abs(spectrum(t, np.sin(2 * np.pi * 1000 * t), "Rectangular", "W")["mag"][i] - 0.01) < 1e-9
    d = spectrum(t, v, "Hanning", "dBm", source_unit="V/s")
    assert d["unit"] == "V/s rms" and abs(np.max(d["mag"][1:]) - 0.7) < 0.1
    alt = spectrum(t[:1024], np.tile([1.0, -1.0], 512), "Rectangular", "Vrms")
    assert peaks(alt["freq"], alt["mag"], 1, 1) == [(500e3, 1.0)]  # Nyquist 格
    for name in WINDOWS:
        assert len(window(name, 8)) == 8
    for bad in (lambda: spectrum(t, v, r_ohm=0), lambda: spectrum(np.r_[t[:5], t[6:]], np.r_[v[:5], v[6:]])):
        try:
            bad()
            raise AssertionError("應該丟出 ScopeError")
        except ScopeError:
            pass
    print("analysis.fft self-check OK")


if __name__ == "__main__":
    _self_check()
