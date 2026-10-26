"""端到端自檢（不開視窗）：真 Server + Api + Analysis + Jobs，FakeDriver，urllib 走真實 HTTP。

執行：/opt/anaconda3/bin/python3 -m scope_tool.web.e2e_check
"""
from __future__ import annotations

import json
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from scope_tool import config as config_mod
from scope_tool.web.analysis_api import Analysis
from scope_tool.web.api import Api
from scope_tool.web.jobs import Jobs
from scope_tool.web.server import Server


def main() -> None:
    jobs = Jobs()
    api = Api(jobs, cfg=dict(config_mod.DEFAULTS), persist=False)
    srv = Server(api, Analysis(), jobs, token="tok")
    srv.start()
    base = f"http://127.0.0.1:{srv.port}"
    tmp = Path(tempfile.mkdtemp())
    seen = {"seq": 0}  # wait_events 游標

    def http(path: str, body=None):
        r = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def rpc(name: str, body: dict | None = None, /, **kw):
        s, b = http(f"/rpc/{name}?k=tok", {**(body or {}), **kw})
        return json.loads(b)  # 信封

    def ok(name, body=None, /, **kw):
        r = rpc(name, body, **kw)
        assert r["ok"], (name, r)
        return r["result"]

    def job(name, body=None, /, **kw):
        """送出工作型方法並等 job 事件；回事件 dict（含 ok／result／error）。"""
        j = ok(name, body, **kw)["job"]
        for _ in range(20):
            o = rpc("wait_events", {"since": seen["seq"], "timeout": 3})["result"]
            for e in o["events"]:
                if e.get("type") == "job" and e["id"] == j:
                    seen["seq"] = max(seen["seq"], o["seq"])
                    return e
            seen["seq"] = o["seq"]
        raise AssertionError(f"job 逾時：{name}")

    def job_ok(name, body=None, /, **kw):
        e = job(name, body, **kw)
        assert e["ok"], (name, e)
        return e["result"]

    def wave(ch, t0, t1, px, gen):
        s, b = http(f"/wave?k=tok&ch={ch}&t0={t0!r}&t1={t1!r}&px={px}&gen={gen}")
        return s, b

    def dec(b):
        n, mode, r0, r1 = struct.unpack_from("<4I", b)
        assert (r0, r1) == (0, 0) and len(b) == 16 + 16 * n, (n, len(b))
        x = np.frombuffer(b, "<f8", n, 16)
        lo = np.frombuffer(b, "<f4", n, 16 + 8 * n)
        hi = np.frombuffer(b, "<f4", n, 16 + 12 * n)
        return n, mode, x, lo, hi

    try:
        # 1 狀態／連線
        st = ok("get_state")
        assert st["connected"] is False and "catalog" in st
        seen["seq"] = st["seq"]
        assert ok("connect_fake")["model"] == "FAKE-SCOPE"
        assert ok("get_state")["connected"] is True
        # 2 capture_info（job）
        info = job_ok("capture_info")
        assert info["channels"] == ["CHAN1", "CHAN2"] and info["max_points"] > 0
        # 3 截圖
        shot = job_ok("screenshot", directory=str(tmp), name="s", image_format="PNG", inverted=False, area="full")
        assert Path(shot["path"]).exists() and shot["preview"] == 1
        s, png = http("/screenshot/last?k=tok&n=1")
        assert s == 200 and png.startswith(b"\x89PNG")
        # 4 擷取（寫 h5）
        N = 4000
        cap = job_ok("capture", directory=str(tmp), name="w", channels=["CHAN1", "CHAN2"], points=N, retrigger=False)
        assert cap["got_points"] == N and cap["path"].endswith(".h5") and Path(cap["path"]).exists(), cap
        # 5 開檔
        fi = job_ok("open_waveform", path=cap["path"])
        gen = fi["gen"]
        assert [c["name"] for c in fi["channels"]] == ["CHAN1", "CHAN2"] and fi["channels"][0]["points"] == N
        t0, t1 = fi["channels"][0]["t0"], fi["channels"][0]["t1"]
        # 6 /wave 二進位
        s, b = wave("CHAN1", t0, t1, 100, gen)
        n, mode, x, lo, hi = dec(b)
        assert s == 200 and mode == 1 and n == 100 and abs(hi.max() - 1.0) < 0.05 and abs(lo.min() + 1.0) < 0.05
        assert np.all(np.diff(x) > 0) and x[0] >= t0 - 1e-12
        s, b = wave("CHAN1", t0, t1, 5000, gen)  # 點數 ≤ 2px → 原始模式
        n, mode, x, lo, hi = dec(b)
        assert mode == 0 and np.array_equal(lo, hi) and n == N
        n2 = dec(wave("CHAN1", t1, t0, 5000, gen)[1])[0]  # 反序區間等價
        assert n2 == N
        assert wave("CHAN1", t0, t1, 0, gen)[0] == 400 and wave("NOPE", t0, t1, 10, gen)[0] == 400
        # 7 量測：含 dx、反序 range
        ent = [{"channel": "CHAN1", "name": "Vp-p", "rising": True}, {"channel": "CHAN2", "name": "頻率", "rising": True}]
        mid = (t0 + t1) / 2
        m = job_ok("measure", entries=ent, range=[t0, t1], dx={}, threshold="10/50/90 %")
        assert m["gen"] == gen and all(r["ok"] for r in m["results"]), m
        assert abs(m["results"][0]["stats"]["current"] - 2.0) < 0.1
        assert abs(m["results"][1]["stats"]["current"] - 1e6) / 1e6 < 0.02
        m_rev = job_ok("measure", entries=ent, range=[t1, t0], dx={}, threshold="10/50/90 %")  # 反序
        assert m_rev["results"][0]["stats"]["current"] == m["results"][0]["stats"]["current"]
        m_dx = job_ok("measure", entries=ent[:1], range=[t0, mid], dx={"CHAN1": (t1 - t0) / 4}, threshold="20/50/80 %")
        assert m_dx["results"][0]["ok"] and m_dx["revision"] > m["revision"]
        # 註：Analysis 工作型方法的參數錯誤經 job 事件回報（非同步 RPC 信封），見問題清單
        bad = job("measure", entries=[{"channel": "CHAN1", "name": "不存在"}], range=None, dx={}, threshold="10/50/90 %")
        assert bad["ok"] is False and bad["error"]["code"] == "BAD_REQUEST", bad
        empty = job_ok("measure", entries=ent[:1], range=[t1 + 1, t1 + 2], dx={}, threshold="10/50/90 %")
        assert empty["results"][0]["ok"] is False and empty["results"][0]["reason"]
        # 8 math
        f1 = job_ok("math", op="加", a="CHAN1", b="CHAN2", param=0)
        assert f1["name"] == "F1" and f1["derived"] is True
        f2 = job_ok("math", op="除", a="CHAN1", b="CHAN1", param=0)  # 0/0 → NaN
        assert f2["name"] == "F2"
        # 9 fft／spectrum
        fr = job_ok("fft", source="CHAN1", range=[t0, t1], dx={}, window="Hanning", unit="dBm", r_ohm=50,
                    peak_count=5, peak_level=-80, peak_sort="Decreasing Magnitude", rbw=None, vbw=None)
        assert fr["ok"] and fr["spectrum_id"] and fr["peaks"], fr
        assert abs(fr["peaks"][0]["x"] - 1e6) / 1e6 < 0.05, fr["peaks"][0]
        sid = fr["spectrum_id"]
        s, b = http(f"/fft?k=tok&id={sid}&f0=0&f1=5e6&px=64&log=0")
        fn_, fmode, fx, flo, fhi = dec(b)
        assert s == 200 and fn_ > 0 and abs(fx[np.argmax(fhi)] - 1e6) < 1e5
        s, b = http(f"/fft?k=tok&id={sid}&f0=1e5&f1={fr['f_max']!r}&px=64&log=1")
        assert s == 200 and dec(b)[2].min() > 0
        assert http(f"/fft?k=tok&id=zz&f0=0&f1=1&px=64&log=0")[0] == 409
        tr = ok("fft_track_rf", spectrum_id=sid, x=9.5e5, direction=0, level=-200)
        assert tr["available"] and abs(tr["x"] - 1e6) / 1e6 < 0.05, tr
        assert rpc("fft_track_rf", spectrum_id="zz", x=0, direction=0, level=0)["error"]["code"] == "STALE"
        wr = job_ok("fft", source="CHAN1", range=[t0, t1], dx={}, window="Hanning", unit="dBm", r_ohm=50,
                    peak_count=5, peak_level=-80, peak_sort="Decreasing Magnitude", rbw=1e6, vbw=None)
        assert wr["ok"] and wr["segments"] > 1 and wr["rbw"] == wr["enbw"] and wr["vbw"] is None
        # 10 cursor／marker
        cr = ok("cursor_readout", t1=t0, t2=t1, dx={"CHAN2": 1e-9})
        assert set(cr["y"]) >= {"CHAN1", "CHAN2", "F1", "F2"} and cr["index1"] == 0 and cr["index2"] == N - 1
        far = ok("cursor_readout", t1=t0, t2=t1, dx={"CHAN2": 1.0})  # 平移出範圍 → null
        assert far["y"]["CHAN2"]["y1"] is None
        me = ok("marker_eval", mode="Manual X only", channel="CHAN1", x1=t0, x2=t1, y1=0.0, y2=0.0,
                screen_width=800, measurements=[])
        assert me["available"] and me["delta_x"] is not None, me
        assert rpc("marker_eval", mode="Track RF", channel="CHAN1", x1=0, x2=0, y1=0, y2=0, screen_width=800,
                   measurements=[])["error"]["code"] == "BAD_REQUEST"
        # 11 匯出
        csvp = job_ok("export_csv", range=[t0, t1], max_points=1000, directory=str(tmp))
        assert Path(csvp["path"]).exists() and Path(csvp["path"]).suffix == ".csv"
        mm = job_ok("measure", entries=ent, range=None, dx={}, threshold="10/50/90 %")
        exm = ok("export_measurements", rows=[{}] * 2, gen=mm["gen"], revision=mm["revision"], directory=str(tmp))
        assert Path(exm["path"]).exists() and "量測" in Path(exm["path"]).read_text("utf-8-sig")
        rep = ok("export_report", html="<!doctype html><p>報告 ✓</p>", directory=None)
        assert Path(rep["path"]).parent == Path(cap["path"]).parent and Path(rep["path"]).read_text("utf-8").endswith("報告 ✓</p>")
        assert rpc("export_report", html=None, directory=str(tmp))["error"]["code"] == "BAD_REQUEST"
        assert rpc("export_measurements", rows=[{}] * 2, gen=mm["gen"], revision=mm["revision"] - 1,
                   directory=str(tmp))["error"]["code"] == "STALE"
        # 12 BUSY 並行：慢截圖進行中再送 capture_info
        class Slow(type(api._drv)):
            def screenshot(self, opts):
                time.sleep(0.8)
                return super().screenshot(opts)
        slow = Slow()
        api._drv = slow
        shotbody = dict(directory=str(tmp), name="b", image_format="PNG", inverted=False, area="full")
        a = ok("screenshot", shotbody, request_id="r1")
        b = rpc("capture_info")
        assert not b["ok"] and b["error"]["code"] == "BUSY" and b["error"]["retryable"], b
        # 13 request_id 冪等
        a2 = ok("screenshot", shotbody, request_id="r1")
        assert a2 == a
        assert rpc("screenshot", {**shotbody, "name": "other"}, request_id="r1")["error"]["code"] == "BAD_REQUEST"
        t_end = time.time() + 10
        while time.time() < t_end:  # 等工作結束
            o = rpc("wait_events", {"since": seen["seq"], "timeout": 2})["result"]
            seen["seq"] = o["seq"]
            if any(e.get("id") == a["job"] for e in o["events"]):
                break
        assert ok("screenshot", shotbody, request_id="r1")["job"] == a["job"]
        # 14 STALE：重新開檔 gen+1，舊 gen
        fi2 = job_ok("open_waveform", path=cap["path"])
        assert fi2["gen"] == gen + 1
        assert wave("CHAN1", t0, t1, 10, gen)[0] == 409
        assert wave("CHAN1", t0, t1, 10, fi2["gen"])[0] == 200
        assert rpc("export_measurements", rows=[{}] * 2, gen=mm["gen"], revision=mm["revision"],
                   directory=str(tmp))["error"]["code"] == "STALE"
        assert rpc("fft_track_rf", spectrum_id=sid, x=1e6, direction=0, level=0)["error"]["code"] == "STALE"
        # 15 NaN → null（CSV 含 nan）
        nanp = tmp / "nan.csv"
        nanp.write_text("Time(s),CH1(V)\n0,1\n1e-6,nan\n2e-6,3\n3e-6,1\n", "utf-8")
        fi3 = job_ok("open_waveform", path=str(nanp))
        ch = fi3["channels"][0]
        assert ch["vmin"] == 1.0 and ch["vmax"] == 3.0
        cn = ok("cursor_readout", t1=1e-6, t2=2e-6, dx={})
        assert cn["y"]["CHAN1"]["y1"] is None and cn["y"]["CHAN1"]["y2"] == 3.0, cn
        s, raw = http("/rpc/cursor_readout?k=tok", {"t1": 1e-6, "t2": 2e-6, "dx": {}})
        assert b"NaN" not in raw and b"Infinity" not in raw
        nb = dec(wave("CHAN1", 0, 3e-6, 10, fi3["gen"])[1])
        assert np.isnan(nb[3]).any(), "二進位應保留 NaN"
        print("e2e self-check OK")
    finally:
        srv.stop()
        jobs_threads = threading.active_count()  # noqa: F841


if __name__ == "__main__":
    main()
