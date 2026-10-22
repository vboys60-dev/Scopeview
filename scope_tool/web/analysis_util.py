"""分析服務共用：例外類別（與 jobs.py 同源）與輸入驗證／JSON 清理小工具。"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

try:  # L1a 已提供則共用同一組例外類別，server 才能映射錯誤碼
    from scope_tool.web.jobs import BadRequestError as BadRequest, StaleError
except ImportError:  # pragma: no cover  最小 stub：與 jobs.py 同名同語義（待 jobs.py 就緒）
    class BadRequest(ValueError):
        """參數錯誤（BAD_REQUEST）。"""

    class StaleError(Exception):
        """gen／revision／spectrum_id 過期（STALE）。"""
        code = "STALE"


def _clean(o: Any) -> Any:
    """NaN／Infinity → None，numpy → 原生型別（契約：JSON 不得出現 NaN）。"""
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    if isinstance(o, (str, bool, int)) or o is None:
        return o
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return str(o)


def _si(v: float, unit: str) -> str:
    if not math.isfinite(v) or v == 0:
        return f"{v:g} {unit}"
    for p, s in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if abs(v) >= p:
            return f"{v / p:.6g} {s}{unit}"
    return f"{v:.6g} {unit}"


def _range(r: Any) -> tuple[float, float] | None:
    if r is None:
        return None
    if not (isinstance(r, (list, tuple)) and len(r) == 2 and all(
            isinstance(x, (int, float)) and math.isfinite(x) for x in r)):
        raise BadRequest("range 必須是 [t0,t1] 或 null")
    return (float(min(r)), float(max(r)))  # 反序由後端排序


def _dx(dx: Any) -> dict[str, float]:
    if not isinstance(dx, dict) or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in dx.values()):
        raise BadRequest("dx 必須是 {通道名: 秒}")
    return {str(k): float(v) for k, v in dx.items()}


def _nearest(t: np.ndarray, x: float) -> int:
    i = min(max(int(np.searchsorted(t, x)), 0), len(t) - 1)
    return i - 1 if i > 0 and abs(t[i - 1] - x) < abs(t[i] - x) else i  # 同距取右
