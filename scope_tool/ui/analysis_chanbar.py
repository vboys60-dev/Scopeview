"""分析頁通道列（Infiniium channel bar）與水平列（horizontal bar），以及 V/格檔位規則。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFrame,
                               QHBoxLayout, QLabel, QScrollArea, QToolButton, QWidget)

DIVS = 5  # 縱軸 ±5 格，共 10 格
# 單位為 V 的通道只用使用者指定的檔位；其他單位（V²、V/s…）用 1-2-5。
V_TABLE = (500e-6, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)
STEPS_125 = tuple(m * 10.0 ** e for e in range(-12, 13) for m in (1, 2, 5))


def scale_steps(unit: str) -> tuple[float, ...]:
    return V_TABLE if unit == "V" else STEPS_125


def value_range(v: np.ndarray) -> tuple[float, float]:
    lo, hi = (float(np.nanmin(v)), float(np.nanmax(v))) if np.any(np.isfinite(v)) else (0.0, 0.0)
    return lo, hi


def auto_scale(lo: float, hi: float, unit: str) -> tuple[float, float]:
    """回傳 (V/格, 位置格數)：波形佔 8 格並置中；超出檔位上限就夾在最大檔。"""
    steps = scale_steps(unit)
    target = (hi - lo) / 8 if hi != lo else abs(hi) / 4
    scale = next((s for s in steps if s >= target), steps[-1]) if target else 1.0
    return scale, -((hi + lo) / 2) / scale


def step_scale(scale: float, unit: str, up: bool) -> float:
    """往大（up）或往小走一檔，到端點就停。"""
    steps = scale_steps(unit)
    i = min(range(len(steps)), key=lambda k: abs(np.log(steps[k] / scale)))
    return steps[min(max(i + (1 if up else -1), 0), len(steps) - 1)]


def rescale(lo: float, hi: float, scale: float, pos: float, new: float) -> tuple[float, bool]:
    """以波形目前中心為準換檔，回傳 (新位置, 是否仍在 ±5 格內)。"""
    center = (lo + hi) / 2
    yc = center / scale + pos
    return yc - center / new, abs(yc) + (hi - lo) / 2 / new <= DIVS + 1e-9


class _Chip(QFrame):
    """單一通道色塊：顯示勾選、V/格、位置、（衍生通道）刪除。"""

    def __init__(self, bar: ChannelBar, i: int, name: str, color: str, unit: str, removable: bool) -> None:
        super().__init__()
        self.i, self.bar, self.color, self.unit = i, bar, color, unit
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        self.check = QCheckBox()
        self.check.setChecked(True)
        self.check.setToolTip("顯示／隱藏")
        self.check.toggled.connect(lambda on: bar.visibility_changed.emit(self.i, on))
        # 名稱用 QLabel：點擊會傳到色塊本身（選取），雙擊換色；勾選框只管顯示。
        self.name = QLabel(name)
        self.name.setToolTip("點一下：選為量測／游標換算來源；雙擊：換色")
        self.scale = QComboBox()
        for s in scale_steps(unit):
            self.scale.addItem(pg.siFormat(s, suffix=f"{unit}/格"), s)
        self.scale.activated.connect(lambda k: bar.scale_chosen.emit(self.i, self.scale.itemData(k)))
        self.pos = QDoubleSpinBox()
        self.pos.setRange(-50, 50)
        self.pos.setSingleStep(0.1)
        self.pos.setSuffix(" 格")
        self.pos.valueChanged.connect(lambda p: bar.position_chosen.emit(self.i, p))
        for w in (self.check, self.name, self.scale, self.pos):
            lay.addWidget(w)
        if removable:
            remove = QToolButton()
            remove.setText("×")
            remove.setToolTip("刪除此衍生波形")
            remove.clicked.connect(lambda: bar.remove_requested.emit(self.i))
            lay.addWidget(remove)
        self.set_color(color)
        self.set_selected(False)

    def set_color(self, color: str) -> None:
        self.color = color
        self.name.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.set_selected(self.property("selected") is True)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", on)
        self.setStyleSheet(f"_Chip {{ border: {3 if on else 1}px solid {self.color if on else '#888'};"
                           " border-radius: 4px; }")

    def mousePressEvent(self, ev: object) -> None:
        self.bar.set_selected(self.i)

    def mouseDoubleClickEvent(self, ev: object) -> None:
        color = QColorDialog.getColor(QColor(self.color), self, "選擇通道顏色")
        if color.isValid():
            self.bar.set_color(self.i, color.name())


class ChannelBar(QScrollArea):
    """通道多時可左右捲動，不撐寬整個分析頁。"""

    visibility_changed = Signal(int, bool)
    color_changed = Signal(int, str)
    selected_changed = Signal(int)
    scale_chosen = Signal(int, float)
    position_chosen = Signal(int, float)
    remove_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        inner = QWidget()
        self._lay = QHBoxLayout(inner)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.addStretch()
        self.setWidget(inner)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chips: list[_Chip] = []
        self._selected = -1

    def set_channels(self, names: list[str], colors: list[str], units: list[str],
                     removable: list[bool], visible: list[bool]) -> None:
        old = self.chips[self._selected].name.text() if 0 <= self._selected < len(self.chips) else None
        for chip in self.chips:  # 先拿出版面，deleteLater 要等事件迴圈才真的刪
            self._lay.removeWidget(chip)
            chip.hide()
            chip.deleteLater()
        self.chips = [_Chip(self, i, *args) for i, args in enumerate(zip(names, colors, units, removable))]
        for chip, shown in zip(self.chips, visible):
            with QSignalBlocker(chip.check):
                chip.check.setChecked(shown)
            self._lay.insertWidget(self._lay.count() - 1, chip)
        chip_h = max((c.sizeHint().height() for c in self.chips), default=0)
        self.setFixedHeight(chip_h + self.horizontalScrollBar().sizeHint().height() + 4)
        # 依名稱保留選取（刪掉前面的通道不會選錯）；選取的通道被刪就選原位置附近的。重建後一定通知一次。
        keep = names.index(old) if old in names else min(max(self._selected, 0), len(names) - 1)
        self._selected = -1
        self.set_selected(keep)

    def set_state(self, i: int, scale: float, pos: float) -> None:
        chip = self.chips[i]
        with QSignalBlocker(chip.scale), QSignalBlocker(chip.pos):
            k = chip.scale.findData(scale)
            if k < 0:  # 預設檔位以外的值（例如超出上限）先加進清單
                chip.scale.addItem(pg.siFormat(scale, suffix=f"{chip.unit}/格"), scale)
                k = chip.scale.count() - 1
            chip.scale.setCurrentIndex(k)
            chip.pos.setValue(pos)

    def set_selected(self, i: int) -> None:
        for chip in self.chips:
            chip.set_selected(chip.i == i)
        if i != self._selected:
            self._selected = i
            self.selected_changed.emit(i)

    def selected(self) -> int:
        return self._selected

    def set_color(self, i: int, color: str) -> None:
        self.chips[i].set_color(color)
        self.color_changed.emit(i, color)


class HorizontalBar(QWidget):
    """H 時間/格（10 格）與中心位置，跟主圖雙向同步。"""

    range_chosen = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("H"))
        self.per_div = pg.SpinBox(value=1e-3, suffix="s/格", siPrefix=True, dec=True, bounds=(1e-15, None))
        self.center = pg.SpinBox(value=0.0, suffix="s", siPrefix=True, dec=True)
        for box, tip in ((self.per_div, "時間/格"), (self.center, "畫面中心時間")):
            box.setToolTip(tip)
            box.setMinimumWidth(110)
            box.sigValueChanged.connect(self._emit)
            lay.addWidget(box)
        help_label = QLabel("滾輪（空白處）：縮放時間軸｜滾輪（波形上）：換該通道 V/格｜拖曳波形：上下移動（Shift＝左右）｜"
                            "拖曳時間軸：平移｜點通道色塊：選量測／游標換算來源｜雙擊色塊：換色")
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(help_label, stretch=1)

    def set_range(self, lo: float, hi: float) -> None:
        for box, value in ((self.per_div, (hi - lo) / 10), (self.center, (hi + lo) / 2)):
            with QSignalBlocker(box):
                box.setValue(value, delaySignal=False)

    def _emit(self, *_: object) -> None:
        half = self.per_div.value() * 5
        self.range_chosen.emit(self.center.value() - half, self.center.value() + half)


def _self_check() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert auto_scale(-1.0, 3.0, "V") == (0.5, -2.0)
    assert auto_scale(0.0, 0.0, "V") == (1.0, 0.0)
    assert auto_scale(-100.0, 100.0, "V")[0] == 10.0  # 超出上限夾在 10 V
    assert auto_scale(0.0, 8e6, "V/s")[0] == 1e6
    assert step_scale(500e-6, "V", True) == 2e-3 and step_scale(500e-6, "V", False) == 500e-6
    assert step_scale(10.0, "V", True) == 10.0 and step_scale(0.1, "V", False) == 50e-3
    assert step_scale(1e3, "V/s", True) == 2e3
    # 0~2 V 在 0.5 V/格、中心 0 格：放大到 0.2 V/格會佔 10 格 → 剛好；到 0.1 V/格 → 超出
    pos, ok = rescale(0.0, 2.0, 0.5, -2.0, 0.2)
    assert ok and np.isclose(pos, -5.0)
    assert not rescale(0.0, 2.0, 0.5, -2.0, 0.1)[1]
    bar = ChannelBar()
    events: list[tuple] = []
    bar.selected_changed.connect(lambda i: events.append(("sel", i)))
    bar.scale_chosen.connect(lambda i, s: events.append(("scale", i, s)))
    bar.remove_requested.connect(lambda i: events.append(("rm", i)))
    bar.set_channels(["CHAN1", "F1"], ["#ffcc00", "#00d0ff"], ["V", "V²"], [False, True], [True, False])
    assert bar.selected() == 0 and ("sel", 0) in events
    bar.set_channels(["CHAN1", "F1"], ["#ffcc00", "#00d0ff"], ["V", "V²"], [False, True], [True, False])
    assert bar._lay.count() == 3  # 重建不會留下舊色塊
    assert bar.height() >= bar.chips[0].sizeHint().height()
    assert not bar.chips[1].check.isChecked() and bar.chips[0].scale.count() == len(V_TABLE)
    bar.set_state(0, 0.2, 1.5)
    assert bar.chips[0].scale.currentData() == 0.2 and bar.chips[0].pos.value() == 1.5
    assert not any(e[0] == "scale" for e in events)  # 程式設定不回送
    bar.chips[0].scale.activated.emit(0)
    assert ("scale", 0, 500e-6) in events
    bar.set_state(1, 3e-7, 0)
    assert bar.chips[1].scale.currentData() == 3e-7
    bar.chips[1].mousePressEvent(None)
    assert bar.selected() == 1 and bar.chips[1].property("selected")
    from PySide6.QtTest import QTest
    QTest.mouseClick(bar.chips[0].name, Qt.LeftButton)  # 點名稱＝選取，不切換顯示
    assert bar.selected() == 0 and bar.chips[0].check.isChecked()
    bar.chips[1].findChild(QToolButton).click()
    assert ("rm", 1) in events
    bar.set_channels(["CHAN1", "F1", "F2", "F3"], ["#fff"] * 4, ["V"] * 4, [False, True, True, True], [True] * 4)
    bar.set_selected(2)
    bar.set_channels(["CHAN1", "F2", "F3"], ["#fff"] * 3, ["V"] * 3, [False, True, True], [True] * 3)
    assert bar.selected() == 1  # 仍是 F2
    hb = HorizontalBar()
    got: list[tuple] = []
    hb.range_chosen.connect(lambda lo, hi: got.append((lo, hi)))
    hb.set_range(0.0, 1e-3)
    assert np.isclose(hb.per_div.value(), 1e-4) and np.isclose(hb.center.value(), 5e-4) and not got
    hb.per_div.setValue(2e-4, delaySignal=False)
    assert np.allclose(got[-1], (5e-4 - 1e-3, 5e-4 + 1e-3))
    app.processEvents()
    print("analysis_chanbar self-check OK")


if __name__ == "__main__":
    _self_check()
