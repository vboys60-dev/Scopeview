# 統一使用 PySide6 作為唯一 Qt 綁定

開發機上同時裝了 PyQt5、PyQt6 與 PySide6，三套在同一個 process 裡混用會直接讓程式當掉，而 pyqtgraph 預設會自己挑一套，挑到哪套不保證。我們選 PySide6：它是唯一查得到明確版號（6.9.2）且授權為 LGPL 的一套，換掉的成本是全專案所有 Qt import。程式進入點必須在 import pyqtgraph 之前設定 `QT_API=pyside6`，不讓 pyqtgraph 自行決定。
