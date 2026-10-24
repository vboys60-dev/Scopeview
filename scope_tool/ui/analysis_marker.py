"""Marker 模式接線：沿用分析頁四條游標，來源座標與顯示格數在此換算。"""
from __future__ import annotations

import os
import math

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import TYPE_CHECKING

import pyqtgraph as pg

from scope_tool.analysis.marker import MarkerResult, Position, Source, evaluate

if TYPE_CHECKING:
    from scope_tool.ui.tab_analysis import AnalysisTab


class MarkerController:
    def __init__(self, tab: AnalysisTab) -> None:
        self.tab = tab
        self.measurements: list[tuple[float, float, str]] = []
        self.measurement_source = ""
        self.points = pg.ScatterPlotItem(size=10, pen="w", brush=None)
        tab.plot_widget.addItem(self.points, ignoreBounds=True)
        self.labels: list[pg.TextItem] = []

    def set_measurements(self, source: str, positions: list[tuple[float, float, str]]) -> None:
        """呼叫端提供最近新增量測實際使用的位置；空清單會清掉標記。

        現有量測引擎只提供統計值，尚未接此接口；手冊未載明的各量測位置不推測。
        """
        self.measurement_source, self.measurements = source, list(positions)
        self.tab._update_readout()

    def update(self, src: int) -> tuple[bool, MarkerResult | None]:
        tab, plot = self.tab, self.tab.plot_widget
        mode = tab.toolbar.marker_mode.currentData()
        legacy = mode is None
        xs = legacy or mode in ("Manual X only", "Manual X and Y", "Track Waveforms")
        ys = legacy or mode in ("Manual Y only", "Manual X and Y")
        for line in (plot.vline1, plot.vline2):
            line.setVisible(xs)
            line.setMovable(xs)
        for line in (plot.hline1, plot.hline2):
            line.setVisible(ys)
            line.setMovable(ys)
        if mode == "Track Measurements" and self.measurement_source in tab._names():
            src = tab._names().index(self.measurement_source)
        wf = tab._waveforms[src]
        dx, pos = plot.offsets[src]
        scale = plot.scales[src]
        self.points.clear()
        for label in self.labels:
            plot.removeItem(label)
        self.labels.clear()
        if legacy:
            return True, None
        width = plot.viewRange()[0][1] - plot.viewRange()[0][0]
        result = evaluate(mode, Position(plot.vline1.value() - dx, plot.vline2.value() - dx,
                                        (plot.hline1.value() - pos) * scale,
                                        (plot.hline2.value() - pos) * scale),
                          Source(wf.time, wf.voltage), screen_width=width,
                          measurements=self.measurements if self.measurement_source == wf.channel else [])
        p = result.position
        points = result.points
        if mode == "Track Waveforms" and result.available:
            plot.vline1.setValue(p.x1 + dx)
            plot.vline2.setValue(p.x2 + dx)
            points = ((p.x1, p.y1, "X1"), (p.x2, p.y2, "X2"))
        if points:
            self.points.setData([x + dx for x, _, _ in points], [y / scale + pos for _, y, _ in points])
            for x, y, text in points:
                label = pg.TextItem(text, color="w", anchor=(0, 1))
                label.setPos(x + dx, y / scale + pos)
                plot.addItem(label, ignoreBounds=True)
                self.labels.append(label)
        tab.results.set_cursor_values(p.x1, p.x2, p.y1, p.y2, tab._units[wf.channel], wf.channel,
                                      [], marker=result)
        return False, result


class RFMarkerController:
    """FFT 格獨立的 Track RF；預設關閉，沿用純函式與來源座標讀值慣例。"""

    def __init__(self, plot: pg.PlotWidget, row: object) -> None:
        from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLabel, QPushButton

        self.enabled = QCheckBox("Track RF")
        self.x = QDoubleSpinBox()
        self.x.setRange(0, 1e15)
        self.x.setDecimals(6)
        self.x.setSuffix(" Hz")
        self.readout = QLabel("—")
        self.line = pg.InfiniteLine(angle=90, movable=True, pen="#66ddff")
        self.point = pg.ScatterPlotItem(size=9, brush="#66ddff")
        plot.addItem(self.line, ignoreBounds=True)
        plot.addItem(self.point, ignoreBounds=True)
        self.line.hide()
        self.data: dict | None = None
        self.log = False
        self.level = -float('inf')
        self.pos = 0.0  # 完整精度位置；spin box 只到六位小數，僅供顯示與輸入
        for w in (self.enabled, self.x):
            row.addWidget(w)
        for title, direction in (("← 下一峰", -1), ("下一峰 →", 1)):
            button = QPushButton(title)
            button.clicked.connect(lambda _, d=direction: self.update(d))
            row.addWidget(button)
        row.addWidget(self.readout)
        row.addStretch()
        self.enabled.toggled.connect(lambda _: self.update())
        self.x.valueChanged.connect(self._typed)
        self.line.sigPositionChangeFinished.connect(self._dragged)

    def _typed(self, value: float) -> None:
        self.pos = value
        self.update()

    def _dragged(self) -> None:
        self.pos = 10 ** self.line.value() if self.log else self.line.value()
        self.update()

    def set_data(self, data: dict | None, log: bool, level: float) -> None:
        self.data, self.log, self.level = data, log, level
        self.update()

    def update(self, direction: int = 0) -> None:
        from scope_tool.analysis.marker import track_rf
        from scope_tool.ui.analysis_results import fmt

        on = self.enabled.isChecked() and self.data is not None and self.data['unit'] != "°"
        self.line.setVisible(on)
        self.point.setVisible(on)
        self.x.setEnabled(on)
        if not on:
            self.readout.setText("—")
            return
        result = track_rf(self.data['freq'], self.data['mag'], self.pos,
                          level=self.level, direction=direction)
        p = result.position
        self.pos = p.x1
        self.x.blockSignals(True)
        self.x.setValue(p.x1)
        self.x.blockSignals(False)
        visible = not self.log or p.x1 > 0
        self.line.setVisible(visible)
        self.point.setVisible(visible)
        if visible:
            x = math.log10(p.x1) if self.log else p.x1
            self.line.setValue(x)
            self.point.setData([x], [p.y1])
        self.readout.setText(f"{fmt(p.x1, 'Hz')}｜{fmt(p.y1, self.data['unit'])}" +
                             (f"｜{result.reason}" if not result.available else ""))


def _self_check() -> None:
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from scope_tool.contracts import Waveform
    from scope_tool.ui.tab_analysis import AnalysisTab

    app = QApplication.instance() or QApplication([])
    tab = AnalysisTab()
    t = np.array([-2., -1., -0.1, 0., 0.3, 0.8, 1., 2.])
    tab.load_waveforms([Waveform("CHAN1", t, t * 2)])
    plot, combo = tab.plot_widget, tab.toolbar.marker_mode
    combo.setCurrentIndex(1)
    plot.vline1.setValue(0.123456)
    tab._update_readout()
    assert plot.vline1.value() == 0.123456 and plot.vline1.isVisible() and not plot.hline1.isVisible()
    combo.setCurrentIndex(2)
    assert not plot.vline1.isVisible() and plot.hline1.isVisible() and plot.hline1.movable
    combo.setCurrentIndex(3)
    assert plot.vline1.isVisible() and plot.hline1.isVisible()
    plot.setXRange(-0.2, 0.2, padding=0)
    plot.vline1.setValue(-99)
    plot.vline2.setValue(99)
    seq = tab.runner._seq
    combo.setCurrentIndex(4)
    assert tab.runner._seq > seq and tab.runner._timer.isActive()
    assert tab._slice(0)[0].tolist() == [-1., -0.1, 0., 0.3, 0.8, 1.]
    assert plot.vline1.value() == -1 and plot.vline2.value() == 1
    assert not plot.hline1.isVisible() and len(tab.markers.points.points()) == 2
    assert tab.results.cursor_table.item(2, 1).text() == "2 s"
    assert tab.results.cursor_table.item(0, 0).text() == "X1" and tab.results.cursor_table.rowCount() == 10
    assert tab.results.cursor_table.item(9, 0).text() == "Delta To" and tab.results.channel_table.rowCount() == 0
    assert tab.results.cursor_table.item(7, 1).text() == "2 V/s"
    # 縮放使 Track Waveforms 重新吸附移動游標時，量測與 FFT 必須失效重算（setValue 不發 sigDragged）。
    plot.setXRange(-3, 3, padding=0)
    plot.vline1.setValue(-2)
    plot.vline2.setValue(2)
    tab._update_readout()
    tab.runner._timer.stop()
    seq, fft_seq = tab.runner._seq, tab.fft._seq
    plot.setXRange(-.2, .2, padding=0)
    assert plot.vline1.value() == -1 and plot.vline2.value() == 1
    assert tab.runner._seq > seq and tab.runner.busy() and tab.fft._seq > fft_seq
    seq = tab.runner._seq
    plot.setXRange(-.3, .3, padding=0)  # 吸附位置不變就不重算
    assert tab.runner._seq == seq
    plot.set_scale(0, 2.)
    plot.shift_channel(0, 0.5, 1.)
    tab.markers.set_measurements("CHAN1", [(0, 1, "起點"), (0.3, 2, "終點")])
    combo.setCurrentIndex(5)
    assert not plot.vline1.isVisible() and not plot.vline1.movable
    assert len(tab.markers.points.points()) == 2 and tab.markers.labels[0].pos().x() == 0.5
    assert tab.results.cursor_table.item(6, 1).text() == "1 V"
    tab.markers.set_measurements("CHAN1", [])
    assert len(tab.markers.points.points()) == 0 and tab.results.cursor_table.item(2, 1).text() == "—"
    combo.setCurrentIndex(0)
    assert plot.vline1.isVisible() and plot.hline1.isVisible() and plot.hline1.movable
    # 峰頻 1.0000004 在六位小數 spin box 會捨成 1.0；狀態須保留完整精度，否則下一峰卡在同一峰。
    from PySide6.QtWidgets import QHBoxLayout
    rf_plot, rf_row = pg.PlotWidget(), QHBoxLayout()  # 保留參照，免得 Qt 物件被回收
    rf = RFMarkerController(rf_plot, rf_row)
    rf.set_data({"freq": np.array([0., 1.0000004, 2., 3.]), "mag": np.array([0., 3., 0., 2.]),
                 "unit": "Vrms"}, False, 0)
    rf.enabled.setChecked(True)
    rf.update(1)
    assert rf.pos == 1.0000004 and rf.line.value() == 1.0000004
    rf.update(1)
    assert rf.pos == 3 and rf.line.value() == 3
    rf.update(-1)
    assert rf.pos == 1.0000004
    rf.x.setValue(2.4)  # 使用者輸入仍生效
    assert rf.pos == 2 and rf.x.value() == 2
    print("analysis_marker self-check OK")


if __name__ == "__main__":
    _self_check()
