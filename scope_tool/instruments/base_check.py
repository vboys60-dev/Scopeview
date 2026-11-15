"""SCPI 共用邏輯自檢。"""
from scope_tool.instruments.base import SCPIDriver, _binary_block
from scope_tool.contracts import ScopeError, ScopeTimeoutError, RemoteDesktopError
import numpy as np
import pyvisa
from unittest.mock import patch

def _self_check():
    class _StubResource:
        """假的 pyvisa resource，只記錄收到的命令並回固定值。"""

        def __init__(self) -> None:
            self.timeout = 5000
            self.commands: list[str] = []
            self.payload = bytes([1, 2, 3])
            self.read_sizes: list[int] = []
            self.cleared = False
            self.scale = "0.5"

        def clear(self) -> None:
            self.cleared = True

        def write(self, cmd: str) -> None:
            self.commands.append(cmd)
            self.block = _binary_block(self.payload)

        def query(self, cmd: str) -> str:
            self.commands.append(cmd)
            if cmd == ":TIMebase:SCALe?":
                return self.scale
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

    class _TriggerTimeoutResource(_StubResource):
        def query(self, cmd: str) -> str:
            if cmd == "*OPC?" and self.commands[-1:] == [":DIGitize"]:
                self.commands.append(cmd)
                raise pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_timeout)
            return super().query(cmd)

    trigger_res = _TriggerTimeoutResource()
    trigger_res.scale = "1e-3"
    try:
        _StubDriver(trigger_res, "STUB")._prepare_capture(True)
    except ScopeError as exc:
        assert not isinstance(exc, ScopeTimeoutError)
        assert "等不到觸發" in str(exc)
        assert isinstance(exc.__cause__, ScopeTimeoutError)
        assert trigger_res.cleared
        assert trigger_res.commands == [":TIMebase:SCALe?", ":DIGitize", "*OPC?"]
    else:
        raise AssertionError("等不到觸發應清除通訊並轉成 ScopeError")

    class _PartialTimeout(_StubResource):
        def read_bytes(self, count):
            if count == 3:
                raise pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_timeout)
            return super().read_bytes(count)
    for fail_clear in (False, True):
        r = _PartialTimeout()
        if fail_clear:
            def bad_clear(): raise RuntimeError("clear")
            r.clear = bad_clear
        try: _StubDriver(r, "STUB")._query_binary("DATA?", "B")
        except ScopeTimeoutError as exc:
            assert ("重新連線" in str(exc)) == fail_clear
            if not fail_clear: assert r.cleared
        else: raise AssertionError("應逾時")
    r = _StubResource()
    def bad_write(cmd): raise RuntimeError("write")
    r.write = bad_write
    try: _StubDriver(r, "STUB")._query_binary("DATA?", "B")
    except ScopeError: assert not r.cleared
    else: raise AssertionError("寫入應失敗")
    for scale, retrigger in (("50", False), ("50", True), ("abc", False)):
        r = _StubResource(); r.scale = scale
        with patch("scope_tool.instruments.base.time.sleep") as sleep:
            try: _StubDriver(r, "STUB")._prepare_capture(retrigger)
            except ScopeError as exc:
                if scale == "50": assert "STOP" in str(exc)
            else: raise AssertionError("時基應被拒絕")
            sleep.assert_not_called()
            assert ":STOP" not in r.commands and ":DIGitize" not in r.commands
    for scale, wait in (("1e-3", 1.01), ("0.5", 6.0)):
        r = _StubResource(); r.scale = scale
        with patch("scope_tool.instruments.base.time.sleep") as sleep:
            _StubDriver(r, "STUB")._prepare_capture(False)
            sleep.assert_called_once_with(wait)
            assert ":STOP" in r.commands

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
