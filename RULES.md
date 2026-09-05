# 開發規則與界線

**寫任何一行程式碼前先讀完這份。違反硬規則的產出一律退回重做。**

先備知識：`CONTEXT.md`（術語）、`docs/示波器命令規格書.md`（權威 SCPI 規格）、`scope_tool/contracts.py`（契約）。

---

## 一、硬規則（不可協商）

1. **`scope_tool/contracts.py` 不准改。** 它是所有並行任務的唯一共同依賴，改它會讓別人的工作全部作廢。覺得非改不可 → 停下來回報，不要自己動。
2. **不准安裝新的第三方套件。** 可用的只有：`pyvisa`、`pyqtgraph`、`numpy`、`h5py`、`zeroconf`、`PySide6`，以及 Python 標準函式庫。缺什麼就用標準庫湊。
3. **Qt 綁定只能用 PySide6。** 機器上 PyQt5 / PyQt6 / PySide6 三套並存，混用會直接 crash。程式進入點必須在 `import pyqtgraph` **之前**執行 `os.environ["QT_API"] = "pyside6"`。任何模組都不准 `import PyQt5` 或 `import PyQt6`。
4. **UI 執行緒不准做 VISA I/O。** 所有 `driver.*()` 呼叫一律丟進 `ui/worker.py` 的 QThread，結果用 signal 回傳。UI 裡出現 `self.res.query(...)` 就是錯的。
5. **不准偷改使用者選的格式。** 選了 CSV 又要存 ≥100k 點 → 跳對話框給兩顆按鈕（「改用 HDF5」／「我知道，照存」），使用者按哪顆就做哪個。程式不准自己決定。
6. **檔名一律加時間戳，永不覆蓋。** 格式 `{name}_{YYYYMMDD}_{HHMMSS}.{ext}`。
7. **VISA 例外一律轉成 `ScopeError` 子類別再往外丟。** UI 只 catch `ScopeError`。SCPI Error 273 必須轉成 `RemoteDesktopError`。
8. **寫入型 SCPI 命令後要 `*OPC?`。** 逾時：截圖 15 秒、大檔傳輸 60 秒。逾時或失敗前，要清掉自己在儀器上留下的暫存檔（`:DISK:DELete`）。
9. **RUN/STOP 狀態要還原。** 擷取前記住原狀態，做完還原。不准無條件 `:RUN`。
10. **每個模組留一個 `if __name__ == "__main__":` 自我檢查**，用 `assert`。不要 pytest、不要 fixture、不要測試框架。執行方式一律 `python3 -m scope_tool.<模組路徑>`，必須印出 `xxx self-check OK` 且 exit code 0。

## 二、風格規則

- 註解、docstring、UI 文字全部**繁體中文**。變數與函式名用英文。
- 函式簽章寫型別註記。`from __future__ import annotations` 放檔案最上面。
- 不寫只有一個實作的介面、不寫工廠、不為固定值寫設定。`contracts.py` 裡的 `ScopeDriver` 是唯一允許的抽象，因為它真的有兩個以上實作。
- 檔案路徑一律用 `pathlib.Path`。SCPI 裡的 Windows 路徑一律用 raw string（`r"C:\temp\x.h5"`）。
- 單一檔案超過 300 行就是設計有問題，停下來回報。

## 三、明確不做（別自作主張加回去）

掃網段搜尋、自動量測（Vpp／頻率／上升時間）、傳輸中途取消、示波器面板存到 USB 的 CSV 解析、自訂的 HDF5 結構、非 Keysight 機型、多語系、深色主題、打包成 exe。

## 四、檔案擁有權（並行的關鍵）

**只准改自己 task 名下的檔案。** 需要別人的檔案時，照 `contracts.py` 的介面寫，不要去改對方的實作。

| 檔案 | 擁有者 |
|---|---|
| `scope_tool/contracts.py` | **凍結** |
| `scope_tool/config.py` | **凍結** |
| `scope_tool/instruments/fake.py` | **凍結** |
| `scope_tool/instruments/base.py`、`registry.py`、`discovery.py` | T1 |
| `scope_tool/instruments/infiniivision.py` | T2 |
| `scope_tool/instruments/infiniium.py` | T3 |
| `scope_tool/storage/writer.py` | T4 |
| `scope_tool/storage/reader.py` | T5 |
| `scope_tool/ui/main_window.py`、`ui/worker.py` | T6 |
| `scope_tool/ui/tab_analysis.py` | T7 |
| `scope_tool/ui/tab_screenshot.py` | T8 |
| `scope_tool/ui/tab_capture.py` | T9 |
| `scope_tool/main.py` | T10 |

## 五、交付前自我驗收

1. `python3 -m scope_tool.<你的模組>` 印出 OK、exit 0。
2. `git diff --stat`（或 `ls`）確認沒動到別人的檔案。
3. 沒真機的路徑，在 docstring 裡寫明 `# 待真機驗證`，不要假裝驗證過。
4. 回報格式：改了哪些檔、自我檢查結果、哪些行為只有紙上驗證。三行以內。
