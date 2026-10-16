# Handoff：示波器截圖與波形擷取工具

目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖`（git repo，main，無 remote）

## 現況（2026-10-16）

- 已 commit（`8d80d84`），工作區乾淨。
- 已上機：DSO-X 3014G（**舊擷取規則**下驗證）、HD304MSO、MXR254B（Infiniium 首次）。3000T、EXR、S 系列沒上機。逐輪紀錄在 `docs/真機驗證清單.md`。
- 自我檢查：`for m in instruments.base instruments.infiniivision instruments.infiniium instruments.fake instruments.registry storage.writer storage.reader ui.tab_capture ui.tab_screenshot ui.main_window contracts; do QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -m scope_tool.$m; done`（系統 `python3` 沒有 numpy）。
- 啟動：`python main.py`（在 `scope_tool/`），有「測試儀器（模擬）」按鈕。

## 下一步

1. 同步文件：`RULES.md` 第 5 條（CSV 對話框）、第 9 條（RUN/STOP 還原）已被下方定案取代但**尚未改**；`docs/adr/0003` 補「存原始整數」與「Infiniium 原生檔不扣 YReference」。
2. 上機：HD304 重測四通道 100M、`:DIGitize` 四通道（上次 USB 斷線；接上先確認設定已還原）；3014G 在新規則下重驗擷取；MXR 補 Error 273（遠端桌面）、LAN、慢時基、GUI 全流程；3000T。
3. CSV 匯出規則與使用者討論。

## 擷取規則（使用者定案，覆蓋舊規則）

- **示波器只因「使用者手動」或「按下擷取」而停止。** 擷取時若在 RUN：等 `10×時基+1` 秒再 `:STOP`，讀完**維持 STOP**。原本 STOP 直接讀。`retrigger` → `:DIGitize`。
- **一律存 HDF5**；CSV 匯出之後再議（reader 仍讀 CSV，writer 的 CSV 函式保留）。
- **HDF5 存原始整數**：uint16 + group attrs `YInc/YOrg/YReference`；無 preamble 才存 float64 電壓。
- `max_points()`：HD3 100M、3000G 4M、Infiniium 查 `:ACQuire:POINts:MAXimum?`（MXR 200M）。
- **Infiniium 一律存檔轉取整筆記錄**（`:DISK:SAVE ALL` → `GETFILE?` → `DELete`），「點數」只當上限：記錄點數 > 設定點數就丟 ScopeError，不改使用者記憶體深度。存檔維持 `ALL`，原生檔含所有顯示中通道。

## 真機踩到的坑（已修，勿回退）

- pyvisa `query_binary_values` 傳輸 > 約 64 MiB 會卡死：`_query_binary` 手動分段讀 IEEE 488.2 block（每段 4 MiB）。
- InfiniiVision `:HARDcopy:AREA GRAT` 回 `-221`，**不要送**。3014G 格線區由 driver 用 QImage 裁 (16,52,642×400)，只在 800×512 時裁。
- `:ACQuire:POINts:MAXimum?` 在 InfiniiVision/HD3 不存在（-113 + 逾時）。
- `bytes(np.array)` 會把每個位元組展開成 8 倍 → 檔案損壞。
- `channels()` 探測不存在通道會逾時並留 `-113`：探測期間 timeout 1 秒，之後 `*CLS`。
- 沒有完整採集（Single/Normal 等觸發、剛 RUN 就 STOP）：3000G PREamble 卡死（5 秒逾時 + device clear），HD3 回空欄位；都丟明確 ScopeError。HD3 無法查採集是否完成。
- `*OPC?` 在 Single 等待觸發時不回應：`*CLS` 用 `_write_nowait`。
- HDF5 attrs 在 **group** 上；reader 先讀 group，退回 dataset。
- Keysight 原生 H5INt：`YReference=1` **不能扣**，V = raw×YInc+YOrg。本工具寫的檔（有 `/ScopeTool`）才扣。
- HD3：沒有 `:OPERegister:CONDition?`（用 `:RSTate?`）、沒有 INKSaver（程式端 `invertPixels()`）、截圖波形區隨面板變動（偵測 `#282828` 外框）。
- MXR：沒有 `:WAVeform:POINts <n>`/`:WAVeform:UNSigned`、PREamble 24 欄 → 直讀路線已刪。

## 已知小問題（未處理）

- Infiniium Error 273 只有紙上驗證。
- HD3 `DATA?` 連 1000 點也要約 4 秒。
- 4 通道 × 100M 記憶體約 7 GB 以上，再大要改契約（凍結）。
- CSV 時間欄 `.6e` 精度略損；CSV 通道名 `CH1` vs HDF5 `CHAN1` 不一致（待 CSV 規則一起處理）。
- 截圖頁區域選項仍標「(待驗證)」。

## 先讀

| 檔案 | 內容 |
|---|---|
| `RULES.md` | 硬規則（第 5、9 條已被上方定案取代）：`contracts.py` 不准改、不准裝新套件（**沒有 Pillow**）、只用 PySide6 |
| `scope_tool/contracts.py` | 凍結契約，含 CSV/HDF5 格式 |
| `docs/真機驗證清單.md` | 逐輪實測紀錄 |
| `docs/示波器命令規格書.md`、`docs/reference/` | SCPI 規格與原廠文件 |
| `docs/adr/` | 0001 PySide6；0002 搜尋；0003 HDF5 沿用 Keysight 結構 |

## 環境

- `/opt/anaconda3/bin/python3`（3.13）、pyvisa（macOS `/Library/Frameworks/visa.framework`）、numpy、h5py、PySide6；進入點先 `os.environ["QT_API"]="pyside6"`。
- 實機（輸入皆接地雜訊；**測試改設定要記下並還原**）：

| 機台 | VISA | 使用者設定 |
|---|---|---|
| HD304MSO | `USB0::0x2A8D::0x4704::MY66190300::INSTR` | RUN、100 µs/div、AUTO、只開 CH1、5 V/div |
| DSO-X 3014G | `USB0::0x2A8D::0x1768::MY65520038::INSTR` | 5 ms/div、AUTO、RUN（輸入平 DC，測 Single 用 LINE 觸發） |
| MXR254B | `USB0::0x2A8D::0x9007::MY63310109::INSTR` | RUN、100 ns/div、AUTO、RTIM、記憶體深度 AUTO、只開 CH1、5 V/div |

- Codex：`codex exec --sandbox workspace-write ... </dev/null`（**一定要 `</dev/null`**）。Codex 沙箱連不到 VISA，實機測試由 Claude 執行。

## 已定案（仍有效）

- 搜尋：VISA 列表 + zeroconf + 手動 IP；`*IDN?` 判不出系列讓使用者手選一次。
- 截圖頁：檔名自動接時間戳，永不覆蓋；BMP/PNG、正常/反轉、全螢幕/格線區。HD3 反轉為程式端反相、格線區自動偵測。
- 擷取頁：通道多選，單位是點數，只存 HDF5。「重新觸發」預設關。
- 分析頁：離線；兩條垂直、兩條水平游標，讀值取原始資料；不做自動量測。
- I/O 全在 QThread；逾時截圖 15s、擷取每個 VISA 操作 60s；Error 273 → 「請關閉遠端桌面」；不做取消。

## 不做

掃網段搜尋、自動量測、傳輸取消、面板 USB CSV 解析、自訂 HDF5 結構。

## 溝通

繁體中文，直白，不長篇大論。沒真機的路徑要說清楚只有紙上驗證。改程式交 Codex，Opus 審。
