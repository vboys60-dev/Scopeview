"""HTTP 自檢：保留原伺服器回歸，另驗長度、JSON 與閒置逾時。"""
from __future__ import annotations

import json
import socket
import sys
import threading
from contextlib import contextmanager
from http.client import HTTPResponse
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

from scope_tool.web.api import STATIC
from scope_tool.web.jobs import Jobs


def _http_check(handler_cls: type) -> None:
    assert handler_cls.timeout == 60
    calls = []
    auth = []

    def rpc(name: str, body: object) -> dict:
        calls.append((name, body))
        return {"ok": True, "result": body}

    class Handler(handler_cls):
        timeout = 0.15  # 只縮短測試類別，不更動正式伺服器
        srv = SimpleNamespace(token="tok", methods={"get_state": {}}, rpc=rpc)

        def _auth(self, q: dict) -> bool:
            auth.append(q)
            return super()._auth(q)

    @contextmanager
    def connection() -> Iterator[socket.socket]:
        client, peer = socket.socketpair()
        errors = []

        def serve() -> None:
            try:
                with peer:
                    Handler(peer, ("127.0.0.1", 0), None)
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=serve, daemon=True)
        client.settimeout(2)
        worker.start()
        try:
            yield client
        finally:
            client.close()
            worker.join(2)
            assert not worker.is_alive(), "HTTP 處理執行緒未結束"
            assert not errors, errors

    def send(client: socket.socket, length: str, body: bytes = b"", token: str = "tok") -> None:
        head = (f"POST /rpc/get_state?k={token} HTTP/1.1\r\nHost: localhost\r\n"
                f"Content-Length: {length}\r\n\r\n")
        client.sendall(head.encode("latin-1") + body)

    def response(client: socket.socket) -> tuple[int, dict]:
        with HTTPResponse(client) as resp:
            resp.begin()
            return resp.status, json.loads(resp.read())

    def closed(client):
        try: return client.recv(1) == b""
        except (ConnectionResetError, ConnectionAbortedError): return True

    for length in ("abc", "-1", "²", "9" * 30, str(8 * 1024 * 1024 + 1)):
        with connection() as client:
            send(client, length)
            if sys.platform != "win32": send(client, "2", b"{}")  # 若沒關線，伺服器會回應這筆（recv 得到 b"H"）；Windows 關線有未讀資料會 RST 吞掉 400，改只靠 closed()
            status, payload = response(client)
            assert status == 400 and payload["error"]["code"] == "BAD_REQUEST", length
            assert closed(client), length  # 無 body 也立即拒絕並關線
    assert not calls and not auth
    with connection() as client:
        send(client, "2", token="bad")  # 宣告 body 卻不送，必須先讀到閒置逾時
        assert closed(client), "應逾時關線，不應提前回 403"
    assert not calls and not auth, "token 檢查不得前移"
    with connection() as client:
        for raw, expected in ((b"{}", {}), (b"", {}), (b'{"x": 1}', {"x": 1})):
            send(client, str(len(raw)), raw)
            assert response(client) == (200, {"ok": True, "result": expected})
        count = len(calls)
        for raw in (b"{", b"\xff"):
            send(client, str(len(raw)), raw)
            assert response(client) == (200, {"ok": False, "error": {
                "code": "BAD_REQUEST", "message": "body 不是合法 JSON", "retryable": False}})
        assert len(calls) == count
        send(client, "2", b"{}", token="bad")
        status, payload = response(client)
        assert status == 403 and payload["error"]["code"] == "FORBIDDEN"
        send(client, "2", b"{}")  # 錯誤後同一連線仍可處理合法 JSON
        assert response(client) == (200, {"ok": True, "result": {}})
    print("server HTTP boundary self-check OK")


def _self_check(server_cls: type, handler_cls: type) -> None:
    _http_check(handler_cls)
    import tempfile
    import time
    import urllib.error
    import urllib.request
    from scope_tool.instruments.fake import FakeDriver
    from scope_tool.web.api import Api, _filename, _write_or_temp, _check_cfg
    from scope_tool.web.jobs import BadRequestError
    from scope_tool.web.jobs import StaleError
    class SlowFake(FakeDriver):
        def screenshot(self, opts):  # type: ignore[override]
            time.sleep(0.6)
            return super().screenshot(opts)
    class FakeAna:  # 只為驗證 server 對分析工作的包裝
        def open_waveform(self, path):
            return {"path": path, "x": float("nan")}
        def close_waveform(self):
            return None
    def wave_bytes(ana, ch, t0, t1, px, gen):
        if gen != 1:
            raise StaleError("開檔世代已變更")
        return b"\x00" * 16
    FakeMod = type("FakeMod", (), {"wave_bytes": staticmethod(wave_bytes),
                                  "fft_bytes": staticmethod(lambda *a: b"\x01" * 16)})
    for name in ("a:b", "C:x", "a?b", "a*b", 'a"b', "a<b", "a>b", "a|b", "a\x01b", "", ".", "..", "a/b", "a\\b", "x" * 201):
        try:
            _filename(name)
        except BadRequestError:
            pass
        else:
            raise AssertionError(name)
    for name in ("scope", "測試 波形", "a.b", "abc.", "abc ", "x" * 200):
        assert _filename(name) == name
    writes = []
    def fake_write(directory, name):
        writes.append((directory, name))
        if len(writes) == 1:
            raise OSError("測試")
        return directory / name
    _write_or_temp(Path("/unused"), "original", fake_write)
    assert writes[1] == (Path(tempfile.gettempdir()) / "scope_tool", "scope_tool_recovered")
    _check_cfg("screenshot_name", "scope")
    try: _check_cfg("waveform_name", "a:b")
    except BadRequestError: pass
    else: raise AssertionError("不合法檔名應被拒絕")
    from scope_tool.config import DEFAULTS
    assert Api(Jobs(), cfg={**DEFAULTS, "waveform_name": "a:b"}, persist=False)._cfg["waveform_name"] == "wave"
    jobs = Jobs()
    api = Api(jobs, cfg=dict(__import__("scope_tool.config", fromlist=["x"]).DEFAULTS), persist=False)
    srv = server_cls(api, FakeAna(), jobs, token="tok", analysis_mod=FakeMod)
    srv.start()
    base = f"http://127.0.0.1:{srv.port}"
    def req(path, body=None):
        r = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers
    def rpc(name, body, k="tok"):
        s, b, _ = req(f"/rpc/{name}?k={k}", body)
        return s, json.loads(b)
    assert (rpc("get_state", {}, k="bad")[0], rpc("no_such_method", {})[0], req("/wave?ch=C&t0=0")[0]) == (403, 404, 403)
    assert req("/")[2]["Content-Type"][:9] == "text/html" and req("/js/bridge.js")[0] == 200
    assert req("/js/../../server.py")[0] == req("/nope")[0] == 404
    st = rpc("get_state", {})[1]["result"]
    assert st["connected"] is False and st["native_dialogs"] is False and "catalog" in st
    seq0 = st["seq"]
    rpc("open_waveform", {"path": "x"})
    ev = rpc("wait_events", {"since": seq0, "timeout": 5})[1]["result"]
    assert ev["events"][0]["type"] == "job" and ev["events"][0]["result"]["x"] is None, ev
    assert rpc("close_waveform", {})[1]["ok"]
    for bad in ({"screenshot_dir": None}, {"screenshot_dir": ""}, {"points": None}, {"points": 0}):
        assert rpc("save_config", {"patch": bad})[1]["error"]["code"] == "BAD_REQUEST", bad  # 型別錯誤
    old_name = api._cfg["screenshot_name"]
    assert rpc("save_config", {"patch": {"screenshot_name": "a:b"}})[1]["error"]["code"] == "BAD_REQUEST"
    assert api._cfg["screenshot_name"] == old_name
    assert rpc("connect_fake", {})[1]["result"]["model"] == "FAKE-SCOPE"
    cap = dict(directory="/x", name="n", channels=["CHAN1"], points=10, retrigger=False)
    for bad in ({"retrigger": "false"}, {"channels": "CHAN1"}, {"channels": ["CHAN10"]}):  # 型別／白名單：不得碰儀器
        assert rpc("capture", {**cap, **bad})[1]["error"]["code"] == "BAD_REQUEST", bad
    api._drv = SlowFake()
    tmp = tempfile.mkdtemp()
    shot = {"directory": tmp, "name": "s", "image_format": "PNG", "inverted": False, "area": "full"}
    before = set(Path(tmp).iterdir())
    bad_shot = rpc("screenshot", {**shot, "name": "a:b"})[1]
    assert not bad_shot["ok"] and bad_shot["error"]["code"] == "BAD_REQUEST" and "result" not in bad_shot
    assert set(Path(tmp).iterdir()) == before
    a = rpc("screenshot", {**shot, "request_id": "r1"})[1]["result"]
    b = rpc("capture_info", {})[1]
    assert not b["ok"] and b["error"]["code"] == "BUSY" and b["error"]["retryable"], b
    assert rpc("screenshot", {**shot, "request_id": "r1"})[1]["result"] == a
    assert rpc("screenshot", {**shot, "name": "o", "request_id": "r1"})[1]["error"]["code"] == "BAD_REQUEST"
    assert rpc("capture_info", {"request_id": "r1"})[1]["error"]["code"] == "BAD_REQUEST"  # 同 id 不同方法
    since, got = seq0 + 1, []
    while not any(e.get("id") == a["job"] for e in got):
        o = rpc("wait_events", {"since": since, "timeout": 2})[1]["result"]
        got += o["events"]
        since = o["seq"]
    seqs = [e["seq"] for e in got]
    assert seqs == sorted(set(seqs)), seqs
    done = [e for e in got if e.get("id") == a["job"]][0]
    assert done["ok"] and done["result"]["preview"] == 1 and Path(done["result"]["path"]).exists(), done
    assert rpc("screenshot", {**shot, "request_id": "r1"})[1]["result"]["done"]["ok"]
    s, data, h = req("/screenshot/last?k=tok&n=1")
    assert data.startswith(b"\x89PNG") and h["Content-Type"] == "image/png"
    assert req("/wave?k=tok&ch=CHAN1&t0=0&t1=1&px=10&gen=1")[:2] == (200, b"\x00" * 16)
    s, b, _ = req("/wave?k=tok&ch=CHAN1&t0=0&t1=1&px=10&gen=2")
    assert s == 409 and json.loads(b)["error"]["code"] == "STALE"
    assert req("/fft?k=tok&id=s1&f0=0&f1=1&px=10&log=0")[0] == 200 and req("/wave?k=tok&ch=CHAN1")[0] == 400
    api._drv = None
    j = rpc("connect", {"resource": "BOGUS::nowhere", "series_override": None})[1]["result"]["job"]
    e = None
    for _ in range(40):  # CI runner 開 VISA 資源可能 >1 秒，輪詢最多約 20 秒
        time.sleep(.5)
        e = next((x for x in rpc("wait_events", {"since": 0, "timeout": 1})[1]["result"]["events"] if x.get("id") == j), None)
        if e: break
    assert e, "connect 事件逾時"
    assert not e["ok"] and e["error"]["code"] == "SCOPE_ERROR" and "BOGUS" in e["error"]["message"], e
    assert rpc("wait_events", {"since": 10**6, "timeout": 0.3})[1]["result"]["events"] == []
    srv.stop()
    assert jobs.close(lambda: None, 2) and STATIC.is_dir()
    print("server self-check OK")



if __name__ == "__main__":
    from scope_tool.web.server import Server, _Handler
    _self_check(Server, _Handler)
