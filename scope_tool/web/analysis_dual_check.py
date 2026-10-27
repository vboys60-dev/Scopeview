"""雙來源量測的服務整合自檢：顯示時間、游標、契約、失敗列與 CSV。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from scope_tool.contracts import Waveform
from scope_tool.web.analysis_api import Analysis
from scope_tool.web.analysis_params import validate_params
from scope_tool.web.analysis_util import BadRequest


def _self_check() -> None:
    from scope_tool.web.analysis_current_check import api_check
    api_check(True)
    a = Analysis()
    t = np.arange(4000, dtype=float) / 1000
    v = np.tile(np.r_[np.zeros(100), np.ones(100)], 20)
    a._gen = 1
    a._waves = [Waveform("CH1", t, v*2+7), Waveform("CH2", t+.05, v-13)]
    a._units = {"CH1": "V", "CH2": "V"}
    entries = [dict(channel="CH1", channel2="CH2", name=n, rising=True) for n in ("延遲", "相位", "電壓比")]

    def run(rows: list = entries, rng: list | None = None, dx: dict | None = None) -> dict:
        return a.measure(rows, rng, dx or {}, "10/50/90 %")

    batch = run()
    for row, value, unit in zip(batch["results"], (.05, 90, 6.020599913279624), ("s", "°", "dB")):
        assert row["ok"] and row["channel2"] == "CH2" and row["unit"] == unit
        assert np.isclose(row["stats"]["current"], value)
    assert np.isclose(run(dx={"CH1": .02, "CH2": .03})["results"][0]["stats"]["current"], .06)
    assert np.isclose(run(dx={"CH1": .1})["results"][0]["stats"]["current"], -.05)
    cursor = run(rng=[.06, .95])
    assert cursor["results"][0]["stats"]["count"] == 5
    assert cursor["results"][1]["stats"]["count"] == 4
    rev = run(rng=[.95, .06])
    assert [r["stats"] for r in cursor["results"]] == [r["stats"] for r in rev["results"]]
    # 各來源各切各自時間／dx；空來源與已刪除均為具名失敗。
    for dx, reason in (({"CH2": 10}, "來源 2"), ({"CH1": 10}, "來源 1：所選範圍內沒有資料")):
        assert all(reason in r["reason"] and not r["ok"] for r in run(rng=[0, 1], dx=dx)["results"])
    for ch in ("CH1", "CH2"):
        missing = [dict(e, **{ "channel" if ch == "CH1" else "channel2": "deleted" }) for e in entries]
        assert all(r["reason"] == "來源通道已刪除" for r in run(missing)["results"])
    missing = [dict(e, channel2="deleted") for e in entries]
    assert all(r["reason"] == "來源通道已刪除" for r in run(missing, [0, 1], {"CH1": 10})["results"])
    for n in ("延遲", "相位", "電壓比"):
        params = dict(entries=[dict(channel="CH1", name=n, rising=True)], range=None, dx={}, threshold="10/50/90 %")
        for fn in (lambda: validate_params("measure", params), lambda: a.measure(**params)):
            try:
                fn()
                raise AssertionError("缺少 channel2 應回 BAD_REQUEST")
            except BadRequest:
                pass
    for field, value in (("channel2", None), ("channel2", 2), ("rising2", None), ("rising2", 1)):
        try:
            validate_params("measure", dict(entries=[dict(entries[0], **{field:value})], range=None, dx={}, threshold="10/50/90 %"))
            raise AssertionError("可選欄型別仍須驗證")
        except BadRequest:
            pass
    single = run([dict(channel="CH1", name="Vmax", rising=True, channel2="deleted", rising2=False)])["results"][0]
    assert single["ok"] and "channel2" not in single
    # CSV 使用後端快照，來源 2 併入量測標籤，與畫面相同。
    with tempfile.TemporaryDirectory() as tmp:
        batch = run([dict(entries[0], rising2=False), *entries[1:]])
        dest = a.export_measurements(batch["results"], 1, batch["revision"], tmp)
        text = Path(dest["path"]).read_text(encoding="utf-8-sig")
        for label in ("Delay(CH1→CH2 ↑↓)", "Phase(CH1→CH2 ↑↑)", "Gain(CH1→CH2)"):
            assert label in text
    print("analysis_dual self-check OK")


if __name__ == "__main__":
    _self_check()
