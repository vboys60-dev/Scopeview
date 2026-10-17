"""數學函式（依 Infiniium 手冊 Math_Functions_Setup、Add/Subtract/Multiply/Divide、Differentiate、Integrate…）。

兩個來源時間軸不同時，只取重疊區間，B 線性內插到 A 的取樣點（不外插）。
log10 以 1 個單位為參考，結果無單位。除以 0、負數開根號、非正數取 log 得 NaN。
"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis import filter as flt
from scope_tool.analysis.measure import validate
from scope_tool.contracts import ScopeError

BINARY = ("加", "減", "乘", "除")
UNARY = ("反相", "絕對值", "平方", "開根號", "log10", "微分", "積分")
FILTERS = ("低通", "高通", "平滑")
OPERATIONS = BINARY + UNARY + FILTERS
SYMBOLS = {"加": "+", "減": "−", "乘": "×", "除": "÷"}


def _wrap(u: str) -> str:
    return f"({u})" if any(c in u for c in "/·²√") else u


def _square(u: str) -> str:
    return f"{_wrap(u)}²" if u else ""


def _mul(a: str, b: str) -> str:
    return _square(a) if a == b else a if not b else b if not a else f"{_wrap(a)}·{_wrap(b)}"


def _div(a: str, b: str) -> str:
    return "" if a == b else a if not b else f"{_wrap(a) or '1'}/{_wrap(b)}"


def _overlap(ta: np.ndarray, va: np.ndarray, tb: np.ndarray, vb: np.ndarray) -> tuple[np.ndarray, ...]:
    if len(ta) == len(tb) and np.array_equal(ta, tb):
        return ta, va, vb
    sel = (ta >= max(ta[0], tb[0])) & (ta <= min(ta[-1], tb[-1]))
    if np.count_nonzero(sel) < 2:
        raise ScopeError("兩個來源的時間範圍沒有重疊。")
    t = ta[sel]
    return t, va[sel], np.interp(t, tb, vb)


def derive(op: str, ta: np.ndarray, va: np.ndarray, ua: str, tb: np.ndarray | None = None,
           vb: np.ndarray | None = None, ub: str = "", param: float = 0.0) -> tuple[np.ndarray, np.ndarray, str]:
    """回傳 (時間, 數值, 單位)。濾波的 param 為截止頻率 Hz，平滑的 param 為點數。"""
    validate(ta, va)
    with np.errstate(divide="ignore", invalid="ignore"):
        if op in BINARY:
            if tb is None or vb is None:
                raise ScopeError("此運算需要兩個來源。")
            validate(tb, vb)
            t, a, b = _overlap(ta, va, tb, vb)
            if op in ("加", "減"):
                if ua != ub:
                    raise ScopeError(f"單位不同（{ua} 與 {ub}）不能相加減。")
                return t, a + b if op == "加" else a - b, ua
            if op == "乘":
                return t, a * b, _mul(ua, ub)
            return t, np.where(b == 0, np.nan, a / np.where(b == 0, 1, b)), _div(ua, ub)
        if op == "反相":
            return ta, -va, ua
        if op == "絕對值":
            return ta, np.abs(va), ua
        if op == "平方":
            return ta, va ** 2, _square(ua)
        if op == "開根號":
            inner = ua[:-1].strip("()") if ua.endswith("²") else f"√{_wrap(ua)}" if ua else ""
            return ta, np.sqrt(va), inner
        if op == "log10":
            return ta, np.log10(np.where(va > 0, va, np.nan)), ""
        if op == "微分":
            return ta, np.gradient(va, ta), f"{_wrap(ua) or '1'}/s"
        if op == "積分":
            area = np.concatenate(([0.0], np.cumsum((va[1:] + va[:-1]) / 2 * np.diff(ta))))
            return ta, area, f"{_wrap(ua)}·s" if ua else "s"
        if op == "低通":
            return ta, flt.lowpass(ta, va, param), ua
        if op == "高通":
            return ta, flt.highpass(ta, va, param), ua
        if op == "平滑":
            t, v = flt.smooth(ta, va, int(param))
            return t, v, ua
    raise ScopeError(f"未知的運算：{op}")


def _self_check() -> None:
    t = np.linspace(0, 1e-3, 1001)
    a, b = np.sin(2 * np.pi * 1e3 * t), np.full_like(t, 2.0)
    tt, v, u = derive("加", t, a, "V", t, b, "V")
    assert np.allclose(v, a + 2) and u == "V"
    assert derive("乘", t, a, "V", t, b, "V")[2] == "V²"
    assert derive("乘", t, a, "V", t, b, "A")[2] == "V·A"
    assert derive("乘", t, a, "", t, b, "V")[2] == "V" and derive("除", t, a, "V", t, b, "")[2] == "V"
    assert derive("除", t, a, "", t, b, "V")[2] == "1/V"
    _, q, u = derive("除", t, a, "V", t, np.r_[0.0, b[1:]], "V")
    assert np.isnan(q[0]) and np.allclose(q[1:], a[1:] / 2) and u == ""
    # 時間軸不同：只取重疊區，不外插
    tb = t + 0.5e-3
    tt, v, _ = derive("減", t, a, "V", tb, np.zeros_like(t), "V")
    assert tt[0] >= tb[0] and tt[-1] <= t[-1] and np.allclose(v, a[t >= tb[0]])
    try:
        derive("加", t, a, "V", t + 1, a, "V")
        raise AssertionError("沒有重疊應該丟出 ScopeError")
    except ScopeError:
        pass
    try:
        derive("加", t, a, "V", t, a, "V/s")
        raise AssertionError("單位不同應該丟出 ScopeError")
    except ScopeError:
        pass
    # 積分(微分) 還原（扣掉起點）
    _, d, ud = derive("微分", t, a, "V")
    _, back, ub = derive("積分", t, d, ud)
    assert ud == "V/s" and ub == "(V/s)·s" and np.max(np.abs(back - (a - a[0]))) < 1e-3
    assert np.allclose(derive("微分", t, a, "V")[1][500], 2 * np.pi * 1e3 * np.cos(np.pi), rtol=1e-3)
    assert derive("開根號", t, b, "V²")[2] == "V" and np.allclose(derive("開根號", t, b, "V²")[1], np.sqrt(2))
    assert np.isnan(derive("開根號", t, -b, "V")[1]).all()
    _, lg, ul = derive("log10", t, np.full_like(t, 100.0), "V")
    assert np.allclose(lg, 2) and ul == ""
    assert np.allclose(derive("反相", t, a, "V")[1], -a)
    assert derive("平滑", t, a, "V", param=5)[1].size == len(t) - 4
    assert derive("低通", t, a, "V", param=1e5)[2] == "V"
    print("analysis.mathfn self-check OK")


if __name__ == "__main__":
    _self_check()
