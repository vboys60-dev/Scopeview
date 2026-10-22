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
            """不可在此呼叫對話框（macOS 處理函式在主執行緒，會死鎖）。
            改設 window.confirm_close，由 pywebview 在 closing 事件之後自己確認
            （cocoa／winforms／qt／gtk 皆在事件後才讀此旗標）。 # 待桌面環境驗證"""
            window.confirm_close = jobs.busy or api._drv is not None
            return True  # 不是 False（False＝取消關閉）

        window.events.closing += on_closing
        webview.settings["ALLOW_DOWNLOADS"] = True  # 截圖頁「另存」需要
        webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        api._shutdown()
        srv.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
