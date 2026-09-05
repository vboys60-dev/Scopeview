"""跨模組契約：資料結構、驅動抽象、錯誤型別、檔案格式規格。

這個檔案是所有模組唯一的共同依賴。**任何任務都不得修改它**，
要改必須先回報並更新 PLAN.md。

檔案格式規格（writer 與 reader 必須一致）
------------------------------------------------
CSV：UTF-8，第一列為欄位名，之後每列一筆取樣。
    Time(s),CH1(V),CH2(V)
    -1.000000e-05,0.012,1.980
    同一次擷取的所有通道共用時間軸。除此之外不寫任何註解列或 metadata。

HDF5：沿用 Keysight 原生結構（見 docs/adr/0003）
    /Waveforms/Channel 1/Channel 1Data   ← 電壓值 float64 一維陣列
        該 group 的 attrs：NumPoints, XInc, XOrg, YInc, YOrg, YReference
    /ScopeTool                            ← 本工具自訂 group（原生檔沒有，讀取時要容忍缺席）
        attrs：Model, Series, CapturedAt, SCPI
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

import numpy as np


# --------------------------------------------------------------------------
# 列舉
# --------------------------------------------------------------------------

class Series(str, Enum):
    """機型分家。決定 SCPI 命令寫法。"""
    INFINIIVISION = "InfiniiVision"   # 3000G / 3000X，非 PC base
    INFINIIUM = "Infiniium"           # EXR / MXR / S，PC base


class ImageFormat(str, Enum):
    PNG = "PNG"
    BMP = "BMP"


class CaptureArea(str, Enum):
    FULL = "full"            # 全螢幕，含選單與量測欄
    GRATICULE = "graticule"  # 只有 10x8 格線波形區


class WaveformFormat(str, Enum):
    CSV = "CSV"
    HDF5 = "HDF5"


# --------------------------------------------------------------------------
# 錯誤
# --------------------------------------------------------------------------

class ScopeError(Exception):
    """本工具所有可預期錯誤的基底。UI 只需要 catch 這一個。"""


class RemoteDesktopError(ScopeError):
    """Infiniium 的 SCPI Error 273：遠端桌面連線中，畫面無法擷取。

    UI 必須顯示「請關閉遠端桌面連線後重試」。
    """


class ScopeTimeoutError(ScopeError):
    """VISA 逾時。driver 必須在拋出前清掉儀器上的暫存檔。"""


class UnsupportedError(ScopeError):
    """這台機器不支援這個操作（例如 InfiniiVision 要求存檔轉取）。"""


# --------------------------------------------------------------------------
# 波形資料
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Preamble:
    """儀器回傳的十個換算參數。缺了它原始碼值沒有物理意義。

    對應 `:WAVeform:PREamble?` 回傳的逗號分隔十個欄位，順序固定。
    """
    format: int
    type: int
    points: int
    count: int
    x_increment: float
    x_origin: float
    x_reference: int
    y_increment: float
    y_origin: float
    y_reference: int

    @classmethod
    def parse(cls, text: str) -> "Preamble":
        """把 `:WAVeform:PREamble?` 的回應字串轉成物件。"""
        parts = [p.strip() for p in text.strip().split(",")]
        if len(parts) != 10:
            raise ScopeError(f"PREamble 欄位數不對，預期 10 個，拿到 {len(parts)} 個：{text!r}")
        return cls(
            format=int(float(parts[0])),
            type=int(float(parts[1])),
            points=int(float(parts[2])),
            count=int(float(parts[3])),
            x_increment=float(parts[4]),
            x_origin=float(parts[5]),
            x_reference=int(float(parts[6])),
            y_increment=float(parts[7]),
            y_origin=float(parts[8]),
            y_reference=int(float(parts[9])),
        )

    def times(self, n: int) -> np.ndarray:
        """產生 n 個取樣點的時間軸（秒）。"""
        idx = np.arange(n, dtype=np.float64)
        return (idx - self.x_reference) * self.x_increment + self.x_origin

    def volts(self, raw: np.ndarray) -> np.ndarray:
        """把原始碼值換算成電壓（伏特）。"""
        return (raw.astype(np.float64) - self.y_reference) * self.y_increment + self.y_origin


@dataclass
class Waveform:
    """單一通道的波形。時間與電壓都已換算完成。

    `preamble` 只有走直讀時才有；從 CSV 讀回來時是 None。
    任何程式碼都不得假設 preamble 一定存在。
    """
    channel: str                      # 例如 "CHAN1"
    time: np.ndarray                  # float64，秒
    voltage: np.ndarray               # float64，伏特
    preamble: Preamble | None = None

    @classmethod
    def from_raw(cls, channel: str, preamble: Preamble, raw: np.ndarray) -> "Waveform":
        return cls(
            channel=channel,
            time=preamble.times(len(raw)),
            voltage=preamble.volts(raw),
            preamble=preamble,
        )

    def __post_init__(self) -> None:
        if len(self.time) != len(self.voltage):
            raise ScopeError(f"{self.channel} 時間與電壓長度不符：{len(self.time)} vs {len(self.voltage)}")


@dataclass
class CaptureResult:
    """一次波形擷取的完整結果。"""
    waveforms: list[Waveform]
    model: str                                    # *IDN? 拆出來的型號
    series: Series
    captured_at: str                              # ISO8601，例如 "2026-09-05T14:30:12"
    scpi_settings: dict[str, str] = field(default_factory=dict)
    native_file: bytes | None = None              # 存檔轉取拿回的 Keysight 原生 .h5 原始位元組


# --------------------------------------------------------------------------
# 儀器搜尋
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FoundInstrument:
    """搜尋結果的一筆。連線前不知道型號，label 只是給人看的。"""
    resource: str          # VISA 資源字串，例如 "TCPIP0::192.168.1.5::hislip0::INSTR"
    source: str            # "visa" | "mdns" | "manual"
    label: str             # 顯示用文字


# --------------------------------------------------------------------------
# 驅動抽象
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ScreenshotOptions:
    image_format: ImageFormat = ImageFormat.PNG
    inverted: bool = False
    area: CaptureArea = CaptureArea.FULL


class ScopeDriver(ABC):
    """所有示波器驅動的介面。UI 只認這個，不認任何具體機型。

    新增機型 = 新增一個子類別 + 在 registry 註冊，UI 一行都不用改。
    實作者責任：
      - 所有 VISA 例外都要轉成 ScopeError 的子類別再往外丟。
      - 寫入型命令後要 `*OPC?` 等它做完。
      - 逾時或失敗時要清掉自己在儀器上留下的暫存檔。
    """

    series: ClassVar[Series]
    #: 型號比對用的前綴。registry 用 *IDN? 的型號欄位做前綴比對。
    model_prefixes: ClassVar[tuple[str, ...]] = ()

    def __init__(self, resource, model: str) -> None:
        """resource 是已開啟的 pyvisa resource；driver 不負責開關連線。"""
        self.res = resource
        self.model = model

    @abstractmethod
    def screenshot(self, opts: ScreenshotOptions) -> bytes:
        """回傳影像的原始位元組，呼叫端直接寫檔即可。逾時 15 秒。"""

    @abstractmethod
    def channels(self) -> list[str]:
        """回傳目前開啟中的通道，例如 ["CHAN1", "CHAN2"]。"""

    @abstractmethod
    def max_points(self) -> int:
        """回傳這台機器目前設定下的最大可取點數，UI 用它擋超限。"""

    @abstractmethod
    def capture(self, channels: list[str], points: int, retrigger: bool) -> CaptureResult:
        """擷取波形。逾時 60 秒。

        retrigger=True 才做單次重新觸發；預設 False。
        不論走哪條路線，都必須在結束前把 RUN/STOP 狀態還原成呼叫前的樣子。
        """


# --------------------------------------------------------------------------
# 自我檢查
# --------------------------------------------------------------------------

def _self_check() -> None:
    pre = Preamble.parse("1,2,1000,1,1e-9,-5e-7,500,0.01,0.0,128")
    assert pre.points == 1000 and pre.x_reference == 500

    t = pre.times(3)
    # (0-500)*1e-9 + (-5e-7) = -1e-6
    assert abs(t[0] - -1e-6) < 1e-18, t[0]
    assert abs(t[1] - t[0] - 1e-9) < 1e-18

    v = pre.volts(np.array([128, 228, 28]))
    assert abs(v[0] - 0.0) < 1e-12
    assert abs(v[1] - 1.0) < 1e-12
    assert abs(v[2] - -1.0) < 1e-12

    w = Waveform.from_raw("CHAN1", pre, np.array([128, 228]))
    assert len(w.time) == 2 and w.preamble is pre

    try:
        Preamble.parse("1,2,3")
    except ScopeError:
        pass
    else:
        raise AssertionError("欄位數不足應該要拋 ScopeError")

    try:
        Waveform("CHAN1", np.zeros(3), np.zeros(2))
    except ScopeError:
        pass
    else:
        raise AssertionError("長度不符應該要拋 ScopeError")

    print("contracts self-check OK")


if __name__ == "__main__":
    _self_check()
