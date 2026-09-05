"""型號辨識與 driver 對應表。新增機型時在自己的模組呼叫 `register()` 註冊即可。"""

from __future__ import annotations

from scope_tool.contracts import ScopeDriver, Series, UnsupportedError

#: module-level 註冊表，故意不做 metaclass 或 plugin 掃描。
_DRIVERS: list[type[ScopeDriver]] = []


def register(cls: type[ScopeDriver]) -> None:
    """把一個 driver 類別加進註冊表。"""
    if cls not in _DRIVERS:
        _DRIVERS.append(cls)


def parse_idn(idn: str) -> tuple[str, str]:
    """把 `*IDN?` 的回應拆成 (廠牌, 型號)。

    標準格式是 "廠牌,型號,序號,版本"，逗號數不足時缺的欄位一律回空字串。
    """
    parts = [p.strip() for p in idn.strip().split(",")]
    make = parts[0] if len(parts) >= 1 else ""
    model = parts[1] if len(parts) >= 2 else ""
    return make, model


def driver_for(resource, idn: str, override: Series | None = None) -> ScopeDriver:
    """依 `*IDN?` 型號找出對應的 driver 並實例化。

    override 給定時直接選那個系列底下第一個註冊的 driver，
    跳過前綴比對（UI 在自動判斷失敗時讓使用者手選一次）。
    比對不到 → 拋 UnsupportedError，UI 據此要求使用者手選系列。
    """
    _, model = parse_idn(idn)

    if override is not None:
        for cls in _DRIVERS:
            if cls.series is override:
                return cls(resource, model)
        raise UnsupportedError(f"沒有任何 driver 屬於系列 {override.value}")

    for cls in _DRIVERS:
        if any(model.startswith(prefix) for prefix in cls.model_prefixes):
            return cls(resource, model)

    raise UnsupportedError(f"無法辨識型號 {model!r}，請手動選擇系列")


if __name__ == "__main__":
    from scope_tool.instruments.fake import FakeDriver

    register(FakeDriver)

    make, model = parse_idn("FAKE,FAKE-SCOPE,0,1")
    assert make == "FAKE" and model == "FAKE-SCOPE"

    d = driver_for(None, "FAKE,FAKE-SCOPE,0,1")
    assert isinstance(d, FakeDriver)

    try:
        driver_for(None, "UNKNOWN,UNKNOWN-MODEL,0,1")
    except UnsupportedError:
        pass
    else:
        raise AssertionError("未知型號應該要拋 UnsupportedError")

    d2 = driver_for(None, "FAKE,FAKE-SCOPE,0,1", override=Series.INFINIIVISION)
    assert isinstance(d2, FakeDriver)

    try:
        driver_for(None, "FAKE,FAKE-SCOPE,0,1", override=Series.INFINIIUM)
    except UnsupportedError:
        pass
    else:
        raise AssertionError("沒有 Infiniium driver 時應該要拋 UnsupportedError")

    # 逗號數不足不能爆
    make3, model3 = parse_idn("ONLYMAKE")
    assert make3 == "ONLYMAKE" and model3 == ""
    make4, model4 = parse_idn("")
    assert make4 == "" and model4 == ""

    print("registry self-check OK")
