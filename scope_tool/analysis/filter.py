"""濾波（依 Infiniium 手冊 Low_Pass_Filter、High_Pass_Filter、Smoothing）。

低通：4 階 Bessel-Thompson，H = 105 / P(j·k·f/fc)，P(s)=s⁴+10s³+45s²+105s+105，
k=2.113917675 使 -3 dB 落在 fc；已補償 DC 群延遲，濾波後波形不會相對原始通道往後移
（手冊沒說原廠是否補償，# 待真機驗證）。高通：單極 jf/(jf+fc)。平滑：N 點移動平均。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis.measure import uniform_dt, validate
from scope_tool.contracts import ScopeError

_BESSEL_K = 2.113917675


def _bessel4(f: np.ndarray, fc: float) -> np.ndarray:
    s = 1j * _BESSEL_K * f / fc
    return 105 / (s ** 4 + 10 * s ** 3 + 45 * s ** 2 + 105 * s + 105) * np.exp(1j * _BESSEL_K * f / fc)


def _apply(t: np.ndarray, v: np.ndarray, fc: float, lowpass: bool) -> np.ndarray:
    validate(t, v)
    dt = uniform_dt(t)
    if not 0 < fc < 0.5 / dt:
        raise ScopeError("截止頻率必須介於 0 與取樣率的一半之間。")
    # 頻域相乘是循環摺積，兩端以邊值補長（約 4/fc）吸收暫態。
    required = max(np.ceil(4 / (fc * dt)), 16)
    if required > len(v):
        message = "記錄太短，請取更長記錄。" if len(v) < 16 else "記錄太短，邊界效應過大，請取更長記錄或提高截止頻率。"
        raise ScopeError(message)
    pad = int(required)
    x = np.pad(v, pad, mode="edge")
    f = np.fft.rfftfreq(len(x), dt)
    h = _bessel4(f, fc) if lowpass else 1j * f / (1j * f + fc)
    return np.fft.irfft(np.fft.rfft(x) * h, len(x))[pad:pad + len(v)]


def lowpass(t: np.ndarray, v: np.ndarray, fc: float) -> np.ndarray:
    return _apply(t, v, fc, True)


def highpass(t: np.ndarray, v: np.ndarray, fc: float) -> np.ndarray:
    return _apply(t, v, fc, False)


def smooth(t: np.ndarray, v: np.ndarray, n: float) -> tuple[np.ndarray, np.ndarray]:
    """等距取樣的整數 N 點移動平均；只輸出完整視窗，時間取中心，少 N-1 點。"""
    validate(t, v)
    uniform_dt(t)
    if not np.isfinite(n) or n != int(n):
        raise ScopeError("平滑點數必須為整數。")
    n = int(n)
    if not 2 <= n <= len(v):
        raise ScopeError("平滑點數必須介於 2 與資料點數之間。")
    c = np.concatenate(([0.0], np.cumsum(v, dtype=np.float64)))
    return (t[:len(v) - n + 1] + t[n - 1:]) / 2, (c[n:] - c[:-n]) / n


def _self_check() -> None:
    assert abs(abs(_bessel4(np.array([1.0]), 1.0)[0]) ** 2 - 0.5) < 1e-6  # -3 dB 在 fc
    dt = 1e-6
    t = np.arange(50000) * dt

    def gain(fn, f: float, fc: float) -> float:
        y = fn(t, np.sin(2 * np.pi * f * t), fc)[5000:15000]
        return float(np.sqrt(2 * np.mean(y ** 2)))

    assert abs(gain(lowpass, 1e3, 1e3) - np.sqrt(0.5)) < 0.01
    assert gain(lowpass, 100, 10e3) > 0.999 and gain(lowpass, 100e3, 1e3) < 1e-3
    assert abs(gain(highpass, 1e3, 1e3) - np.sqrt(0.5)) < 0.01
    assert gain(highpass, 100e3, 100) > 0.999 and gain(highpass, 100, 100e3) < 0.002
    # 群延遲已補償：低頻弦波濾波後與原波形同相
    x = np.sin(2 * np.pi * 1e3 * t)
    assert np.max(np.abs(lowpass(t, x, 50e3) - x)[1000:-1000]) < 1e-3
    # 直流通過低通、被高通擋掉；邊值補長讓兩端沒有大暫態
    assert np.allclose(lowpass(t, np.full_like(t, 3.0), 1e3), 3.0, atol=1e-6)
    assert np.allclose(highpass(t, np.full_like(t, 3.0), 1e3), 0.0, atol=1e-6)
    ts, vs = smooth(t[:10], np.arange(10.0), 4)
    assert len(vs) == 7 and np.allclose(vs, np.arange(1.5, 8.5)) and np.allclose(ts, t[:7] + 1.5 * dt)
    for fn in (lowpass, highpass):
        assert len(fn(np.arange(16.), np.ones(16), .25)) == 16
        for times, values, fc, message in (
                (t[:100], x[:100], 1e3, "記錄太短，邊界效應過大，請取更長記錄或提高截止頻率。"),
                (np.arange(15.), np.ones(15), .4, "記錄太短，請取更長記錄。")):
            try:
                fn(times, values, fc)
                raise AssertionError("應拒絕補長量超過原長")
            except ScopeError as exc:
                assert str(exc) == message
    for bad in (lambda: lowpass(t, x, 0.6 / dt), lambda: smooth(t, x, 1),
                lambda: smooth(t, x, 3.9), lambda: smooth(t, x, np.nan),
                lambda: smooth(t, x, np.inf),
                lambda: smooth(np.array([0., 1., 3.]), np.ones(3), 2),
                lambda: lowpass(np.r_[t[:5], t[6:]], np.r_[x[:5], x[6:]], 1e3)):
        try:
            bad()
            raise AssertionError("應該丟出 ScopeError")
        except ScopeError:
            pass
    print("analysis.filter self-check OK")


if __name__ == "__main__":
    _self_check()
