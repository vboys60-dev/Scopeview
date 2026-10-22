"""分析頁上方工具列與左側量測圖示欄（Infiniium 的 Time Meas／Vertical Meas 分頁）。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QLabel, QMenu, QTabWidget, QToolBar, QToolButton,
                               QVBoxLayout, QWidget, QWidgetAction)

from scope_tool.analysis.measure import MEASUREMENTS, SLOPED, THRESHOLDS
from scope_tool.ui.analysis_export import ExportBar

# 量測說明（滑鼠停留提示），依手冊定義濃縮。
_TIPS = {
    "上升時間": "上升緣從下閾值到上閾值的時間（邊緣至少 4 點）",
    "下降時間": "下降緣從上閾值到下閾值的時間（邊緣至少 4 點）",
    "上升斜率": "上下閾值電壓差 ÷ 上升時間", "下降斜率": "上下閾值電壓差 ÷ 下降時間",
    "週期": "同方向相鄰兩邊緣在中閾值的時間差", "頻率": "1 ÷ 週期（逐週期）",
    "+寬度": "上升緣中閾值到下一個下降緣中閾值", "-寬度": "下降緣中閾值到下一個上升緣中閾值",
    "工作週期": "+寬度 ÷ 週期 × 100（逐週期）",
    "Vmax": "最大值", "Vmin": "最小值", "Vp-p": "最大值 − 最小值",
    "Vtop": "上方平台（直方圖眾數，不明顯時用最大值）", "Vbase": "下方平台（直方圖眾數，不明顯時用最小值）",
    "Vamp": "Vtop − Vbase", "Vavg": "第一個完整週期的平均", "Vrms(DC)": "含直流的有效值", "Vrms(AC)": "扣掉平均後的有效值",
    "過衝": "邊緣後到平台中點的局部極值超出 top／base 的量，÷ 振幅 × 100",
    "前衝": "平台中點到邊緣前的局部極值超出 base／top 的量，÷ 振幅 × 100",
}


class AnalysisToolBar(QToolBar):
    """工具列；放不下的按鈕由 QToolBar 自動收進溢出選單（»）。"""

    def __init__(self, cursor_range: Callable[[], tuple[float, float]]) -> None:
        super().__init__("分析工具列")
        self.open_action = self.addAction("開啟")
        self.info_action = self.addAction("檔案資訊")
        self.addSeparator()
        self.reset_action = self.addAction("重設視圖")
        self.channels_action = self.addAction("通道歸位")
        self.cursors_action = self.addAction("游標歸位")
        self.addSeparator()
        self.export_bar = ExportBar(cursor_range)
        menu = QMenu(self)
        holder = QWidgetAction(menu)
        holder.setDefaultWidget(self.export_bar)
        menu.addAction(holder)
        self.export_button = QToolButton()
        self.export_button.setText("匯出 CSV ▾")
        self.export_button.setMenu(menu)
        self.export_button.setPopupMode(QToolButton.InstantPopup)
        self.addWidget(self.export_button)
        self.math_action = self.addAction("數學…")
        self.fft_action = self.addAction("FFT")
        self.fft_action.setCheckable(True)
        self.addSeparator()
        self.addWidget(QLabel(" 閾值 "))
        self.threshold = QComboBox()
        self.threshold.addItems(list(THRESHOLDS))
        self.addWidget(self.threshold)
        self.addWidget(QLabel(" 量測範圍 "))
        self.range = QComboBox()
        self.range.addItems(["游標區間", "全部"])
        self.addWidget(self.range)
        self.preview_action = self.addAction("預覽")
        self.preview_action.setCheckable(True)
        self.summary = QLabel()
        self.summary.setStyleSheet("color: gray; padding-left: 8px;")
        self.addWidget(self.summary)
        self.set_loaded(False)

    def set_loaded(self, loaded: bool) -> None:
        for action in (self.info_action, self.reset_action, self.channels_action, self.cursors_action,
                       self.math_action, self.fft_action):
            action.setEnabled(loaded)
        self.export_button.setEnabled(loaded)

    def pct(self) -> tuple[float, float, float]:
        return THRESHOLDS[self.threshold.currentText()]

    def use_cursors(self) -> bool:
        return self.range.currentIndex() == 0


class MeasureBar(QWidget):
    """點一下＝對目前選取的通道加一筆量測；邊緣方向在加入時固定。"""

    measure_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slope = QComboBox()
        self.slope.addItems(["上升緣 ↑", "下降緣 ↓"])
        self.slope.setToolTip("週期、頻率、工作週期、過衝、前衝使用的邊緣方向")
        lay.addWidget(self.slope)
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.West)
        self.buttons: dict[str, QToolButton] = {}
        for category in ("時間", "電壓"):
            page = QWidget()
            col = QVBoxLayout(page)
            col.setContentsMargins(2, 2, 2, 2)
            for name, (cat, _) in MEASUREMENTS.items():
                if cat != category:
                    continue
                button = QToolButton()
                button.setText(name + (" ↕" if name in SLOPED else ""))
                button.setToolTip(_TIPS[name])
                button.setMinimumWidth(90)
                button.clicked.connect(lambda _=False, n=name: self.measure_requested.emit(n))
                col.addWidget(button)
                self.buttons[name] = button
            col.addStretch()
            self.tabs.addTab(page, f"{category}量測")
        lay.addWidget(self.tabs)
        self.setEnabled(False)

    def rising(self) -> bool:
        return self.slope.currentIndex() == 0


def _self_check() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    bar = AnalysisToolBar(lambda: (0.0, 1.0))
    assert not bar.math_action.isEnabled() and not bar.export_button.isEnabled()
    bar.set_loaded(True)
    assert bar.math_action.isEnabled() and bar.fft_action.isCheckable()
    assert bar.pct() == (10.0, 50.0, 90.0) and bar.use_cursors()
    bar.threshold.setCurrentIndex(1)
    bar.range.setCurrentIndex(1)
    assert bar.pct() == (20.0, 50.0, 80.0) and not bar.use_cursors()
    assert bar.export_bar.export_range.count() == 2
    mb = MeasureBar()
    got: list[str] = []
    mb.measure_requested.connect(got.append)
    assert set(mb.buttons) == set(MEASUREMENTS) and set(_TIPS) == set(MEASUREMENTS)
    mb.buttons["週期"].click()
    assert not got  # 尚未開檔時停用
    mb.setEnabled(True)
    mb.buttons["週期"].click()
    mb.buttons["Vp-p"].click()
    assert got == ["週期", "Vp-p"] and mb.rising()
    mb.slope.setCurrentIndex(1)
    assert not mb.rising() and mb.tabs.count() == 2 and mb.tabs.tabText(1) == "電壓量測"
    print("analysis_controls self-check OK")


if __name__ == "__main__":
    _self_check()
