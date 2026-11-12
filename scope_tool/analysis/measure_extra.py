"""Web 額外量測：中閾值電壓與完整邊緣、脈衝計數。"""
import numpy as np
from scope_tool.analysis import edge
from scope_tool.analysis.measure import levels, validate, _validate_pct
from scope_tool.contracts import ScopeError

EXTRA = {"Vmid": ("電壓", "{u}"), "上升邊緣計數": ("時間", ""),
         "下降邊緣計數": ("時間", ""), "+脈衝計數": ("時間", ""), "-脈衝計數": ("時間", "")}


def vmid(base: float, top: float, mid: float) -> float:
    return base + (top - base) * mid / 100


def measure_extra(name, t, v, pct):
    _validate_pct(pct)
    validate(t, v)
    _, _, top, base = levels(v)
    if top <= base:
        raise ScopeError("TOP_EQ_BASE：波形沒有振幅（top = base）。")
    if name == "Vmid":
        return np.array([vmid(base, top, pct[1])])
    es = edge.edges(t, v, *(vmid(base, top, p) for p in pct))
    if name in ("上升邊緣計數", "下降邊緣計數"):
        value = sum(e.rising == (name == "上升邊緣計數") for e in es)
    elif name in ("+脈衝計數", "-脈衝計數"):
        value = sum(a.rising == (name == "+脈衝計數") and a.rising != b.rising for a, b in zip(es, es[1:]))
    else:
        raise ScopeError(f"未知量測：{name}")
    return np.array([float(value)])


def delta_time(t1, v1, t2, v2, pct, rising1, rising2, n1, n2, level1, level2):
    """從各自範圍左緣數完整邊緣，回傳指定閾值交越的時間差。"""
    _validate_pct(pct)
    crossings = []
    for i, (t, v, rising, n, level) in enumerate(((t1, v1, rising1, n1, level1), (t2, v2, rising2, n2, level2)), 1):
        validate(t, v)
        _, _, top, base = levels(v)
        if top <= base:
            raise ScopeError(f"來源 {i}：TOP_EQ_BASE：波形沒有振幅（top = base）。")
        es = [e for e in edge.edges(t, v, *(vmid(base, top, p) for p in pct)) if e.rising == rising]
        if len(es) < n:
            raise ScopeError(f"EDGE_NOT_FOUND：來源 {i} 找不到第 {n} 個指定方向的完整邊緣。")
        crossings.append(getattr(es[n - 1], {"lower": "t_lo", "middle": "t_mid", "upper": "t_hi"}[level]))
    return np.array([crossings[1] - crossings[0]])


def _self_check():
    t = np.arange(401, dtype=float)
    v = np.tile(np.r_[np.zeros(20), np.ones(20)], 10)
    v = np.r_[v, 0.]
    for pct in ((10, 50, 90), (20, 50, 80)):
        for name, expected in zip(EXTRA, (0.5, 10, 10, 10, 9)):
            assert measure_extra(name, t, v, pct)[0] == expected
        for name in EXTRA:
            try:
                measure_extra(name, t, np.zeros_like(t), pct)
                raise AssertionError(name)
            except ScopeError as exc:
                assert "TOP_EQ_BASE" in str(exc)
    # 左界切入漸升緣：半截緣不列入，下一個完整緣才是第 1 個。
    ramp = np.array([0., 0., .25, .5, .75, 1., 1., 0., 0., .25, .5, .75, 1., 1., 0.])
    rt = np.arange(len(ramp), dtype=float)
    assert abs(delta_time(rt[3:], ramp[3:], rt[3:], ramp[3:], (10, 50, 90), True, True, 1, 1, "lower", "upper")[0] - 3.2) < 1e-12
    print("measure_extra self-check OK")


if __name__ == "__main__":
    _self_check()
