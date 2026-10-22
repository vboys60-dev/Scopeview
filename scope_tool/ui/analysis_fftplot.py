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
                               QSpinBox, QVBoxLayout, QWidget)

from scope_tool.analysis import fft
from scope_tool.analysis.peaks import SORTS
from scope_tool.ui.analysis_marker import RFMarkerController
from scope_tool.ui.analysis_results import fmt
from scope_tool.ui.worker import Job

# provider(通道名) -> (時間, 數值, 單位, 顏色) 或 None；範圍由分析頁決定（游標區間／全部）。
Provider = Callable[[str], "tuple[np.ndarray, np.ndarray, str, str] | None"]


def _compute(t: np.ndarray, v: np.ndarray, window: str, unit: str, r_ohm: float, source_unit: str,
             count: int = 5, level: float = -40, sort: str = SORTS[0], spec: dict | None = None) -> dict:
    """spec 為同設定的快取頻譜時只重做峰表，不重跑 FFT。"""
    res = fft.spectrum(t, v, window, unit, r_ohm, source_unit) if spec is None else dict(spec)
    # 補零會解析出窗旁瓣局部峰；手冊未載明壓旁瓣方法，保留列峰待真機比對。
    res["peaks"] = ([] if res['unit'] == "°" else fft.peaks(
        res['freq'], res['mag'], count, res['lobe'], level=level, sort=sort,
        interpolate=True, amplitude=res['rms']))
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
        self.unit.addItems([unit for unit in fft.UNITS if unit != "W"])  # W 僅留純函式別名
        self.r_ohm = QDoubleSpinBox()
        self.impedance = QComboBox()
        self.impedance.addItems(["Auto：其他／未知 50Ω", "Auto：單端 50Ω", "Auto：差動 100Ω",
                                 "Auto：共模 25Ω", "手動"])
        self.impedance.setToolTip("檔案未含探棒／通道型態；Auto 型態由使用者指定，未知來源假設 50Ω")
        self.r_ohm.setRange(10, 200)
        self.r_ohm.setEnabled(False)
        self.r_ohm.setValue(50)
        self.r_ohm.setSuffix(" Ω")
        self.r_ohm.setToolTip("參考阻抗（dBm、W 用）")
        self.log_x = QCheckBox("對數頻率")
        for label, w in (("FFT 來源", self.source), ("視窗", self.window), ("單位", self.unit), ("", self.impedance), ("", self.r_ohm),
                         ("", self.log_x)):
            if label:
                row.addWidget(QLabel(label))
            row.addWidget(w)
        self.status = QLabel()
        self.status.setStyleSheet("color: gray;")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # 太長就截斷，完整資訊在結果區
        row.addWidget(self.status, stretch=1)
        lay.addLayout(row)
        controls = QHBoxLayout()
        self.peak_sort = QComboBox()
        self.peak_sort.addItems(SORTS)
        self.peak_level = QDoubleSpinBox()
        self.peak_level.setRange(-1e12, 1e12)
        self.peak_level.setDecimals(6)
        self.peak_level.setValue(-40)
        self.peak_level.setSuffix(" dBm")
        self.peak_count = QSpinBox()
        self.peak_count.setRange(0, 1000)
        self.peak_count.setValue(5)
        for title, widget in (("Peak Sort", self.peak_sort), ("Peak Level", self.peak_level),
                              ("最大峰數", self.peak_count)):
            controls.addWidget(QLabel(title))
            controls.addWidget(widget)
        controls.addStretch()
        lay.addLayout(controls)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "頻率", units="Hz")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.plot.plot(pen=pg.mkPen("#c58bff", width=1))
        self.curve.setDownsampling(auto=True, method="peak")
        self.curve.setClipToView(True)
        self.marks = pg.ScatterPlotItem(symbol="t", size=10, brush="#ff5b5b")
        self.plot.addItem(self.marks)
        lay.addWidget(self.plot)
        rf_row = QHBoxLayout()
        self.rf = RFMarkerController(self.plot, rf_row)
        lay.addLayout(rf_row)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._run)
        for w in (self.source, self.window, self.unit):
            w.currentIndexChanged.connect(self.refresh)
        self.r_ohm.valueChanged.connect(self.refresh)
        self.impedance.currentIndexChanged.connect(self._impedance_changed)
        self.peak_sort.currentIndexChanged.connect(self._schedule)  # 峰值控制只重做峰表
        self.peak_level.valueChanged.connect(self._schedule)
        self.peak_count.valueChanged.connect(self._schedule)
        self.unit.currentTextChanged.connect(self._unit_changed)
        self.log_x.toggled.connect(self.refresh)
        self._last: dict | None = None
        self._cache: tuple[tuple, dict] | None = None  # (來源與頻譜設定, 頻譜)；refresh() 即作廢

    def _impedance_changed(self, index: int) -> None:
        self.r_ohm.setEnabled(index == 4)
        self.refresh()

    def _unit_changed(self, unit: str) -> None:
        # 門檻沿用畫面數字，明示新單位；不猜使用者跨單位的門檻意圖。
        self.peak_level.setSuffix(" " + ("°" if unit == "Phase" else unit))
        for control in (self.peak_sort, self.peak_level, self.peak_count):
            control.setEnabled(unit != "Phase")
        self.refresh()

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
        """來源資料（範圍、游標、通道）或頻譜設定可能變了：作廢頻譜快取再重算。"""
        self._cache = None
        self._schedule()

    def _schedule(self, *_: object) -> None:
        """防抖：游標拖曳時只在停下 200 ms 後重算。"""
        self._seq += 1  # 舊工作回來時序號不符就丟掉
        self.rf.set_data(None, self.log_x.isChecked(), self.peak_level.value())
        if self.isVisible() and self.source.count():
            self._timer.start()

    def _run(self) -> None:
        seq, name = self._seq, self.source.currentText()
        self.rf.set_data(None, self.log_x.isChecked(), self.peak_level.value())
        resistance = ([50., 50., 100., 25.][self.impedance.currentIndex()]
                      if self.impedance.currentIndex() < 4 else self.r_ohm.value())
        key = (name, self.window.currentText(), self.unit.currentText(), resistance)
        peak_args = (self.peak_count.value(), self.peak_level.value(), self.peak_sort.currentText())
        if self._cache is not None and self._cache[0] == key:
            job = Job(_compute, None, None, *key[1:], None, *peak_args, spec=self._cache[1])
        else:
            src = self._provider(name)
            if src is None:
                self._fail("沒有 FFT 來源。")
                return
            t, v, source_unit, _ = src
            job = Job(_compute, t, v, *key[1:], source_unit, *peak_args)
        self.status.setText("計算中…")
        job.done.connect(lambda res, s=seq, n=name, k=key: self._done(s, n, res, k))
        job.failed.connect(lambda msg, s=seq: s == self._seq and self._fail(msg))
        job.finished.connect(lambda j=job: self._jobs.discard(j))
        self._jobs.add(job)
        job.start()

    def _fail(self, message: str) -> None:
        self._last = self._cache = None
        self.rf.set_data(None, self.log_x.isChecked(), self.peak_level.value())
        self.status.setText(message)
        self.curve.setData([], [])
        self.marks.setData([], [])
        self.result_ready.emit(message, [], "")

    def _done(self, seq: int, name: str, res: dict, key: tuple) -> None:
        if seq != self._seq:
            return
        self._last, self._cache = res, (key, res)
        log = self.log_x.isChecked()
        k = 1 if log else 0  # 對數軸不能畫 0 Hz
        self.plot.setLogMode(x=log)
        self.curve.setData(res["freq"][k:], res["mag"][k:])
        pk = res['peaks']
        self.peak_level.setSuffix(" " + res['unit'])
        for control in (self.peak_sort, self.peak_level, self.peak_count):
            control.setEnabled(res['unit'] != "°")
        self.rf.set_data(res, log, self.peak_level.value())
        self.marks.setData([np.log10(f) if log else f for f, _ in pk], [m for _, m in pk])
        self.plot.setLabel("left", res["unit"])
        info = (f"{name}｜{self.window.currentText()}｜Δf = {fmt(res['df'], 'Hz')}｜"
                f"RBW = {fmt(res['rbw'], 'Hz')}｜窗 ENBW = {fmt(res['enbw'], 'Hz')} "
                f"({res['enbw_bins']:.4g} 原始 bin)｜{res['n']:,} → {res['effective_n']:,} 點（前後補零）｜"
                f"{res['r_ohm']:g} Ω｜峰頻為本工具拋物線內插")
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
    assert unit == "dBm" and abs(pk[0][0] - 10e3) < 300 and "前後補零" in info
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
    got.clear()
    pane.peak_level.setValue(.1)
    wait()
    pane.rf.enabled.setChecked(True)
    pane.rf.x.setValue(10e3)
    assert pane.rf.line.isVisible() and "Hz" in pane.rf.readout.text()
    pane.rf.x.setValue(0)
    pane.rf.update(1)
    assert abs(pane.rf.x.value() - 10e3) < 300
    # 只改 Peak Sort／Level／最大峰數不得重跑 FFT；頻譜設定或來源資料一變就必須重算。
    spectrum, calls = fft.spectrum, []
    fft.spectrum = lambda *a, **k: calls.append(1) or spectrum(*a, **k)
    try:
        got.clear()
        pane.peak_sort.setCurrentIndex(1)
        pane.peak_count.setValue(2)
        pane.peak_level.setValue(.05)
        wait()
        f_peaks = [f for f, _ in got[-1][1]]
        assert not calls and 0 < len(f_peaks) <= 2 and f_peaks == sorted(f_peaks)
        got.clear()
        pane.window.setCurrentText("Hanning")
        wait()
        assert len(calls) == 1
        got.clear()  # 換資料但不換任何設定：快取不得沿用
        data["CHAN1"] = (t, np.sin(2 * np.pi * 20e3 * t), "V", "#ffcc00")
        pane.refresh()  # 分析頁在範圍／游標／通道變動時呼叫
        wait()
        assert len(calls) == 2 and abs(got[-1][1][0][0] - 20e3) < 300
    finally:
        fft.spectrum = spectrum
    pane.impedance.setCurrentIndex(4)
    assert pane.r_ohm.isEnabled() and pane.r_ohm.minimum() == 10 and pane.r_ohm.maximum() == 200
    got.clear()
    pane.r_ohm.setValue(100)
    pane.unit.setCurrentText("Phase")
    wait()
    assert got[-1][2] == "°" and not got[-1][1] and not pane.rf.line.isVisible()
    assert pane._last['r_ohm'] == 100
    assert "原始 bin" in got[-1][0]
    controls = (pane.peak_sort, pane.peak_level, pane.peak_count)
    assert not any(w.isEnabled() for w in controls)
    assert pane.unit.findText("W") == -1 and pane.unit.findText("Watt") >= 0
    # Phase 成功後換到失敗來源，再切 dBm；即使仍失敗，也要恢復峰值控制。
    got.clear()
    pane.source.setCurrentIndex(1)
    wait()
    assert pane._last is None and not any(w.isEnabled() for w in controls)
    got.clear()
    pane.unit.setCurrentText("dBm")
    wait()
    assert pane._last is None and all(w.isEnabled() for w in controls)
    print("analysis_fftplot self-check OK")


if __name__ == "__main__":
    _self_check()
