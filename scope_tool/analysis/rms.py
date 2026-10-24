"""整段等權 RMS：有限浮點輸入一律以 2 冪縮放。"""
from __future__ import annotations

import numpy as np


def rms_dc(v: np.ndarray) -> float:
    """含直流分量；縮放後平方，避免極端尺度溢位／下溢。"""
    a = np.max(np.abs(v))
    if a == 0:
        return 0.0
    _, e = np.frexp(a)
    y = np.ldexp(v, -e)
    return float(np.ldexp(np.sqrt(np.mean(y * y)), e))


def rms_ac(v: np.ndarray) -> float:
    """先縮放再扣同段平均，避免平均／相減先溢位。"""
    a = np.max(np.abs(v))
    if a == 0:
        return 0.0
    _, e = np.frexp(a)
    y = np.ldexp(v, -e)
    z = y - y.mean()
    return float(np.ldexp(np.sqrt(np.mean(z * z)), e))


def _self_check() -> None:
    from decimal import Decimal, localcontext

    def old_dc(v: np.ndarray) -> float:
        return float(np.sqrt(np.mean(v ** 2)))

    def old_ac(v: np.ndarray) -> float:
        return float(np.sqrt(np.mean((v - v.mean()) ** 2)))

    rng = np.random.default_rng(20261024)
    for i in range(1000):
        n, scale = int(rng.integers(2, 10001)), 10.0 ** rng.uniform(-6, 6)
        x = np.arange(n) / n
        signals = (np.full(n, -scale), scale * np.sin(2 * np.pi * x * 7),
                   scale * np.where(x % 0.1 < 0.025, 1., -0.5), scale * (2 + rng.normal(size=n)))
        v = signals[i % 4]
        for helper, old in ((rms_dc, old_dc), (rms_ac, old_ac)):
            got, expected = np.float64(helper(v)), np.float64(old(v))
            assert got.view(np.uint64) == expected.view(np.uint64), (i, n, scale, helper.__name__, got, expected)
    # 負值主導（max(v)≤0）：擋 max(abs(v)) 被誤改成 max(v)。
    for v in (np.zeros(7), np.full(7, -0.0), np.array([-1., -2., -3.]), np.array([-2., 0., 0.])):
        for helper, old in ((rms_dc, old_dc), (rms_ac, old_ac)):
            assert np.float64(helper(v)).view(np.uint64) == np.float64(old(v)).view(np.uint64)
    print("RMS uint64 regression: 1000 groups + zero/negative, differences=0")

    def reference(v: np.ndarray, ac: bool, precision: int) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = precision
            values = [Decimal.from_float(float(x)) for x in v]
            avg = sum(values) / len(values) if ac else Decimal(0)
            return (sum((x - avg) ** 2 for x in values) / len(values)).sqrt()

    smallest = Decimal.from_float(float(np.nextafter(0., 1.)))
    max_relative = normal_relative = Decimal(0)

    def verify(v: np.ndarray, ac: bool, constant: bool = False) -> None:
        nonlocal max_relative, normal_relative
        ref, finer = reference(v, ac, 1600), reference(v, ac, 2400)
        assert float(ref) == float(finer), ("Decimal 未收斂", v, ac)
        got = (rms_ac if ac else rms_dc)(v)
        assert np.isfinite(got), (v, ac, got)
        with localcontext() as ctx:
            ctx.prec = 2400
            assert ref == finer or abs(ref - finer) <= abs(finer) * Decimal("1e-150")
            error = abs(Decimal.from_float(got) - finer)
            bound = Decimal.from_float(float(np.max(np.abs(v)))) if constant else finer
            tolerance = Decimal('5e-15') * bound
            assert error <= (tolerance if constant else max(tolerance, smallest)), (v, ac, got, finer, error)
            if finer and not constant:
                max_relative = max(max_relative, error / finer)
                if finer >= Decimal.from_float(float(np.finfo(np.float64).tiny)):
                    normal_relative = max(normal_relative, error / finer)
            if not ac and finer >= smallest:
                assert got > 0

    for a in (1e200, 1e-200):
        for v in (np.array([a, a]), np.array([-a, a])):
            verify(v, False)
        verify(np.array([-a, a]), True)
        for sign in (-1, 1):
            for n in (7, 9999):
                verify(np.full(n, sign * a), True, True)
    for v in (np.array([1e200, 1e-200]), np.array([1e-200, 0.]), np.r_[1e200, np.zeros(9999)]):
        verify(v, False)
        verify(v, True)
    # 指數切換點兩側含正常／次正常邊界及近最大有限值。
    for e in (-1073, -1022, -665, -1, 0, 1, 665, 1023):
        a = np.ldexp(1., e)
        for b in (np.nextafter(a, 0.), a, np.nextafter(a, np.inf)):
            for v in (np.array([b, 0., -b]), np.full(7, b)):
                verify(v, False)
                verify(v, True, bool(np.all(v == v[0])))
    for a in (np.nextafter(0., 1.), np.finfo(np.float64).max, np.nextafter(np.finfo(np.float64).max, 0.)):
        verify(np.full(7, a), False)
        verify(np.full(7, a), True, True)
    for flag in (False, True):
        verify(np.array([-1e200, 1e-200]), flag)  # 負值主導的極端尺度，舊公式會溢位
    a = np.ldexp(1., 660)
    # 對稱擾動使平均可精確表示；不對稱擾動受平均值捨入限制，只保證相對 |a| 的誤差（舊公式相同）。
    verify(a + np.spacing(a) * np.array([-8., -4., -2., 0., 2., 4., 8.]), True)
    print(f"RMS extreme max relative error: {max_relative:.6E} (subnormal absolute tolerance applies)")
    print(f"RMS normal-result max relative error: {normal_relative:.6E}")
    print("rms self-check OK")


if __name__ == "__main__":
    _self_check()
