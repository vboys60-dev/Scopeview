# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec：Windows 單資料夾（onedir）。從專案根目錄執行：pyinstaller packaging/scope_tool_web.spec
# 待 Win10 實機驗證
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("webview.platforms") + [
    "clr_loader", "pythonnet", "clr", "webview.platforms.edgechromium", "webview.platforms.winforms",
    "pyvisa_py", "zeroconf",
]
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
