"""分析頁匯出列：以原始資料匯出 CSV，背景執行並回報結果。"""
from __future__ import annotations

import os
os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

import datetime as dt
from pathlib import Path
from typing import Callable
from PySide6.QtWidgets import (QCheckBox, QComboBox, QSpinBox, QFileDialog,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget)
from scope_tool.contracts import Waveform
from scope_tool.storage.csv_export import export_csv
from scope_tool.storage.writer import timestamped
from scope_tool.ui.analysis_results import ResultsPane
from scope_tool.ui.worker import Job


def write_results(results: ResultsPane, directory: Path, source_path: Path | None,
                  meta: list[tuple[str, str]]) -> Path:
    """量測結果 CSV：檔名照規則加時間戳，開頭附來源檔與參數。"""
    stem = source_path.stem if source_path else "waveform"
    meta = [("來源檔", str(source_path or "（未存檔）")), *meta,
            ("匯出時間", dt.datetime.now().isoformat(" ", "seconds"))]
    return results.write_csv(timestamped(directory, f"{stem}_量測", "csv"), meta)


def export_results(parent: QWidget, results: ResultsPane, source_path: Path | None,
                   meta: list[tuple[str, str]]) -> None:
    directory = source_path.parent if source_path else QFileDialog.getExistingDirectory(parent, "選擇輸出資料夾")
    if directory:
        QMessageBox.information(parent, "匯出完成", str(write_results(results, Path(directory), source_path, meta)))


class ExportBar(QWidget):
    """擷取匯出參數，保留來源檔資料夾與縮點行為。"""

    def __init__(self, cursor_range: Callable[[], tuple[float, float]]) -> None:
        super().__init__()
        self._cursor_range = cursor_range
        self._waveforms: list[Waveform] = []
        self._source_path: Path | None = None
        self._export_job: Job | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("範圍"))
        self.export_range = QComboBox()
        self.export_range.addItems(["全部", "游標區間"])
        self.reduce_points = QCheckBox("縮點")
        self.point_limit = QSpinBox()
        self.point_limit.setRange(1, 2_000_000_000)
        self.point_limit.setValue(10_000_000)
        self.point_limit.setGroupSeparatorShown(True)
        self.point_limit.setEnabled(False)
        self.reduce_points.toggled.connect(self.point_limit.setEnabled)
        self.export_button = QPushButton("匯出 CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._on_export_clicked)
        for widget in (self.export_range, self.reduce_points, self.point_limit, self.export_button):
            controls.addWidget(widget)
        root.addLayout(controls)

    def set_data(self, waveforms: list[Waveform], source_path: Path | None) -> None:
        self._waveforms = waveforms
        self._source_path = source_path
        self.export_button.setEnabled(bool(waveforms) and
                                      (self._export_job is None or not self._export_job.isRunning()))

    def export_args(self, directory: Path) -> dict:
        """在 UI 執行緒擷取匯出參數，不開對話框也不啟動工作。匯出原始資料，不套用顯示位移。"""
        return dict(directory=directory,
                    name=self._source_path.stem if self._source_path else "waveform",
                    waveforms=list(self._waveforms),
                    t_range=self._cursor_range()
                    if self.export_range.currentIndex() == 1 else None,
                    max_points=self.point_limit.value() if self.reduce_points.isChecked() else None)

    def _on_export_clicked(self) -> None:
        if self._export_job is not None and self._export_job.isRunning():
            return
        if self._source_path is not None:
            directory = self._source_path.parent
        else:
            chosen = QFileDialog.getExistingDirectory(self, "選擇 CSV 輸出資料夾")
            if not chosen:
                return
            directory = Path(chosen)
        self._export_job = Job(export_csv, **self.export_args(directory))
        self._export_job.done.connect(self._export_done)
        self._export_job.failed.connect(self._export_failed)
        self._export_job.finished.connect(self._export_finished)
        self.export_button.setEnabled(False)
        self.export_button.setText("匯出中…")
        self._export_job.start()

    def _export_finished(self) -> None:
        self.export_button.setText("匯出 CSV")
        self.export_button.setEnabled(bool(self._waveforms))

    def _export_done(self, path: Path) -> None:
        QMessageBox.information(self, "匯出完成", str(path))

    def _export_failed(self, message: str) -> None:
        QMessageBox.critical(self, "匯出失敗", message)

def _self_check() -> None:
    import tempfile
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from scope_tool.storage.reader import read_waveform_file

    app = QApplication.instance() or QApplication([])
    time = np.arange(1000) * 1e-6
    bar = ExportBar(lambda: (time[100], time[199]))
    assert not bar.export_button.isEnabled()
    waveform = Waveform("CHAN1", time, np.sin(time))
    bar.set_data([waveform], None)
    assert bar.export_button.isEnabled()
    bar.export_range.setCurrentIndex(1)
    with tempfile.TemporaryDirectory() as tmp:
        args = bar.export_args(Path(tmp))
        assert args["waveforms"][0] is waveform
        assert len(read_waveform_file(export_csv(**args))[0].time) == 100
        bar.reduce_points.setChecked(True)
        bar.point_limit.setValue(30)
        assert bar.point_limit.isEnabled()
        assert len(read_waveform_file(export_csv(**bar.export_args(Path(tmp))))[0].time) == 25
        pane = ResultsPane()
        pane.set_measurements([("Vmax(CHAN1)", "V", (1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1))], [None])
        out = write_results(pane, Path(tmp), Path(tmp) / "a.h5", [("量測範圍", "全部")])
        assert out.name.startswith("a_量測_") and "量測範圍" in out.read_text(encoding="utf-8-sig")
    bar.set_data([], None)
    assert not bar.export_button.isEnabled()
    print("analysis_export self-check OK")


if __name__ == "__main__":
    _self_check()
