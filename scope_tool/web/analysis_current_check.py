"""目前值服務自檢：顯示座標、平移、區間與同距選較早事件。"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np

from scope_tool.analysis.edge import timed
from scope_tool.analysis.measure_current_check import signal
from scope_tool.contracts import Waveform
from scope_tool.web.analysis_api import Analysis


def api_check(dual: bool = False) -> None:
    t, v, rise, _ = signal()
    a = Analysis()
    a._gen = 1
    a._waves = [Waveform("A", t, v)]
    a._units = {"A": "V", "B": "V"}
    entry = dict(channel="A", name="上升時間", rising=True)
    expected = np.arange(2, 7)*.16
    if dual:
        delays = np.arange(1, 6)*.1
        # 每組邊緣附近保持相同平移，確保交越時間為已知延遲。
        d = np.interp(t, np.ravel(np.column_stack((rise-1, rise+4))), np.repeat(delays, 2))
        a._waves.append(Waveform("B", t+d, v))
        entry.update(name="延遲", channel2="B")
        expected = delays
    for dx, rng, index in (({}, None, 2), ({"A": 100., "B": 100.}, None, 3),
                            ({"A": -10., "B": -10.}, None, 3),
                            ({"A": 100., "B": 100.}, [105., 128.], 4)):
        result = a.measure([entry], rng, dx, "10/50/90 %")["results"][0]
        assert result["ok"] and np.isclose(result["stats"]["current"], expected[index]), result
    if dual:
        entry["name"] = "相位"
        result = a.measure([entry], None, {}, "10/50/90 %")["results"][0]
        assert np.isclose(result["stats"]["current"], delays[2]/(rise[3]-rise[2])*360)
    print(f"analysis current API {'dual' if dual else 'single'} self-check OK")


def _self_check() -> None:
    api_check()
    api_check(True)
    # 兩事件相對視窗中點為 ±0.3；顯示座標同距，反向扣 dx 會誤選較晚。
    a = Analysis()
    a._gen, a._units = 1, {"A": "V"}
    entry = dict(channel="A", name="上升時間", rising=True)
    for d, center in ((.1, .4), (.7, .1)):
        at = np.array([center-.3, center+.3])
        a._waves = [Waveform("A", at, np.array([0., 1.]))]
        with patch("scope_tool.analysis.measure.measure", return_value=timed(np.array([3., 9.]), at)):
            result = a.measure([entry], None, {"A": d}, "10/50/90 %")["results"][0]
        assert result["ok"] and result["stats"]["current"] == 3, result
    # 顯示時間含零時，單週期以顯示時間參考與 dx 選事件；無欄位沿用全部事件。
    from scope_tool.analysis.measure import measure
    t, v, _, _ = signal()
    a._waves = [Waveform("A", t, v)]
    d = -10.0
    ref = 0.0 if t[0] + d <= 0 <= t[-1] + d else (t[0] + t[-1]) / 2 + d
    cycle = dict(channel="A", name="Vavg", rising=True, mode="cycle")
    actual = a.measure([cycle], None, {"A": d}, "10/50/90 %")["results"][0]
    assert actual["ok"] and np.isclose(actual["stats"]["current"], measure("Vavg", t, v, mode="cycle", ref_time=ref-d)[0])
    assert not np.isclose(actual["stats"]["current"], measure("Vavg", t, v, mode="cycle", ref_time=ref)[0])
    # 顯示時間同距與大 dx 的捨入反例。
    v = np.array([0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 0], float)
    for scale, d, bounds in ((.1, 1., [1.2, 2.]), (1e-6, 1e6, [1e6 + 2e-6, 1e6 + 10e-6])):
        a._waves = [Waveform("A", np.arange(v.size) * scale, v)]
        result = a.measure([cycle], bounds, {"A": d}, "10/50/90 %")["results"][0]
        assert result["ok"] and result["stats"]["current"] == .5, result
    from scope_tool.web.analysis_export import _en_label
    assert _en_label("Vavg(A 單週期)") == "Vavg(A One Cycle)"
    assert _en_label("週期(A 單一事件)") == "Period(A Single Event)"
    assert _en_label("相位(A→B 全部邊緣)") == "Phase(A→B All Edges)"
    a._waves = [Waveform("A", t, signal()[1])]
    old = a.measure([entry], None, {}, "10/50/90 %")["results"][0]["stats"]
    single = a.measure([dict(entry, all_edges=False)], None, {}, "10/50/90 %")["results"][0]["stats"]
    assert old["count"] > 1 and single["count"] == 1 and single["current"] == old["current"]
    # 單事件的 SLOPED 比較兩種極性；相位一律統計全部事件。
    from scope_tool.analysis.measure import measure_all
    tt = np.arange(4001) * 1e-6
    vv = np.interp(tt % 1e-3, [0, 1e-6, 300e-6, 301e-6, 1e-3], [0, 1, 1, 0, 0])
    a._waves = [Waveform("A", tt, vv), Waveform("B", tt, vv)]
    for name in ("週期", "工作週期", "過衝", "前衝"):
        for dx in (-.0023005, -.0021, 0.):
            row = a.measure([dict(channel="A", name=name, rising=True, all_edges=False)], None, {"A": dx}, "10/50/90 %")["results"][0]
            start, end = tt[0] + dx, tt[-1] + dx
            ref = (0. if start <= 0 <= end else (start + end) / 2)
            expected = measure_all([(name, tt, vv, True)], (10, 50, 90), ref_time=ref, meas_all_edges=False, dx=dx)[0]
            assert row["ok"] and tuple(row["stats"][k] for k in ("current", "mean", "min", "max", "range", "std", "count")) == expected, (name, dx, row, expected)
            assert "↑" not in a._snap["results"][0]["_label"]
    phase = dict(channel="A", channel2="B", name="相位", rising=True)
    all_phase = a.measure([phase], None, {}, "10/50/90 %")["results"][0]
    one_phase = a.measure([dict(phase, all_edges=False)], None, {}, "10/50/90 %")["results"][0]
    assert all_phase["stats"] == one_phase["stats"] and "全部邊緣" in a._snap["results"][0]["_label"]
    print("analysis current API self-check OK")


if __name__ == "__main__":
    _self_check()
