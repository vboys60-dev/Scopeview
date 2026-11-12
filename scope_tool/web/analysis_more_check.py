"""Web 額外量測的範圍、閾值與平坦資料檢查。"""
import numpy as np
from scope_tool.analysis.measure import MEASUREMENTS
from scope_tool.analysis.measure_extra import EXTRA
from scope_tool.contracts import Waveform
from scope_tool.web.analysis_api import Analysis


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
    a._waves = [Waveform("A", t, np.zeros_like(t))]
    for name in EXTRA:
        row = a.measure([dict(channel="A", name=name)], None, {}, "10/50/90 %")["results"][0]
        assert not row["ok"] and "TOP_EQ_BASE" in row["reason"], row
    print("analysis_more_check self-check OK")


if __name__ == "__main__":
    _self_check()
