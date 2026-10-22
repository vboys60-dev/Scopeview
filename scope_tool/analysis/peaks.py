"""FFT 局部峰與排序，依 FFT_Magnitude 的 Peak Annotation。"""
from __future__ import annotations

import numpy as np

SORTS = ("Decreasing Magnitude", "Increasing Frequency", "Decreasing Frequency", "Increasing Magnitude")


def peaks(freq: np.ndarray, mag: np.ndarray, n: int = 5, start: int = 1, *,
          level: float = -np.inf, sort: str = SORTS[0],
          interpolate: bool = False, amplitude: np.ndarray | None = None) -> list[tuple[float, float]]:
    """嚴格高於 level 的局部峰；門檻與回傳振幅皆使用 mag 的單位。

    手冊未載明，採標準定義：平台取最左格，端點可為峰；同值峰由左至右。
    峰至少一側有實際下降；整條等值譜（含單格）不算峰，避免 RF 跳到假 DC。
    補零可解析出窗旁瓣局部峰；手冊未載明如何壓旁瓣，維持列峰，待真機比對。
    頻率內插為本工具做法：在 log 線性振幅上做三點拋物線，限制 ±半格；
    振幅保留原始峰格讀值，不以內插掩蓋 scalloping。amplitude 應傳線性有效值。
    """
    f, y = np.asarray(freq), np.asarray(mag)
    if f.ndim != 1 or y.shape != f.shape or not np.isfinite(f).all() or not np.isfinite(y).all():
        raise ValueError("峰值來源必須為等長有限一維陣列")
    if np.any(np.diff(f) <= 0) or sort not in SORTS or n < 0 or np.isnan(level):
        raise ValueError("峰值頻率、排序、數量或門檻無效")
    a = y if amplitude is None else np.asarray(amplitude)
    if interpolate and (a.shape != y.shape or not np.isfinite(a).all() or np.any(a < 0)):
        raise ValueError("內插需要等長非負線性振幅")
    if not len(y) or n == 0 or np.all(y == y[0]):
        return []
    starts = np.r_[0, np.flatnonzero(y[1:] != y[:-1]) + 1]
    heights = y[starts]
    # 平台必須比兩側都高；平台後還在上升時不算局部峰。
    idx = starts[(heights > np.r_[-np.inf, heights[:-1]]) &
                 (heights > np.r_[heights[1:], -np.inf]) & (heights > level)]
    idx = idx[idx >= max(0, start)]
    # 穩定排序確保同值峰仍由左至右，不將完整頻譜轉成 Python 物件排序。
    values = {SORTS[0]: -y[idx], SORTS[1]: f[idx], SORTS[2]: -f[idx], SORTS[3]: y[idx]}[sort]
    idx = idx[np.argsort(values, kind="stable")[:n]]
    out = []
    for i in idx:
        x = float(f[i])
        if interpolate and 0 < i < len(y) - 1 and np.all(a[i - 1:i + 2] > 0):
            l, c, r = np.log(a[i - 1:i + 2])
            den = l - 2 * c + r
            if den < 0:
                x += float(np.clip(0.5 * (l - r) / den, -0.5, 0.5)) * (f[i + 1] - f[i])
        out.append((float(x), float(y[i])))
    return out


def _self_check() -> None:
    from scope_tool.analysis.fft import spectrum

    f, y = np.arange(9.), np.array([0., 3., 0., 5., 0., 3., 0., 1., 0.])
    assert [x for x, _ in peaks(f, y)] == [3, 1, 5, 7]
    assert [x for x, _ in peaks(f, y, sort=SORTS[1])] == [1, 3, 5, 7]
    assert [x for x, _ in peaks(f, y, sort=SORTS[2])] == [7, 5, 3, 1]
    assert [x for x, _ in peaks(f, y, sort=SORTS[3])] == [7, 1, 5, 3]
    assert peaks(f, y, 1, level=3) == [(3., 5.)] and not peaks(f, y, 0)
    assert peaks(np.arange(4.), np.array([0., 2., 2., 0.])) == [(1., 2.)]
    assert peaks(np.arange(5.), np.array([0., 2., 2., 3., 0.])) == [(3., 3.)]
    # 端點可為峰，預設 start=1 僅略過首格；整條等值譜則沒有實際下降。
    assert peaks(np.arange(3.), np.array([3., 0., 2.]), start=0) == [(0., 3.), (2., 2.)]
    assert peaks(np.arange(3.), np.array([3., 0., 2.])) == [(2., 2.)]
    for size in (1, 5):
        assert not peaks(np.arange(float(size)), np.zeros(size), start=0)
    # mag 決定峰格，amplitude 決定內插；刻意分開以測到夾限與凸向拒絕。
    f3, y3 = np.arange(3.), np.array([0., 2., 0.])
    for logs, expected_x in (([0., 2., 3.], 1.5), ([3., 2., 0.], .5),
                             ([0., -2., 1.], 1.)):
        assert peaks(f3, y3, interpolate=True, amplitude=np.exp(logs)) == [(expected_x, 2.)]
    # 零鄰格不可取 log；以浮點例外確保即使 NaN 被後續略過也抓得到。
    with np.errstate(divide="raise", invalid="raise"):
        assert peaks(f3, y3, interpolate=True, amplitude=np.array([0., 2., 1.])) == [(1., 2.)]
    t = np.arange(16384) / 16384
    tones = [100.23, 600.37, 1700.41]
    s = spectrum(t, sum(np.sin(2 * np.pi * x * t) for x in tones), unit="Vrms")
    p = peaks(s['freq'], s['mag'], 3, level=0.4, sort=SORTS[1],
              interpolate=True, amplitude=s['rms'])
    assert len(p) == 3 and np.all(np.abs(np.array(p)[:, 0] - tones) < s['rbw'] / 10)
    # 非 2 冪次長度也驗證：補零後頻格較密，頻率誤差仍須小於 RBW/10。
    s = spectrum(t[:10000], sum(np.sin(2 * np.pi * x * t[:10000]) for x in tones), unit="Vrms")
    p = peaks(s['freq'], s['mag'], 3, level=.4, sort=SORTS[1], interpolate=True, amplitude=s['rms'])
    assert len(p) == 3 and np.all(np.abs(np.array(p)[:, 0] - tones) < s['rbw'] / 10)
    print("analysis.peaks self-check OK")


if __name__ == "__main__":
    _self_check()
