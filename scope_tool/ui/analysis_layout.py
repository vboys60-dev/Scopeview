"""分析頁的元件、版面與訊號接線（類似 Qt Designer 的 setupUi）；行為留在 tab_analysis.py。

版面：工具列；左側量測圖示欄；中央＝通道列、垂直分隔（預覽／主波形／FFT）、水平列；下方結果區。
"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from scope_tool.ui.analysis_chanbar import ChannelBar, HorizontalBar
from scope_tool.ui.analysis_controls import AnalysisToolBar, MeasureBar
from scope_tool.ui.analysis_fftplot import FFTPane
from scope_tool.ui.analysis_overview import OverviewPlot
from scope_tool.ui.analysis_plot import AnalysisPlot
from scope_tool.ui.analysis_results import ResultsPane
from scope_tool.ui.analysis_runner import MeasureRunner

if TYPE_CHECKING:
    from scope_tool.ui.tab_analysis import AnalysisTab


def setup_ui(tab: AnalysisTab) -> None:
    tab.toolbar = AnalysisToolBar(lambda: (tab.vline1.value(), tab.vline2.value()))
    tab.export_bar = tab.toolbar.export_bar
    tab.measbar, tab.chanbar, tab.hbar = MeasureBar(), ChannelBar(), HorizontalBar()
    tab.plot_widget = AnalysisPlot()
    tab.vline1, tab.vline2 = tab.plot_widget.vline1, tab.plot_widget.vline2
    tab.hline1, tab.hline2 = tab.plot_widget.hline1, tab.plot_widget.hline2
    tab.overview = OverviewPlot()
    tab.overview.link(tab.plot_widget)
    tab.fft = FFTPane(tab._source)
    tab.results = ResultsPane()
    grids = QSplitter(Qt.Vertical)
    for w in (tab.overview, tab.plot_widget, tab.fft):
        grids.addWidget(w)
        w.setVisible(w is tab.plot_widget)
    grids.setStretchFactor(1, 3)
    grids.setStretchFactor(2, 2)
    center = QWidget()
    col = QVBoxLayout(center)
    col.setContentsMargins(0, 0, 0, 0)
    for w in (tab.chanbar, grids, tab.hbar):
        col.addWidget(w, stretch=1 if w is grids else 0)
    top = QWidget()
    row = QHBoxLayout(top)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(tab.measbar)
    row.addWidget(center, stretch=1)
    main = QSplitter(Qt.Vertical)
    main.addWidget(top)
    main.addWidget(tab.results)
    main.setSizes([640, 260])
    root = QVBoxLayout(tab)
    root.addWidget(tab.toolbar)
    root.addWidget(main, stretch=1)
    tab.runner = MeasureRunner(tab.results, tab._source, tab.toolbar.pct)


def wire(tab: AnalysisTab) -> None:
    tb, plot, bar = tab.toolbar, tab.plot_widget, tab.chanbar
    tb.open_action.triggered.connect(tab._on_open_clicked)
    tb.info_action.triggered.connect(tab._show_file_info)
    tb.reset_action.triggered.connect(plot.reset_view)
    tb.channels_action.triggered.connect(plot.reset_channels)
    tb.cursors_action.triggered.connect(plot.recenter_cursors)
    tb.math_action.triggered.connect(tab._open_math)
    tb.fft_action.toggled.connect(tab.fft.setVisible)  # FFT 格顯示時自己重算
    tb.fft_action.toggled.connect(tab.results.set_fft_visible)
    tb.preview_action.toggled.connect(tab.overview.setVisible)
    tb.threshold.currentIndexChanged.connect(tab._range_changed)
    tb.range.currentIndexChanged.connect(tab._range_changed)
    tab.measbar.measure_requested.connect(tab._add_measurement)
    bar.visibility_changed.connect(plot.set_visible)
    bar.visibility_changed.connect(lambda i, on: i < tab._n_raw and tab.overview.set_visible(i, on))
    bar.color_changed.connect(tab._set_color)
    bar.selected_changed.connect(tab._update_readout)
    bar.scale_chosen.connect(plot.set_scale)
    bar.position_chosen.connect(plot.set_position)
    bar.remove_requested.connect(tab._remove_channel)
    tab.hbar.range_chosen.connect(lambda lo, hi: plot.setXRange(lo, hi, padding=0))
    plot.getViewBox().sigXRangeChanged.connect(lambda _box, r: tab.hbar.set_range(*r))
    plot.cursors_moved.connect(tab._update_readout)
    plot.cursors_moved.connect(tab._range_changed)
    plot.offsets_changed.connect(tab._offsets_changed)
    tab.results.export_requested.connect(tab._export_results)
    tab.fft.result_ready.connect(tab.results.set_fft)


def _self_check() -> None:
    from PySide6.QtWidgets import QApplication

    from scope_tool.ui.tab_analysis import AnalysisTab

    app = QApplication.instance() or QApplication([])
    tab = AnalysisTab()  # 建構時呼叫 setup_ui＋wire
    tab.resize(1200, 800)
    tab.show()
    app.processEvents()
    assert tab.plot_widget.isVisible() and not tab.fft.isVisible()
    assert not tab.toolbar.fft_action.isEnabled()  # 開檔前停用
    tab.toolbar.set_loaded(True)
    tab.toolbar.fft_action.setChecked(True)
    app.processEvents()
    assert tab.fft.isVisible() and tab.results.fft_group.isVisible()
    print("analysis_layout self-check OK")


if __name__ == "__main__":
    _self_check()
