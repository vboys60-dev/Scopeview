# Handoff：示波器截圖與波形擷取工具

目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖`（git repo，main）

## 現況

- T0–T11 全部完成，15 個模組自我檢查全過（Qt 模組加 `QT_QPA_PLATFORM=offscreen`；直接 `python3 -m scope_tool.<模組>`，不要加 `-I`）。
- 啟動：`python main.py`（在 `scope_tool/`）。連線列有「測試儀器（模擬）」按鈕，不接真機也能玩三個分頁。
- **InfiniiVision 已在真機驗證**：DSO-X 3014G，USB。截圖、直讀、CSV/HDF5、GUI 全流程都通過。
- **HD304MSO 已在真機驗證**（第五輪）：獨立 `HD3Driver`，截圖（含反相、格線偵測）、擷取、CSV/HDF5 通過。
- **Infiniium 完全沒上機**。還剩的項目見 `docs/真機驗證清單.md`（附逐輪實測紀錄）。

## 下一步

1. 拿 Infiniium（EXR/MXR/S）照 `docs/真機驗證清單.md` 跑：存檔轉取三步驟、Error 273、`:ACQuire:POINts:MAXimum?`、H5INt 電壓還原、`channels()` 1 秒 timeout 在 LAN 是否太短。
2. Infiniium 的 `bytes(np.array)` 損壞修正（截圖、轉取兩處）**沒上機測**。
3. 其他沒測：mDNS/LAN 搜尋、其他 InfiniiVision 型號（`model_prefixes` 只驗過 `DSO-X 3014G`）、4M 點以上、Roll 以外的邊角。

## InfiniiVision 真機踩到的坑（已修，勿回退）

- `:HARDcopy:AREA GRAT` 回 `-221`，**不要送**。格線區在 driver 用 QImage 裁 (16,52,642×400)，只在截圖為 800×512 時裁。
- `:ACQuire:POINts:MAXimum?` 不存在（-113 + 逾時）。`max_points()` 固定 4M，儀器自己截斷（3014G 實際只回 1M）。
- `bytes(np.array)` 會把每個位元組展開成 8 倍 → PNG 損壞。用 `astype(np.uint8).tobytes()`。
- `channels()` 探測不存在通道會逾時並留 `-113`：探測期間 timeout 1 秒，之後 `*CLS`。
- **從 STOP 重新 RUN 後，要等一整筆記錄（10×時基 + 約 0.5 秒）才能 STOP**，否則 `:WAVeform:PREamble?` 卡死。已 RUN 的畫面直接 STOP 沒事。driver 記 `_run_started`，補足 `10×時基+1` 秒；RUN 時間未知（手動按的）退回 1.5 秒。只量過 Auto 觸發。
- 沒有完整採集（Single/Normal 等觸發、剛 RUN 就手動 STOP）→ PREamble 5 秒逾時，device clear，丟明確 ScopeError。
- `*OPC?` 在 Single 等待觸發時不回應：`*CLS` 與 `_run_state` 還原一律用 `_write_nowait`，還原失敗不蓋掉原始例外。
- HDF5 attrs（XInc/XOrg…）在 **group** 上（契約 + Infiniium 轉取皆如此）。reader 先讀 group，退回 dataset。

## HD3（HD304MSO）與 3000G 的差異（已處理，勿回退）

- 沒有 `:OPERegister:CONDition?` → 用 `:RSTate?`（`_is_running()` 覆寫）。
- 沒有 INKSaver 與任何反轉指令 → 程式端 `invertPixels()`（使用者選定）。
- 截圖 1280×800，波形區隨結果面板變動 → 偵測 `#282828` 外框裁切，找不到回全圖。
- 沒有完整採集時 PREamble 回 `,,,,,,,,,`（不卡）→ 空 preamble 直接丟 ScopeError。
- `DATA?` 連 1000 點也要約 4 秒，擷取每次約 5.5 秒。`max_points()` 仍 4M（HD3 有 100M，未開放）。

## 已知小問題（未處理）

- CSV 時間欄 `.6e` 精度略損；CSV 通道名保留 `CH1`，HDF5 轉 `CHAN1`，不一致。
- 截圖頁區域選項仍標「(待驗證)」。
- 裁切座標只量過 3014G。

## 先讀

| 檔案 | 內容 |
|---|---|
| `RULES.md` | 硬規則：`contracts.py` 不准改、不准裝新套件（只有 pyvisa/pyqtgraph/numpy/h5py/zeroconf/PySide6，**沒有 Pillow**）、只用 PySide6 |
| `PLAN.md` | T1–T11 切分 |
| `scope_tool/contracts.py` | 凍結契約，含 CSV/HDF5 格式 |
| `CONTEXT.md` | 詞彙表 |
| `docs/示波器命令規格書.md` | 權威 SCPI 規格 |
| `docs/adr/` | 0001 PySide6；0002 搜尋用 VISA+mDNS；0003 HDF5 沿用 Keysight 結構 |
| `docs/reference/` | 原廠命令文件 |

## 環境

- Python 3.13、pyvisa（macOS `/Library/Frameworks/visa.framework`）、pyqtgraph、numpy、h5py；pyvisa-py 沒裝。
- PyQt5/PyQt6/PySide6 並存，進入點必須先 `os.environ["QT_API"]="pyside6"`。
- 實機：HD304MSO `USB0::0x2A8D::0x4704::MY66190300::INSTR`（輸入接地雜訊，50 ms/div、AUTO、只開 CH1）；`USB0::0x2A8D::0x1768::MY65520038::INSTR`（DSO-X 3014G，輸入是平的 DC，邊緣觸發不會發生；測 Single 用 `:TRIGger:EDGE:SOURce LINE`）。**測試改設定要記下並還原**（時基、觸發、模式、RUN）。

## 兩家系列差異

| | InfiniiVision | Infiniium |
|---|---|---|
| 反轉色 | `:HARDcopy:INKSaver ON` | `:DISPlay:DATA?` 帶 `INVert` |
| 截圖區域 | 一律全螢幕，driver 裁切 | 參數帶 `GRATicule` |
| 大點數 | 只能直讀 | `:DISK:SAVE` → `:DISK:GETFILE?` → `:DISK:DELete` |

新增示波器 = 加一個 `instruments/*.py` + `registry.py` 一行，UI 不動。

## 已定案（使用者確認，不要改）

- 搜尋：VISA 列表 + zeroconf + 手動 IP；`*IDN?` 判不出系列讓使用者手選一次。
- 截圖頁：檔名自動接時間戳，永不覆蓋；BMP/PNG、正常/反轉、全螢幕/格線區。
- 擷取頁：通道多選，單位是點數；CSV 且 ≥100k 點 → 對話框「改用 HDF5 / 照存」，不可偷改格式。
- RUN/STOP：擷取前記住、做完還原，不無條件 `:RUN`。「重新觸發」勾選預設關。
- 分析頁：離線；兩條垂直、兩條水平游標，讀值取原始資料；不做自動量測。
- 檔案支援：本工具 CSV/HDF5 + Keysight 原生 h5；面板 USB 的 CSV 不支援。
- I/O 全在 QThread；逾時截圖 15s、擷取 60s；Error 273 → 「請關閉遠端桌面」；不做取消。

## 不做

掃網段搜尋、自動量測、傳輸取消、面板 USB CSV 解析、自訂 HDF5 結構。

## 溝通

繁體中文，直白，不長篇大論。沒真機的路徑要說清楚只有紙上驗證。
