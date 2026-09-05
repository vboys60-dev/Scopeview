"""示波器截圖工具的進入點。

QApplication 初始化、主視窗啟動、事件迴圈。
"""

from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"  # 必須在任何 pyqtgraph / Qt import 之前

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from scope_tool.ui.main_window import MainWindow


def main() -> None:
    """啟動應用程式的主視窗。"""
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


def _self_check() -> None:
    """自我檢查：驗證 MainWindow 能正常初始化並有三個分頁。"""
    app = QApplication.instance() or QApplication([])
    w = MainWindow()

    # 驗證三個分頁都存在
    assert hasattr(w, "tab_screenshot"), "截圖分頁不存在"
    assert hasattr(w, "tab_capture"), "擷取分頁不存在"
    assert hasattr(w, "tab_analysis"), "分析分頁不存在"

    # 驗證 tabs 中實際有三個分頁
    assert w.tabs.count() == 3, f"應有 3 個分頁，實際 {w.tabs.count()}"

    # 驗證初始狀態：未連線
    assert not w.tab_screenshot.isEnabled(), "未連線時截圖分頁應 disable"
    assert not w.tab_capture.isEnabled(), "未連線時擷取分頁應 disable"
    assert w.tab_analysis.isEnabled(), "分析分頁應永遠 enable"

    def finish() -> None:
        """自動關閉視窗並結束。"""
        app.quit()

    QTimer.singleShot(0, finish)
    app.exec()

    print("main self-check OK")


if __name__ == "__main__":
    # 判斷是否為自我檢查模式（offscreen 環境）
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        _self_check()
    else:
        main()
