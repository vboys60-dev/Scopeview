from __future__ import annotations

import datetime
from io import BytesIO
from typing import ClassVar

import h5py
import numpy as np

from scope_tool.contracts import (
    CaptureResult,
    ScopeError,
    ScreenshotOptions,
    Series,
    Waveform,
)
from scope_tool.instruments.base import SCPIDriver, _binary_block
from scope_tool.instruments.registry import register


class InfiniiumDriver(SCPIDriver):
    """Keysight Infiniium (EXR/MXR/S) 系列示波器驅動。

    一律以存檔轉取擷取完整記錄，points 僅作為點數上限。
    存檔轉取、H5INt 換算、截圖與 max_points 已在 MXR254B（韌體 11.51）驗證。
    """

    series: ClassVar[Series] = Series.INFINIIUM
    # MSO9/DSO9 = 9000A 系列，沿用 EXR 命令（待真機驗證）
    model_prefixes: ClassVar[tuple[str, ...]] = ("EXR", "MXR", "DSOS", "MSOS", "MSO9", "DSO9")

    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        """擷取示波器螢幕，直接回傳 PNG/BMP 位元組。

        命令：:DISPlay:DATA? <format>,<screen_mode>,<compression>,<inversion>
        逾時：15 秒；已在 MXR254B 驗證。
        # 待真機驗證：Error 273 的實際觸發條件與訊息
        """
        self._check_error()

        img_fmt = opts.image_format.value
        area = "SCReen" if opts.area.value == "full" else "GRATicule"
        inversion = "INVert" if opts.inverted else "NORMal"

        cmd = f":DISPlay:DATA? {img_fmt},{area},ON,{inversion}"

        with self._timeout(15000):
            data = self._query_binary(cmd, "B")
        return data.astype(np.uint8).tobytes()

    def max_points(self) -> int:
        """查詢硬體最大可取點數。

        :ACQuire:POINts:MAXimum? 已在 MXR254B 驗證。
        """
        try:
            resp = self._query(":ACQuire:POINts:MAXimum?")
            return int(float(resp.strip()))
        except Exception:
            return 4_000_000

    def capture(
        self, channels: list[str], points: int, retrigger: bool
    ) -> CaptureResult:
        """擷取波形。逾時 60 秒。

        一律存檔轉取完整記錄；目前記錄超過 points 上限時拒絕擷取。
        RUN 中先等 10×時基 + 1 秒再 STOP，擷取後維持 STOP（待真機驗證）。
        存檔轉取已在 MXR254B 驗證。
        """
        self._check_error()

        with self._timeout(60000):
            self._prepare_capture(retrigger)
            record_points = int(float(self._query(":WAVeform:POINts?")))
            if record_points > points:
                raise ScopeError(
                    f"目前記錄 {record_points} 點，超過設定的 {points} 點；"
                    "請調高點數或在示波器降低記憶體深度。"
                )
            return self._capture_disk(channels, points, retrigger)

    def _capture_disk(
        self, channels: list[str], points: int, retrigger: bool
    ) -> CaptureResult:
        """存檔轉取完整記錄，已在 MXR254B 驗證。

        三步驟：
        1. :DISK:SAVE:WAVeform ALL → 示波器本機寫檔 + *OPC?
        2. :DISK:GETFILE? → 取回位元組
        3. :DISK:DELete（finally 塊保證執行）
        """
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_path = rf"C:\Users\Public\Documents\Infiniium\st_{ts}.h5"

        file_bytes = None
        try:
            with self._timeout(60000):
                cmd_save = f':DISK:SAVE:WAVeform ALL,"{remote_path}",H5INt,ON'
                self._write(cmd_save)

                cmd_get = f':DISK:GETFILE? "{remote_path}"'
                file_data = self._query_binary(cmd_get, "B")
                file_bytes = np.asarray(file_data).astype(np.uint8).tobytes()
        finally:
            cmd_del = f':DISK:DELete "{remote_path}"'
            try:
                self._write(cmd_del)
            except Exception:
                pass

        waveforms = self._parse_h5_bytes(file_bytes, channels)

        return CaptureResult(
            waveforms=waveforms,
            model=self.model,
            series=self.series,
            captured_at=datetime.datetime.now().isoformat(),
            native_file=file_bytes,
        )

    def _parse_h5_bytes(self, data: bytes, channels: list[str]) -> list[Waveform]:
        """從 HDF5 位元組（記憶體）直接解析波形。

        Infiniium H5 結構：
        /Waveforms/Channel N/Channel NData（資料集）
        該 group 的 attrs：NumPoints, XInc, XOrg, YInc, YOrg, YReference

        H5INt 格式為 int16，需用公式轉成電壓：
        V = RawValue * YInc + YOrg
        MXR254B 實測：即使 YReference = 1 也不讀取或扣除，否則會差 1 LSB。
        """
        try:
            with h5py.File(BytesIO(data), "r") as h5:
                waveforms: list[Waveform] = []
                for ch in channels:
                    ch_num = ch.replace("CHAN", "")
                    ch_group = h5[f"Waveforms/Channel {ch_num}"]

                    raw = np.array(ch_group[f"Channel {ch_num}Data"])
                    x_org = float(ch_group.attrs["XOrg"])
                    x_inc = float(ch_group.attrs["XInc"])
                    y_org = float(ch_group.attrs["YOrg"])
                    y_inc = float(ch_group.attrs["YInc"])

                    time_axis = x_org + np.arange(len(raw), dtype=np.float64) * x_inc

                    if np.issubdtype(raw.dtype, np.floating):
                        voltage_axis = raw.astype(np.float64)
                    else:
                        voltage_axis = (
                            raw.astype(np.float64) * y_inc + y_org
                        )

                    wf = Waveform(channel=ch, time=time_axis, voltage=voltage_axis)
                    waveforms.append(wf)

                return waveforms
        except Exception as exc:
            raise ScopeError(f"解析 HDF5 檔案失敗：{exc}") from exc


# 註冊此驅動
register(InfiniiumDriver)


if __name__ == "__main__":
    # 原生 H5INt：YReference = 1 仍應直接乘比例再加偏移。
    raw = np.array([-2, 0, 2], dtype=np.int16)
    h5_buffer = BytesIO()
    with h5py.File(h5_buffer, "w") as hf:
        hf.create_dataset("FileType", data=b"Keysight Waveform")
        hf.create_group("Frame")
        group = hf.create_group("Waveforms/Channel 1")
        group.create_dataset("Channel 1Data", data=raw)
        group.attrs.update({"XOrg": 0.0, "XInc": 1e-9, "YOrg": 1.0,
                            "YInc": 0.1, "YReference": 1})
    native_bytes = h5_buffer.getvalue()

    class _StubResource:
        """測試用假 resource，記錄所有命令。"""

        def __init__(self) -> None:
            self.timeout = 5000
            self.commands: list[str] = []

        def write(self, cmd: str) -> None:
            self.commands.append(cmd)
            self.block = _binary_block(native_bytes)

        def query(self, cmd: str) -> str:
            self.commands.append(cmd)
            if cmd == "*OPC?":
                return "1"
            if cmd == ":SYSTem:ERRor?":
                return "+0,\"No error\""
            if cmd == ":OPERegister:CONDition?":
                return "0"
            if cmd.startswith(":CHANnel"):
                return "1" if cmd in (":CHANnel1:DISPlay?", ":CHANnel2:DISPlay?") else "0"
            if cmd == ":TIMebase:SCALe?":
                return "0.5"
            if cmd == ":WAVeform:POINts?":
                return "3"
            return "0"

        def read_bytes(self, count: int) -> bytes:
            data, self.block = self.block[:count], self.block[count:]
            return data

    # 驗收 1：超過上限時拒絕擷取，不能先存檔。
    res = _StubResource()
    d = InfiniiumDriver(res, "TEST-MXR")
    try:
        d.capture(["CHAN1"], 2, False)
    except ScopeError as exc:
        assert "3 點" in str(exc) and "2 點" in str(exc)
        assert "請調高點數或在示波器降低記憶體深度" in str(exc)
    else:
        raise AssertionError("超過上限應拋 ScopeError")
    assert not any(":DISK:SAVE" in c for c in res.commands)
    assert res.timeout == 5000

    # 驗收 2：低點數也走存檔轉取，並正確解析原生整數波形。
    result = d.capture(["CHAN1"], 3, False)
    assert result.native_file == native_bytes
    assert np.array_equal(result.waveforms[0].voltage, raw * 0.1 + 1.0)
    assert not any(c in res.commands for c in (":STOP", ":RUN", ":TIMebase:SCALe?"))
    disk_cmds = [c for c in res.commands if ":DISK:" in c]
    assert len(disk_cmds) == 3
    assert ":DISK:SAVE" in disk_cmds[0] and ":DISK:GETFILE?" in disk_cmds[1]
    assert ":DISK:DELete" in disk_cmds[2]
    save_idx = res.commands.index(disk_cmds[0])
    assert res.commands[save_idx + 1] == "*OPC?"

    # 驗收 3：RUN 中等待後 STOP，再存檔，且不送 RUN。
    from unittest.mock import patch
    class _RunningResource(_StubResource):
        def query(self, cmd: str) -> str:
            if cmd == ":OPERegister:CONDition?":
                self.commands.append(cmd)
                return "8"
            return super().query(cmd)
    running = _RunningResource()
    with patch("scope_tool.instruments.base.time.sleep") as sleep:
        InfiniiumDriver(running, "TEST").capture(["CHAN1"], 1000, False)
    sleep.assert_called_once_with(6.0)
    assert running.commands.index(":TIMebase:SCALe?") < running.commands.index(":STOP")
    assert ":RUN" not in running.commands
    assert running.commands.index(":STOP") < running.commands.index(":WAVeform:POINts?")
    assert any(":DISK:SAVE" in c for c in running.commands)

    # 驗收 4：GETFILE 失敗時 DELETE 仍執行，順序正確。
    class _FailingStubResource(_StubResource):
        def write(self, cmd: str) -> None:
            super().write(cmd)
            if ":DISK:GETFILE?" in cmd:
                raise RuntimeError("模擬 GETFILE 失敗")

    res2 = _FailingStubResource()
    d2 = InfiniiumDriver(res2, "TEST-EXR")

    try:
        d2.capture(["CHAN1"], 200_000, False)
    except ScopeError as exc:
        assert "模擬 GETFILE 失敗" in str(exc)
    else:
        raise AssertionError("GETFILE 失敗應拋 ScopeError")

    save_idx = next((i for i, c in enumerate(res2.commands) if ":DISK:SAVE" in c), -1)
    get_idx = next((i for i, c in enumerate(res2.commands) if ":DISK:GETFILE?" in c), -1)
    del_idx = next((i for i, c in enumerate(res2.commands) if ":DISK:DELete" in c), -1)

    assert save_idx >= 0, "未找到 SAVE 命令"
    assert get_idx >= 0, "未找到 GETFILE 命令"
    assert del_idx >= 0, "未找到 DELETE 命令（finally 應保證執行）"
    assert save_idx < get_idx < del_idx, (
        f"命令順序錯誤：SAVE={save_idx}, GET={get_idx}, DEL={del_idx}"
    )

    # 驗收 5：Error 273 轉成 RemoteDesktopError
    from scope_tool.contracts import RemoteDesktopError

    class _Error273Resource(_StubResource):
        def query(self, cmd: str) -> str:
            self.commands.append(cmd)
            if cmd == ":SYSTem:ERRor?":
                return "273,\"Remote desktop connection\""
            return super().query(cmd)

    res3 = _Error273Resource()
    d3 = InfiniiumDriver(res3, "TEST-EXR")

    try:
        d3.screenshot(ScreenshotOptions())
        assert False, "應該拋 RemoteDesktopError"
    except RemoteDesktopError:
        pass
    # 驗收 6：路徑字串含單個反斜線，未被跳脫。
    assert "\\" in disk_cmds[0], f"路徑字串應含單個反斜線：{disk_cmds[0]}"

    print("\ninfiniium self-check OK")
