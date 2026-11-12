"""Web 額外量測的範圍、閾值與平坦資料檢查。"""
import numpy as np
from scope_tool.analysis.measure import MEASUREMENTS
from scope_tool.analysis.measure_extra import EXTRA
from scope_tool.contracts import Waveform
from scope_tool.web.analysis_api import Analysis
from scope_tool.web.analysis_util import BadRequest
from scope_tool.web.analysis_params import validate_params


def _self_check():
    t = np.arange(401, dtype=float)
    v = np.r_[np.tile(np.r_[np.zeros(20), np.full(20, 2.)], 10), 0.]
    a = Analysis()
    a._gen, a._units, a._waves = 1, {"A": "V"}, [Waveform("A", t, v)]
    assert not set(EXTRA) & set(MEASUREMENTS)
    for threshold in ("10/50/90 %", "20/50/80 %"):
        for name, expected in zip(EXTRA, (1, 10, 10, 10, 9)):
            for all_edges in (True, False):
                row = a.measure([dict(channel="A", name=name, all_edges=all_edges)], None, {}, threshold)["results"][0]
                assert row["ok"] and row["stats"]["current"] == expected, row
                assert row["unit"] == ("V" if name == "Vmid" else "")
        row = a.measure([dict(channel="A", name="+脈衝計數")], [21., 61.], {}, threshold)["results"][0]
        assert row["ok"] and row["stats"]["current"] == 0, row
    a._waves = [Waveform("A", t, v), Waveform("B", t, np.roll(v, 3))]
    entry = dict(channel="A", channel2="B", name="Delta Time", rising=True, edge_num=2, edge_num2=2)
    def result(e=entry, rng=None, dx=None):
        return a.measure([e], rng, dx or {}, "10/50/90 %")["results"][0]
    assert abs(result()["stats"]["current"] - 3) < 1e-10
    assert abs(result({**entry, "edge_level":"lower", "edge_level2":"upper"})["stats"]["current"] - 3.8) < 1e-10
    assert result(dx={"B": -5})["stats"]["current"] == -2
    assert "EDGE_NOT_FOUND" in result({**entry, "edge_num":100})["reason"]
    assert abs(result({**entry, "edge_num":1, "edge_num2":1}, [20., 200.])["stats"]["current"] + 37) < 1e-10
    for bad in (0, 65535, 1.5, True):
        try:
            result({**entry, "edge_num":bad})
            raise AssertionError(bad)
        except BadRequest:
            pass
    for key, value in (("edge_level", "bad"), ("edge_num", 1.5)):
        try:
            validate_params("measure", dict(entries=[{**entry, key:value}], range=None, dx={}, threshold="10/50/90 %"))
            raise AssertionError(value)
        except BadRequest:
            pass
    for name in list(MEASUREMENTS) + list(EXTRA) + ["延遲", "相位", "電壓比", "Delta Time"]:
        e = dict(channel="A", name=name, rising=True, track=True)
        if name in ("延遲", "相位", "電壓比", "Delta Time"):
            e["channel2"] = "B"
        row = result(e, dx={"A": 2, "B": -1})
        assert row["ok"], (name, row)
        points = row["marks"]
        if name == "電壓比" or "計數" in name:
            assert points is None
        else:
            assert points and all(len(p) == 3 and p[2] in ("A", "B") for p in points), (name, points)
            if name == "Delta Time":
                assert abs(points[0][0] - 21.5) < 1e-12 and abs(points[1][0] - 21.5) < 1e-12, points
            if name == "Vmax":
                assert points == [[22., 2., "A"]], points
    for mode in ("full", "cycles", "cycle"):
        row = result(dict(channel="A", name="Vavg", mode=mode, rising=True, track=True), dx={"A":2})
        assert row["ok"] and len(row["marks"]) == 2, row
    try:
        result(dict(channel="A", name="Vmax", track="yes"))
        raise AssertionError("track must be boolean")
    except BadRequest:
        pass
    a._waves = [Waveform("A", t, np.zeros_like(t))]
    for name in EXTRA:
        row = a.measure([dict(channel="A", name=name)], None, {}, "10/50/90 %")["results"][0]
        assert not row["ok"] and "TOP_EQ_BASE" in row["reason"], row
    print("analysis_more_check self-check OK")


if __name__ == "__main__":
    _self_check()
