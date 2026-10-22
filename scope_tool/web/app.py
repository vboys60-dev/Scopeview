"""Web 版進入點：`python -m scope_tool.web.app [--browser]`。

server 跑在 daemon 執行緒；pywebview 視窗必須在主執行緒（macOS 限制）。
--browser：只開預設瀏覽器、不建視窗（此時 native_dialogs=false，前端改用 ui.prompt）。
"""

from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"  # 防 pywebview 退到 qt 時三套 Qt 綁定相撞（RULES 第 3 條）

import argparse
import sys
import time
import webbrowser

from scope_tool.web.api import Api
from scope_tool.web.jobs import Jobs
from scope_tool.web.server import Server


def _analysis():
    try:
        from scope_tool.web.analysis_api import Analysis  # L1b 提供
        return Analysis()
    except ImportError:
        return None  # 分析頁的呼叫會得到「分析服務尚未安裝」


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="示波器截圖工具（Web 版）")
    ap.add_argument("--browser", action="store_true", help="用預設瀏覽器開啟，不建立 pywebview 視窗")
    args = ap.parse_args(argv)

    jobs = Jobs()
    api = Api(jobs)
    srv = Server(api, _analysis(), jobs)
    srv.start()
    try:
        if args.browser:
            webbrowser.open(srv.url)
            print(f"已在瀏覽器開啟：{srv.url}（Ctrl+C 結束）")
            while True:
                time.sleep(3600)
        import webview

        window = webview.create_window("示波器截圖工具", srv.url, width=1360, height=860,
                                       min_size=(900, 600))
        api._attach_window(window)

        def on_closing() -> bool:
            """儀器工作進行中或仍連線時先確認；回 False 取消關閉。 # 待桌面環境驗證"""
            if jobs.busy:
                return bool(window.create_confirmation_dialog("確認離開", "儀器工作進行中，確定要關閉嗎？"))
            if api._drv is not None:
                return bool(window.create_confirmation_dialog("確認離開", "仍連線著儀器，確定要關閉嗎？"))
            return True

        window.events.closing += on_closing
        webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        api._shutdown()
        srv.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
