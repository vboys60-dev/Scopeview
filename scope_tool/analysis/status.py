"""量測三態與可序列化原因碼；狀態合併取較差者。"""
from __future__ import annotations

from typing import NamedTuple

VALID, LIMITED, INVALID = "valid", "limited", "invalid"
STATUS_TEXT = {VALID: "有效", LIMITED: "受限", INVALID: "無效"}
RATE_INFERRED = "RATE_INFERRED"
RATE_AMBIGUOUS = "RATE_AMBIGUOUS"
GRID_SLIP_SUSPECT = "GRID_SLIP_SUSPECT"
GRID_COLLISION = "GRID_COLLISION"
GRID_COLLISION_MANY = "GRID_COLLISION_MANY"
HALF_UI_AMBIGUOUS = "HALF_UI_AMBIGUOUS"
CROSSING_TRIMMED = "CROSSING_TRIMMED"
EYE_NO_POSITIVE_OPENING = "EYE_NO_POSITIVE_OPENING"
LOW_EDGE_COUNT = "LOW_EDGE_COUNT"
REASON_TEXT = {
    RATE_INFERRED: "未給定速率，UI 與速率由資料推估。",
    RATE_AMBIGUOUS: "邊緣間隔具有共同倍數，速率有多解歧義。",
    GRID_SLIP_SUSPECT: "TIE 局部出現整 UI 跳變，且間隔接近半 UI 捨入邊界，格號可能滑格；TIE 統計僅供參考。",
    GRID_COLLISION: "少數相鄰邊緣的最終格號衝突。",
    GRID_COLLISION_MANY: "多處相鄰邊緣的最終格號衝突，超過產品門檻。",
    HALF_UI_AMBIGUOUS: "部分邊緣間隔落在半 UI 附近，格號配對有歧義。",
    CROSSING_TRIMMED: "交叉點統計剔除超過 1% 樣本，裁切 σ、6σ 估計與眼寬可能偏樂觀。",
    EYE_NO_POSITIVE_OPENING: "此模型未得到正開口。",
    LOW_EDGE_COUNT: "邊緣數偏少，統計穩定性有限。",
}


class Result(NamedTuple):
    status: str
    reasons: tuple[str, ...]
    diagnostics: dict

    def to_dict(self) -> dict:
        return {"status": self.status, "reasons": list(self.reasons), "diagnostics": dict(self.diagnostics)}


def worst(*results: Result | str) -> Result:
    """原因碼聯集保序；同名診斷由後者覆蓋，不受狀態優劣影響。"""
    rank = {VALID: 0, LIMITED: 1, INVALID: 2}
    state, reasons, diagnostics = VALID, [], {}
    for item in results:
        item = Result(item, (), {}) if isinstance(item, str) else item
        if rank[item.status] > rank[state]:
            state = item.status
        reasons.extend(r for r in item.reasons if r not in reasons)
        diagnostics.update(item.diagnostics)
    return Result(state, tuple(reasons), diagnostics)


def _self_check() -> None:
    import json

    a = Result(LIMITED, (RATE_INFERRED,), {"g": 2})
    b = Result(INVALID, (RATE_INFERRED, GRID_COLLISION_MANY), {})
    assert worst().status == VALID and worst(VALID, a) == a
    assert worst(a, b) == Result(INVALID, (RATE_INFERRED, GRID_COLLISION_MANY), {"g": 2})
    assert worst(b, a).status == INVALID
    conflict = b._replace(diagnostics={"g": 3})
    assert worst(a, conflict).diagnostics == {"g": 3}
    assert worst(conflict, a).diagnostics == {"g": 2}
    assert STATUS_TEXT == {VALID: "有效", LIMITED: "受限", INVALID: "無效"}
    assert a.to_dict()["status"] == "limited"
    codes = {v for k, v in globals().items() if k.isupper() and isinstance(v, str)} - {VALID, LIMITED, INVALID}
    assert codes == set(REASON_TEXT) and all(REASON_TEXT.values())
    assert json.loads(json.dumps(a.to_dict()))["reasons"] == [RATE_INFERRED]
    print("analysis.status self-check OK")


if __name__ == "__main__":
    _self_check()
