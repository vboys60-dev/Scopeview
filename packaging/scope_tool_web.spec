# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec：Windows 單資料夾（onedir）／macOS .app。從專案根目錄執行：pyinstaller packaging/scope_tool_web.spec
# 待 Win10／macOS 實機驗證；CI 見 .github/workflows/build.yml
import sys
from PyInstaller.utils.hooks import collect_submodules

# 動態 import（importlib／__import__）PyInstaller 看不到，必須明列：解碼協定與儀器 driver
hidden = collect_submodules("webview.platforms") + ["pyvisa_py", "zeroconf"] \
    + [f"scope_tool.web.{n}_decode" for n in ("i3c", "i2c", "spi", "uart", "can", "espi", "usbpd")] \
    + ["scope_tool.instruments.infiniivision", "scope_tool.instruments.infiniium"]
if sys.platform == "win32":
    hidden += ["clr_loader", "pythonnet", "clr", "webview.platforms.edgechromium", "webview.platforms.winforms"]
# PySide6 必須保留（infiniivision 用 QImage）；只排除其他綁定與大型 Qt 模組
excludes = [
    "PyQt5", "PyQt6", "tkinter",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
]

a = Analysis(
    ["../scope_tool/web/app.py"],
    pathex=[".."],  # 專案根目錄，讓 scope_tool.* 可匯入
    datas=[("../scope_tool/web/static", "scope_tool/web/static")],
    hiddenimports=hidden,
    excludes=excludes,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="scope_tool_web", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="scope_tool_web")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="示波器截圖工具.app", bundle_identifier="com.scopeview.scopetool",
                 info_plist={"NSHighResolutionCapable": True, "CFBundleDisplayName": "示波器截圖工具"})
