"""整段波形預覽：以區域方框連動主圖時間範圍。"""
from __future__ import annotations

import os
os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

import pyqtgraph as pg
from scope_tool.contracts import Waveform
from scope_tool.ui.analysis_plot import AnalysisPlot


class OverviewPlot(pg.PlotWidget):
    """保留整段原始電壓，區域方框代表主圖的可見時間。"""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(90)
        self.setMouseEnabled(False, False)
        self.hideAxis("left")
        self.setLabel("bottom", "時間", units="s")
        self.curves: list[pg.PlotDataItem] = []
        self.region = pg.LinearRegionItem()
        self.addItem(self.region, ignoreBounds=True)
        self._syncing = False
        self._main: AnalysisPlot | None = None
        self.region.sigRegionChanged.connect(self._region_changed)

    def set_waveforms(self, waveforms: list[Waveform], colors: list[str]) -> None:
        for curve in self.curves:
            self.removeItem(curve)
        self.curves = []
        for wf, color in zip(waveforms, colors):
            curve = self.plot(wf.time, wf.voltage, pen=pg.mkPen(color, width=1))
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(False)
            self.curves.append(curve)
        self.enableAutoRange()
        if self._main is not None:
            self._main_changed(self._main.getViewBox(), self._main.viewRange()[0])

    def link(self, main: AnalysisPlot) -> None:
        if self._main is not None:
            self._main.getViewBox().sigXRangeChanged.disconnect(self._main_changed)
        self._main = main
        main.getViewBox().sigXRangeChanged.connect(self._main_changed)
        self._main_changed(main.getViewBox(), main.viewRange()[0])

    def _main_changed(self, _box: pg.ViewBox, bounds: tuple[float, float]) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.region.setRegion(bounds)
        finally:
            self._syncing = False

    def _region_changed(self) -> None:
        if self._syncing or self._main is None:
            return
        self._syncing = True
        try:
            self._main.setXRange(*self.region.getRegion(), padding=0)
        finally:
            self._syncing = False

    def set_visible(self, i: int, visible: bool) -> None:
        self.curves[i].setVisible(visible)

    def set_color(self, i: int, color: str) -> None:
        self.curves[i].setPen(pg.mkPen(color, width=1))


def _self_check() -> None:
    import numpy as np
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    main, overview = AnalysisPlot(), OverviewPlot()
    waves = [Waveform("CHAN1", np.arange(100.), np.sin(np.arange(100.)))]
    main.set_waveforms(waves, ["#ffcc00"], ["V"])
    overview.set_waveforms(waves, ["#ffcc00"])
    overview.link(main)
    main.show()
    overview.show()
    app.processEvents()
    overview.region.setRegion((10, 30))
    assert np.allclose(main.viewRange()[0], [10, 30])
    main.setXRange(40, 60, padding=0)
    assert np.allclose(overview.region.getRegion(), [40, 60])
    for i in range(50):
        overview.region.setRegion((i, i + 10))
        main.setXRange(i + 1, i + 11, padding=0)
    assert not overview._syncing
    assert overview.viewRange()[0][0] <= 0 and overview.viewRange()[0][1] >= 99
    overview.set_color(0, "#123456")
    assert overview.curves[0].opts["pen"].color().name() == "#123456"
    overview.set_visible(0, False)
    assert not overview.curves[0].isVisible()
    print("analysis_overview self-check OK")


if __name__ == "__main__":
    _self_check()
