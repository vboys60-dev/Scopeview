"""分析主波形格：10×10 格、多通道曲線、游標與單通道拖曳位移（示波器模式）。"""
from __future__ import annotations

import os

# 必須在匯入 pyqtgraph 前指定 Qt 綁定。
os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

import numpy as np
from PySide6.QtGui import QTransform
from PySide6.QtCore import QPointF, Qt, Signal
import pyqtgraph as pg

from scope_tool.contracts import Waveform
from scope_tool.ui.analysis_chanbar import DIVS, auto_scale, rescale, step_scale, value_range


class _DivAxis(pg.AxisItem):
    """時間軸固定切成 10 格（對齊畫面左右邊），格線跟著刻度走。"""

    def tickValues(self, minVal: float, maxVal: float, size: float) -> list:
        step = (maxVal - minVal) / 10
        return [(step, [minVal + k * step for k in range(11)])] if step > 0 else []

    def tickStrings(self, values: list[float], scale: float, spacing: float) -> list[str]:
        # 格線不落在整數值上，內建格式依間距四捨五入會誤導（0.168 顯示成 0.2），改用 4 位有效數字。
        return [f"{v * scale:.4g}" for v in values]


class _DragViewBox(pg.ViewBox):
    """命中曲線時只平移該通道，其他操作沿用內建行為。"""

    def __init__(self, plot: AnalysisPlot) -> None:
        super().__init__()
        self._plot = plot
        self._drag_channel: int | None = None

    def mouseDragEvent(self, ev: object, axis: int | None = None) -> None:
        if axis is not None:
            super().mouseDragEvent(ev, axis)
            return
        if ev.button() == Qt.LeftButton:
            ev.accept()
            if ev.isStart():
                self._drag_channel = self._plot.channel_at(ev.buttonDownScenePos())
            if self._drag_channel is not None:
                delta = self.mapSceneToView(ev.scenePos()) - self.mapSceneToView(ev.lastScenePos())
                horizontal = bool(ev.modifiers() & Qt.ShiftModifier)
                self._plot.shift_channel(self._drag_channel, delta.x() if horizontal else 0,
                                         0 if horizontal else delta.y())
            if ev.isFinish():
                self._drag_channel = None
            return
        super().mouseDragEvent(ev, axis)

    def wheelEvent(self, ev: object, axis: int | None = None) -> None:
        channel = self._plot.channel_at(ev.scenePos()) if axis is None else None
        if channel is not None:
            self._plot.scale_channel(channel, up=ev.delta() < 0)
            ev.accept()
        else:
            super().wheelEvent(ev, axis)


class AnalysisPlot(pg.PlotWidget):
    """以顯示座標平移縮放曲線，不改動或複製原始資料。縱軸單位是「格」。"""

    offsets_changed = Signal()
    cursors_moved = Signal()

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent=parent, viewBox=_DragViewBox(self), axisItems={"bottom": _DivAxis("bottom")})
        self.curves: list[pg.PlotDataItem] = []
        self.offsets: list[tuple[float, float]] = []
        self.scales: list[float] = []
        self.units: list[str] = []
        self._ranges: list[tuple[float, float]] = []
        self._defaults: list[tuple[float, float]] = []
        self.setLabel("bottom", "時間", units="s")
        self.setLabel("left", "格")
        self.setYRange(-DIVS, DIVS, padding=0)
        self.setMouseEnabled(x=True, y=False)
        self.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.getAxis("left").setTicks([[(i, str(i)) for i in range(-DIVS, DIVS + 1)]])
        self.showGrid(x=True, y=True, alpha=0.3)
        lines = []
        for name, angle, color in (("t1", 90, "#ffffff"), ("t2", 90, "#aaaaaa"),
                                    ("v1", 0, "#ffffff"), ("v2", 0, "#aaaaaa")):
            line = pg.InfiniteLine(angle=angle, movable=True, label=name,
                                   labelOpts={"position": 0.95, "color": color, "movable": False},
                                   pen=pg.mkPen(color, style=Qt.SolidLine if angle else Qt.DashLine))
            # 內建符號沿線的局部座標指向正／負方向，兩端尖端皆朝內。
            line.addMarker("^", position=0, size=12)
            line.addMarker("v", position=1, size=12)
            self.addItem(line)
            line.sigDragged.connect(lambda *_: self.cursors_moved.emit())
            lines.append(line)
        self.vline1, self.vline2, self.hline1, self.hline2 = lines

    def recenter_cursors(self) -> None:
        """將四條游標移回目前可見範圍，再通知分析頁吸附取樣點。"""
        (x_min, x_max), (y_min, y_max) = self.getViewBox().viewRange()
        for line, lo, hi, fraction in (
                (self.vline1, x_min, x_max, 0.25), (self.vline2, x_min, x_max, 0.75),
                (self.hline1, y_min, y_max, 0.25), (self.hline2, y_min, y_max, 0.75)):
            line.setValue(lo + (hi - lo) * fraction)
        self.cursors_moved.emit()

    def set_waveforms(self, waveforms: list[Waveform], colors: list[str], units: list[str]) -> None:
        for curve in self.curves:
            self.removeItem(curve)
        self.curves, self.offsets, self.scales, self.units, self._ranges, self._defaults = [], [], [], [], [], []
        for wf, color, unit in zip(waveforms, colors, units):
            self.add_waveform(wf, color, unit)
        self.reset_view()

    def add_waveform(self, wf: Waveform, color: str, unit: str) -> None:
        lo, hi = value_range(wf.voltage)
        scale, pos = auto_scale(lo, hi, unit)
        curve = self.plot(wf.time, wf.voltage, pen=pg.mkPen(color, width=1), connect="finite")
        curve.setDownsampling(auto=True, method="peak")
        curve.setClipToView(True)
        curve.curve.setClickable(True, width=8)
        self.curves.append(curve)
        self.units.append(unit)
        self._ranges.append((lo, hi))
        self._defaults.append((scale, pos))
        self.scales.append(scale)
        self.offsets.append((0.0, pos))
        self._apply(len(self.curves) - 1)

    def remove_waveform(self, i: int) -> None:
        self.removeItem(self.curves.pop(i))
        for values in (self.units, self._ranges, self._defaults, self.scales, self.offsets):
            values.pop(i)
        self.offsets_changed.emit()

    def set_visible(self, i: int, visible: bool) -> None:
        self.curves[i].setVisible(visible)

    def set_color(self, i: int, color: str) -> None:
        self.curves[i].setPen(pg.mkPen(color, width=1))

    def reset_view(self) -> None:
        self.getViewBox().enableAutoRange(axis=pg.ViewBox.XAxis)
        self.setYRange(-DIVS, DIVS, padding=0)

    def _apply(self, i: int) -> None:
        self.curves[i].setTransform(QTransform.fromScale(1, 1 / self.scales[i]))
        self.curves[i].setPos(*self.offsets[i])

    def set_scale(self, i: int, scale: float, check: bool = False) -> bool:
        """換 V/格並以波形中心為準；check=True 時，新檔位會超出 ±5 格就不換。"""
        dx, pos = self.offsets[i]
        new_pos, fits = rescale(*self._ranges[i], self.scales[i], pos, scale)
        if check and not fits:
            return False
        self.scales[i] = scale
        self.offsets[i] = (dx, new_pos)
        self._apply(i)
        self.offsets_changed.emit()
        return True

    def scale_channel(self, i: int, up: bool) -> None:
        """滾輪換檔：縮小（up）一律可以；放大前先判斷會不會超出畫面。"""
        self.set_scale(i, step_scale(self.scales[i], self.units[i], up), check=not up)

    def set_position(self, i: int, pos: float) -> None:
        self.offsets[i] = (self.offsets[i][0], pos)
        self._apply(i)
        self.offsets_changed.emit()

    def shift_channel(self, i: int, dx: float, dpos: float) -> None:
        x, pos = self.offsets[i]
        self.offsets[i] = (x + dx, pos + dpos)
        self._apply(i)
        self.offsets_changed.emit()

    def reset_channels(self) -> None:
        for i, (scale, pos) in enumerate(self._defaults):
            self.scales[i] = scale
            self.offsets[i] = (0.0, pos)
            self._apply(i)
        self.offsets_changed.emit()

    def channel_at(self, scene_pos: QPointF) -> int | None:
        for i in reversed(range(len(self.curves))):
            curve = self.curves[i]
            if curve.isVisible() and curve.curve.mouseShape().contains(curve.curve.mapFromScene(scene_pos)):
                return i
        return None


def _self_check() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    plot = AnalysisPlot()
    time = np.linspace(0, 1, 1000)
    plot.set_waveforms([Waveform("CHAN1", time, time * 4 - 1), Waveform("CHAN2", time, time * 0 - 3)],
                       ["#ffcc00", "#00d0ff"], ["V", "V"])
    plot.resize(900, 600)
    plot.show()
    app.processEvents()
    assert plot.viewRange()[1] == [-5, 5] and plot.scales == [0.5, 1.0]
    assert list(plot.getViewBox().state["mouseEnabled"]) == [True, False]
    ticks = plot.getAxis("bottom").tickValues(0.0, 1.0, 800)
    assert len(ticks[0][1]) == 11 and np.isclose(ticks[0][0], 0.1)
    assert plot.getAxis("bottom").tickStrings([0.168], 1.0, 0.2) == ["0.168"]
    curve = plot.curves[0]
    data = curve.xData, curve.yData
    # 滾輪放大：-1~3 V 在 0.5 V/格佔 8 格，換 0.2 V/格會超出 → 不換；縮小一律可以
    plot.scale_channel(0, up=False)
    assert plot.scales[0] == 0.5
    plot.scale_channel(0, up=True)
    assert plot.scales[0] == 1.0 and np.isclose(plot.offsets[0][1], -1.0)  # 中心 1 V 仍在 0 格
    assert curve.transform().m22() == 1.0
    assert plot.set_scale(0, 0.5, check=True) and plot.scales[0] == 0.5
    plot.set_position(0, 1.0)
    assert plot.offsets[0] == (0.0, 1.0)
    plot.shift_channel(0, 0.1, 0.5)
    app.processEvents()
    box = plot.getViewBox()

    def on_curve(tt: float) -> QPointF:
        dx, pos = plot.offsets[0]
        return box.mapViewToScene(QPointF(tt + dx, (tt * 4 - 1) / plot.scales[0] + pos))

    point = on_curve(0.25)
    assert plot.channel_at(point) == 0
    assert plot.channel_at(box.mapViewToScene(QPointF(0.5, 4.9))) is None

    class Event:
        """用場景座標模擬拖曳與滾輪。"""
        def __init__(self, point: QPointF, last: QPointF, delta: int = 120) -> None:
            self.point, self.last, self._delta = point, last, delta
            self.accepted = False
        def button(self) -> Qt.MouseButton:
            return Qt.LeftButton
        def isStart(self) -> bool:
            return True
        def isFinish(self) -> bool:
            return True
        def accept(self) -> None:
            self.accepted = True
        def buttonDownScenePos(self) -> QPointF:
            return self.last
        def scenePos(self) -> QPointF:
            return self.point
        def lastScenePos(self) -> QPointF:
            return self.last
        def modifiers(self) -> Qt.KeyboardModifier:
            return getattr(self, "modifier", Qt.NoModifier)
        def delta(self) -> int:
            return self._delta

    before = box.viewRange()
    blank = box.mapViewToScene(QPointF(0.5, 4.8))
    ev = Event(blank + QPointF(30, 20), blank)
    box.mouseDragEvent(ev)
    assert ev.accepted and box.viewRange() == before
    offsets = list(plot.offsets)
    box.mouseDragEvent(Event(point + QPointF(0, 20), point))
    assert plot.offsets[0][1] != offsets[0][1] and plot.offsets[1] == offsets[1]
    app.processEvents()
    point = on_curve(0.3)
    ev = Event(point + QPointF(20, 0), point)
    ev.modifier = Qt.ShiftModifier
    offsets = list(plot.offsets)
    box.mouseDragEvent(ev)
    assert plot.offsets[0][0] != offsets[0][0] and plot.offsets[0][1] == offsets[0][1]
    app.processEvents()
    point = on_curve(0.4)
    box.wheelEvent(Event(point, point, -120))
    assert plot.scales[0] == 1.0 and plot.scales[1] == 1.0, (plot.scales, plot.channel_at(point))
    assert curve.xData is data[0] and curve.yData is data[1]
    plot.add_waveform(Waveform("F1", time, time * 1e6), "#ffffff", "V/s")
    assert len(plot.curves) == 3 and plot.scales[2] == 2e5
    plot.remove_waveform(2)
    assert len(plot.curves) == len(plot.scales) == 2
    plot.reset_channels()
    assert plot.scales == [0.5, 1.0] and plot.offsets == [(0, v[1]) for v in plot._defaults]
    plot.set_color(0, "#123456")
    assert curve.opts["pen"].color().name() == "#123456"
    plot.set_visible(0, False)
    assert not curve.isVisible()
    signals: list[bool] = []
    plot.cursors_moved.connect(lambda: signals.append(True))
    for line, name in zip((plot.vline1, plot.vline2, plot.hline1, plot.hline2), ("t1", "t2", "v1", "v2")):
        assert len(line.markers) == 2 and line.label.format == name
        line.sigDragged.emit(line)
    plot.recenter_cursors()
    assert len(signals) == 5 and plot.hline1.value() == -2.5 and plot.hline2.value() == 2.5
    print("analysis_plot self-check OK")


if __name__ == "__main__":
    _self_check()
