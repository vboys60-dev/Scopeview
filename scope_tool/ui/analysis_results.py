"""分析頁下方 Results 區：量測表、游標表、FFT 峰值表；寬時並排、窄時改分頁。"""
from __future__ import annotations

import csv
import os
from pathlib import Path

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMenu,
                               QPushButton, QSizePolicy, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from scope_tool.analysis.marker import MarkerResult, Position
from scope_tool.analysis.measure import STAT_COLUMNS
from scope_tool.contracts import ScopeError, Waveform
from scope_tool.storage.reader import read_file_info

_NARROW = 900  # 視窗寬度低於此值改成分頁


def fmt(value: float | None, unit: str) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    if unit in ("", "%") or unit.startswith("dB"):  # 無單位、百分比、dB 不加 SI 字首
        return f"{value:.6g} {unit}".strip()
    return pg.siFormat(value, precision=6, suffix=unit)


def file_info_rows(source_path: Path | None, waveforms: list[Waveform]) -> list[tuple[str, str]]:
    """組裝檔案資訊；來源資訊讀取失敗時仍提供波形摘要。"""
    rows = [("檔名", source_path.name if source_path else "（未存檔）")]
    try:
        info = read_file_info(source_path) if source_path else {}
    except ScopeError:
        info = {}
    rows.extend((label, info[key]) for key, label in
                (("Model", "機型"), ("Series", "系列"), ("CapturedAt", "擷取時間")) if key in info)
    if not waveforms:
        return rows
    time = waveforms[0].time
    rows.extend([("通道", ", ".join(wf.channel for wf in waveforms)), ("點數", f"{len(time):,}")])
    if len(time) > 1:
        interval = float(time[1] - time[0])
        rows.extend([("取樣間隔", fmt(interval, "s")),
                     ("取樣率", fmt(1 / interval if interval else float("inf"), "Sa/s"))])
    if len(time):
        rows.append(("時間長度", fmt(float(time[-1] - time[0]), "s")))
    return rows


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(22)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    return table


def _fill(table: QTableWidget, rows: list[list[str]], colors: list[str | None] | None = None,
          tips: list[str] | None = None) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            item = QTableWidgetItem(text)
            if c and text not in ("—", "…"):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if colors and colors[r] and c == 0:
                item.setForeground(QColor(colors[r]))
            if tips and tips[r]:
                item.setToolTip(tips[r])
            table.setItem(r, c, item)


class ResultsPane(QWidget):
    remove_requested = Signal(int)
    clear_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._raw: list[tuple[str, str, tuple | str | None]] = []
        # 量測
        self.meas_group = QGroupBox("量測")
        lay = QVBoxLayout(self.meas_group)
        self.meas_table = _table(["量測", *STAT_COLUMNS])
        self.meas_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.meas_table.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.meas_table)
        buttons = QHBoxLayout()
        self.clear_button, self.export_button = QPushButton("清除全部"), QPushButton("匯出結果 CSV")
        self.clear_button.clicked.connect(self.clear_requested.emit)
        self.export_button.clicked.connect(self.export_requested.emit)
        self.note = QLabel("「目前」＝最接近顯示時間參考點的事件（範圍含零取零，否則取中點）")
        self.note.setStyleSheet("color: gray; font-size: 11px;")
        self.note.setWordWrap(True)
        for w in (self.note, self.clear_button, self.export_button):
            buttons.addWidget(w)
        lay.addLayout(buttons)
        # 游標
        self.cursor_group = QGroupBox("游標")
        lay = QHBoxLayout(self.cursor_group)
        self.cursor_table = _table(["項目", "值"])
        self.channel_table = _table(["通道", "@t1", "@t2", "Δ(t2−t1)"])
        lay.addWidget(self.cursor_table)
        lay.addWidget(self.channel_table, stretch=1)
        # FFT
        self.fft_group = QGroupBox("FFT 峰值")
        lay = QVBoxLayout(self.fft_group)
        self.fft_info = QLabel("—")
        self.fft_info.setWordWrap(True)
        self.fft_table = _table(["#", "頻率", "大小"])
        lay.addWidget(self.fft_info)
        lay.addWidget(self.fft_table)
        self.fft_group.hide()
        # 寬：並排（可拖分隔、可收合）；窄：分頁
        self._groups = (self.meas_group, self.cursor_group, self.fft_group)
        self._split, self._tabs, self._stack = QSplitter(Qt.Horizontal), QTabWidget(), QStackedWidget()
        for g in self._groups:
            self._split.addWidget(g)
        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        self._stack.addWidget(self._split)
        self._stack.addWidget(self._tabs)
        # 忽略子元件的最小寬度，視窗才縮得到 _NARROW 以下、觸發改分頁。
        self._stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        QVBoxLayout(self).addWidget(self._stack)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._narrow = False

    def resizeEvent(self, ev: object) -> None:
        super().resizeEvent(ev)
        self.arrange(self.width() < _NARROW)

    def arrange(self, narrow: bool) -> None:
        if narrow == self._narrow:
            return
        fft_on = self._tabs.isTabVisible(2) if self._narrow else not self.fft_group.isHidden()
        self._narrow = narrow
        if narrow:
            for g in self._groups:
                self._tabs.addTab(g, g.title())
            self._tabs.setTabVisible(2, fft_on)
        else:
            while self._tabs.count():
                self._tabs.removeTab(0)
            for g in self._groups:
                self._split.addWidget(g)
                g.setVisible(g is not self.fft_group or fft_on)
        self._stack.setCurrentIndex(int(narrow))

    def set_fft_visible(self, on: bool) -> None:
        if self._narrow:
            self._tabs.setTabVisible(2, on)
        else:
            self.fft_group.setVisible(on)

    def _menu(self, pos: object) -> None:
        row = self.meas_table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        menu.addAction("刪除此量測", lambda: self.remove_requested.emit(row))
        menu.exec(self.meas_table.viewport().mapToGlobal(pos))

    def set_measurements(self, rows: list[tuple[str, str, tuple | str | None]], colors: list[str | None]) -> None:
        """rows：(標籤, 單位, 結果)；結果為 stats tuple、失敗原因字串，或 None（計算中）。"""
        self._raw = rows
        texts, tips = [], []
        for label, unit, res in rows:
            if isinstance(res, tuple):
                texts.append([label, *(fmt(x, unit) for x in res[:-1]), str(res[-1])])
                tips.append("")
            else:
                texts.append([label] + ["…" if res is None else "—"] * len(STAT_COLUMNS))
                tips.append(res or "計算中")
        _fill(self.meas_table, texts, colors, tips)

    def write_csv(self, path: Path, meta: list[tuple[str, str]]) -> Path:
        """數值用完整精度、單位獨立一欄，方便重現；開頭附來源與參數。"""
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerows(meta)
            w.writerow([])
            w.writerow(["量測", "單位", *STAT_COLUMNS, "備註"])
            for label, unit, res in self._raw:
                w.writerow([label, unit, *(repr(x) for x in res), ""] if isinstance(res, tuple)
                           else [label, unit, *[""] * len(STAT_COLUMNS), res or ""])
        return path

    def set_cursor_values(self, t1: float | None, t2: float | None, v1: float | None, v2: float | None,
                          unit: str, source: str, channels: list[tuple[str, str, str, float, float]],
                          marker: MarkerResult | None = None) -> None:
        """v1/v2 以 source 通道換算；channels：(名稱, 顏色, 單位, @t1, @t2)。"""
        d = marker.delta_x if marker else (None if t1 is None or t2 is None else t2 - t1)
        inv = marker.inverse_delta_x if marker else (1 / d if d else None)
        dy = marker.delta_y if marker else (None if v1 is None or v2 is None else v2 - v1)
        labels = ("X1", "X2", "ΔX", "1/ΔX", "Y1", "Y2", "ΔY") if marker else (
                  "t1", "t2", "Δt", "1/Δt", "v1", "v2", "ΔV")
        values = ((t1, "s"), (t2, "s"), (d, "s"), (inv, "Hz"), (v1, unit), (v2, unit), (dy, unit))
        rows = [[label, fmt(v, u)] for label, (v, u) in zip(labels, values)]
        slope = (marker or MarkerResult(Position(t1, t2, v1, v2))).delta_y_over_delta_x
        rows.append(["ΔY/ΔX", fmt(slope, f"{unit}/s" if unit else "1/s") if slope is not None else ""])
        rows.append(["換算來源", source])
        if marker:
            rows.append(["Delta To", "X1↔X2；Y1↔Y2"])
        _fill(self.cursor_table, rows)
        self.cursor_table.setToolTip(marker.reason if marker and not marker.available else
                                     "Track Measurements 為唯讀位置" if marker and marker.read_only else "")
        _fill(self.channel_table, [[n, fmt(a, u), fmt(b, u), fmt(b - a, u)] for n, _, u, a, b in channels],
              [c for _, c, _, _, _ in channels])

    def set_fft(self, info: str, peaks: list[tuple[float, float]], unit: str) -> None:
        self.fft_info.setText(info)
        _fill(self.fft_table, [[str(k + 1), fmt(f, "Hz"), fmt(m, unit)] for k, (f, m) in enumerate(peaks)])


def _self_check() -> None:
    import tempfile
    import h5py
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert fmt(1.5e-6, "s") == "1.5 µs" and fmt(-0.0123, "V") == "-12.3 mV"
    assert fmt(-0.02, "dBm") == "-0.02 dBm" and fmt(50, "%") == "50 %" and fmt(np.nan, "V") == "—"
    pane = ResultsPane()
    events: list[tuple] = []
    pane.remove_requested.connect(lambda r: events.append(("rm", r)))
    pane.clear_requested.connect(lambda: events.append(("clear",)))
    stats = (1e-3, 1.1e-3, 0.9e-3, 1.2e-3, 0.3e-3, 1e-4, 4)
    pane.set_measurements([("週期(CHAN1 ↑)", "s", stats), ("頻率(CHAN2 ↑)", "Hz", "範圍內沒有完整週期"),
                           ("Vmax(F1)", "V", None)], ["#ffcc00", "#00d0ff", None])
    t = pane.meas_table
    assert t.rowCount() == 3 and t.item(0, 1).text() == "1 ms" and t.item(0, 7).text() == "4"
    assert t.item(1, 2).text() == "—" and t.item(1, 2).toolTip() == "範圍內沒有完整週期"
    assert t.item(2, 1).text() == "…" and t.item(0, 0).foreground().color().name() == "#ffcc00"
    pane.clear_button.click()
    assert events == [("clear",)]
    with tempfile.TemporaryDirectory() as tmp:
        path = pane.write_csv(Path(tmp) / "m.csv", [("來源檔", "a.h5"), ("範圍", "全部")])
        rows = list(csv.reader(open(path, encoding="utf-8-sig")))
        assert rows[0] == ["來源檔", "a.h5"] and rows[3][:3] == ["量測", "單位", "目前"]
        assert float(rows[4][2]) == 1e-3 and rows[5][-1] == "範圍內沒有完整週期"
        source = Path(tmp) / "source.h5"
        with h5py.File(source, "w") as hf:
            hf.create_group("ScopeTool").attrs["Model"] = "DSO-X 3014G"
        waves = [Waveform("CHAN1", np.arange(1000) * 1e-6, np.zeros(1000))]
        info = file_info_rows(source, waves)
        assert ("機型", "DSO-X 3014G") in info and ("點數", "1,000") in info
    assert ("檔名", "（未存檔）") in file_info_rows(None, waves)
    pane.set_cursor_values(0.0, 1e-3, -1.0, 1.0, "V", "CHAN1", [("CHAN1", "#ffcc00", "V", 0.1, 0.3)])
    assert pane.channel_table.item(0, 3).text() == fmt(0.3 - 0.1, "V")
    assert pane.cursor_table.item(3, 1).text() == "1 kHz" and pane.cursor_table.item(8, 1).text() == "CHAN1"
    assert pane.cursor_table.rowCount() == 9
    assert [pane.cursor_table.item(i, 0).text() for i in range(8)] == ["t1", "t2", "Δt", "1/Δt", "v1", "v2", "ΔV", "ΔY/ΔX"]
    assert [pane.channel_table.horizontalHeaderItem(i).text() for i in range(4)] == ["通道", "@t1", "@t2", "Δ(t2−t1)"]
    assert pane.cursor_table.item(7, 1).text() == fmt(2000, "V/s")
    for marker_mode in (False, True):
        for x1, x2, y1, y2, want in ((0, 2, 1, 5, 2), (2, 0, 1, 5, -2), (0, 2, 1, 1, 0),
                (0, 0, 1, 5, None), (None, 2, 1, 5, None), (0, 2, None, 5, None),
                (0, np.inf, 1, 5, None), (0, 2, 1, np.nan, None), (0, 1e-308, 0, 1e308, None)):
            marker = MarkerResult(Position(x1, x2, y1, y2)) if marker_mode else None
            pane.set_cursor_values(x1, x2, y1, y2, "A", "CHAN2", [], marker=marker)
            assert pane.cursor_table.item(7, 1).text() == (fmt(want, "A/s") if want is not None else "")
            assert pane.cursor_table.rowCount() == (10 if marker_mode else 9)
    pane.set_fft("Δf = 1 Hz", [(1e3, -3.0)], "dBm")
    assert pane.fft_table.item(0, 1).text() == "1 kHz" and pane.fft_table.item(0, 2).text() == "-3 dBm"
    pane.resize(1200, 300)
    pane.show()
    pane.set_fft_visible(True)
    app.processEvents()
    assert not pane._narrow and pane.fft_group.isVisible()
    pane.resize(600, 300)
    app.processEvents()
    assert pane._narrow and pane._tabs.count() == 3 and pane._tabs.isTabVisible(2)
    pane.set_fft_visible(False)
    pane.resize(1200, 300)
    app.processEvents()
    assert not pane._narrow and pane.meas_group.isVisible() and pane.cursor_group.isVisible()
    assert not pane.fft_group.isVisible() and pane._split.count() == 3
    print("analysis_results self-check OK")


if __name__ == "__main__":
    _self_check()
