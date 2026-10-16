"""截圖頁：選路徑/檔名/格式，按鈕觸發背景執行緒存圖，秀預覽與存檔路徑。

依 RULES.md 第 3 條，本模組是可能的程式進入點
（`python3 -m scope_tool.ui.tab_screenshot`），import pyqtgraph 之前
一定要先指定 Qt 綁定。這個頁面沒用到 pyqtgraph，但仍先設好環境變數，
避免其他模組先被 import 時挑錯 Qt 綁定。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_API", "pyside6")

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from scope_tool import config
from scope_tool.contracts import CaptureArea, ImageFormat, ScreenshotOptions
from scope_tool.storage.writer import write_screenshot
from scope_tool.ui.worker import Job


class ScreenshotTab(QWidget):
    """截圖頁：設定 → 觸發背景截圖 → 存檔 → 預覽。

    `main_window` 只需要具備 `driver`（`ScopeDriver | None`）屬性。
    """

    def __init__(self, main_window: QWidget | None = None) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._job: Job | None = None
        self.cfg = config.load()

        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI 組裝
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        grid = QGridLayout()

        self.dir_edit = QLineEdit()
        self.btn_browse = QPushButton("瀏覽…")
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        grid.addWidget(QLabel("存檔目錄"), 0, 0)
        grid.addWidget(self.dir_edit, 0, 1)
        grid.addWidget(self.btn_browse, 0, 2)

        self.name_edit = QLineEdit()
        grid.addWidget(QLabel("檔名前綴"), 1, 0)
        grid.addWidget(self.name_edit, 1, 1, 1, 2)

        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG", ImageFormat.PNG)
        self.format_combo.addItem("BMP", ImageFormat.BMP)
        grid.addWidget(QLabel("格式"), 2, 0)
        grid.addWidget(self.format_combo, 2, 1)

        self.color_combo = QComboBox()
        self.color_combo.addItem("正常色", False)
        self.color_combo.addItem("反轉色", True)
        grid.addWidget(QLabel("顏色"), 3, 0)
        grid.addWidget(self.color_combo, 3, 1)

        self.area_combo = QComboBox()
        self.area_combo.addItem("全螢幕", CaptureArea.FULL)
        self.area_combo.addItem("格線區", CaptureArea.GRATICULE)
        grid.addWidget(QLabel("擷取區域"), 4, 0)
        grid.addWidget(self.area_combo, 4, 1)

        root.addLayout(grid)

        self.btn_start = QPushButton("開始存圖")
        self.btn_start.clicked.connect(self._on_start_clicked)
        root.addWidget(self.btn_start)

        self.preview_label = QLabel("尚無預覽")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(240)
        root.addWidget(self.preview_label, stretch=1)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # config 進出
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        self.dir_edit.setText(self.cfg.get("screenshot_dir", ""))
        self.name_edit.setText(self.cfg.get("screenshot_name", "scope"))
        _select_by_data(self.format_combo, ImageFormat(self.cfg.get("image_format", "PNG")))
        _select_by_data(self.color_combo, bool(self.cfg.get("inverted", False)))
        _select_by_data(self.area_combo, CaptureArea(self.cfg.get("area", "full")))

    def _save_config(self) -> None:
        self.cfg["screenshot_dir"] = self.dir_edit.text()
        self.cfg["screenshot_name"] = self.name_edit.text()
        self.cfg["image_format"] = ImageFormat(self.format_combo.currentData()).value
        self.cfg["inverted"] = bool(self.color_combo.currentData())
        self.cfg["area"] = CaptureArea(self.area_combo.currentData()).value
        config.save(self.cfg)

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "選擇存檔目錄", self.dir_edit.text())
        if directory:
            self.dir_edit.setText(directory)

    def _on_start_clicked(self) -> None:
        driver = getattr(self._main_window, "driver", None)
        if driver is None:
            QMessageBox.information(self, "尚未連線", "請先連線儀器。")
            return
        if not self.dir_edit.text().strip():
            QMessageBox.information(self, "缺少目錄", "請先選擇存檔目錄。")
            return

        self._save_config()
        opts = ScreenshotOptions(
            image_format=ImageFormat(self.format_combo.currentData()),
            inverted=bool(self.color_combo.currentData()),
            area=CaptureArea(self.area_combo.currentData()),
        )
        self.btn_start.setEnabled(False)
        self.status_label.setText("存圖中…")

        self._job = Job(driver.screenshot, opts)
        self._job.done.connect(lambda data: self._on_screenshot_done(data, opts))
        self._job.failed.connect(self._on_screenshot_failed)
        self._job.start()

    def _on_screenshot_done(self, data: bytes, opts: ScreenshotOptions) -> None:
        try:
            path = write_screenshot(
                Path(self.dir_edit.text()), self.name_edit.text() or "scope", data, opts.image_format
            )
        except OSError as exc:
            self._on_screenshot_failed(f"存檔失敗：{exc}")
            return

        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.preview_label.width() or 640,
                self.preview_label.height() or 480,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled)
        self._last_pixmap = pixmap

        self.status_label.setText(f"已存檔：{path}")
        self.btn_start.setEnabled(True)

    def _on_screenshot_failed(self, message: str) -> None:
        self.btn_start.setEnabled(True)
        self.status_label.setText("存圖失敗")
        QMessageBox.critical(self, "存圖失敗", message)


def _select_by_data(combo: QComboBox, value: object) -> None:
    """把 combo 的目前選項設成 data 等於 value 的那一個，找不到就不動。"""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return


def _self_check() -> None:
    import tempfile
    import time

    from PySide6.QtWidgets import QApplication

    from scope_tool.instruments.fake import FakeDriver

    app = QApplication.instance() or QApplication([])

    class _FakeMainWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.driver = FakeDriver()

    main_window = _FakeMainWindow()
    tab = ScreenshotTab(main_window)

    with tempfile.TemporaryDirectory() as tmpdir:
        tab.dir_edit.setText(tmpdir)
        tab.name_edit.setText("selfcheck")

        tab._on_start_clicked()
        assert not tab.btn_start.isEnabled(), "存圖期間按鈕應該 disable"

        for _ in range(50):
            if tab.btn_start.isEnabled():
                break
            time.sleep(0.05)
            app.processEvents()

        assert tab.btn_start.isEnabled(), "存圖結束後按鈕應該恢復可按"
        assert "已存檔" in tab.status_label.text(), tab.status_label.text()

        files = list(Path(tmpdir).glob("selfcheck_*.png"))
        assert len(files) == 1, f"應該產生一個 PNG 檔：{files}"
        assert files[0].exists() and files[0].stat().st_size > 0

        assert tab.preview_label.pixmap() is not None
        assert not tab.preview_label.pixmap().isNull(), "預覽 QPixmap 不該是空的"

    # 區域選項固定顯示名稱，不附加驗證狀態標記。
    area_texts = [tab.area_combo.itemText(i) for i in range(tab.area_combo.count())]
    assert area_texts == ["全螢幕", "格線區"], area_texts
    assert all("待驗證" not in text for text in area_texts), area_texts

    print("tab_screenshot self-check OK")


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _self_check()
