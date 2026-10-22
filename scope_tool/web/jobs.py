"""工作排程、事件環形緩衝、錯誤碼映射。

規則：儀器（VISA）工作一律由專用單一執行緒執行，全域儀器鎖
`acquire(blocking=False)`，搶不到 → BusyError（RPC 同步回 BUSY）。
分析工作另用一條執行緒，不拿儀器鎖、不排在儀器工作後面。
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from scope_tool.contracts import RemoteDesktopError, ScopeError, UnsupportedError

log = logging.getLogger("scope_tool.web")

RING_SIZE = 500
DEDUPE_SIZE = 256


class BusyError(Exception):
    """儀器鎖被佔用。"""


class BadRequestError(ValueError):
    """參數錯誤（映射 BAD_REQUEST）。"""


class StaleError(Exception):
    """gen／revision／spectrum_id 過期（映射 STALE）。L1b 可直接使用。"""

    code = "STALE"


_CODES = {"STALE", "BAD_REQUEST", "BUSY"}


def map_error(exc: BaseException) -> dict[str, Any]:
    """例外 → 契約錯誤物件。判斷順序：REMOTE_DESKTOP 優先於 SCOPE_ERROR。"""
    if isinstance(exc, BusyError):
        return {"code": "BUSY", "message": "儀器忙碌中，請等目前操作完成", "retryable": True}
    if isinstance(exc, RemoteDesktopError):
        return {"code": "REMOTE_DESKTOP", "message": "請關閉遠端桌面連線後重試", "retryable": False}
    if isinstance(exc, UnsupportedError):
        return {"code": "UNSUPPORTED", "message": str(exc), "retryable": False}
    if isinstance(exc, ScopeError):  # 含 ScopeTimeoutError
        return {"code": "SCOPE_ERROR", "message": str(exc), "retryable": False}
    code = getattr(exc, "code", None)  # 鴨子型別：分析層可丟帶 .code 的例外
    if code in _CODES:
        return {"code": code, "message": str(exc), "retryable": code == "BUSY"}
    if isinstance(exc, ValueError):  # 分析層 ValueError
        return {"code": "BAD_REQUEST", "message": str(exc), "retryable": False}
    log.exception("未預期錯誤", exc_info=exc)
    return {"code": "UNEXPECTED", "message": f"未預期錯誤：{exc}", "retryable": False}


def json_safe(o: Any) -> Any:
    """遞迴轉成可 JSON 的物件：NaN／Infinity → None，numpy／Path 轉原生型別。"""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, (str, int, bool)) or o is None:
        return o
    if isinstance(o, dict):
        return {str(k): json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if hasattr(o, "tolist"):  # numpy 純量／陣列
        return json_safe(o.tolist())
    return str(o)  # Path 等


def dumps(o: Any) -> bytes:
    return json.dumps(json_safe(o), ensure_ascii=False, allow_nan=False).encode("utf-8")


class EventBus:
    """事件環形緩衝（500）＋ Condition，供 wait_events long-poll。"""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._ring: deque[dict[str, Any]] = deque(maxlen=RING_SIZE)
        self.seq = 0

    def emit(self, ev: dict[str, Any]) -> dict[str, Any]:
        with self._cv:
            self.seq += 1
            ev = {"seq": self.seq, **json_safe(ev)}
            self._ring.append(ev)
            self._cv.notify_all()
            return ev

    def wait(self, since: int, timeout: float) -> dict[str, Any]:
        """回傳 seq > since 的事件；沒有就等到有或逾時（上限 25 秒）。"""
        deadline = time.monotonic() + max(0.0, min(float(timeout), 25.0))
        with self._cv:
            while self.seq <= since:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cv.wait(left)
            return {"seq": self.seq, "events": [e for e in self._ring if e["seq"] > since]}


class Jobs:
    def __init__(self) -> None:
        self.events = EventBus()
        self._inst_lock = threading.Lock()
        # ponytail: 每類一條執行緒；儀器鎖已保證儀器工作不會排隊，分析工作若多了再改 pool
        self._inst_exec = ThreadPoolExecutor(1, thread_name_prefix="inst")
        self._ana_exec = ThreadPoolExecutor(1, thread_name_prefix="ana")
        self._tbl: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._tbl_lock = threading.Lock()
        self._n = 0
        self._ctx = threading.local()

    @contextmanager
    def request(self, rid: str | None, params: dict[str, Any]) -> Iterator[None]:
        """server 在呼叫方法前綁定本次 request_id 與參數簽章。"""
        self._ctx.rid = rid
        self._ctx.sig = json.dumps(params, sort_keys=True, default=str, ensure_ascii=False)
        try:
            yield
        finally:
            self._ctx.rid = self._ctx.sig = None

    @contextmanager
    def try_lock(self) -> Iterator[None]:
        """非工作型方法暫時借用儀器鎖；搶不到 → BusyError。"""
        if not self._inst_lock.acquire(blocking=False):
            raise BusyError()
        try:
            yield
        finally:
            self._inst_lock.release()

    @property
    def busy(self) -> bool:
        return self._inst_lock.locked()

    def submit(self, kind: str, fn: Callable[[], Any], *, lock: bool) -> dict[str, Any]:
        """登記並執行一個工作，回 {job} 或（已完成的重送）{job, done}。"""
        rid = getattr(self._ctx, "rid", None)
        sig = getattr(self._ctx, "sig", None)
        with self._tbl_lock:
            ent = self._tbl.get(rid) if rid else None
            if ent is not None:
                if ent["sig"] != sig:
                    raise BadRequestError("同一個 request_id 卻帶了不同參數")
                out = {"job": ent["job"]}
                if ent["done"] is not None:
                    out["done"] = ent["done"]
                return out
            if lock and not self._inst_lock.acquire(blocking=False):
                raise BusyError()  # BUSY 不登記
            self._n += 1
            jid = f"j{self._n}"
            ent = {"sig": sig, "job": jid, "done": None}
            if rid:
                self._tbl[rid] = ent
                while len(self._tbl) > DEDUPE_SIZE:
                    self._tbl.popitem(last=False)
        (self._inst_exec if lock else self._ana_exec).submit(self._run, rid, jid, kind, fn, lock, ent)
        return {"job": jid}

    def _run(self, rid: str | None, jid: str, kind: str, fn: Callable[[], Any], lock: bool,
             ent: dict[str, Any]) -> None:
        try:
            done: dict[str, Any] = {"ok": True, "result": json_safe(fn())}
        except BaseException as e:  # noqa: BLE001 — 任何例外都要變成 job 事件
            done = {"ok": False, "error": map_error(e)}
        with self._tbl_lock:
            ent["done"] = done
            # 可重試的失敗不保留，讓使用者沿用同 id 重送時真的重做
            if rid and not done["ok"] and done["error"]["retryable"]:
                self._tbl.pop(rid, None)
        if lock:
            self._inst_lock.release()  # 先放鎖再發事件，前端收到事件即可接著下一個工作
        self.events.emit({"type": "job", "id": jid, "kind": kind, **done})


def _self_check() -> None:
    j = Jobs()
    gate = threading.Event()
    # 基本：成功與失敗
    with j.request("a", {"x": 1}):
        r = j.submit("t", lambda: {"v": float("nan")}, lock=False)
    assert set(r) == {"job"}
    ev = j.events.wait(0, 2)["events"][0]
    assert ev["type"] == "job" and ev["ok"] and ev["result"] == {"v": None}, ev
    # 已完成重送 → 帶 done；同 id 不同參數 → BAD_REQUEST
    with j.request("a", {"x": 1}):
        r2 = j.submit("t", lambda: 1 / 0, lock=False)
    assert r2["job"] == r["job"] and r2["done"]["ok"], r2
    try:
        with j.request("a", {"x": 2}):
            j.submit("t", lambda: 1, lock=False)
        raise AssertionError("應拋 BadRequestError")
    except BadRequestError:
        pass
    # 儀器鎖：第二個 → Busy 且不登記；進行中重送回原 job
    with j.request("b", {}):
        rb = j.submit("slow", lambda: gate.wait(5) and "ok", lock=True)
    with j.request("c", {}):
        try:
            j.submit("x", lambda: 1, lock=True)
            raise AssertionError("應 BUSY")
        except BusyError:
            pass
    assert "c" not in j._tbl
    with j.request("b", {}):
        assert j.submit("slow", lambda: 0, lock=True) == {"job": rb["job"]}
    gate.set()
    seen = j.events.wait(1, 3)["events"]
    assert any(e["id"] == rb["job"] and e["result"] == "ok" for e in seen), seen
    assert not j.busy
    # 失敗映射
    assert map_error(RemoteDesktopError("x"))["code"] == "REMOTE_DESKTOP"
    assert map_error(UnsupportedError("x"))["code"] == "UNSUPPORTED"
    assert map_error(ScopeError("x"))["code"] == "SCOPE_ERROR"
    assert map_error(StaleError("x"))["code"] == "STALE"
    assert map_error(ValueError("x"))["code"] == "BAD_REQUEST"
    assert map_error(KeyError("x"))["message"].startswith("未預期錯誤：")
    # 可重試失敗不保留
    with j.request("d", {}):
        j.submit("t", lambda: (_ for _ in ()).throw(BusyError()), lock=False)
    j.events.wait(j.events.seq, 0.3)
    time.sleep(0.2)
    assert "d" not in j._tbl
    # 去重表上限
    for i in range(DEDUPE_SIZE + 5):
        with j.request(f"r{i}", {}):
            j.submit("t", lambda: 1, lock=False)
    assert len(j._tbl) <= DEDUPE_SIZE
    # 事件環形緩衝與 long-poll 逾時
    for _ in range(RING_SIZE + 10):
        j.events.emit({"type": "driver"})
    assert len(j.events.wait(0, 0)["events"]) == RING_SIZE
    time.sleep(0.5)  # 等前面的背景工作事件發完
    t0 = time.monotonic()
    assert j.events.wait(j.events.seq, 0.2)["events"] == [] and time.monotonic() - t0 >= 0.15
    print("jobs self-check OK")


if __name__ == "__main__":
    _self_check()
