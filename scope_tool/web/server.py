"""本機 HTTP 伺服器（stdlib，僅綁 127.0.0.1）。

- 靜態檔白名單（`/`、`/js`、`/css`、`/static`）不驗 token；
  `/rpc`、`/wave`、`/fft`、`/screenshot` 驗 token（`?k=`）。
- `POST /rpc/<method>`：body 為 kwargs JSON（需帶齊 params 所有鍵），保留鍵 request_id。
- `/wave`、`/fft` 轉給 `analysis_api.wave_bytes / fft_bytes`
  （L1b 提供：wave_bytes(analysis,ch,t0,t1,px,gen)、fft_bytes(analysis,id,f0,f1,px,log:bool)；
  過期丟帶 .code=="STALE" 的例外，server 轉 409）。
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from scope_tool.web.api import CONTRACT_PATH
from scope_tool.web.jobs import BadRequestError, Jobs, dumps, map_error

log = logging.getLogger("scope_tool.web")
STATIC = Path(__file__).parent / "static"
# Windows 的 mimetypes 讀登錄檔，.js 可能變 text/plain，故寫死
MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
    ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
}
_STATIC_PREFIX = {"js": "js", "css": "css", "static": ""}  # URL 第一段 → static/ 下的子目錄
_HTTP = {"STALE": 409, "BAD_REQUEST": 400, "FORBIDDEN": 403, "NOT_FOUND": 404}
MAX_BODY = 8 * 1024 * 1024


class _MissingAnalysis:
    """analysis_api 尚未存在時的退化物件：任何分析方法都回明確錯誤。"""

    def __getattr__(self, name: str) -> Any:
        def _f(**_: Any) -> Any:
            raise RuntimeError("分析服務（analysis_api）尚未安裝")
        return _f


class Server:
    def __init__(self, api: Any, analysis: Any, jobs: Jobs, token: str | None = None,
                 port: int = 0, analysis_mod: Any = None) -> None:
        self.api, self.analysis, self.jobs = api, analysis or _MissingAnalysis(), jobs
        self.token = token or secrets.token_urlsafe(16)
        if analysis_mod is None:
            try:
                from scope_tool.web import analysis_api as analysis_mod  # L1b 提供
            except ImportError:
                pass
        self.amod = analysis_mod
        self.methods = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))["methods"]
        handler = type("Handler", (_Handler,), {"srv": self})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/?k={self.token}"

    def start(self) -> None:
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="http").start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    # --------------------------------------------------------------- RPC
    def rpc(self, name: str, body: Any) -> dict[str, Any]:
        """回傳信封 dict；不存在的方法由呼叫端先擋（404）。"""
        try:
            if not isinstance(body, dict):
                raise BadRequestError("body 必須是 JSON 物件")
            body = dict(body)
            rid = body.pop("request_id", None)
            if name == "wait_events":
                if set(body) != {"since", "timeout"}:
                    raise BadRequestError("wait_events 需要 since、timeout")
                return {"ok": True, "result": self.jobs.events.wait(int(body["since"]), float(body["timeout"]))}
            m = self.methods[name]
            want = {p["name"] for p in m["params"]}
            if set(body) != want:
                raise BadRequestError(f"參數鍵不符：缺 {sorted(want - set(body))}，多 {sorted(set(body) - want)}")
            owner = self.api if m["owner"] == "Api" else self.analysis
            fn = getattr(owner, name)
            with self.jobs.request(rid, body):
                if m["job"] and m["owner"] == "Analysis":  # Api 的工作型方法自行 submit
                    return {"ok": True, "result": self.jobs.submit(name, lambda: fn(**body), lock=m["lock"])}
                return {"ok": True, "result": fn(**body)}
        except BaseException as e:  # noqa: BLE001
            return {"ok": False, "error": map_error(e)}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    srv: Server

    def log_message(self, *a: Any) -> None:  # 安靜
        pass

    # ----------------------------------------------------------- 輸出
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, dumps(obj), "application/json; charset=utf-8")

    def _err(self, code: str, message: str, http: int | None = None) -> None:
        self._json({"ok": False, "error": {"code": code, "message": message, "retryable": False}},
                   http or _HTTP.get(code, 500))

    def _auth(self, q: dict[str, list[str]]) -> bool:
        k = (q.get("k") or [""])[0]
        if hmac.compare_digest(k.encode(), self.srv.token.encode()):
            return True
        self._err("FORBIDDEN", "token 錯誤")
        return False

    # ----------------------------------------------------------- 路由
    def do_GET(self) -> None:  # noqa: N802
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        parts = [p for p in u.path.split("/") if p]
        head = parts[0] if parts else ""
        try:
            if head in ("wave", "fft"):
                if self._auth(q):
                    self._binary(head, q)
            elif head == "screenshot":
                if self._auth(q):
                    self._shot()
            else:
                self._static(parts)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:  # noqa: N802
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        parts = [p for p in u.path.split("/") if p]
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if 0 < n <= MAX_BODY else b""
        if n > MAX_BODY:
            self.close_connection = True
            return self._err("BAD_REQUEST", "body 過大")
        if len(parts) != 2 or parts[0] != "rpc":
            return self._err("NOT_FOUND", "路徑不存在")
        if not self._auth(q):
            return
        name = parts[1]
        if name != "wait_events" and name not in self.srv.methods:
            return self._err("NOT_FOUND", f"方法不存在：{name}")
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            return self._json({"ok": False, "error": {"code": "BAD_REQUEST", "message": "body 不是合法 JSON",
                                                      "retryable": False}})
        try:
            self._json(self.srv.rpc(name, body))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _static(self, parts: list[str]) -> None:
        if not parts:
            f = STATIC / "index.html"
        elif parts[0] in _STATIC_PREFIX and len(parts) > 1:
            f = STATIC / _STATIC_PREFIX[parts[0]] / "/".join(parts[1:])
        else:
            return self._err("NOT_FOUND", "路徑不存在")
        try:
            f = f.resolve()
            f.relative_to(STATIC.resolve())  # 擋 ../
            ctype = MIME[f.suffix.lower()]
            if any(p.startswith(".") for p in f.relative_to(STATIC.resolve()).parts):
                raise KeyError
            data = f.read_bytes()
        except (ValueError, KeyError, OSError):
            return self._err("NOT_FOUND", "檔案不存在")
        self._send(200, data, ctype)

    def _binary(self, kind: str, q: dict[str, list[str]]) -> None:
        mod = self.srv.amod
        fn = getattr(mod, "wave_bytes" if kind == "wave" else "fft_bytes", None)
        if fn is None:
            return self._err("UNEXPECTED", "分析服務尚未安裝", 500)
        try:
            g = {k: v[0] for k, v in q.items()}
            args = ((g["ch"], float(g["t0"]), float(g["t1"]), int(g["px"]), int(g["gen"])) if kind == "wave"
                    else (g["id"], float(g["f0"]), float(g["f1"]), int(g["px"]), g["log"] == "1"))
            data = fn(self.srv.analysis, *args)
        except (KeyError, ValueError) as e:  # 參數缺漏／格式錯（分析層 ValueError 同）
            return self._err("BAD_REQUEST", f"參數錯誤：{e}")
        except Exception as e:  # noqa: BLE001
            err = map_error(e)
            return self._err(err["code"], err["message"])
        self._send(200, data, "application/octet-stream")

    def _shot(self) -> None:
        data = self.srv.api._last_screenshot()
        if data is None:
            return self._err("NOT_FOUND", "尚無截圖")
        self._send(200, data, "image/bmp" if data[:2] == b"BM" else "image/png")



def _self_check() -> None:
    import tempfile
    import time
    import urllib.error
    import urllib.request
    from scope_tool.instruments.fake import FakeDriver
    from scope_tool.web.api import Api
    from scope_tool.web.jobs import StaleError
    class SlowFake(FakeDriver):
        def screenshot(self, opts):  # type: ignore[override]
            time.sleep(0.6)
            return super().screenshot(opts)
    class FakeAna:  # 只為驗證 server 對分析工作的包裝
        def open_waveform(self, path):
            return {"path": path, "x": float("nan")}
    def wave_bytes(ana, ch, t0, t1, px, gen):
        if gen != 1:
            raise StaleError("開檔世代已變更")
        return b"\x00" * 16
    FakeMod = type("FakeMod", (), {"wave_bytes": staticmethod(wave_bytes),
                                  "fft_bytes": staticmethod(lambda *a: b"\x01" * 16)})
    jobs = Jobs()
    api = Api(jobs, cfg=dict(__import__("scope_tool.config", fromlist=["x"]).DEFAULTS), persist=False)
    srv = Server(api, FakeAna(), jobs, token="tok", analysis_mod=FakeMod)
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
    assert rpc("get_state", {}, k="bad")[0] == 403
    assert rpc("no_such_method", {})[0] == 404
    assert req("/wave?ch=CHAN1&t0=0&t1=1&px=10&gen=1")[0] == 403
    assert req("/")[2]["Content-Type"].startswith("text/html")
    assert req("/js/bridge.js")[2]["Content-Type"].startswith("text/javascript")
    assert req("/js/../../server.py")[0] == 404 and req("/nope")[0] == 404
    assert rpc("save_config", {})[1]["error"]["code"] == "BAD_REQUEST"
    st = rpc("get_state", {})[1]["result"]
    assert st["connected"] is False and st["native_dialogs"] is False and "catalog" in st
    seq0 = st["seq"]
    assert "job" in rpc("open_waveform", {"path": "x"})[1]["result"]
    ev = rpc("wait_events", {"since": seq0, "timeout": 5})[1]["result"]
    assert ev["events"][0]["type"] == "job" and ev["events"][0]["result"]["x"] is None, ev
    assert rpc("connect_fake", {})[1]["result"]["model"] == "FAKE-SCOPE"
    api._drv = SlowFake()
    tmp = tempfile.mkdtemp()
    shot = {"directory": tmp, "name": "s", "image_format": "PNG", "inverted": False, "area": "full"}
    a = rpc("screenshot", {**shot, "request_id": "r1"})[1]["result"]
    b = rpc("capture_info", {})[1]
    assert not b["ok"] and b["error"]["code"] == "BUSY" and b["error"]["retryable"], b
    assert rpc("screenshot", {**shot, "request_id": "r1"})[1]["result"] == a
    assert rpc("screenshot", {**shot, "name": "o", "request_id": "r1"})[1]["error"]["code"] == "BAD_REQUEST"
    since, got = seq0 + 1, []
    while not any(e.get("id") == a["job"] for e in got):
        o = rpc("wait_events", {"since": since, "timeout": 2})[1]["result"]
        got += o["events"]
        since = o["seq"]
    seqs = [e["seq"] for e in got]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), seqs
    done = [e for e in got if e.get("id") == a["job"]][0]
    assert done["ok"] and done["result"]["preview"] == 1 and Path(done["result"]["path"]).exists(), done
    d = rpc("screenshot", {**shot, "request_id": "r1"})[1]["result"]
    assert d["job"] == a["job"] and d["done"]["ok"], d
    s, data, h = req("/screenshot/last?k=tok&n=1")
    assert s == 200 and data.startswith(b"\x89PNG") and h["Content-Type"] == "image/png"
    assert req("/wave?k=tok&ch=CHAN1&t0=0&t1=1&px=10&gen=1")[:2] == (200, b"\x00" * 16)
    s, b, _ = req("/wave?k=tok&ch=CHAN1&t0=0&t1=1&px=10&gen=2")
    assert s == 409 and json.loads(b)["error"]["code"] == "STALE"
    assert req("/fft?k=tok&id=s1&f0=0&f1=1&px=10&log=0")[0] == 200 and req("/wave?k=tok&ch=CHAN1")[0] == 400
    t0 = time.time()
    o = rpc("wait_events", {"since": 10**6, "timeout": 0.3})[1]["result"]
    assert o["events"] == [] and time.time() - t0 >= 0.25
    srv.stop()
    print("server self-check OK")


if __name__ == "__main__":
    _self_check()
