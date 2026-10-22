"""analysis_api 自檢（獨立檔以維持單檔 ≤300 行）：python -m scope_tool.web.analysis_check。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from scope_tool.analysis.peaks import SORTS
from scope_tool.contracts import ScopeError
from scope_tool.storage.reader import read_waveform_file
from scope_tool.web.analysis_api import Analysis, fft_bytes, wave_bytes
from scope_tool.web.analysis_util import BadRequest, StaleError


def _self_check() -> None:
    import inspect
    import json
    import tempfile

    import h5py

    from scope_tool.web.decimate import decode

    # 方法名與參數名須與契約 owner=Analysis 完全一致
    c = json.loads((Path(__file__).parent / "static" / "api_contract.json").read_text(encoding="utf-8"))["methods"]
    want = {n: [p["name"] for p in m["params"]] for n, m in c.items() if m["owner"] == "Analysis"}
    got = {n: [p for p in inspect.signature(f).parameters if p != "self"]
           for n, f in inspect.getmembers(Analysis, inspect.isfunction) if not n.startswith("_")}
    assert got == want, (set(got) ^ set(want), got, want)

    A = Analysis()

    def run(r: Any) -> Any:  # 工作型方法已是同步函式
        return r

    def err(fn, *a, exc=Exception):
        try:
            fn(*a)
        except exc as e:
            return e
        raise AssertionError("應該失敗")

    n = 20000
    t = np.arange(n) * 1e-6
    sq = np.interp(t % 1e-3, [0, 10e-6, 500e-6, 510e-6, 1e-3], [0, 2, 2, 0, 0])
    sin = np.sin(2 * np.pi * 5e3 * t)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        csvp = tmp / "a.csv"
        csvp.write_text("Time(s),CH1(V),CH2(V)\n" + "\n".join(
            f"{float(a)!r},{float(b)!r},{float(c_)!r}" for a, b, c_ in zip(t, sq, sin)) + "\n", encoding="utf-8")
        assert isinstance(err(A.measure, [], None, {}, "10/50/90 %", exc=ScopeError), ScopeError)  # 未開檔

        fs = run(A.open_waveform(str(csvp)))
        assert fs["gen"] == 1 and [c["name"] for c in fs["channels"]] == ["CHAN1", "CHAN2"] and not fs["pyramid"]
        assert fs["channels"][0]["points"] == n and fs["model"] is None and ["檔名", "a.csv"] in fs["info"]

        ent = [{"channel": "CHAN1", "name": "頻率", "rising": True}, {"channel": "CHAN1", "name": "Vp-p", "rising": True},
               {"channel": "F9", "name": "Vmax", "rising": True}]
        m = run(A.measure(ent, None, {}, "10/50/90 %"))
        assert m["gen"] == 1 and m["revision"] == 1
        r0, r1, r2 = m["results"]
        assert r0["ok"] and abs(r0["stats"]["mean"] - 1000) < 1 and r0["stats"]["count"] >= 10 and r0["unit"] == "Hz"
        assert r1["ok"] and abs(r1["stats"]["max"] - 2) < 1e-9 and not r2["ok"] and r2["stats"] is None
        # dx：CHAN2 的 dx 讓同一顯示區間對應不同來源區間；反序 range 等價；兩端含
        e2 = [{"channel": "CHAN2", "name": "Vmax", "rising": True}]
        a1 = run(A.measure(e2, [0.004, 0.001], {}, "10/50/90 %"))["results"][0]
        a2 = run(A.measure(e2, [0.001, 0.004], {}, "10/50/90 %"))["results"][0]
        assert a1["stats"] == a2["stats"] and a1["ok"]
        b = run(A.measure(e2, [0.001, 0.004], {"CHAN2": 0.0002}, "10/50/90 %"))["results"][0]
        sl = (t >= 0.001 - 0.0002) & (t <= 0.004 - 0.0002)
        assert abs(b["stats"]["max"] - sin[sl].max()) < 1e-9
        # 空區間：具名失敗，不得 count=1
        em = run(A.measure(e2, [5.0, 6.0], {}, "10/50/90 %"))["results"][0]
        assert not em["ok"] and em["stats"] is None and em["reason"] == "所選範圍內沒有資料"
        # 匯出量測：最新 revision 成功，過期 revision／gen 為 STALE
        rev = run(A.measure(ent[:2], None, {}, "20/50/80 %"))
        exp = A.export_measurements(rev["results"], rev["gen"], rev["revision"], str(tmp))
        text = Path(exp["path"]).read_text(encoding="utf-8-sig")
        assert "頻率(CHAN1 ↑)" in text and "20/50/80 %" in text
        assert isinstance(err(A.export_measurements, rev["results"], 1, rev["revision"] - 1, str(tmp),
                              exc=StaleError), StaleError)
        assert isinstance(err(A.export_measurements, rev["results"], 9, rev["revision"], str(tmp),
                              exc=StaleError), StaleError)

        # 游標
        cr = A.cursor_readout(0.0012341, 0.002, {"CHAN2": 1e-6})
        assert cr["index1"] == 1234 and cr["y"]["CHAN2"]["y1"] is not None
        out = A.cursor_readout(0.0, 1.0, {})
        assert out["y"]["CHAN1"]["y2"] is not None and out["t2"] == float(t[-1])
        out = A.cursor_readout(0.0, 0.01, {"CHAN2": 0.5})  # CHAN2 平移後落在時間軸外 → null
        assert out["y"]["CHAN2"]["y1"] is None
        # Marker
        mk = A.marker_eval("Track Waveforms", "CHAN1", 1e-3, 2e-3, 0.0, 0.0, 1e-3, [])
        assert mk["available"] and mk["position"]["x1"] == 1e-3
        assert isinstance(err(A.marker_eval, "Track RF", "CHAN1", 0, 0, 0, 0, 1e-3, [], exc=BadRequest), BadRequest)
        mm = A.marker_eval("Track Measurements", "CHAN1", 0, 0, 0, 0, 1e-3, [[0, 1, "a"], [1, 3, "b"]])
        assert mm["read_only"] and mm["delta_y"] == 2

        # 數學：F1，編號不重用
        f1 = run(A.math("平方", "CHAN1", None, 0))
        assert f1["name"] == "F1" and f1["derived"] and f1["unit"] == "V²" and f1["gen"] == 1
        f2 = run(A.math("加", "CHAN1", "CHAN2", 0))
        assert f2["name"] == "F2"
        A.remove_channel("F2")
        assert run(A.math("反相", "CHAN1", None, 0))["name"] == "F3"
        assert isinstance(err(A.remove_channel, "CHAN1", exc=ScopeError), ScopeError)
        assert isinstance(err(A.math, "低通", "CHAN1", None, 0, exc=BadRequest), BadRequest)

        # FFT／Track RF
        kw = dict(window="Hanning", unit="dBV", r_ohm=50.0, peak_count=3, peak_level=-40.0,
                  peak_sort="Decreasing Magnitude")
        fr = run(A.fft("CHAN2", None, {}, **kw))
        assert fr["ok"] and fr["spectrum_id"] == "s1" and abs(fr["peaks"][0]["x"] - 5000) < 100
        assert fr["f_min"] == 0 and fr["df"] > 0
        fr2 = run(A.fft("F1", None, {}, **kw))  # 衍生通道：輸出單位為 <u> rms
        assert fr2["unit"] == "V² rms" and fr2["spectrum_id"] == "s2"
        assert isinstance(err(A.fft_track_rf, "s1", 5000.0, 0, -40.0, exc=StaleError), StaleError)
        fr = run(A.fft("CHAN2", None, {}, **kw))
        rf = A.fft_track_rf(fr["spectrum_id"], 4900.0, 0, -40.0)
        assert rf["available"] and abs(rf["x"] - 4900) <= fr["df"]
        rf = A.fft_track_rf(fr["spectrum_id"], rf["x"], 1, 0.0)  # 門檻 0 dBV 以上沒有峰 → 維持原位
        assert not rf["available"] and rf["reason"] and rf["y"] is not None and rf["x"] is not None
        assert isinstance(err(A.fft_track_rf, fr["spectrum_id"], 1.0, 2, -40.0, exc=BadRequest), BadRequest)
        # FFT 空區間形狀；失敗後舊頻譜失效
        fe = run(A.fft("CHAN2", [5.0, 6.0], {}, **kw))
        assert fe["ok"] is False and fe["spectrum_id"] is None and fe["peaks"] == [] and fe["df"] is None \
            and fe["reason"]
        assert isinstance(err(A.fft_track_rf, fr["spectrum_id"], 1.0, 0, -40.0, exc=StaleError), StaleError)
        fr = run(A.fft("CHAN2", None, {}, **kw))
        # 二進位
        n_, mode, bx, lo, hi = decode(wave_bytes(A, "CHAN1", 0.0, 1.0, 100, 1))
        assert mode == 1 and n_ == 100
        assert isinstance(err(wave_bytes, A, "CHAN1", 0.0, 1.0, 100, 7, exc=StaleError), StaleError)
        assert decode(fft_bytes(A, fr["spectrum_id"], 0.0, 1e6, 200, False))[1] == 1
        assert decode(fft_bytes(A, fr["spectrum_id"], 100.0, 1e6, 200, True))[2][0] > 0
        assert isinstance(err(fft_bytes, A, "s999", 0, 1, 10, False, exc=StaleError), StaleError)

        # 匯出 CSV（來源時間、不套 dx）；directory=null → 來源檔資料夾
        ex = run(A.export_csv([0.001, 0.002], 50, None))
        got_w = read_waveform_file(Path(ex["path"]))
        assert Path(ex["path"]).parent == tmp and 1 <= len(got_w[0].time) <= 50 and len(got_w) == 2
        assert isinstance(err(A.export_csv, [5.0, 6.0], None, str(tmp), exc=ScopeError), ScopeError)

        # NaN → null：含 NaN 的 h5；二進位保留 NaN
        nan_v = sq.copy()
        nan_v[100:110] = np.nan
        h5p = tmp / "b.h5"
        with h5py.File(h5p, "w") as hf:
            g = hf.create_group("Waveforms/Channel 1")
            g.create_dataset("Channel 1Data", data=nan_v)
            g.attrs["XInc"], g.attrs["XOrg"] = 1e-6, 0.0
        fs2 = run(A.open_waveform(str(h5p)))
        assert fs2["gen"] == 2 and fs2["channels"][0]["vmax"] == 2.0
        assert isinstance(err(wave_bytes, A, "CHAN1", 0.0, 1.0, 100, 1, exc=StaleError), StaleError)  # 舊 gen
        assert isinstance(err(A.fft_track_rf, fr["spectrum_id"], 1.0, 0, -40.0, exc=StaleError), StaleError)
        assert isinstance(err(A.export_measurements, [], 1, 5, str(tmp), exc=StaleError), StaleError)
        nm = run(A.measure([{"channel": "CHAN1", "name": "Vmax", "rising": True}], [0.0, 0.0001], {}, "10/50/90 %"))
        s = nm["results"][0]
        assert not s["ok"] and "NaN" in s["reason"] and json.dumps(nm, allow_nan=False)
        allnan = run(A.measure([{"channel": "CHAN1", "name": "Vmax", "rising": True}], [100e-6, 109e-6], {},
                               "10/50/90 %"))["results"][0]
        assert not allnan["ok"] and allnan["reason"] == "所選範圍內沒有資料"
        cr = A.cursor_readout(100e-6, 105e-6, {})
        assert cr["y"]["CHAN1"]["y1"] is None and json.dumps(cr, allow_nan=False)
        _, _, _, lo, hi = decode(wave_bytes(A, "CHAN1", 0.0, 1.0, 50, 2))
        assert np.isnan(lo).any() and np.array_equal(np.isnan(lo), np.isnan(hi))
        # 換檔後舊頻譜 id 不得取得新檔頻譜；id 程序內遞增不重用
        old_id = fr["spectrum_id"]
        nf = run(A.fft("CHAN1", [0.0002, 0.01], {}, **kw))
        assert nf["spectrum_id"] != old_id and int(nf["spectrum_id"][1:]) > int(old_id[1:]) and nf["ok"], nf
        assert isinstance(err(A.fft_track_rf, old_id, 1.0, 0, -40.0, exc=StaleError), StaleError)
        # Track Waveforms：資料起點不在 0 秒（5 ~ 5.1 s）仍可追蹤
        t5 = 5.0 + np.arange(1000) * 1e-4
        off = tmp / "off.csv"
        off.write_text("Time(s),CH1(V)\n" + "\n".join(f"{float(a)!r},{float(b)!r}" for a, b in
                                                      zip(t5, np.sin(t5 * 100))) + "\n", encoding="utf-8")
        run(A.open_waveform(str(off)))
        mk = A.marker_eval("Track Waveforms", "CHAN1", 5.02, 5.05, 0.0, 0.0, 0.1, [])
        assert mk["available"] and abs(mk["position"]["x1"] - 5.02) < 1e-4, mk
        # close_waveform：釋放並讓舊 gen／頻譜／快照全部 STALE
        g_open = A._gen
        sid = run(A.fft("CHAN1", None, {}, **kw))["spectrum_id"]
        assert A.close_waveform() is None and A._gen == g_open + 1 and not A._waves and A._spec is None
        assert isinstance(err(wave_bytes, A, "CHAN1", 0.0, 1.0, 10, g_open, exc=StaleError), StaleError)
        assert isinstance(err(A.fft_track_rf, sid, 5.0, 0, -40.0, exc=StaleError), StaleError)
        assert isinstance(err(A.export_measurements, [], g_open, 1, str(tmp), exc=StaleError), StaleError)
        assert isinstance(err(A.cursor_readout, 0.0, 1.0, {}, exc=ScopeError), ScopeError)
        # validate_params：只檢查型別／必填／列舉
        from scope_tool.web.analysis_params import validate_params as vp
        good = dict(entries=[{"channel": "CHAN1", "name": "Vmax", "rising": True}], range=None, dx={},
                    threshold="10/50/90 %")
        vp("measure", good)
        for bad in (dict(good, threshold="x"), dict(good, range=[1]), dict(good, dx={"a": "b"}),
                    dict(good, entries=[{"channel": "C"}]), {k: v for k, v in good.items() if k != "dx"},
                    dict(good, extra=1)):
            assert isinstance(err(vp, "measure", bad, exc=BadRequest), BadRequest), bad
        vp("close_waveform", {})
        vp("export_csv", dict(range=[1, 0.5], max_points=None, directory=None))
        assert isinstance(err(vp, "export_csv", dict(range=None, max_points="5", directory=None), exc=BadRequest),
                          BadRequest)
        assert isinstance(err(vp, "marker_eval", dict(mode="Track RF", channel="a", x1=0, x2=0, y1=0, y2=0,
                                                       screen_width=1, measurements=[]), exc=BadRequest), BadRequest)
        assert isinstance(err(vp, "nope", {}, exc=BadRequest), BadRequest)
        # 參數錯誤
        assert isinstance(err(A.measure, [], [1, "x"], {}, "10/50/90 %", exc=BadRequest), BadRequest)
        assert isinstance(err(A.measure, [], None, {}, "bad", exc=BadRequest), BadRequest)
        assert isinstance(err(A.fft, "CHAN1", None, {}, "Bad", "dBV", 50.0, 3, -40.0, SORTS[0], exc=BadRequest),
                          BadRequest)
    print("analysis_api self-check OK")


if __name__ == "__main__":
    _self_check()
