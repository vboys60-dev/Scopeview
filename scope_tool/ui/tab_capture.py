"""波形擷取頁：選通道、點數，固定 HDF5，擷取後寫檔。
RULES.md 第 4 條：driver.channels()／max_points()／capture() 都可能是真正的
VISA 查詢，一律透過 `worker.Job` 丟到背景執行緒，UI 執行緒本身不直接呼叫。
"""

from __future__ import annotations

import os
os.environ.setdefault("QT_API", "pyside6")  # 必須在 import pyqtgraph/Qt 系列之前

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from scope_tool.contracts import CaptureResult, ScopeDriver, WaveformFormat
from scope_tool.storage.writer import write_waveform
from scope_tool.ui.worker import Job

def _query_driver_info(driver: ScopeDriver) -> tuple[list[str], int]:
    """在背景執行緒跑：查目前開啟的通道與最大可取點數。"""
    return driver.channels(), driver.max_points()

class CaptureTab(QWidget):
    """波形擷取頁。透過 `host`（通常是 MainWindow）取得 `driver`／`cfg`／`driver_changed`。"""

    def __init__(self, host: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.host = host
        self._job: Job | None = None
        self._info_job: Job | None = None
        self._max_points: int | None = None
        self._channel_checks: dict[str, QCheckBox] = {}
        self._build_ui()
        self._load_from_config()
        if hasattr(host, "driver_changed"):
            host.driver_changed.connect(self._on_driver_changed)
        self._on_driver_changed(getattr(host, "driver", None))
    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        path_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.browse_button = QPushButton("瀏覽…")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        path_row.addWidget(QLabel("目錄："))
        path_row.addWidget(self.dir_edit, stretch=1)
        path_row.addWidget(self.browse_button)
        root.addLayout(path_row)
        name_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        name_row.addWidget(QLabel("檔名："))
        name_row.addWidget(self.name_edit, stretch=1)
        root.addLayout(name_row)
        self.channel_group = QGroupBox("通道")
        self.channel_layout = QHBoxLayout(self.channel_group)
        root.addWidget(self.channel_group)
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("點數："))
        self.points_spin = QSpinBox()
        self.points_spin.setRange(1, 2_000_000_000)
        self.points_spin.setValue(10_000)
        opt_row.addWidget(self.points_spin)
        self.retrigger_check = QCheckBox("擷取前重新觸發單次擷取")
        self.retrigger_check.setChecked(False)  # 預設關
        opt_row.addWidget(self.retrigger_check)
        root.addLayout(opt_row)
        self.start_button = QPushButton("開始擷取")
        self.start_button.clicked.connect(self._on_start_clicked)
        root.addWidget(self.start_button)
        self.status_label = QLabel("尚未擷取")
        root.addWidget(self.status_label)
        root.addStretch(1)

    def _load_from_config(self) -> None:
        cfg = getattr(self.host, "cfg", {})
        self.dir_edit.setText(str(cfg.get("waveform_dir", str(Path.home()))))
        self.name_edit.setText(str(cfg.get("waveform_name", "wave")))
        self.points_spin.setValue(int(cfg.get("points", 10_000)))
        self.retrigger_check.setChecked(bool(cfg.get("retrigger", False)))

    def _save_to_config(self) -> None:
        cfg = getattr(self.host, "cfg", None)
        if cfg is None:
            return
        cfg["waveform_dir"] = self.dir_edit.text()
        cfg["waveform_name"] = self.name_edit.text()
        cfg["points"] = self.points_spin.value()
        cfg["retrigger"] = self.retrigger_check.isChecked()
    # ---------------------------------------------------------- driver 狀態
    def _on_driver_changed(self, driver: ScopeDriver | None) -> None:
        """連線／斷線時觸發，背景查通道與點數上限。# 待真機驗證：查詢逾時行為。"""
        self._clear_channels()
        self._max_points = None
        if driver is None:
            self.status_label.setText("尚未連線")
            return
        self.status_label.setText("查詢通道與點數上限中…")
        self._info_job = Job(_query_driver_info, driver)
        self._info_job.done.connect(self._on_info_done)
        self._info_job.failed.connect(self._on_info_failed)
        self._info_job.start()

    def _clear_channels(self) -> None:
        for check in self._channel_checks.values():
            check.setParent(None)
            check.deleteLater()
        self._channel_checks.clear()

    def _on_info_done(self, info: tuple[list[str], int]) -> None:
        channels, max_points = info
        self._max_points = max_points
        for ch in channels:
            check = QCheckBox(ch)
            check.setChecked(True)
            self.channel_layout.addWidget(check)
            self._channel_checks[ch] = check
        self.status_label.setText(f"就緒（最大點數 {max_points}）")

    def _on_info_failed(self, message: str) -> None:
        self.status_label.setText("查詢通道失敗")
        QMessageBox.warning(self, "查詢失敗", message)

    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "選擇輸出目錄", self.dir_edit.text())
        if directory:
            self.dir_edit.setText(directory)
    # --------------------------------------------------------------- 擷取
    def _selected_channels(self) -> list[str]:
        return [ch for ch, check in self._channel_checks.items() if check.isChecked()]

    def _on_start_clicked(self) -> None:
        driver = getattr(self.host, "driver", None)
        if driver is None:
            QMessageBox.warning(self, "尚未連線", "請先連線儀器。")
            return
        channels = self._selected_channels()
        if not channels:
            QMessageBox.warning(self, "未選通道", "請至少勾選一個通道。")
            return
        if self._max_points is None:
            QMessageBox.warning(self, "尚未就緒", "還沒查到這台機器的點數上限，請稍候再試。")
            return
        points = self.points_spin.value()
        if points > self._max_points:
            msg = f"這台機器目前最多可取 {self._max_points} 點，請調低點數。"
            QMessageBox.warning(self, "點數超過上限", msg)
            return
        self._save_to_config()
        self.start_button.setEnabled(False)
        self.status_label.setText("擷取中…")
        self._job = Job(driver.capture, channels, points, self.retrigger_check.isChecked())
        self._job.done.connect(self._on_capture_done)
        self._job.failed.connect(self._on_capture_failed)
        self._job.start()

    def _on_capture_done(self, result: CaptureResult) -> None:
        self.start_button.setEnabled(True)
        directory = Path(self.dir_edit.text())
        name = self.name_edit.text() or "wave"
        try:
            path = write_waveform(directory, name, result, WaveformFormat.HDF5)
        except OSError as exc:
            self.status_label.setText("寫檔失敗")
            QMessageBox.critical(self, "寫檔失敗", str(exc))
            return
        got = min(len(w.time) for w in result.waveforms)
        hint = ""
        if got < self.points_spin.value():
            hint = f"（示波器實際只有 {got} 點，時基調慢可增加）"
        self.status_label.setText(f"已存檔：{path}{hint}")

    def _on_capture_failed(self, message: str) -> None:
        self.start_button.setEnabled(True)
        self.status_label.setText("擷取失敗")
        QMessageBox.critical(self, "擷取失敗", message)
# ---------------------------------------------------------------- 自我檢查
def _self_check() -> None:
    import sys
    import tempfile
    import time
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication
    from scope_tool import config
    from scope_tool.instruments.fake import FakeDriver
    app = QApplication.instance() or QApplication([])
    class _Host(QObject):
        driver_changed = Signal(object)
        def __init__(self) -> None:
            super().__init__()
            self.driver: ScopeDriver | None = None
            self.cfg = dict(config.DEFAULTS)

    def pump(predicate, timeout_s: float = 2.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline and not predicate():
            app.processEvents()
            time.sleep(0.01)
        assert predicate(), "等待逾時"
    # 攔截 QMessageBox，避免自我檢查真的跳出視窗（headless 下 exec() 會卡死）。
    class _FakeBox:
        warning = staticmethod(lambda *_a, **_k: None)
        critical = staticmethod(lambda *_a, **_k: None)

    def out_path(tab: "CaptureTab") -> Path:
        return Path(tab.status_label.text().split("：", 1)[1])
    with tempfile.TemporaryDirectory() as tmpdir:
        host = _Host()
        host.cfg["waveform_dir"] = tmpdir
        host.cfg["waveform_format"] = "CSV"  # 舊設定必須忽略
        tab = CaptureTab(host)
        host.driver = FakeDriver()
        host.driver_changed.emit(host.driver)
        pump(lambda: tab._max_points is not None)
        assert tab._max_points == 4_000_000
        assert set(tab._channel_checks) == {"CHAN1", "CHAN2"}
        # 案例 1：點數 1000 → HDF5 直接存成，檔案存在。
        tab.points_spin.setValue(1000)
        tab.name_edit.setText("case1")
        tab._on_start_clicked()
        pump(lambda: "已存檔" in tab.status_label.text())
        p1 = out_path(tab)
        assert p1.exists() and p1.suffix == ".h5", p1
        # `-m` 執行時本模組是 `__main__`；重新 import 會拿到另一份副本、globals
        # 不共用，要用 sys.modules[__name__] 才能改到正在跑的這一份。
        mod = sys.modules[__name__]
        original_msgbox = mod.QMessageBox
        mod.QMessageBox = _FakeBox
        try:
            # 案例 2：點數 200000 → HDF5 直接存成，不跳格式對話框。
            tab.status_label.setText("")
            tab.points_spin.setValue(200_000)
            tab.name_edit.setText("case2")
            tab._on_start_clicked()
            pump(lambda: "已存檔" in tab.status_label.text())
            p2 = out_path(tab)
            assert p2.suffix == ".h5", p2
            # 案例 3：點數超過 max_points() → 擋下，不呼叫 capture。
            calls_before = len(host.driver.calls)
            tab.points_spin.setValue(tab._max_points + 1)
            tab._on_start_clicked()
            assert len(host.driver.calls) == calls_before, "超過上限不該呼叫 capture"
        finally:
            mod.QMessageBox = original_msgbox
    print("tab_capture self-check OK")

if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _self_check()