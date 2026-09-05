"""主視窗：連線列 + 三個分頁（截圖／擷取／分析）。

連線列負責搜尋儀器、選擇資源、連線／斷線；所有 VISA I/O
（搜尋、開啟資源、連線）都透過 `worker.Job` 丟到背景執行緒，
不准在這個檔案裡直接呼叫會卡住 UI 的東西。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_API", "pyside6")  # 必須在 import pyqtgraph 之前

from typing import Any

import pyvisa
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scope_tool import config
from scope_tool.contracts import FoundInstrument, ScopeDriver
from scope_tool.instruments import discovery, registry
from scope_tool.ui.worker import Job

# T2/T3 的具體 driver 模組只需要被 import 一次就會呼叫 registry.register()。
# 還沒寫出來時（並行開發中）容忍它們不存在，不要讓主視窗開不起來。
try:
    from scope_tool.instruments import infiniivision as _infiniivision  # noqa: F401
except Exception:
    pass
try:
    from scope_tool.instruments import infiniium as _infiniium  # noqa: F401
except Exception:
    pass


def _make_placeholder(text: str) -> QWidget:
    """分頁模組還沒寫出來時的佔位頁。"""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.addWidget(QLabel(text))
    return w


def _connect_resource(resource: str, cfg: dict[str, Any]) -> ScopeDriver:
    """在背景執行緒跑：開啟 VISA 資源、查 *IDN?、依型號找出對應 driver。

    # 待真機驗證：真機的 *IDN? 格式、開啟資源的逾時行為都沒有真機可測。
    """
    rm = pyvisa.ResourceManager()
    res = rm.open_resource(resource)
    res.timeout = 5000
    try:
        idn = res.query("*IDN?")
        override_name = cfg.get("series_overrides", {}).get(registry.parse_idn(idn)[1])
        override = None
        if override_name:
            from scope_tool.contracts import Series

            override = Series(override_name)
        return registry.driver_for(res, idn, override=override)
    except Exception:
        res.close()
        raise


class MainWindow(QMainWindow):
    """整個工具的主視窗。分頁從 `self.driver` 取得目前連線的儀器。"""

    #: 連線／斷線時發，帶目前的 driver（斷線時是 None）。
    driver_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("示波器截圖工具")
        self.driver: ScopeDriver | None = None
        self.cfg = config.load()
        self._search_job: Job | None = None
        self._connect_job: Job | None = None

        self._build_ui()
        self._refresh_combo([])
        self._set_connected_ui(False)

    # ------------------------------------------------------------------
    # UI 組裝
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)

        bar = QHBoxLayout()
        self.btn_search = QPushButton("搜尋")
        self.combo = QComboBox()
        self.combo.setMinimumWidth(280)
        self.btn_manual = QPushButton("手動輸入 IP")
        self.btn_connect = QPushButton("連線")
        self.status_label = QLabel("未連線")

        bar.addWidget(self.btn_search)
        bar.addWidget(self.combo, stretch=1)
        bar.addWidget(self.btn_manual)
        bar.addWidget(self.btn_connect)
        bar.addWidget(self.status_label)
        outer.addLayout(bar)

        self.btn_search.clicked.connect(self._on_search_clicked)
        self.btn_manual.clicked.connect(self._on_manual_clicked)
        self.btn_connect.clicked.connect(self._on_connect_clicked)

        self.tabs = QTabWidget()
        self._build_tabs()
        outer.addWidget(self.tabs, stretch=1)

        self.setCentralWidget(central)

    def _build_tabs(self) -> None:
        """用延遲 import 掛上三個分頁；模組還不存在就放佔位頁。"""
        try:
            from scope_tool.ui.tab_screenshot import ScreenshotTab

            self.tab_screenshot = ScreenshotTab(self)
        except Exception:
            self.tab_screenshot = _make_placeholder("尚未實作")

        try:
            from scope_tool.ui.tab_capture import CaptureTab

            self.tab_capture = CaptureTab(self)
        except Exception:
            self.tab_capture = _make_placeholder("尚未實作")

        try:
            from scope_tool.ui.tab_analysis import AnalysisTab

            self.tab_analysis = AnalysisTab(self)
        except Exception:
            self.tab_analysis = _make_placeholder("尚未實作")

        self.tabs.addTab(self.tab_screenshot, "截圖")
        self.tabs.addTab(self.tab_capture, "擷取")
        self.tabs.addTab(self.tab_analysis, "分析")

    def _on_search_clicked(self) -> None:
        self.btn_search.setEnabled(False)
        self.status_label.setText("搜尋中…")
        manual = list(self.cfg.get("manual_resources", []))
        self._search_job = Job(discovery.find_all, manual, timeout=3.0)
        self._search_job.done.connect(self._on_search_done)
        self._search_job.failed.connect(self._on_search_failed)
        self._search_job.start()

    def _on_search_done(self, found: list[FoundInstrument]) -> None:
        self.btn_search.setEnabled(True)
        self.status_label.setText(f"找到 {len(found)} 台" if found else "沒有找到儀器")
        self._refresh_combo(found)

    def _on_search_failed(self, message: str) -> None:
        self.btn_search.setEnabled(True)
        self.status_label.setText("搜尋失敗")
        QMessageBox.warning(self, "搜尋失敗", message)

    def _refresh_combo(self, found: list[FoundInstrument]) -> None:
        self.combo.clear()
        for item in found:
            self.combo.addItem(item.label, userData=item.resource)

    def _on_manual_clicked(self) -> None:
        ip, ok = QInputDialog.getText(self, "手動輸入 IP", "儀器 IP 位址：")
        ip = ip.strip()
        if not ok or not ip:
            return
        resource = f"TCPIP0::{ip}::inst0::INSTR"
        self.combo.addItem(ip, userData=resource)
        self.combo.setCurrentIndex(self.combo.count() - 1)
        manual = list(self.cfg.get("manual_resources", []))
        if ip not in manual:
            manual.append(ip)
            self.cfg["manual_resources"] = manual

    def _on_connect_clicked(self) -> None:
        if self.driver is not None:
            self._disconnect()
            return

        resource = self.combo.currentData()
        if not resource:
            QMessageBox.information(self, "尚未選擇儀器", "請先搜尋或手動輸入一台儀器。")
            return

        self.btn_connect.setEnabled(False)
        self.status_label.setText("連線中…")
        self._connect_job = Job(_connect_resource, resource, self.cfg)
        self._connect_job.done.connect(self._on_connect_done)
        self._connect_job.failed.connect(self._on_connect_failed)
        self._connect_job.start()

    def _on_connect_done(self, driver: ScopeDriver) -> None:
        self.driver = driver
        self.cfg["last_resource"] = self.combo.currentData() or ""
        self._set_connected_ui(True)
        self.status_label.setText(f"已連線：{driver.model}")
        self.btn_connect.setEnabled(True)
        self.driver_changed.emit(self.driver)

    def _on_connect_failed(self, message: str) -> None:
        self.btn_connect.setEnabled(True)
        self.status_label.setText("連線失敗")
        QMessageBox.warning(self, "連線失敗", message)

    def _disconnect(self) -> None:
        if self.driver is not None:
            try:
                if self.driver.res is not None:
                    self.driver.res.close()
            except Exception:
                pass
        self.driver = None
        self._set_connected_ui(False)
        self.status_label.setText("未連線")
        self.driver_changed.emit(None)

    def _set_connected_ui(self, connected: bool) -> None:
        """未連線時截圖頁與擷取頁整頁 disable；分析頁永遠可用。"""
        self.tab_screenshot.setEnabled(connected)
        self.tab_capture.setEnabled(connected)
        self.tab_analysis.setEnabled(True)
        self.btn_connect.setText("斷線" if connected else "連線")

    def closeEvent(self, event: Any) -> None:  # noqa: N802 — Qt 覆寫方法命名固定
        config.save(self.cfg)
        super().closeEvent(event)


def _self_check() -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from scope_tool.instruments.fake import FakeDriver

    app = QApplication.instance() or QApplication([])
    win = MainWindow()

    # 開機時應該是未連線狀態：截圖／擷取頁 disable，分析頁 enable。
    assert not win.tab_screenshot.isEnabled() and not win.tab_capture.isEnabled()
    assert win.tab_analysis.isEnabled()

    received: list[Any] = []
    win.driver_changed.connect(lambda d: received.append(d))

    def inject_fake_driver() -> None:
        # 繞過真正的 VISA 連線，直接模擬 Job.done 的結果。
        win._on_connect_done(FakeDriver())
        app.processEvents()
        assert win.driver is not None
        assert win.tab_screenshot.isEnabled() and win.tab_capture.isEnabled()
        assert win.tab_analysis.isEnabled() and win.btn_connect.text() == "斷線"
        assert len(received) == 1 and isinstance(received[0], FakeDriver)

        win._disconnect()
        app.processEvents()
        assert win.driver is None
        assert not win.tab_screenshot.isEnabled() and not win.tab_capture.isEnabled()
        assert len(received) == 2 and received[1] is None
        app.quit()

    QTimer.singleShot(0, inject_fake_driver)
    app.exec()

    print("main_window self-check OK")


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _self_check()
