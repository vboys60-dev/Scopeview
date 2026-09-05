"""假示波器。沒有真機時用它開發與測試 UI、儲存、分析三條線。

不要為了讓它更像真機而加功能，它只需要產出結構正確的資料。
"""

from __future__ import annotations

import datetime as _dt
import struct
import zlib

import numpy as np

from scope_tool.contracts import (
    CaptureArea,
    CaptureResult,
    Preamble,
    ScopeDriver,
    ScreenshotOptions,
    Series,
    Waveform,
)


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """產一張純色 PNG。不裝 Pillow，手工組最短的合法檔。"""
    row = bytes([0]) + bytes(rgb) * width
    raw = row * height

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


class FakeDriver(ScopeDriver):
    """產生正弦波與純色截圖。介面與真 driver 完全一致。"""

    series = Series.INFINIIVISION
    model_prefixes = ("FAKE",)

    def __init__(self, resource=None, model: str = "FAKE-SCOPE") -> None:
        super().__init__(resource, model)
        self.calls: list[str] = []          # 測試用：記錄呼叫順序

    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        self.calls.append(f"screenshot({opts.image_format.value},{opts.area.value},inv={opts.inverted})")
        w, h = (800, 480) if opts.area is CaptureArea.FULL else (640, 384)
        colour = (255, 255, 255) if opts.inverted else (16, 16, 16)
        return _png(w, h, colour)

    def channels(self) -> list[str]:
        return ["CHAN1", "CHAN2"]

    def max_points(self) -> int:
        return 4_000_000

    def capture(self, channels: list[str], points: int, retrigger: bool) -> CaptureResult:
        self.calls.append(f"capture({channels},{points},retrigger={retrigger})")
        pre = Preamble(
            format=1, type=2, points=points, count=1,
            x_increment=1e-9, x_origin=-points * 5e-10, x_reference=0,
            y_increment=0.01, y_origin=0.0, y_reference=128,
        )
        waves = []
        for i, ch in enumerate(channels):
            t = pre.times(points)
            raw = 128 + 100 * np.sin(2 * np.pi * 1e6 * t + i * np.pi / 2)
            waves.append(Waveform.from_raw(ch, pre, raw))
        return CaptureResult(
            waveforms=waves,
            model=self.model,
            series=self.series,
            captured_at=_dt.datetime.now().isoformat(timespec="seconds"),
            scpi_settings={"POINTS": str(points), "SOURCE": ",".join(channels)},
        )


if __name__ == "__main__":
    d = FakeDriver()
    png = d.screenshot(ScreenshotOptions())
    assert png.startswith(b"\x89PNG"), "截圖不是合法 PNG"
    r = d.capture(["CHAN1", "CHAN2"], 1000, retrigger=False)
    assert len(r.waveforms) == 2
    assert len(r.waveforms[0].voltage) == 1000
    assert abs(r.waveforms[0].voltage.max() - 1.0) < 0.05, r.waveforms[0].voltage.max()
    assert len(d.calls) == 2
    print("fake driver self-check OK")
