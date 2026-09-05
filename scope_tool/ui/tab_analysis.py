"""波形分析頁：開啟波形檔、多通道繪圖、雙游標量測。

只做「畫出來 + 讀值」，不做自動量測（Vpp／頻率／上升時間），那是明確不做的範圍。
"""

from __future__ import annotations

import os

# 本模組是可能的程式進入點（`python3 -m scope_tool.ui.tab_analysis`），
# 依 RULES.md 第 3 條，import pyqtgraph 之前一定要先指定 Qt 綁定。
# 開發機上 PyQt5/PyQt6/PySide6 三套並存：pyqtgraph 會依 PYQTGRAPH_QT_LIB
# 或「哪一套先被 import」自動選，兩者都設，並確保 PySide6 先 import，
# 不讓 pyqtgraph 誤挑到 PyQt6。
os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import numpy as np
import pyqtgraph as pg

from scope_tool.contracts import ScopeError, Waveform
from scope_tool.storage.reader import read_waveform_file

# 通道顏色循環，數量夠多不必為固定值另外做設定。
_CHANNEL_COLORS = ["#ffcc00", "#00d0ff", "#ff5b5b", "#7cff5b", "#c58bff", "#ff9d3f"]


class AnalysisTab(QWidget):
    """波形分析頁：開檔、繪圖、雙游標（垂直=時間、水平=電壓）量測。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._waveforms: list[Waveform] = []
        self._base_time: np.ndarray | None = None  # 游標吸附用的原始時間軸（取第一個通道）
        self._base_voltage: np.ndarray | None = None

        self._build_ui()
        self._build_cursors()

    # ------------------------------------------------------------------
    # UI 建構
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        self.open_button = QPushButton("開啟波形檔")
        self.open_button.clicked.connect(self._on_open_clicked)
        left.addWidget(self.open_button)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.addLegend()
        self.plot_widget.setLabel("bottom", "時間", units="s")
        self.plot_widget.setLabel("left", "電壓", units="V")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        left.addWidget(self.plot_widget)
        root.addLayout(left, stretch=4)

        # 右側即時數值面板
        panel = QGridLayout()
        self._value_labels: dict[str, QLabel] = {}
        for row, key in enumerate(["t1", "t2", "ΔT", "1/ΔT", "v1", "v2", "ΔV"]):
            panel.addWidget(QLabel(key), row, 0)
            value_label = QLabel("--")
            panel.addWidget(value_label, row, 1)
            self._value_labels[key] = value_label
        panel_widget = QWidget()
        panel_widget.setLayout(panel)
        root.addWidget(panel_widget, stretch=1)

    def _build_cursors(self) -> None:
        """建立兩條垂直（時間）+ 兩條水平（電壓）可拖曳游標。"""
        self.vline1 = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#ffffff", width=1))
        self.vline2 = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#aaaaaa", width=1))
        self.hline1 = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("#ffffff", style=pg.QtCore.Qt.DashLine))
        self.hline2 = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("#aaaaaa", style=pg.QtCore.Qt.DashLine))
        for line in (self.vline1, self.vline2, self.hline1, self.hline2):
            self.plot_widget.addItem(line)
        self.vline1.sigDragged.connect(self._update_readout)
        self.vline2.sigDragged.connect(self._update_readout)
        self.hline1.sigDragged.connect(self._update_readout)
        self.hline2.sigDragged.connect(self._update_readout)

    # ------------------------------------------------------------------
    # 開檔
    # ------------------------------------------------------------------
    def _on_open_clicked(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "開啟波形檔", "", "波形檔 (*.csv *.h5 *.hdf5)"
        )
        if not path_str:
            return
        try:
            waveforms = read_waveform_file(Path(path_str))
        except ScopeError as e:
            QMessageBox.critical(self, "開檔失敗", str(e))
            return
        self.load_waveforms(waveforms)

    # ------------------------------------------------------------------
    # 繪圖
    # ------------------------------------------------------------------
    def load_waveforms(self, waveforms: list[Waveform]) -> None:
        """把一組 Waveform 畫到圖上。可直接餵物件（不經檔案），供自我檢查與其他頁面呼叫。"""
        if not waveforms:
            raise ScopeError("沒有波形資料可畫。")

        self.plot_widget.getPlotItem().clear()
        for line in (self.vline1, self.vline2, self.hline1, self.hline2):
            self.plot_widget.addItem(line)

        self._waveforms = waveforms
        for idx, wf in enumerate(waveforms):
            color = _CHANNEL_COLORS[idx % len(_CHANNEL_COLORS)]
            curve = self.plot_widget.plot(wf.time, wf.voltage, pen=pg.mkPen(color, width=1), name=wf.channel)
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)

        # 游標吸附用的原始資料一律取第一個通道，不做跨通道對齊的花俏邏輯。
        self._base_time = waveforms[0].time
        self._base_voltage = waveforms[0].voltage

        t_span = self._base_time[-1] - self._base_time[0]
        v_min, v_max = float(np.min(self._base_voltage)), float(np.max(self._base_voltage))
        self.vline1.setValue(self._base_time[0] + t_span * 0.25)
        self.vline2.setValue(self._base_time[0] + t_span * 0.75)
        self.hline1.setValue(v_min)
        self.hline2.setValue(v_max)
        self._update_readout()

    # ------------------------------------------------------------------
    # 游標讀值
    # ------------------------------------------------------------------
    def _nearest_sample(self, t: float) -> tuple[float, float]:
        """在原始（未 downsample）時間陣列上找最近取樣點，回傳 (snapped_t, v)。"""
        time_arr, volt_arr = self._base_time, self._base_voltage
        idx = int(np.searchsorted(time_arr, t))
        idx = min(max(idx, 0), len(time_arr) - 1)
        if idx > 0 and abs(time_arr[idx - 1] - t) < abs(time_arr[idx] - t):
            idx -= 1
        return float(time_arr[idx]), float(volt_arr[idx])

    def _update_readout(self, *_args) -> None:
        if self._base_time is None:
            return

        t1, v1 = self._nearest_sample(self.vline1.value())
        t2, v2 = self._nearest_sample(self.vline2.value())
        self.vline1.setValue(t1)  # 吸附到真實取樣點
        self.vline2.setValue(t2)
        dt = t2 - t1
        inv_dt = 1.0 / dt if dt != 0 else float("inf")

        vh1 = self.hline1.value()
        vh2 = self.hline2.value()
        dv = vh2 - vh1

        self._value_labels["t1"].setText(f"{t1:.6e} s")
        self._value_labels["t2"].setText(f"{t2:.6e} s")
        self._value_labels["ΔT"].setText(f"{dt:.6e} s")
        self._value_labels["1/ΔT"].setText(f"{inv_dt:.6e} Hz")
        self._value_labels["v1"].setText(f"{vh1:.6e} V")
        self._value_labels["v2"].setText(f"{vh2:.6e} V")
        self._value_labels["ΔV"].setText(f"{dv:.6e} V")

        # 附帶紀錄游標時間對應的原始電壓值（第一通道），供除錯與潛在延伸使用。
        self._last_v_at_t1 = v1
        self._last_v_at_t2 = v2


# --------------------------------------------------------------------------
# 自我檢查
# --------------------------------------------------------------------------

def _self_check() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    tab = AnalysisTab()

    # 1. 直接餵 Waveform 物件，驗證畫得出來（不經檔案）。
    n = 1000
    dt = 1e-6
    time = np.arange(n, dtype=np.float64) * dt
    voltage1 = np.sin(2 * np.pi * 1e3 * time)
    voltage2 = np.cos(2 * np.pi * 1e3 * time)
    wf1 = Waveform(channel="CHAN1", time=time, voltage=voltage1)
    wf2 = Waveform(channel="CHAN2", time=time, voltage=voltage2)
    tab.load_waveforms([wf1, wf2])
    assert len(tab.plot_widget.getPlotItem().listDataItems()) == 2, "應該畫出兩條曲線"

    # 2. 游標移到已知位置，驗算 ΔT 與預期值差 < 一個取樣週期。
    target_t1 = time[100]
    target_t2 = time[900]
    tab.vline1.setValue(target_t1 + dt * 0.3)  # 故意偏移一點，考驗吸附
    tab.vline2.setValue(target_t2 - dt * 0.3)
    tab._update_readout()
    expected_dt = target_t2 - target_t1
    actual_dt = tab.vline2.value() - tab.vline1.value()
    assert abs(actual_dt - expected_dt) < dt, f"ΔT 誤差過大：{actual_dt} vs {expected_dt}"
    assert abs(tab._last_v_at_t1 - voltage1[100]) < 1e-9

    # 3. 100 萬點資料載入不拋例外。
    big_n = 1_000_000
    big_time = np.arange(big_n, dtype=np.float64) * dt
    big_voltage = np.sin(2 * np.pi * 1e3 * big_time)
    wf_big = Waveform(channel="CHAN1", time=big_time, voltage=big_voltage)
    tab.load_waveforms([wf_big])
    assert len(tab.plot_widget.getPlotItem().listDataItems()) == 1

    print("tab_analysis self-check OK")


if __name__ == "__main__":
    _self_check()
