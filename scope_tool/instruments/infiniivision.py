"""Keysight InfiniiVision 3000G/3000X/4000X 與 HD3 系列驅動。

只支援波形直讀，不支援存檔轉取（檔案只能寫面板USB，PC無法取回）。
"""

from __future__ import annotations
import datetime as _dt
import numpy as np
from PySide6.QtGui import QImage

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
from scope_tool.instruments.base import SCPIDriver, _binary_block, _waveform_from_raw
from scope_tool.instruments.registry import register


# 真機量測（DSO-X 3014G，800×512 截圖）：格線 10×8 格，x 16..657、y 52..451。
# 真機量測（MSO-X 4154G，800×632 截圖）：x 16..657、y 92..571。
# ponytail: 僅裁實測的 3014G（800×512）與 4154G（800×632）；其他尺寸回全圖，支援前須重測。
_GRAT_BOX = {(800, 512): (16, 52, 642, 400), (800, 632): (16, 92, 642, 480)}  # x, y, w, h
_NO_ACQUISITION = (
    "儀器目前沒有完整的採集可讀（可能在等待觸發 Single/Normal，"
    "或剛 RUN 就 STOP）。請先觸發一次，或切到 Auto 觸發再試。"
)


def _crop_graticule(img: bytes, fmt: str) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect
    from PySide6.QtGui import QImage

    qimg = QImage.fromData(img)
    box = _GRAT_BOX.get((qimg.width(), qimg.height()))
    if qimg.isNull() or box is None:
        return img
    ba = QByteArray()  # 必須持有參照，否則 QBuffer 指到已釋放的記憶體 → segfault
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.copy(QRect(*box)).save(buf, fmt)
    buf.close()
    return bytes(ba)


def _hd3_graticule_box(qimg: QImage) -> tuple[int, int, int, int]:
    """依 #282828 外框偵測格線區；找不到可靠的上下邊就回全圖。"""
    full = (0, 0, qimg.width(), qimg.height())
    if qimg.isNull():
        return full
    rgb = qimg.convertToFormat(QImage.Format.Format_RGB888)
    pixels = np.frombuffer(rgb.constBits(), dtype=np.uint8).reshape(rgb.height(), rgb.bytesPerLine())
    pixels = pixels[:, :rgb.width() * 3].reshape(rgb.height(), rgb.width(), 3)
    border = np.all(pixels == 40, axis=2)
    rows = np.flatnonzero(border.sum(axis=1) >= rgb.width() / 2)
    if len(rows) < 2 or rows[-1] - rows[0] < 10:
        return full
    top, bottom = int(rows[0]), int(rows[-1])
    xs = np.flatnonzero(border[top])
    return (int(xs[0]), top, int(xs[-1] - xs[0] + 1), bottom - top + 1)


def _transform_hd3(img: bytes, fmt: str, opts: ScreenshotOptions) -> bytes:
    """先依原色裁切，再反相，共用一次影像編碼。"""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    qimg = QImage.fromData(img)
    if qimg.isNull() or (opts.area is CaptureArea.FULL and not opts.inverted):
        return img
    if opts.area is CaptureArea.GRATICULE:
        qimg = qimg.copy(*_hd3_graticule_box(qimg))
    if opts.inverted:
        qimg.invertPixels()
    ba = QByteArray()  # 必須持有參照，否則 QBuffer 指到已釋放的記憶體 → segfault
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.save(buf, fmt)
    buf.close()
    return bytes(ba)


class InfiniiVisionDriver(SCPIDriver):
    """InfiniiVision 3000G/3000X/4000X 示波器的 SCPI 驅動。

    實作接口：screenshot、capture、max_points。
    """

    series = Series.INFINIIVISION
    model_prefixes = ("MSO-X 3", "DSO-X 3", "MSOX3", "DSOX3", "MSO-X 4", "DSO-X 4", "MSOX4", "DSOX4")

    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        """擷取示波器螢幕。timeout 15 秒。

        # :HARDcopy:AREA GRAT 真機不支援，不送；格線區在 driver 內裁切
        """
        with self._timeout(15000):
            # 設定墨粉節省（INKSaver）
            mode = "ON" if opts.inverted else "OFF"
            self._write(f":HARDcopy:INKSaver {mode}")
            # 4154G 實測：清除上次截圖後約 5 秒的遠端操作完成提示，避免連續截圖拍到提示框。
            self._write(":DISPlay:MESSage:CLEar")
            # 真機驗證（DSO-X 3014G）：:HARDcopy:AREA GRAT 回 -221 Settings conflict，
            # 一律回整個螢幕，格線區在這裡裁切。
            # 4154G 實測調色盤參數會保留，每次截圖明確指定彩色，避免沿用灰階。
            fmt = opts.image_format.value
            data = self._query_binary(f":DISPlay:DATA? {fmt},COLor", datatype="B")
            img = data.astype(np.uint8).tobytes()
            if opts.area is CaptureArea.GRATICULE:
                img = _crop_graticule(img, fmt)
            return img

    def capture(
        self, channels: list[str], points: int, retrigger: bool
    ) -> CaptureResult:
        """擷取波形。timeout 60 秒，RUN 中先等完整記錄，擷取後維持 STOP。"""
        with self._timeout(60000):
            self._write_nowait("*CLS")  # 不等 *OPC?：Single 等待觸發時會卡住
            self._prepare_capture(retrigger)

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
                # 真機驗證：沒有完整採集時，3000G 可能逾時，HD3 回十個空欄位
                with self._timeout(5000):
                    try:
                        pre_str = self._query(":WAVeform:PREamble?")
                    except ScopeTimeoutError as exc:
                        self._clear()
                        raise ScopeError(_NO_ACQUISITION) from exc
                if not "".join(pre_str.replace(",", "").split()):
                    raise ScopeError(_NO_ACQUISITION)
                pre = Preamble.parse(pre_str)

                raw_data = self._query_binary(":WAVeform:DATA?", datatype="H")
                waveform = _waveform_from_raw(ch_name, pre, raw_data, waveforms[-1] if waveforms else None)
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


class HD3Driver(InfiniiVisionDriver):
    """HD3 使用 RSTate 查狀態，截圖裁切與反相由本機處理。

    # 待真機驗證：整合後的擷取流程；命令依 HD304MSO USB 實測結果。
    """

    model_prefixes = ("HD3",)

    def max_points(self) -> int:
        """HD3 記憶體 100M 點；儀器會取成 100M 的整數分之一。"""
        return 100_000_000

    def _is_running(self) -> bool:
        return self._query(":RSTate?") != "STOP"

    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        """擷取全圖後裁切、反相；HD3 不支援 INKSaver。"""
        with self._timeout(15000):
            fmt = opts.image_format.value
            data = self._query_binary(f":DISPlay:DATA? {fmt}", datatype="B")
            return _transform_hd3(data.astype(np.uint8).tobytes(), fmt, opts)


# 註冊此驅動
register(InfiniiVisionDriver)
register(HD3Driver)

if __name__ == "__main__":
    from PySide6.QtCore import QBuffer, QIODevice, QSize
    from PySide6.QtGui import QColor, QPainter, QPen
    from scope_tool.instruments.registry import driver_for
    class _StubResource:
        """記錄收到的所有命令，OPERegister 照舊回 8。"""
        def __init__(self) -> None:
            self.timeout = 5000
            self.commands: list[str] = []
        def write(self, cmd: str) -> None:
            self.commands.append(cmd)
            self.block = _binary_block(np.full(100, 128, dtype="<u2").tobytes() if cmd == ":WAVeform:DATA?" else b"PNG")
        def query(self, cmd: str) -> str:
            self.commands.append(cmd)
            return {
                "*OPC?": "1", ":SYSTem:ERRor?": '+0,"No error"',
                ":OPERegister:CONDition?": "8", ":RSTate?": "STOP",
                ":WAVeform:PREamble?": "1,2,100,1,1e-9,-5e-7,0,0.01,0.0,128",
                ":ACQuire:POINts?": "4000000", ":TIMebase:SCALe?": "0.5",
            }.get(cmd, "1" if cmd.startswith(":CHANnel") else "0")
        def read_bytes(self, count: int) -> bytes:
            data, self.block = self.block[:count], self.block[count:]
            return data
    res = _StubResource()
    driver = InfiniiVisionDriver(res, "TEST-3000G")
    driver.screenshot(ScreenshotOptions(inverted=True))
    assert ":HARDcopy:INKSaver ON" in res.commands
    assert any(":DISPlay:DATA?" in cmd for cmd in res.commands)
    assert res.commands.index(":DISPlay:MESSage:CLEar") < res.commands.index(":DISPlay:DATA? PNG,COLor")
    res.commands.clear()
    from unittest.mock import patch
    with patch("scope_tool.instruments.base.time.sleep") as sleep:
        result = driver.capture(["CHAN1", "CHAN2"], 100, retrigger=False)
    sleep.assert_called_once_with(6.0)
    assert res.commands.index(":TIMebase:SCALe?") < res.commands.index(":STOP")
    assert ":RUN" not in res.commands
    assert result.waveforms[0].time is result.waveforms[1].time
    stopped = _StubResource()
    hd3 = HD3Driver(stopped, "HD304MSO")
    hd3.screenshot(ScreenshotOptions())
    assert all("," not in cmd for cmd in stopped.commands if cmd.startswith(":DISPlay:DATA?"))
    assert hd3.max_points() == 100_000_000
    hd3.capture(["CHAN1"], 100, False)
    assert not any(c in stopped.commands for c in (":STOP", ":RUN", ":TIMebase:SCALe?", ":DIGitize"))
    stopped.commands.clear()
    hd3.capture(["CHAN1"], 100, True)
    assert ":DIGitize" in stopped.commands and ":RUN" not in stopped.commands
    class _RunningHD3(_StubResource):
        def query(self, cmd: str) -> str:
            return "RUN" if cmd == ":RSTate?" else super().query(cmd)
    running = _RunningHD3()
    with patch("scope_tool.instruments.base.time.sleep") as sleep:
        HD3Driver(running, "HD304MSO").capture(["CHAN1"], 100, False)
    sleep.assert_called_once_with(6.0)
    assert running.commands.index(":TIMebase:SCALe?") < running.commands.index(":STOP")
    assert ":RUN" not in running.commands
    # 每個通道的 points mode 都要在 points 之前
    for i, cmd in enumerate(res.commands):
        if ":POINts 100" in cmd:
            assert res.commands[i - 2] == ":WAVeform:POINts:MODE RAW"
    assert ":WAVeform:POINts:MODE RAW" in res.commands and ":WAVeform:POINts 100" in res.commands
    assert result.series == Series.INFINIIVISION
    assert len(result.waveforms) == 2 and len(result.waveforms[0].voltage) == 100
    assert all(":DISK:" not in cmd and ":SAVE:" not in cmd for cmd in res.commands)
    assert driver.max_points() == 4_000_000
    # 兩款實測尺寸依表裁切，未知尺寸保留全圖；PNG/BMP 都適用。
    for height, expected in ((512, (642, 400)), (632, (642, 480)), (600, (800, 600))):
        image = QImage(800, height, QImage.Format.Format_RGB32)
        image.fill(0)
        for fmt in ImageFormat:
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.ReadWrite)
            assert image.save(buf, fmt.value)
            assert QImage.fromData(_crop_graticule(bytes(buf.data()), fmt.value)).size() == QSize(*expected)
    # HD3 外框含端點；沒有外框時保留全圖
    image = QImage(1280, 800, QImage.Format.Format_RGB32)
    image.fill(0)
    assert _hd3_graticule_box(image) == (0, 0, 1280, 800)
    painter = QPainter(image)
    painter.setPen(QPen(QColor(40, 40, 40)))
    painter.drawRect(52, 60, 1147, 471)
    painter.end()
    assert _hd3_graticule_box(image) == (52, 60, 1148, 472)
    assert isinstance(driver_for(None, "KEYSIGHT TECHNOLOGIES,HD304MSO,MY1,1"), HD3Driver)
    assert type(driver_for(None, "KEYSIGHT TECHNOLOGIES,DSO-X 3014G,MY1,1")) is InfiniiVisionDriver
    assert type(driver_for(None, "KEYSIGHT TECHNOLOGIES,MSO-X 4154G,MY65060120,07.65.2024120521")) is InfiniiVisionDriver
    class _EmptyPreamble(_StubResource):
        def query(self, cmd: str) -> str:
            return " , , , , , , , , , " if cmd == ":WAVeform:PREamble?" else super().query(cmd)
    for cls in (InfiniiVisionDriver, HD3Driver):
        res = _EmptyPreamble()
        try:
            cls(res, "STUB").capture(["CHAN1"], 100, retrigger=True)
        except ScopeError as exc:
            assert str(exc) == _NO_ACQUISITION
            assert ":WAVeform:DATA?" not in res.commands
        else:
            raise AssertionError("空 PREamble 應該拋出沒有完整採集的 ScopeError")
    print("infiniivision self-check OK")
