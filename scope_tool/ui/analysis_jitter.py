"""時脈還原設定對話框、Jitter 格（TIE 趨勢＋直方圖），以及 Jitter／眼圖格共用的背景計算底座。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from scope_tool.analysis.clock import EDGES, KINDS, MODES, Clock, ClockSpec, rate, recover
from scope_tool.ui.analysis_results import fmt
from scope_tool.ui.worker import Job

# provider(通道名) -> (時間, 數值, 單位, 顏色) 或 None；範圍由分析頁決定（游標區間／全部）。
Provider = Callable[[str], "tuple[np.ndarray, np.ndarray, str, str] | None"]
NOTE = "固定頻率還原（未做 PLL／SSC 追蹤），數值與 Infiniium EZJIT 可能不同"


class ClockDialog(QDialog):
    def __init__(self, spec: ClockSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("時脈還原")
        form = QFormLayout(self)
        self.kind, self.edges, self.mode = QComboBox(), QComboBox(), QComboBox()
        for box, items, value in ((self.kind, KINDS, spec.kind), (self.edges, EDGES, spec.edges),
                                  (self.mode, MODES, spec.mode)):
            box.addItems(list(items))
            box.setCurrentText(value)
        self.rate = pg.SpinBox(value=spec.rate, suffix="Hz", siPrefix=True, dec=True, bounds=(1e-3, None))
        self.n = QSpinBox()
        self.n.setRange(1, 20)
        self.n.setValue(spec.n)
        for label, w in (("訊號類型", self.kind), ("邊緣", self.edges), ("速率", self.mode),
                         ("標稱速率", self.rate), ("N（N 週期／Period-Period）", self.n)):
            form.addRow(label, w)
        note = QLabel("標稱速率：時脈填頻率，資料填位元率。全自動不用填；半自動以它為起點再擬合；"
                      "手動固定 UI 只估相位。資料型一律用兩種邊緣。")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.kind.currentIndexChanged.connect(self._sync)
        self.mode.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        self.edges.setEnabled(self.kind.currentText() == "時脈")
        self.rate.setEnabled(self.mode.currentText() != "全自動")

    def spec(self) -> ClockSpec:
        return ClockSpec(self.kind.currentText(), self.edges.currentText(), self.mode.currentText(),
                         float(self.rate.value()), self.n.value())


class ClockPane(QWidget):
    """Jitter／眼圖格共用：來源下拉、狀態列、警告列；防抖背景計算，序號不符的舊結果丟掉。
    子類別提供 compute（背景執行的純函式，回傳含 "clock" 的 dict）、draw、clear、summary。"""

    TITLE = ""

    def __init__(self, provider: Provider, spec: Callable[[], ClockSpec],
                 pct: Callable[[], tuple[float, float, float]]) -> None:
        super().__init__()
        self._provider, self._spec, self._pct = provider, spec, pct
        self._seq = 0
        self._jobs: set[Job] = set()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.source = QComboBox()
        row.addWidget(QLabel(f"{self.TITLE}來源"))
        row.addWidget(self.source)
        self.status = QLabel()
        self.status.setStyleSheet("color: gray;")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # 太長就截斷，滑鼠停留看全文
        row.addWidget(self.status, stretch=1)
        lay.addLayout(row)
        self.warn = QLabel()
        self.warn.setStyleSheet("color: #d08000;")
        self.warn.setWordWrap(True)
        self.warn.hide()
        lay.addWidget(self.warn)
        self.body = QHBoxLayout()
        lay.addLayout(self.body, stretch=1)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._run)
        self.source.currentIndexChanged.connect(self.refresh)

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
        self._seq += 1
        if self.isVisible() and self.source.count():
            self._timer.start()

    def _run(self) -> None:
        seq, name = self._seq, self.source.currentText()
        src = self._provider(name)
        if src is None:
            self._fail("沒有來源。")
            return
        t, v, unit, color = src
        self.status.setText("計算中…")
        job = Job(self.compute, t, v, self._pct(), self._spec())
        job.done.connect(lambda res, s=seq: s == self._seq and self._show(name, unit, color, res))
        job.failed.connect(lambda msg, s=seq: s == self._seq and self._fail(msg))
        job.finished.connect(lambda j=job: self._jobs.discard(j))
        self._jobs.add(job)
        job.start()

    def _fail(self, message: str) -> None:
        self.status.setText(message)
        self.status.setToolTip(message)
        self.warn.hide()
        self.clear()

    def _show(self, name: str, unit: str, color: str, res: dict) -> None:
        ck: Clock = res["clock"]
        info = (f"{name}｜還原速率 {fmt(rate(ck), 'Hz')}｜UI {fmt(ck.ui, 's')}｜{ck.times.size:,} 個邊緣｜"
                f"{self.summary(res)}｜{NOTE}")
        self.status.setText(info)
        self.status.setToolTip(info)
        self.warn.setText("⚠ " + "；".join(ck.warnings))
        self.warn.setVisible(bool(ck.warnings))
        self.draw(res, unit, color)


def _jitter(t: np.ndarray, v: np.ndarray, pct: tuple, spec: ClockSpec) -> dict:
    return {"clock": recover(t, v, pct, spec)}


class JitterPane(ClockPane):
    TITLE = "Jitter "
    compute = staticmethod(_jitter)

    def __init__(self, provider: Provider, spec: Callable[[], ClockSpec],
                 pct: Callable[[], tuple[float, float, float]]) -> None:
        super().__init__(provider, spec, pct)
        self.trend, self.hist = pg.PlotWidget(), pg.PlotWidget()
        self.trend.setLabel("bottom", "時間", units="s")
        self.trend.setLabel("left", "TIE", units="s")
        self.hist.setLabel("bottom", "TIE", units="s")
        self.hist.setLabel("left", "次數")
        for plot in (self.trend, self.hist):
            plot.showGrid(x=True, y=True, alpha=0.3)
        self.trend_curve = self.trend.plot(connect="finite")
        # 不開自動降採樣：pyqtgraph 0.14 在 x 為秒（數值很小）時會把資料全丟掉。
        self.trend_curve.setClipToView(True)
        self.hist_curve = self.hist.plot(stepMode="center", fillLevel=0)
        self.body.addWidget(self.trend, stretch=3)
        self.body.addWidget(self.hist, stretch=2)

    def summary(self, res: dict) -> str:
        tie = res["clock"].tie
        return f"TIE RMS {fmt(float(tie.std()), 's')}｜p-p {fmt(float(np.ptp(tie)), 's')}"

    def draw(self, res: dict, unit: str, color: str) -> None:
        ck: Clock = res["clock"]
        x, y = ck.times, ck.tie
        if ck.spec.kind == "時脈":  # 缺邊處斷開，不畫成相鄰
            gap = np.flatnonzero(np.diff(ck.n) > ck.step) + 1
            x = np.insert(x, gap, (x[gap - 1] + x[gap]) / 2)
            y = np.insert(y, gap, np.nan)
        self.trend_curve.setData(x, y, pen=pg.mkPen(color, width=1))
        counts, edges = np.histogram(ck.tie, bins=int(np.clip(np.sqrt(ck.tie.size), 10, 200)))
        self.hist_curve.setData(edges, counts, pen=pg.mkPen(color), brush=pg.mkBrush(color + "80"))

    def clear(self) -> None:
        self.trend_curve.setData([], [])
        self.hist_curve.setData([0, 1], [0])


def _self_check() -> None:
    import time
    from PySide6.QtWidgets import QApplication

    from scope_tool.analysis.clock import nrz

    app = QApplication.instance() or QApplication([])
    dlg = ClockDialog(ClockSpec())
    assert dlg.edges.isEnabled() and not dlg.rate.isEnabled()
    dlg.kind.setCurrentText("NRZ 資料")
    dlg.mode.setCurrentText("半自動")
    dlg.n.setValue(3)
    assert not dlg.edges.isEnabled() and dlg.rate.isEnabled()
    assert dlg.spec() == ClockSpec("NRZ 資料", "上升", "半自動", 1e6, 3)
    tc, vc = nrz(np.tile([0, 1], 1500), 1e-9, 10)
    vc[(tc > 1000.95e-9) & (tc < 1002.5e-9)] = 0  # 拿掉一個脈衝 → 缺邊
    data = {"CHAN1": (tc, vc, "V", "#ffcc00"), "CHAN2": (tc, np.zeros_like(tc), "V", "#00d0ff")}
    spec = [ClockSpec()]
    pane = JitterPane(data.get, lambda: spec[0], lambda: (10, 50, 90))
    pane.show()
    pane.set_sources(["CHAN1", "CHAN2"])

    def wait() -> None:
        for _ in range(200):
            app.processEvents()
            if not pane._jobs and not pane._timer.isActive():
                return
            time.sleep(0.01)

    wait()
    assert "還原速率 500 MHz" in pane.status.text() and "缺邊 1 處" in pane.warn.text(), pane.status.text()
    assert np.isnan(pane.trend_curve.yData).sum() == 1 and pane.hist_curve.yData.sum() == 1499
    assert len(pane.trend_curve.getData()[0]) > 1000  # 真的有畫出來（不是被降採樣丟光）
    spec[0] = ClockSpec(edges="兩者")
    pane.refresh()
    wait()
    assert "2,997 個邊緣" in pane.status.text() and "還原速率 500 MHz" in pane.status.text()
    pane.source.setCurrentIndex(1)
    wait()
    assert "振幅" in pane.status.text() and pane.warn.isHidden() and len(pane.trend_curve.xData or []) == 0
    print("analysis_jitter self-check OK")


if __name__ == "__main__":
    _self_check()
