"""SCPI 共用邏輯：InfiniiVision 與 Infiniium 都繼承的中介類別。

實際與真機互動的路徑（_write/_query/_query_binary/_check_error）
沒有真機無法驗證，行為只在 docstring 標註處寫明假設。
# 待真機驗證
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

import numpy as np
import pyvisa

from scope_tool.contracts import Preamble, RemoteDesktopError, ScopeDriver, ScopeError, ScopeTimeoutError, Waveform


def _binary_block(data: bytes) -> bytes:
    """自我檢查共用：產生含結尾換行的 IEEE488.2 block。"""
    length = str(len(data)).encode("ascii")
    return b"#" + str(len(length)).encode("ascii") + length + data + b"\n"


def _waveform_from_raw(channel: str, pre: Preamble, raw: np.ndarray,
                       previous: Waveform | None) -> Waveform:
    """相鄰通道的時間參數與點數相同時，共用時間陣列。"""
    old = previous.preamble if previous is not None else None
    if old is not None and (pre.x_increment, pre.x_origin, pre.x_reference, pre.points) == (
            old.x_increment, old.x_origin, old.x_reference, old.points) and len(raw) == len(previous.time):
        return Waveform(channel=channel, time=previous.time, voltage=pre.volts(raw), preamble=pre)
    return Waveform.from_raw(channel, pre, raw)


class SCPIDriver(ScopeDriver):
    """InfiniiVision 與 Infiniium 共用的 SCPI 存取層。

    子類別只需要處理兩家系列在命令字面上的差異，共用的錯誤轉換、
    逾時與擷取前等待都放在這裡。
    """

    def _write(self, cmd: str) -> None:
        """送出寫入型命令，用 `*OPC?` 等待完成。例外一律轉成 ScopeError。"""
        try:
            self.res.write(cmd)
            self.res.query("*OPC?")
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _write_nowait(self, cmd: str) -> None:
        """送出寫入型命令但不等 `*OPC?`。儀器在等待觸發（Single/Normal）時 `*OPC?` 不會回應。"""
        try:
            self.res.write(cmd)
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _clear(self) -> None:
        """VISA device clear，卡住的查詢之後用來恢復通訊；失敗就算了。"""
        try:
            self.res.clear()
        except Exception:
            pass

    def _query(self, cmd: str) -> str:
        """送出查詢命令，回傳去除頭尾空白的字串。"""
        try:
            return self.res.query(cmd).strip()
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _query_binary(self, cmd: str, datatype: str) -> np.ndarray:
        """送出回傳 IEEE488.2 binary block 的查詢，回傳 numpy 陣列。"""
        try:
            dtype = {"B": np.dtype("uint8"), "H": np.dtype("<u2")}[datatype]
            self.res.write(cmd)
            header = self.res.read_bytes(2)
            if len(header) != 2 or header[:1] != b"#" or not b"1" <= header[1:] <= b"9":
                raise ValueError("不是 definite-length block")
            total = int(self.res.read_bytes(int(header[1:])))
            data = bytearray(total)
            offset = 0
            while offset < total:
                size = min(4 * 1024 * 1024, total - offset)
                chunk = self.res.read_bytes(size)
                if len(chunk) != size:
                    raise ValueError("binary block 資料不足")
                data[offset:offset + size] = chunk
                offset += size
            if self.res.read_bytes(1) != b"\n":
                raise ValueError("binary block 缺少結尾換行")
            return np.frombuffer(data, dtype=dtype)
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

    def _is_running(self) -> bool:
        """用操作暫存器的 RUN 位元（bit3，值8）判斷是否在跑。"""
        return bool(int(self._query(":OPERegister:CONDition?")) & 0x8)

    def _prepare_capture(self, retrigger: bool) -> None:
        """RUN 中先等完整記錄再 STOP；擷取後維持 STOP。Infiniium 待真機驗證。"""
        if retrigger:
            self._write(":DIGitize")
        elif self._is_running():
            scale = float(self._query(":TIMebase:SCALe?"))
            time.sleep(10 * scale + 1)
            self._write(":STOP")

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
            self.payload = bytes([1, 2, 3])
            self.read_sizes: list[int] = []

        def write(self, cmd: str) -> None:
            self.commands.append(cmd)
            self.block = _binary_block(self.payload)

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

        def read_bytes(self, count: int) -> bytes:
            self.read_sizes.append(count)
            data, self.block = self.block[:count], self.block[count:]
            return data

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

    assert d.channels() == ["CHAN1", "CHAN2"]

    arr = d._query_binary(":WAVeform:DATA?", "B")
    assert arr.dtype == np.uint8 and list(arr) == [1, 2, 3]
    assert res.block == b"" and res.read_sizes[-1] == 1
    res.payload = np.arange(2_100_000, dtype="<u2").tobytes()
    arr = d._query_binary(":WAVeform:DATA?", "H")
    assert arr.dtype == np.dtype("<u2") and len(arr) == 2_100_000
    assert arr[-1] == 2_099_999 % 65536
    assert res.read_sizes[-3:] == [4 * 1024 * 1024, 5696, 1] and res.block == b""

    class _TimeoutResource(_StubResource):
        def read_bytes(self, count: int) -> bytes:
            raise pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_timeout)
    try:
        _StubDriver(_TimeoutResource(), "STUB")._query_binary("DATA?", "B")
    except ScopeTimeoutError:
        pass
    else:
        raise AssertionError("binary block 逾時應轉成 ScopeTimeoutError")

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
