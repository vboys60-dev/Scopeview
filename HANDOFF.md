# Handoff：示波器截圖與波形擷取工具

工作目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖`（非 git repo）

## 現況

**T0–T11 全部完成，實作階段結束。** `contracts.py` / `config.py` / `instruments/fake.py` /
`instruments/base.py` / `instruments/registry.py` / `instruments/discovery.py` /
`instruments/infiniivision.py` / `instruments/infiniium.py` / `storage/writer.py` / `storage/reader.py` /
`ui/worker.py` / `ui/main_window.py` / `ui/tab_analysis.py` / `ui/tab_screenshot.py` / `ui/tab_capture.py` /
`main.py`。全部 15 個模組的 `python3 -m scope_tool.<模組>` 自我檢查重跑過一遍，全部 exit 0
（Qt 相關模組要加 `QT_QPA_PLATFORM=offscreen` 環境變數才能在無頭環境跑）。
`QT_QPA_PLATFORM=offscreen python3 -m scope_tool.main` 也驗證過：主視窗開得起來、三個分頁都在、未連線時截圖/擷取頁 disable、分析頁 enable。

**`docs/真機驗證清單.md` 已產出**（T11），彙整了程式碼裡所有 `# 待真機驗證` 標記，13 列表格（含 PLAN.md 要求的六項高風險核心項目 + 7 項其他細節），每列都有檔案:行號、驗證方法、預期結果。

## 下一步：只剩真機驗證

程式碼已經全部寫完並過自我檢查，**沒有真機無法再往前推進**。下一步是拿到 InfiniiVision（3000G/3000X）
與 Infiniium（EXR/MXR/S）各至少一台，照 `docs/真機驗證清單.md` 逐項跑過，特別是標「最高風險」的
`:HARDcopy:AREA GRAT` 那項——驗不過要回頭改 `infiniivision.py` 的截圖設計。

各模組已知的「待真機驗證」項目（詳見各檔案 docstring/註解，T11 要彙整成表）：
- `base.py`：`_run_state()` 用 `:OPERegister:CONDition?` bit3 判斷 RUN/STOP 是推測寫法；`channels()` 假設通道編號從 1 連續、查到失敗就停。
- `infiniivision.py`：`:HARDcopy:AREA GRAT` 是否真的影響 `:DISPlay:DATA?`（**最高風險**，驗不過要改設計）。
- `infiniium.py`：Error 273 實際觸發訊息、`:ACQuire:POINts:MAXimum?` 實際回應、大點數存檔轉取與逾時、H5INt 電壓還原與群組名稱規則。
- `main_window.py`：`_connect_resource` 實際開啟 VISA 資源、查 `*IDN?` 並轉出 driver 的完整流程；`discovery.find_all` 由真實搜尋按鈕觸發的行為，都只驗證過用 `FakeDriver` 走的路徑。
- `tab_screenshot.py`：InfiniiVision 格線區裁切座標是否正確、與 MainWindow 實際串接 `driver_changed` 的行為。
- `tab_capture.py`：`channels()`/`max_points()`/`capture()` 在真實 VISA 硬體上的逾時與錯誤行為。
- `tab_analysis.py`：全程離線，沒有待真機驗證項目。

**開工前先讀 `RULES.md` 與 `PLAN.md`。** `PLAN.md` 把工作切成 T1–T11，標了依賴與可並行的線；
每個 task 是一段獨立對話的份量，開新對話只要貼 `RULES.md` + `scope_tool/contracts.py` + 該 task 區塊。

## 先讀這些（不要重複問使用者）

| 檔案 | 內容 |
|---|---|
| `RULES.md` | **硬規則與檔案擁有權**。動手前必讀 |
| `PLAN.md` | **任務切分 T1–T11**、依賴圖、每個 task 的驗收條件 |
| `scope_tool/contracts.py` | **凍結的契約層**，含 CSV/HDF5 格式規格 |
| `CONTEXT.md` | 詞彙表。系列／截圖區域／反轉色／直讀／存檔轉取／游標等術語已定名 |
| `docs/示波器命令規格書.md` | **權威 SCPI 規格**。命令面已定案，照做即可 |
| `docs/adr/0001` | Qt 綁定鎖 PySide6 |
| `docs/adr/0002` | 搜尋用 VISA + mDNS，不掃網段 |
| `docs/adr/0003` | 自產 HDF5 沿用 Keysight 原生結構 |
| `docs/reference/` | 六份原廠命令文件，依 infiniivision-* / infiniium-* 命名 |

## 環境事實（已驗證）

- Python 3.13.9；pyvisa 1.16.2（走 macOS `/Library/Frameworks/visa.framework`）、pyqtgraph 0.14.0、numpy 2.3.5、h5py 3.15.1 全部已裝。pyvisa-py 沒裝。
- PyQt5 / PyQt6 / PySide6 **三套並存**，混用會 crash → 進入點必須先 `os.environ["QT_API"]="pyside6"` 再 import pyqtgraph。
- 目前沒接示波器，`list_resources()` 只回 `ASRL1::INSTR`、`ASRL2::INSTR`。**開發階段沒有真機可測**。

## 待實作的檔案結構

```
scope_tool/
├─ main.py                  # 設 QT_API=pyside6，開視窗
├─ config.py                # 設定 JSON 存家目錄：上次路徑/格式/點數/儀器清單
├─ instruments/
│  ├─ discovery.py          # VISA list_resources + zeroconf(_hislip._tcp/_lxi._tcp/_scpi-raw._tcp) + 手動 IP
│  ├─ base.py               # ScopeDriver 抽象：screenshot() / capture_waveform()
│  ├─ infiniivision.py      # 3000G/3000X
│  ├─ infiniium.py          # EXR/MXR/S
│  └─ registry.py           # *IDN? 型號 → driver 對應表
├─ storage/
│  ├─ writer.py             # 直讀結果 → CSV / HDF5（Keysight 同構）
│  └─ reader.py             # 統一 loader：CSV / HDF5 / Keysight 原生 h5
├─ ui/
│  ├─ main_window.py        # 連線列 + 三分頁
│  ├─ tab_screenshot.py
│  ├─ tab_capture.py
│  ├─ tab_analysis.py
│  └─ worker.py             # 所有 VISA I/O 的 QThread
```

新增示波器 = 加一個 `instruments/*.py` + `registry.py` 加一行，UI 不動。

## 兩家系列的實質差異（driver 分家的全部理由）

| | InfiniiVision (3000G/3000X) | Infiniium (EXR/MXR/S) |
|---|---|---|
| 反轉色 | `:HARDcopy:INKSaver ON` | `:DISPlay:DATA?` 帶 `INVert` |
| 截圖區域 | 先設 `:HARDcopy:AREA GRAT`（**待真機驗證**，文件未明說 `:DISPlay:DATA?` 是否跟隨） | 參數直接帶 `GRATicule` |
| 大點數波形 | **只能直讀**（`:SAVE:*` 只寫面板 USB，無取回命令），上限 4M 類比 / 8M 數位 | `:DISK:SAVE` → `:DISK:GETFILE?` → `:DISK:DELete` |

## 已定案的行為（使用者確認過，不要再改）

- **搜尋**：VISA 列表 + zeroconf 掃描按鈕 + 手動 IP。`*IDN?` 自動判系列，判不出來讓使用者手選一次並寫入設定。
- **截圖頁**：路徑 + 檔名，檔名自動接時間戳 `name_YYYYMMDD_HHMMSS`，永不覆蓋。BMP/PNG、正常/反轉、全螢幕/格線區。存完顯示在畫面上。
- **波形擷取頁**：通道多選。長度單位是**點數**，連線後查 `:ACQuire:POINts:MAXimum?` 擋超限。選 CSV 又 ≥100k 點 → 跳對話框「改用 HDF5 / 照存」兩顆按鈕，**不可偷偷改格式**。
- **RUN/STOP**：擷取前記住原狀態，做完還原，不要無條件 `:RUN`。「擷取前重新觸發單次擷取」勾選框預設**關**。
- **分析頁**：離線可用。兩條垂直游標（t1/t2/ΔT/1÷ΔT）+ 兩條水平（v1/v2/ΔV），數值即時顯示。縮放平移用 pyqtgraph 內建。大檔 `setDownsampling(auto=True, mode='peak')` + `setClipToView(True)`，**游標讀值一律取原始資料**。自動量測（Vpp/頻率/上升時間）不做。
- **檔案支援**：本工具的 CSV/HDF5 + Keysight 原生 h5。示波器面板存到 USB 的 CSV **不支援**（header 格式各機型不同，等真的拿到檔再加）。
- **I/O**：全部丟 QThread。逾時截圖 15s、大檔 60s，逾時後清儀器暫存檔。認出 **Error 273 → 顯示「請關閉遠端桌面」**。中途取消功能不做。

## 明確不做（別自作主張加回去）

掃網段搜尋、自動量測、傳輸取消、面板 USB CSV 解析、自訂 HDF5 結構。

## 溝通方式

使用者要求**繁體中文、簡單直白說人話**。不要長篇大論。

## Suggested skills

- `test-driven-development` — driver 層的 SCPI 命令組裝與 PREamble 換算適合先寫測試（可用 fake VISA resource，沒真機也能測）
- `verification-before-completion` — 沒真機，交付前務必說清楚哪些路徑只有紙上驗證
- `domain-modeling` — 實作中冒出新術語時更新 `CONTEXT.md`；出現新的難反轉決定時加 ADR（編號從 0004 起）
