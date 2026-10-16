"""Keysight InfiniiVision 3000G/3000X 系列驅動。

只支援波形直讀，不支援存檔轉取（檔案只能寫面板USB，PC無法取回）。
"""

from __future__ import annotations

import datetime as _dt
import time

import numpy as np

from scope_tool.contracts import (
    CaptureArea,
    CaptureResult,
    ScopeError,
    ScopeTimeoutError,
    ImageFormat,
    Preamble,
    ScreenshotOptions,
    Series,
    Waveform,
)
from scope_tool.instruments.base import SCPIDriver
from scope_tool.instruments.registry import register


# 真機量測（DSO-X 3014G，800×512 截圖）：格線 10×8 格，x 16..657、y 52..451。
# ponytail: 只在 800×512 才裁，其他解析度（3000T 等）回全圖，要支援得重量。
_SCREEN_SIZE = (800, 512)
_GRAT_BOX = (16, 52, 642, 400)  # x, y, w, h


def _crop_graticule(img: bytes, fmt: str) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect
    from PySide6.QtGui import QImage

    qimg = QImage.fromData(img)
    if qimg.isNull() or (qimg.width(), qimg.height()) != _SCREEN_SIZE:
        return img
    ba = QByteArray()  # 必須持有參照，否則 QBuffer 指到已釋放的記憶體 → segfault
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.copy(QRect(*_GRAT_BOX)).save(buf, fmt)
    buf.close()
    return bytes(ba)


def _settle_wait(scale: float, run_started: float | None, now: float) -> float:
    """STOP 前還要等幾秒。RUN 時間未知（使用者手動按的）退回固定 1.5 秒。"""
    if run_started is None:
        return 1.5
    return max(0.0, 10 * scale + 1.0 - (now - run_started))


class InfiniiVisionDriver(SCPIDriver):
    """InfiniiVision 3000G/3000X 示波器的 SCPI 驅動。

    實作接口：screenshot、capture、max_points。
    """

    series = Series.INFINIIVISION
    model_prefixes = ("MSO-X 3", "DSO-X 3", "MSOX3", "DSOX3", "HD3")

    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        """擷取示波器螢幕。timeout 15 秒。

        # :HARDcopy:AREA GRAT 真機不支援，不送；格線區在 driver 內裁切
        """
        with self._timeout(15000):
            # 設定墨粉節省（INKSaver）
            mode = "ON" if opts.inverted else "OFF"
            self._write(f":HARDcopy:INKSaver {mode}")

            # 真機驗證（DSO-X 3014G）：:HARDcopy:AREA GRAT 回 -221 Settings conflict，
            # 一律回整個螢幕，格線區在這裡裁切。

            # 擷取影像二進位資料
            fmt = opts.image_format.value
            data = self._query_binary(f":DISPlay:DATA? {fmt}", datatype="B")
            img = data.astype(np.uint8).tobytes()
            if opts.area is CaptureArea.GRATICULE:
                img = _crop_graticule(img, fmt)
            return img

    def capture(
        self, channels: list[str], points: int, retrigger: bool
    ) -> CaptureResult:
        """擷取波形。timeout 60 秒，RUN/STOP 狀態自動還原。"""
        with self._timeout(60000):
            with self._run_state():
                self._write_nowait("*CLS")  # 不等 *OPC?：Single 等待觸發時會卡住
                # 觸發擷取或停止
                if retrigger:
                    self._write(":DIGitize")
                else:
                    # 真機驗證：從 STOP 重新 RUN 後要等一整筆記錄（10×時基）採完才能 :STOP，
                    # 否則 :WAVeform:PREamble? 卡死（已在執行中的畫面 STOP 則無妨）。
                    # ponytail: 只量過 Auto 觸發；Normal/Single/Roll 未測。
                    if int(self._query(":OPERegister:CONDition?")) & 0x8:
                        scale = float(self._query(":TIMebase:SCALe?"))
                        time.sleep(_settle_wait(scale, self._run_started, time.monotonic()))
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
                    # 真機驗證：沒有完整採集（Single/Normal 等觸發、剛 RUN 就 STOP）時這裡會卡死
                    with self._timeout(5000):
                        try:
                            pre_str = self._query(":WAVeform:PREamble?")
                        except ScopeTimeoutError as exc:
                            self._clear()
                            raise ScopeError(
                                "儀器目前沒有完整的採集可讀（可能在等待觸發 Single/Normal，"
                                "或剛 RUN 就 STOP）。請先觸發一次，或切到 Auto 觸發再試。"
                            ) from exc
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
        # 真機驗證：沒有 :ACQuire:POINts:MAXimum?（-113 且逾時）。DSO-X 3014G 要 4M 點實際
        # 只回 1M（= 目前記憶體深度，隨時基/通道數變動），所以不查、固定 4M，儀器自己截斷。
        return 4_000_000


# 註冊此驅動
register(InfiniiVisionDriver)


if __name__ == "__main__":
    assert _settle_wait(0.5, None, 100) == 1.5
    assert abs(_settle_wait(0.5, 100, 100.2) - 5.8) < 1e-9  # 5s 記錄 + 1s - 已過 0.2s
    assert _settle_wait(0.5, 100, 200) == 0.0
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
            if cmd == ":ACQuire:POINts?":
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
