"""純參數檢查（只看型別／必填／列舉，不碰狀態與檔案）：server 在登記 request_id 前呼叫。"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from scope_tool.web.analysis_util import BadRequest

_C = json.loads((Path(__file__).parent / "static" / "api_contract.json").read_text(encoding="utf-8"))
_METHODS, _TYPES, _CAT = _C["methods"], _C["types"], _C.get("catalog", {})
_OPS = [o for g in ("binary", "unary", "filters") for o in _CAT.get("math_ops", {}).get(g, [])]
# 方法 -> {參數名: 允許值清單}
_ENUMS = {"fft": {"window": list(_CAT.get("fft_windows", {})), "unit": _CAT.get("fft_units", []),
                  "peak_sort": _CAT.get("peak_sorts", [])},
          "measure": {"threshold": list(_CAT.get("thresholds", {}))},
          "math": {"op": _OPS},
          "marker_eval": {"mode": _CAT.get("marker_modes", [])}}  # Track RF 不在清單內 → BAD_REQUEST


def _split(s: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += ch in "[<"
        depth -= ch in "]>"
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return out + [cur]


def _ok(v: Any, t: str) -> bool:
    t = t.strip()
    if t.endswith("|null"):
        return v is None or _ok(v, t[:-5])
    if t.endswith("[]"):
        return isinstance(v, list) and all(_ok(e, t[:-2]) for e in v)
    if t.startswith("[") and t.endswith("]"):
        parts = _split(t[1:-1])
        return isinstance(v, list) and len(v) == len(parts) and all(_ok(e, p) for e, p in zip(v, parts))
    if t.startswith("map<"):
        return isinstance(v, dict) and all(isinstance(k, str) and _ok(e, t[4:-1]) for k, e in v.items())
    if t in ("any", "object"):
        return t == "any" or isinstance(v, dict)
    if t == "null":
        return v is None
    if t == "str":
        return isinstance(v, str)
    if t == "bool":
        return isinstance(v, bool)
    if t == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "float":
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    spec = _TYPES.get(t)
    if isinstance(spec, str):
        return _ok(v, spec)
    if not isinstance(v, dict):
        return False
    return t != "MeasureEntry" or all(k in v and _ok(v[k], ft) for k, ft in spec.items())


def validate_params(method: str, kwargs: dict) -> None:
    """鍵集合須與契約 params 完全相同；各值型別、可否為 null、列舉值須合法。失敗丟 BadRequestError。"""
    m = _METHODS.get(method)
    if m is None:
        raise BadRequest(f"未知方法：{method}")
    names = [p["name"] for p in m["params"]]
    if not isinstance(kwargs, dict) or set(kwargs) != set(names):
        raise BadRequest(f"{method} 參數必須恰為：{', '.join(names) or '（無）'}")
    for p in m["params"]:
        v = kwargs[p["name"]]
        if v is None:
            if not p.get("nullable"):
                raise BadRequest(f"參數 {p['name']} 不可為 null")
        elif not _ok(v, p["type"]):
            raise BadRequest(f"參數 {p['name']} 型別錯誤（需要 {p['type']}）")
        allowed = _ENUMS.get(method, {}).get(p["name"])
        if allowed and v not in allowed:
            raise BadRequest(f"參數 {p['name']} 不是合法選項：{v}")
