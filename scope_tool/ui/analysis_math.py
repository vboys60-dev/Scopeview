"""數學對話框（Infiniium 的 Function 對話框）：選運算、來源、參數，產生 F1、F2…。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import Callable

import pyqtgraph as pg
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QMessageBox, QSpinBox, QWidget

from scope_tool.analysis.mathfn import BINARY, FILTERS, OPERATIONS, derive
from scope_tool.contracts import Waveform
from scope_tool.ui.worker import Job


class MathDialog(QDialog):
    def __init__(self, names: list[str], current: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("數學函式")
        form = QFormLayout(self)
        self.op = QComboBox()
        self.op.addItems(list(OPERATIONS))
        self.a, self.b = QComboBox(), QComboBox()
        for box in (self.a, self.b):
            box.addItems(names)
        self.a.setCurrentIndex(current)
        self.b.setCurrentIndex(min(1, len(names) - 1))
        self.fc = pg.SpinBox(value=1e6, suffix="Hz", siPrefix=True, dec=True, bounds=(1e-6, None))
        self.points = QSpinBox()
        self.points.setRange(2, 1_000_000)
        self.points.setValue(5)
        for label, w in (("運算", self.op), ("來源 A", self.a), ("來源 B", self.b),
                         ("截止頻率（-3 dB）", self.fc), ("平滑點數", self.points)):
            form.addRow(label, w)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.op.currentTextChanged.connect(self._update)
        self._update(self.op.currentText())

    def _update(self, op: str) -> None:
        self.b.setEnabled(op in BINARY)
        self.fc.setEnabled(op in FILTERS[:2])
        self.points.setEnabled(op == "平滑")

    def spec(self) -> tuple[str, int, int | None, float]:
        """(運算, 來源 A 序號, 來源 B 序號或 None, 參數)。"""
        op = self.op.currentText()
        param = self.points.value() if op == "平滑" else self.fc.value() if op in FILTERS else 0.0
        return op, self.a.currentIndex(), self.b.currentIndex() if op in BINARY else None, float(param)


def run_math(parent: QWidget, waveforms: list[Waveform], units: dict[str, str], current: int,
             on_done: Callable[..., object]) -> Job | None:
    """開對話框，確定後在背景算；成功呼叫 on_done(時間, 數值, 單位)。呼叫端要保留回傳的 Job。"""
    dlg = MathDialog([wf.channel for wf in waveforms], current, parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    op, a, b, param = dlg.spec()
    wa, wb = waveforms[a], waveforms[b] if b is not None else None
    args = (wb.time, wb.voltage, units[wb.channel]) if wb else (None, None, "")
    job = Job(derive, op, wa.time, wa.voltage, units[wa.channel], *args, param)
    job.done.connect(lambda res: on_done(*res))
    job.failed.connect(lambda msg: QMessageBox.warning(parent, "數學運算失敗", msg))
    job.start()
    return job


def _self_check() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    dlg = MathDialog(["CHAN1", "CHAN2"], current=1)
    assert dlg.spec() == ("加", 1, 1, 0.0) and dlg.b.isEnabled()
    dlg.op.setCurrentText("低通")
    dlg.fc.setValue(2e6)
    assert dlg.spec() == ("低通", 1, None, 2e6) and not dlg.b.isEnabled() and dlg.fc.isEnabled()
    dlg.op.setCurrentText("平滑")
    assert dlg.spec() == ("平滑", 1, None, 5.0) and dlg.points.isEnabled() and not dlg.fc.isEnabled()
    single = MathDialog(["CHAN1"])
    assert single.spec()[2] == 0
    app.processEvents()
    print("analysis_math self-check OK")


if __name__ == "__main__":
    _self_check()
