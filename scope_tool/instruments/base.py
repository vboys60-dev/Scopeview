"""SCPI 共用邏輯：InfiniiVision 與 Infiniium 都繼承的中介類別。

實際與真機互動的路徑（_write/_query/_query_binary/_check_error/_run_state）
沒有真機無法驗證，行為只在 docstring 標註處寫明假設。
# 待真機驗證
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

import numpy as np
import pyvisa

from scope_tool.contracts import RemoteDesktopError, ScopeDriver, ScopeError, ScopeTimeoutError


class SCPIDriver(ScopeDriver):
    """InfiniiVision 與 Infiniium 共用的 SCPI 存取層。

    子類別只需要處理兩家系列在命令字面上的差異，共用的錯誤轉換、
    逾時、RUN/STOP 還原都放在這裡。
    """

    def _write(self, cmd: str) -> None:
        """送出寫入型命令，用 `*OPC?` 等待完成。例外一律轉成 ScopeError。"""
        try:
            self.res.write(cmd)
            self.res.query("*OPC?")
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _query(self, cmd: str) -> str:
        """送出查詢命令，回傳去除頭尾空白的字串。"""
        try:
            return self.res.query(cmd).strip()
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _query_binary(self, cmd: str, datatype: str) -> np.ndarray:
        """送出回傳 IEEE488.2 binary block 的查詢，回傳 numpy 陣列。"""
        try:
            return np.array(
                self.res.query_binary_values(cmd, datatype=datatype, container=list)
            )
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _wrap(self, exc: Exception, cmd: str) -> ScopeError:
        """把 pyvisa 例外轉成本工具的 ScopeError 子類別。"""
        if isinstance(exc, pyvisa.errors.VisaIOError) and "timeout" in str(exc).lower():
            return ScopeTimeoutError(f"執行 {cmd!r} 逾時：{exc}")
        return ScopeError(f"執行 {cmd!r} 失敗：{exc}")

    def _check_error(self) -> None:
        """查 `:SYSTem:ERRor?`，273 轉 RemoteDesktopError，其他非 0 轉 ScopeError。"""
        resp = self._query(":SYSTem:ERRor?")
        code_str = resp.split(",", 1)[0].strip()
        try:
            code = int(code_str)
        except ValueError:
            return
        if code == 0:
            return
        if code == 273:
            raise RemoteDesktopError("儀器畫面無法擷取，請關閉遠端桌面連線後重試")
        raise ScopeError(f"儀器回報錯誤：{resp}")

    @contextmanager
    def _timeout(self, ms: int) -> Iterator[None]:
        """暫時改 VISA timeout，離開時（含例外）還原成原本的值。"""
        original = self.res.timeout
        self.res.timeout = ms
        try:
            yield
        finally:
            self.res.timeout = original

    #: 本 driver 上次寫 :RUN 的 time.monotonic()；未知（使用者手動按的）為 None
    _run_started: float | None = None

    @contextmanager
    def _run_state(self) -> Iterator[None]:
        """記住 RUN/STOP，離開時（含例外）還原成呼叫前的樣子。

        # 待真機驗證：用 `:OPERegister:CONDition?` 的 RUN 位元（bit3，值8）
        # 判斷目前是否在跑。查不到就保守假設原本在跑，離開時還原成 RUN。
        """
        try:
            cond = int(self._query(":OPERegister:CONDition?"))
            was_running = bool(cond & 0x8)
        except (ScopeError, ValueError):
            was_running = True
        try:
            yield
        finally:
            self._write(":RUN" if was_running else ":STOP")
            if was_running:
                self._run_started = time.monotonic()

    def channels(self) -> list[str]:
        """查 `:CHANnel<n>:DISPlay?` 找出目前開啟中的通道，兩家系列命令相同。

        # 真機驗證（InfiniiVision）：關閉的通道回 "0"；查到不存在的通道會逾時，所以
        # 探測期間 timeout 縮為 1 秒。Infiniium 未測，LAN 較慢時 1 秒可能偏短。
        """
        found: list[str] = []
        with self._timeout(1000):  # 探測不存在的通道會等到逾時，縮短
            for n in range(1, 9):
                try:
                    resp = self._query(f":CHANnel{n}:DISPlay?")
                except ScopeError:
                    break
                if resp.strip() in ("1", "ON"):
                    found.append(f"CHAN{n}")
        # 真機驗證：探測到不存在的通道會逾時並留下 -113，清掉避免污染之後的 _check_error
        self.res.write("*CLS")
        return found


if __name__ == "__main__":
    class _StubResource:
        """假的 pyvisa resource，只記錄收到的命令並回固定值。"""

        def __init__(self) -> None:
            self.timeout = 5000
            self.commands: list[str] = []

        def write(self, cmd: str) -> None:
            self.commands.append(cmd)

        def query(self, cmd: str) -> str:
            self.commands.append(cmd)
            if cmd == "*OPC?":
                return "1"
            if cmd == ":SYSTem:ERRor?":
                return "+0,\"No error\""
            if cmd == ":OPERegister:CONDition?":
                return "8"
            if cmd.startswith(":CHANnel"):
                return "1" if cmd in (":CHANnel1:DISPlay?", ":CHANnel2:DISPlay?") else "0"
            return "0"

        def query_binary_values(self, cmd, datatype, container):
            self.commands.append(cmd)
            return [1, 2, 3]

    class _StubDriver(SCPIDriver):
        series = None
        model_prefixes = ()

        def screenshot(self, opts):
            raise NotImplementedError

        def max_points(self):
            raise NotImplementedError

        def capture(self, channels, points, retrigger):
            raise NotImplementedError

    res = _StubResource()
    d = _StubDriver(res, "STUB")

    d._write(":RUN")
    assert res.commands[-2:] == [":RUN", "*OPC?"]

    assert d._query(":SYSTem:ERRor?") == "+0,\"No error\""

    d._check_error()  # 不應該拋例外

    with d._timeout(15000):
        assert res.timeout == 15000
    assert res.timeout == 5000

    with d._run_state():
        pass
    assert res.commands[-2:] == [":RUN", "*OPC?"]  # OPERegister 回 8，bit3 有值 → 還原成 RUN

    assert d.channels() == ["CHAN1", "CHAN2"]

    arr = d._query_binary(":WAVeform:DATA?", "B")
    assert list(arr) == [1, 2, 3]

    # Error 273 要轉成 RemoteDesktopError
    class _ErrResource(_StubResource):
        def query(self, cmd: str) -> str:
            if cmd == ":SYSTem:ERRor?":
                return "273,\"Remote desktop\""
            return super().query(cmd)

    d2 = _StubDriver(_ErrResource(), "STUB")
    try:
        d2._check_error()
    except RemoteDesktopError:
        pass
    else:
        raise AssertionError("Error 273 應該轉成 RemoteDesktopError")

    print("base self-check OK")
