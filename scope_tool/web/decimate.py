"""波形／頻譜降採樣：min/max 包絡 + 二進位編碼（契約第 4 節，/wave 與 /fft 共用）。

純 numpy、無 I/O、不碰儀器。降採樣只供視覺預覽；量測與 FFT 一律用原始資料。
- 範圍內點數 ≤ 2·px：原始模式（mode=0），前後各多帶一點讓折線接到視窗邊緣，故 n ≤ 2·px+2。
- 否則包絡模式（mode=1）：px 個桶，x＝桶起點，lo／hi＝桶內 min／max。
- NaN：np.minimum／maximum.reduceat 語義，桶內含 NaN → 該桶 lo／hi 皆 NaN；二進位保留 NaN。
- >1M 點的通道可建單層 factor-1024 金字塔；桶邊界貼齊 1024 倍數，結果與暴力解逐桶相同。
"""
from __future__ import annotations

import struct

import numpy as np

PX_MAX = 16384
MAX_POINTS = 32768        # 單通道單次回傳上限
BLOCK = 1024              # 金字塔縮減倍率
PYRAMID_MIN = 1_000_000   # 超過此點數才建金字塔
_HEADER = struct.Struct("<4I")


class Pyramid:
    """單層金字塔：每 BLOCK 點一格的 min／max（尾端不足一格者自成一格）。"""

    def __init__(self, y: np.ndarray) -> None:
        starts = np.arange(0, len(y), BLOCK)
        self.n = len(y)
        self.lo = np.minimum.reduceat(y, starts)
        self.hi = np.maximum.reduceat(y, starts)


def _check_px(px: int) -> int:
    if int(px) != px or not 1 <= px <= PX_MAX:
        raise ValueError(f"px 必須是 1 ~ {PX_MAX} 的整數")
    return int(px)


def edges_linear(a: int, b: int, nb: int, pyr_n: int | None = None) -> np.ndarray:
    """[a,b) 切成至多 nb 個桶的原始索引邊界（含兩端）。給 pyr_n 且桶夠大時，內部邊界貼齊 BLOCK 倍數。"""
    if pyr_n is not None and (b - a) >= 4 * BLOCK * nb:
        ia = -(-a // BLOCK)
        ib = -(-pyr_n // BLOCK) if b == pyr_n else b // BLOCK
        if ib - ia >= nb:
            k = np.unique(np.rint(np.linspace(ia, ib, nb + 1)).astype(np.int64))
            e = np.minimum(k * BLOCK, pyr_n)
            e[0], e[-1] = a, b
            if len(e) >= 2 and np.all(np.diff(e) > 0):
                return e
    return np.unique(np.linspace(a, b, nb + 1).astype(np.int64))


def edges_log(f: np.ndarray, a: int, b: int, nb: int) -> np.ndarray:
    """對數等距切 f[a:b]（f[a]>0）；低頻桶不足一格者併掉（unique）。"""
    cut = np.searchsorted(f, np.geomspace(f[a], f[b - 1], nb + 1), side="left")
    return np.unique(np.concatenate(([a], np.clip(cut, a, b), [b])))


def reduce_raw(y: np.ndarray, e: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seg = y[e[0]:e[-1]]
    idx = e[:-1] - e[0]
    return np.minimum.reduceat(seg, idx), np.maximum.reduceat(seg, idx)


def reduce_pyr(y: np.ndarray, p: Pyramid, e: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """e 須來自 edges_linear(..., pyr_n=p.n) 的貼齊結果；頭尾不足一格的部分用原始資料補。"""
    a, b = int(e[0]), int(e[-1])
    ia = -(-a // BLOCK)
    ib = -(-p.n // BLOCK) if b == p.n else b // BLOCK
    k = np.concatenate(([ia], e[1:-1] // BLOCK, [ib]))
    lo = np.minimum.reduceat(p.lo[ia:ib], k[:-1] - ia)
    hi = np.maximum.reduceat(p.hi[ia:ib], k[:-1] - ia)
    if a < ia * BLOCK:  # 頭
        lo[0], hi[0] = np.minimum(lo[0], y[a:ia * BLOCK].min()), np.maximum(hi[0], y[a:ia * BLOCK].max())
    if b < p.n and b > ib * BLOCK:  # 尾
        lo[-1], hi[-1] = np.minimum(lo[-1], y[ib * BLOCK:b].min()), np.maximum(hi[-1], y[ib * BLOCK:b].max())
    return lo, hi


def _build(x: np.ndarray, y: np.ndarray, a0: int, b0: int, lo_clamp: int, px: int,
           mk_edges, pyr: Pyramid | None) -> tuple[int, np.ndarray, np.ndarray, np.ndarray]:
    if b0 - a0 <= 2 * px:
        a, b = max(a0 - 1, lo_clamp), min(b0 + 1, len(x))
        return 0, x[a:b], y[a:b], y[a:b]
    e = mk_edges(a0, b0, px, pyr)
    lo, hi = reduce_pyr(y, pyr, e) if pyr is not None and e[1:-1].size and np.all(e[1:-1] % BLOCK == 0) \
        and (b0 - a0) >= 4 * BLOCK * px else reduce_raw(y, e)
    return 1, x[e[:-1]], lo, hi


def encode(mode: int, x: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> bytes:
    """16-byte header + float64 x（位移 16）+ float32 lo（16+8n）+ float32 hi（16+12n）。"""
    n = len(x)
    return (_HEADER.pack(n, mode, 0, 0) + np.ascontiguousarray(x, "<f8").tobytes()
            + np.ascontiguousarray(lo, "<f4").tobytes() + np.ascontiguousarray(hi, "<f4").tobytes())


def decode(buf: bytes) -> tuple[int, int, np.ndarray, np.ndarray, np.ndarray]:
    n, mode, r1, r2 = _HEADER.unpack_from(buf, 0)
    if r1 or r2 or mode not in (0, 1) or len(buf) != 16 + 16 * n:
        raise ValueError("二進位格式錯誤")
    return (n, mode, np.frombuffer(buf, "<f8", n, 16), np.frombuffer(buf, "<f4", n, 16 + 8 * n),
            np.frombuffer(buf, "<f4", n, 16 + 12 * n))


def wave(x: np.ndarray, y: np.ndarray, t0: float, t1: float, px: int, pyr: Pyramid | None = None) -> bytes:
    """x＝來源時間（遞增）；t0／t1 可反序。"""
    px = _check_px(px)
    t0, t1 = sorted((float(t0), float(t1)))
    a0, b0 = int(np.searchsorted(x, t0, "left")), int(np.searchsorted(x, t1, "right"))
    return encode(*_build(x, y, a0, b0, 0, px,
                          lambda a, b, nb, p: edges_linear(a, b, nb, p.n if p is not None else None), pyr))


def spectrum(f: np.ndarray, y: np.ndarray, f0: float, f1: float, px: int, log: bool) -> bytes:
    """log=True：f0>0，對數等距分桶，x 排除 0 Hz；仍回傳 Hz。"""
    px = _check_px(px)
    f0, f1 = sorted((float(f0), float(f1)))
    if log and not f0 > 0:
        raise ValueError("對數頻率軸的 f0 必須 > 0")
    first = int(np.searchsorted(f, 0, "right")) if log else 0  # 對數軸排除 0 Hz
    a0 = max(int(np.searchsorted(f, f0, "left")), first)
    b0 = max(int(np.searchsorted(f, f1, "right")), a0)
    mk = (lambda a, b, nb, p: edges_log(f, a, b, nb)) if log else (lambda a, b, nb, p: edges_linear(a, b, nb))
    return encode(*_build(f, y, a0, b0, first, px, mk, None))


def _self_check() -> None:
    rng = np.random.default_rng(1)
    # 小資料：原始模式，前後各帶一點
    x = np.arange(100) * 1e-3
    y = rng.normal(size=100)
    n, mode, dx, lo, hi = decode(wave(x, y, 0.010, 0.020, 50))
    assert mode == 0 and n == 13 and np.array_equal(dx, x[9:22]) and np.array_equal(lo, y[9:22].astype("f4")) \
        and np.array_equal(lo, hi)
    assert decode(wave(x, y, 0.020, 0.010, 50))[2].tolist() == dx.tolist()  # 反序等價
    assert decode(wave(x, y, 5, 6, 10))[0] == 1  # 完全在右側：只帶最後一點
    assert decode(wave(x[:0], y[:0], 0, 1, 10))[0] == 0
    # 包絡 vs 暴力解
    N = 200_000
    x = np.arange(N) * 1e-6
    y = rng.normal(size=N)
    n, mode, dx, lo, hi = decode(wave(x, y, 0.01, 0.15, 500))
    assert mode == 1 and n == 500 and n <= 2 * 500 + 2
    a, b = np.searchsorted(x, 0.01, "left"), np.searchsorted(x, 0.15, "right")
    e = np.unique(np.linspace(a, b, 501).astype(np.int64))
    assert np.array_equal(dx, x[e[:-1]])
    assert np.array_equal(lo, np.minimum.reduceat(y[a:b], e[:-1] - a).astype("f4"))
    assert np.array_equal(hi, np.maximum.reduceat(y[a:b], e[:-1] - a).astype("f4"))
    # NaN 桶：只有含 NaN 的桶為 NaN，沒有 ±inf
    y2 = y.copy()
    y2[50_000] = np.nan
    _, _, _, lo, hi = decode(wave(x, y2, 0, 1, 100))
    bad = np.flatnonzero(np.isnan(lo))
    assert len(bad) == 1 and np.array_equal(np.isnan(lo), np.isnan(hi)) and not np.isinf(lo).any() \
        and not np.isinf(hi).any()
    # px／上限
    for badpx in (0, 16385, 1.5):
        try:
            wave(x, y, 0, 1, badpx)
            raise AssertionError("px 應被拒絕")
        except ValueError:
            pass
    big = np.arange(1_000_000) * 1.0
    n, mode, *_ = decode(wave(big, big, 0, 1e6, PX_MAX))
    assert n <= MAX_POINTS and n <= 2 * PX_MAX + 2
    n, mode, *_ = decode(wave(big, big, 0, 20000, PX_MAX))
    assert mode == 0 and n <= 2 * PX_MAX + 2
    # 金字塔 vs 暴力解（含 NaN、頭尾不貼齊、尾端不足一格）
    M = 1_300_517
    xb = np.arange(M) * 1e-7
    yb = rng.normal(size=M)
    yb[777_777] = np.nan
    p = Pyramid(yb)
    for t0, t1, px in ((1e-3, 0.12, 40), (0.0, M * 1e-7, 100), (0.02, M * 1e-7, 30), (0.0, 0.1, 7)):
        a, b = int(np.searchsorted(xb, t0, "left")), int(np.searchsorted(xb, t1, "right"))
        e = edges_linear(a, b, px, M)
        assert (b - a) >= 4 * BLOCK * px and np.all(e[1:-1] % BLOCK == 0), (t0, t1, px)
        plo, phi = reduce_pyr(yb, p, e)
        rlo, rhi = reduce_raw(yb, e)
        assert np.array_equal(plo, rlo, equal_nan=True) and np.array_equal(phi, rhi, equal_nan=True)
        fast = decode(wave(xb, yb, t0, t1, px, p))
        slow = decode(wave(xb, yb, t0, t1, px, None))  # 無金字塔走均分邊界，桶數相同、NaN 桶一致
        assert fast[0] == len(e) - 1 and fast[1] == 1 and slow[1] == 1
        assert np.array_equal(fast[3], rlo.astype("f4"), equal_nan=True)
    # 位移對齊與 frombuffer 往返
    buf = encode(1, np.arange(7.0), np.arange(7, dtype="f4"), np.arange(7, dtype="f4") + 1)
    assert len(buf) == 16 + 16 * 7 and (16 % 8 == 0) and (16 + 8 * 7) % 4 == 0 and (16 + 12 * 7) % 4 == 0
    n, mode, dx, lo, hi = decode(buf)
    assert n == 7 and mode == 1 and dx.dtype == np.float64 and lo.dtype == np.float32 and hi[0] == 1
    # 頻譜：線性與對數
    f = np.fft.rfftfreq(1 << 20, 1e-6)
    s = rng.normal(size=len(f))
    n, mode, dx, lo, hi = decode(spectrum(f, s, 0, f[-1], 1000, False))
    assert mode == 1 and n == 1000 and dx[0] == 0
    n, mode, dx, lo, hi = decode(spectrum(f, s, 1.0, f[-1], 1000, True))
    assert mode == 1 and 1 < n <= 1000 and dx[0] > 0 and np.all(np.diff(dx) > 0)
    r = np.diff(np.log(dx[len(dx) // 2:]))
    assert r.std() < 0.2 * r.mean()  # 高頻段桶寬近似對數等距
    try:
        spectrum(f, s, 0, 10, 10, True)
        raise AssertionError("log 需 f0>0")
    except ValueError:
        pass
    assert decode(spectrum(f, s, 0.5 * f[1], 3 * f[1], 100, True))[2][0] == f[1]  # 排除 0 Hz
    print("decimate self-check OK")


if __name__ == "__main__":
    _self_check()
