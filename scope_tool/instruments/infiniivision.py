"""Keysight InfiniiVision 3000G/3000X 系列驅動。

只支援波形直讀，不支援存檔轉取（檔案只能寫面板USB，PC無法取回）。
"""

from __future__ import annotations

import datetime as _dt

import numpy as np

from scope_tool.contracts import (
    CaptureResult,
    ImageFormat,
    Preamble,
    ScreenshotOptions,
    Series,
    Waveform,
)
from scope_tool.instruments.base import SCPIDriver
from scope_tool.instruments.registry import register


class InfiniiVisionDriver(SCPIDriver):
    """InfiniiVision 3000G/3000X 示波器的 SCPI 驅動。

    實作接口：screenshot、capture、max_points。
    """

    series = Series.INFINIIVISION
    model_prefixes = ("MSO-X 3", "DSO-X 3", "MSOX3", "DSOX3")

    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        """擷取示波器螢幕。timeout 15 秒。

        # 待真機驗證：:HARDcopy:AREA 是否影響 :DISPlay:DATA? 的結果
        """
        with self._timeout(15000):
            # 設定墨粉節省（INKSaver）
            mode = "ON" if opts.inverted else "OFF"
            self._write(f":HARDcopy:INKSaver {mode}")

            # 設定擷取區域（待真機驗證是否生效）
            area = "GRAT" if opts.area.value == "graticule" else "SCReen"
            self._write(f":HARDcopy:AREA {area}")

            # 擷取影像二進位資料
            fmt = opts.image_format.value
            data = self._query_binary(f":DISPlay:DATA? {fmt}", datatype="B")
            return bytes(data)

    def capture(
        self, channels: list[str], points: int, retrigger: bool
    ) -> CaptureResult:
        """擷取波形。timeout 60 秒，RUN/STOP 狀態自動還原。"""
        with self._timeout(60000):
            with self._run_state():
                # 觸發擷取或停止
                if retrigger:
                    self._write(":DIGitize")
                else:
                    self._write(":STOP")

                # 逐通道讀取波形
                waveforms: list[Waveform] = []
                for ch_name in channels:
                    ch_num = ch_name[4]  # "CHAN1" → "1"
                    self._write(f":WAVeform:SOURce CHANnel{ch_num}")
                    self._write(":WAVeform:FORMat WORD")
                    self._write(":WAVeform:UNSigned 1")
                    self._write(":WAVeform:BYTeorder LSBFirst")
                    self._write(":WAVeform:POINts:MODE RAW")
                    self._write(f":WAVeform:POINts {points}")

                    # 讀取前導參數與波形資料
                    pre_str = self._query(":WAVeform:PREamble?")
                    pre = Preamble.parse(pre_str)

                    raw_data = self._query_binary(":WAVeform:DATA?", datatype="H")
                    waveform = Waveform.from_raw(ch_name, pre, raw_data)
                    waveforms.append(waveform)

                self._check_error()

        return CaptureResult(
            waveforms=waveforms,
            model=self.model,
            series=self.series,
            captured_at=_dt.datetime.now().isoformat(timespec="seconds"),
            scpi_settings={
                "FORMAT": "WORD",
                "POINTS": str(points),
                "CHANNELS": ",".join(channels),
                "RETRIGGER": str(retrigger),
            },
        )

    def max_points(self) -> int:
        """查詢最大可取點數。"""
        try:
            resp = self._query(":ACQuire:POINts:MAXimum?")
            return int(float(resp.strip()))
        except Exception:
            # 查詢失敗，回傳保守的上限
            return 4_000_000


# 註冊此驅動
register(InfiniiVisionDriver)


if __name__ == "__main__":
    # 自我檢查：用假的 resource stub 驗證命令順序與行為
    class _StubResource:
        """記錄收到的所有命令。"""

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
            if cmd == ":WAVeform:PREamble?":
                # 回傳合法的 preamble：10 個欄位
                return "1,2,100,1,1e-9,-5e-7,0,0.01,0.0,128"
            if cmd.startswith(":CHANnel"):
                return "1"
            if cmd == ":ACQuire:POINts:MAXimum?":
                return "4000000"
            return "0"

        def query_binary_values(self, cmd, datatype, container):
            self.commands.append(cmd)
            # 回傳 100 個值（與 preamble 裡的 points 相符）
            if datatype == "H":  # WORD = 16-bit
                return [128] * 100
            return [128] * 100

    res = _StubResource()
    driver = InfiniiVisionDriver(res, "TEST-3000G")

    # 驗證 1: screenshot 送出正確的命令
    opts = ScreenshotOptions(inverted=True)
    driver.screenshot(opts)
    assert any(":HARDcopy:INKSaver ON" in cmd for cmd in res.commands), \
        "screenshot(inverted=True) 應該送 INKSaver ON"
    assert any(":DISPlay:DATA?" in cmd for cmd in res.commands), \
        "screenshot 應該送 DISPlay:DATA?"

    # 清空命令記錄用於下一個測試
    res.commands.clear()

    # 驗證 2: capture 送出的命令順序
    result = driver.capture(["CHAN1", "CHAN2"], 100, retrigger=False)

    # 檢查 points mode 在 points 之前
    points_mode_idx = None
    points_idx = None
    for i, cmd in enumerate(res.commands):
        if ":POINts:MODE RAW" in cmd:
            points_mode_idx = i
        if ":POINts 100" in cmd:
            points_idx = i
    assert points_mode_idx is not None and points_idx is not None, \
        "應該有 :POINts:MODE 和 :POINts 命令"
    assert points_mode_idx < points_idx, \
        ":POINts:MODE 應該在 :POINts 之前"

    # 驗證 3: capture 的回傳值
    assert result.series == Series.INFINIIVISION, \
        "CaptureResult.series 應該是 INFINIIVISION"
    assert len(result.waveforms) == 2, \
        "應該有 2 個通道的波形"
    assert len(result.waveforms[0].voltage) == 100, \
        "波形點數應該是 100"

    # 驗證 4: 全程沒有 :DISK: 或 :SAVE: 命令
    for cmd in res.commands:
        assert ":DISK:" not in cmd and ":SAVE:" not in cmd, \
            f"InfiniiVision 不支援存檔轉取，但發現命令: {cmd}"

    # 驗證 5: max_points
    max_pts = driver.max_points()
    assert max_pts == 4_000_000, \
        "max_points 應該回傳 4000000"

    print("infiniivision self-check OK")
