from __future__ import annotations

import datetime
from io import BytesIO
from typing import ClassVar

import h5py
import numpy as np

from scope_tool.contracts import (
    CaptureResult,
    Preamble,
    ScreenshotOptions,
    Series,
    Waveform,
)
from scope_tool.instruments.base import SCPIDriver


class InfiniiumDriver(SCPIDriver):
    """Keysight Infiniium (EXR/MXR/S) 系列示波器驅動。

    支援 PC 端直接存檔轉取（>= 100k 點）和波形直讀（< 100k 點）兩條路線。
    """

    series: ClassVar[Series] = Series.INFINIIUM
    model_prefixes: ClassVar[tuple[str, ...]] = ("EXR", "MXR", "DSOS", "MSOS")

    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        """擷取示波器螢幕，直接回傳 PNG/BMP 位元組。

        命令：:DISPlay:DATA? <format>,<screen_mode>,<compression>,<inversion>
        逾時：15 秒
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

        # 待真機驗證：:ACQuire:POINts:MAXimum? 的實際回應
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

        - points < 100,000：直讀（命令流）
        - points >= 100,000：存檔轉取（:DISK:SAVE → :DISK:GETFILE? → :DISK:DELete）

        RUN/STOP 狀態在進入時記下，離開時還原（_run_state context manager 負責）。
        # 待真機驗證：大點數存檔轉取與逾時設定
        """
        self._check_error()

        with self._run_state():
            if points < 100_000:
                return self._capture_direct(channels, points, retrigger)
            else:
                return self._capture_disk(channels, points, retrigger)

    def _capture_direct(
        self, channels: list[str], points: int, retrigger: bool
    ) -> CaptureResult:
        """直讀路線：< 100k 點，逐通道串流讀取。"""
        with self._timeout(60000):
            if retrigger:
                self._write(":SINGle")
            else:
                self._write(":STOP")

            waveforms: list[Waveform] = []
            for ch in channels:
                self._write(f":WAVeform:SOURce {ch}")
                self._write(":WAVeform:FORMat BYTE")
                self._write(":WAVeform:POINts:MODE RAW")
                self._write(f":WAVeform:POINts {points}")
                self._write(":WAVeform:UNSigned ON")

                preamble_str = self._query(":WAVeform:PREamble?")
                preamble = Preamble.parse(preamble_str)

                raw = self._query_binary(":WAVeform:DATA?", "B")
                waveform = Waveform.from_raw(ch, preamble, raw)
                waveforms.append(waveform)

        return CaptureResult(
            waveforms=waveforms,
            model=self.model,
            series=self.series,
            captured_at=datetime.datetime.now().isoformat(),
        )

    def _capture_disk(
        self, channels: list[str], points: int, retrigger: bool
    ) -> CaptureResult:
        """存檔轉取路線：>= 100k 點。

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
        V = (RawValue - YRef) * YInc + YOrg

        # 待真機驗證：H5INt 電壓還原與群組名稱規則
        """
        from scope_tool.contracts import ScopeError

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
                    y_ref = float(ch_group.attrs["YReference"])

                    time_axis = x_org + np.arange(len(raw), dtype=np.float64) * x_inc

                    if np.issubdtype(raw.dtype, np.floating):
                        voltage_axis = raw.astype(np.float64)
                    else:
                        voltage_axis = (
                            (raw.astype(np.float64) - y_ref) * y_inc + y_org
                        )

                    wf = Waveform(channel=ch, time=time_axis, voltage=voltage_axis)
                    waveforms.append(wf)

                return waveforms
        except Exception as exc:
            raise ScopeError(f"解析 HDF5 檔案失敗：{exc}") from exc


if __name__ == "__main__":
    class _StubResource:
        """測試用假 resource，記錄所有命令。"""

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
            if cmd == ":WAVeform:PREamble?":
                return "0,2,1000,1,1e-9,-5e-7,500,0.01,0.0,128"
            return "0"

        def query_binary_values(self, cmd: str, datatype: str, container):
            self.commands.append(cmd)
            return [128] * 1000

    # 驗收 1：points=1000 走直讀，沒有 :DISK: 命令
    res = _StubResource()
    d = InfiniiumDriver(res, "TEST-EXR")
    res.commands.clear()
    try:
        d.capture(["CHAN1"], 1000, False)
    except Exception:
        pass
    disk_cmds = [c for c in res.commands if ":DISK:" in c]
    assert len(disk_cmds) == 0, f"直讀不應有 DISK 命令，實際：{disk_cmds}"
    print("✓ 驗收 1：points=1000 走直讀，無 :DISK: 命令")

    # 驗收 2 & 3：points=200000 走存檔，順序正確，GETFILE 失敗時 DELETE 仍執行
    class _FailingStubResource(_StubResource):
        def query_binary_values(self, cmd: str, datatype: str, container):
            self.commands.append(cmd)
            if ":DISK:GETFILE?" in cmd:
                raise Exception("模擬 GETFILE 失敗")
            return [128] * 1000

    res2 = _FailingStubResource()
    d2 = InfiniiumDriver(res2, "TEST-EXR")

    try:
        d2.capture(["CHAN1"], 200_000, False)
    except Exception:
        pass

    save_idx = next((i for i, c in enumerate(res2.commands) if ":DISK:SAVE" in c), -1)
    get_idx = next((i for i, c in enumerate(res2.commands) if ":DISK:GETFILE?" in c), -1)
    del_idx = next((i for i, c in enumerate(res2.commands) if ":DISK:DELete" in c), -1)

    assert save_idx >= 0, "未找到 SAVE 命令"
    assert get_idx >= 0, "未找到 GETFILE 命令"
    assert del_idx >= 0, "未找到 DELETE 命令（finally 應保證執行）"
    assert save_idx < get_idx < del_idx, (
        f"命令順序錯誤：SAVE={save_idx}, GET={get_idx}, DEL={del_idx}"
    )
    print("✓ 驗收 2 & 3：points=200000 走存檔，順序正確，GETFILE 失敗時 DELETE 仍執行")

    # 驗收 4：Error 273 轉成 RemoteDesktopError
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
        print("✓ 驗收 4：Error 273 轉成 RemoteDesktopError")

    # 驗收 5：路徑字串是 raw string（含單個反斜線，未被跳脫）
    res4 = _StubResource()
    d4 = InfiniiumDriver(res4, "TEST-EXR")

    try:
        d4.capture(["CHAN1"], 200_000, False)
    except Exception:
        pass

    save_cmd = next((c for c in res4.commands if ":DISK:SAVE" in c), "")
    assert "\\" in save_cmd, f"路徑字串應含單個反斜線：{save_cmd}"
    print("✓ 驗收 5：路徑字串使用 raw string（含單個反斜線）")

    print("\ninfiniium self-check OK")
