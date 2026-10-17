"""FFT 頻譜格：FFT 開啟才顯示；背景計算，來源資料變了就丟掉舊結果。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from scope_tool.analysis import fft
from scope_tool.ui.analysis_results import fmt
from scope_tool.ui.worker import Job

# provider(通道名) -> (時間, 數值, 單位, 顏色) 或 None；範圍由分析頁決定（游標區間／全部）。
Provider = Callable[[str], "tuple[np.ndarray, np.ndarray, str, str] | None"]


def _compute(t: np.ndarray, v: np.ndarray, window: str, unit: str, r_ohm: float, source_unit: str) -> dict:
    res = fft.spectrum(t, v, window, unit, r_ohm, source_unit)
    res["peaks"] = fft.peaks(res["freq"], res["mag"], 5, res["lobe"])
    return res


class FFTPane(QWidget):
    result_ready = Signal(str, object, str)  # 說明文字, 峰值清單, 單位

    def __init__(self, provider: Provider) -> None:
        super().__init__()
        self._provider = provider
        self._seq = 0
        self._jobs: set[Job] = set()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.source, self.window, self.unit = QComboBox(), QComboBox(), QComboBox()
        self.window.addItems(list(fft.WINDOWS))
        self.unit.addItems(list(fft.UNITS))
        self.r_ohm = QDoubleSpinBox()
        self.r_ohm.setRange(1, 1e6)
        self.r_ohm.setValue(50)
        self.r_ohm.setSuffix(" Ω")
        self.r_ohm.setToolTip("參考阻抗（dBm、W 用）")
        self.log_x = QCheckBox("對數頻率")
        for label, w in (("FFT 來源", self.source), ("視窗", self.window), ("單位", self.unit), ("", self.r_ohm),
                         ("", self.log_x)):
            if label:
                row.addWidget(QLabel(label))
            row.addWidget(w)
        self.status = QLabel()
        self.status.setStyleSheet("color: gray;")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # 太長就截斷，完整資訊在結果區
        row.addWidget(self.status, stretch=1)
        lay.addLayout(row)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "頻率", units="Hz")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.plot.plot(pen=pg.mkPen("#c58bff", width=1))
        self.curve.setDownsampling(auto=True, method="peak")
        self.curve.setClipToView(True)
        self.marks = pg.ScatterPlotItem(symbol="t", size=10, brush="#ff5b5b")
        self.plot.addItem(self.marks)
        lay.addWidget(self.plot)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._run)
        for w in (self.source, self.window, self.unit):
            w.currentIndexChanged.connect(self.refresh)
        self.r_ohm.valueChanged.connect(self.refresh)
        self.log_x.toggled.connect(self.refresh)
        self._last: dict | None = None

    def set_sources(self, names: list[str]) -> None:
        current = self.source.currentText()
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItems(names)
        self.source.setCurrentIndex(max(self.source.findText(current), 0))
        self.source.blockSignals(False)
        self.refresh()

    def showEvent(self, ev: object) -> None:
        super().showEvent(ev)
        self.refresh()

    def refresh(self, *_: object) -> None:
        """防抖：游標拖曳時只在停下 200 ms 後重算。"""
        self._seq += 1  # 舊工作回來時序號不符就丟掉
        if self.isVisible() and self.source.count():
            self._timer.start()

    def _run(self) -> None:
        seq, name = self._seq, self.source.currentText()
        src = self._provider(name)
        if src is None:
            self._fail("沒有 FFT 來源。")
            return
        t, v, source_unit, _ = src
        self.status.setText("計算中…")
        job = Job(_compute, t, v, self.window.currentText(), self.unit.currentText(), self.r_ohm.value(),
                  source_unit)
        job.done.connect(lambda res, s=seq, n=name: self._done(s, n, res))
        job.failed.connect(lambda msg, s=seq: s == self._seq and self._fail(msg))
        job.finished.connect(lambda j=job: self._jobs.discard(j))
        self._jobs.add(job)
        job.start()

    def _fail(self, message: str) -> None:
        self.status.setText(message)
        self.curve.setData([], [])
        self.marks.setData([], [])
        self.result_ready.emit(message, [], "")

    def _done(self, seq: int, name: str, res: dict) -> None:
        if seq != self._seq:
            return
        self._last = res
        log = self.log_x.isChecked()
        k = 1 if log else 0  # 對數軸不能畫 0 Hz
        self.plot.setLogMode(x=log)
        self.curve.setData(res["freq"][k:], res["mag"][k:])
        pk = res["peaks"]
        self.marks.setData([np.log10(f) if log else f for f, _ in pk], [m for _, m in pk])
        self.plot.setLabel("left", res["unit"])
        info = (f"{name}｜{self.window.currentText()}｜Δf = {fmt(res['df'], 'Hz')}｜"
                f"ENBW = {fmt(res['enbw'], 'Hz')}｜{res['n']:,} 點｜未補零（Infiniium 會補到 2 的次方）")
        self.status.setText(info)
        self.result_ready.emit(info, pk, res["unit"])


def _self_check() -> None:
    import time
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    t = np.arange(4096) * 1e-6
    data = {"CHAN1": (t, np.sin(2 * np.pi * 10e3 * t), "V", "#ffcc00"), "CHAN2": (t[:1], t[:1], "V", "#fff")}
    pane = FFTPane(data.get)
    got: list[tuple] = []
    pane.result_ready.connect(lambda info, pk, unit: got.append((info, pk, unit)))
    pane.show()
    pane.set_sources(["CHAN1", "CHAN2"])

    def wait() -> None:
        for _ in range(100):
            app.processEvents()
            if got and not pane._jobs and not pane._timer.isActive():
                return
            time.sleep(0.02)

    wait()
    info, pk, unit = got[-1]
    assert unit == "dBm" and abs(pk[0][0] - 10e3) < 300 and "未補零" in info
    assert abs(pk[0][1] - 10) < 1.5  # 1 V 峰值弦波 ≈ 10 dBm（Hanning 掃到格間會略低）
    got.clear()
    pane.source.setCurrentIndex(1)
    wait()
    assert got[-1][0].startswith("範圍內") and (pane.curve.xData is None or len(pane.curve.xData) == 0)
    # 連續觸發只留最後一次的結果
    got.clear()
    pane.source.setCurrentIndex(0)
    pane.unit.setCurrentText("Vrms")
    pane.window.setCurrentText("Flattop")
    wait()
    assert len(got) == 1 and got[0][2] == "Vrms" and abs(got[0][1][0][1] - 1 / np.sqrt(2)) < 0.01
    pane.log_x.setChecked(True)
    wait()
    assert pane.curve.xData[0] > 0
    print("analysis_fftplot self-check OK")


if __name__ == "__main__":
    _self_check()
