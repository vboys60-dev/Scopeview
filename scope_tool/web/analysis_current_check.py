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
        with patch("scope_tool.web.analysis_api._measure", return_value=timed(np.array([3., 9.]), at)):
            result = a.measure([entry], None, {"A": d}, "10/50/90 %")["results"][0]
        assert result["ok"] and result["stats"]["current"] == 3, result
    print("analysis current API self-check OK")


if __name__ == "__main__":
    _self_check()
