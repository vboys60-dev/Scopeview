# Handoff：示波器截圖與波形擷取工具

目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖`（git repo，main，無 remote）

## 現況（2026-10-16 暫停點）

- **工作區有未 commit 的改動**（Codex 第三輪，Opus 已審、自我檢查全過、HD304 實機驗證見下）：新擷取規則、HDF5 存原始整數、手動 block 讀取、HD3 開放 100M 點、擷取頁只存 HDF5。改了 `base.py`、`infiniivision.py`、`infiniium.py`、`writer.py`、`reader.py`、`tab_capture.py`、`contracts.py`（只改 docstring 一行）。
- 已驗證機台：DSO-X 3014G（第一～四輪，**舊規則**下驗證）、HD304MSO（第五輪＋本輪）、**MXR254B（第六輪，Infiniium 首次上機）**。3000T、EXR、S 系列沒上機。
- 第六輪（MXR）另改了 `infiniium.py`（刪直讀、一律存檔轉取、點數當上限、H5INt 不扣 YReference）與 `reader.py`（只有本工具檔才扣 YReference），同樣未 commit。
- 自我檢查：`for m in instruments.base instruments.infiniivision instruments.infiniium instruments.fake instruments.registry storage.writer storage.reader ui.tab_capture ui.tab_screenshot ui.main_window contracts; do QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -m scope_tool.$m; done`（系統 `python3` 沒有 numpy，要用 Anaconda）。
- 啟動：`python main.py`（在 `scope_tool/`），有「測試儀器（模擬）」按鈕。

## 本輪新定案（使用者確認，覆蓋舊規則）

- **示波器只會因「使用者手動」或「按下擷取」而停止。** 擷取時若在 RUN：等 `10×時基+1` 秒（一整筆）再 `:STOP`，讀完**維持 STOP，不還原 RUN**。原本 STOP 就直接讀。`retrigger` 照舊 `:DIGitize`。使用者通常在 STOP 狀態下擷取。
- **擷取一律存 HDF5**，擷取頁已拿掉格式選單與 CSV ≥100k 對話框。CSV 匯出規則**之後再議**（reader 仍讀 CSV，writer 的 CSV 函式保留）。
- **HDF5 存原始整數**：`Channel NData` 存 uint16，group attrs `YInc/YOrg/YReference` 換算；無 preamble（例如由 CSV 讀回）才存 float64 電壓。reader 遇整數 dataset 自動換算（Keysight 原生整數 h5 也因此讀對）。
- HD3 記憶體 100M 點，`max_points()` = 100M（3000G 仍 4M）。
- **Infiniium 一律存檔轉取整筆記錄，「點數」只當上限**：記錄點數（`:WAVeform:POINts?`）> 設定點數就丟 ScopeError，不改使用者的記憶體深度。直讀路線已刪（MXR 沒有 `:WAVeform:POINts <n>`/`UNSigned`、PREamble 24 欄）。
- **Infiniium 存檔維持 `ALL`（使用者定案）**：原生檔含所有顯示中通道（只選 CH1 但 CH2 開著，檔案也有 CH2），保留 Keysight 原生格式。

## 下一步

1. **commit 本輪改動**（使用者尚未下令；commit 前看一眼 `git diff`）。
2. 同步文件：`RULES.md` 第 5 條（CSV 對話框）、第 9 條（RUN/STOP 還原）已被新定案取代但**尚未改**；`docs/adr/0003` 補「存原始整數」；`docs/真機驗證清單.md` 補本輪紀錄（實測數字在下方）。
3. 3014G 需在**新規則**下重驗擷取（舊規則才驗過）；3000T 上機；MXR 補 Error 273（遠端桌面）、LAN、慢時基、GUI 全流程。
4. CSV 匯出規則與使用者討論。
5. 離線重播測試可用 scratchpad 存下的 HD3 原始 block（見「離線資料」），但 scratchpad 是 session 暫存，要保留需搬進 repo 外的固定位置。

## HD3 實測重點（本輪）

- **pyvisa `query_binary_values` 傳輸量 > 約 64 MiB 會卡死到逾時**（WORD 50M = 100 MB 卡 311 秒），儀器本身沒問題。`_query_binary` 已改為手動讀 IEEE 488.2 block（每段 4 MiB，`read_bytes`），**勿回退**。
- 手動 block：100M 點 WORD 23 秒、BYTE 15 秒；四通道全開時每通道仍 100M 點，各約 23 秒。
- 要求點數會被取成 100M 的整數分之一（要 40M 回 33,333,333）。
- HD3 沒有分段讀取指令（`:WAVeform:STARt` 等皆無），沒有 `:ADER?`，`:ACQuire:COMPlete?` 恆 100：**無法查採集是否完成**。採集中途 STOP，那一筆直接作廢、事後不補（PREamble 回 `,,,,,,,,,`）。
- 新規則流程實測：剛 RUN 後擷取，0.5 s/div 等 6.2 秒、1 s/div 等 11.2 秒，資料完整，結束為 STOP。
- `:DIGitize` 四通道 100M（50 ms/div）0.9 秒完成，結束為 STOP。
- 記憶體：每通道 time+voltage float64 各 800 MB（契約規定），多通道已共用 time 陣列。機器 24 GiB。

### 本輪新程式（未 commit 版）在 HD304 實機端到端結果

| 案例 | 結果 |
|---|---|
| RUN 中擷取 CH1 1000 點 | 通過：5.5 秒，HDF5 dtype uint16，讀回電壓誤差 0，結束為 STOP |
| STOP 中擷取 CH1 100M 點 | 通過：擷取 23.9 秒、寫檔 0.5 秒、讀回 0.3 秒，檔案 200 MB，誤差 0，結束為 STOP |
| 四通道各 100M 點 | **未完成**：讀取中 USB 斷線（`VI_ERROR_IO` → `VI_ERROR_CONN_LOST`），研判為使用者拔除設備，不是程式錯誤，但**仍需重測** |
| `:DIGitize` 四通道 1000 點 | 未執行（斷線） |

**斷線導致還原沒跑：HD304 可能停在 CH1–CH4 全開、50 ms/div、STOP。** 下次接上先還原成使用者設定（RUN、100 µs/div、AUTO、只開 CH1、5 V/div）。

### 離線資料（session 暫存，可能已被清除）

`/private/tmp/claude-501/-Users-lianshi-Desktop-claude-cowork------/ab6ca321-45d0-496a-8d24-7dd1711a83db/scratchpad/` 下：`hd3_capture/`（HD3 原始 IEEE block：CH1 1k／100M WORD、四通道 1k、:DIGitize 後 1k、截圖，各附 `.preamble`；`log.jsonl` 為逐步紀錄）、`hd3_capture.py`（收集腳本）、`hd3_e2e.py`（端到端腳本，下次接機可直接重跑：`/opt/anaconda3/bin/python3 -u hd3_e2e.py <輸出資料夾>`）、`hd3_test.py`（多通道＋慢時基補測腳本，Codex 寫）。右上角面板讀的 `codex_status.json` 也在這裡，session 結束後面板會顯示空清單。

## 真機踩到的坑（已修，勿回退）

- InfiniiVision `:HARDcopy:AREA GRAT` 回 `-221`，**不要送**。3014G 格線區 driver 用 QImage 裁 (16,52,642×400)，只在 800×512 時裁。
- `:ACQuire:POINts:MAXimum?` 在 InfiniiVision/HD3 不存在（-113 + 逾時）。
- `bytes(np.array)` 會把每個位元組展開成 8 倍 → 檔案損壞。
- `channels()` 探測不存在通道會逾時並留 `-113`：探測期間 timeout 1 秒，之後 `*CLS`。
- 沒有完整採集（Single/Normal 等觸發、剛 RUN 就 STOP）：3000G 是 PREamble 卡死（5 秒逾時 + device clear），HD3 是回空欄位；兩者都丟明確 ScopeError。
- `*OPC?` 在 Single 等待觸發時不回應：`*CLS` 用 `_write_nowait`。
- HDF5 attrs 在 **group** 上。reader 先讀 group，退回 dataset。
- Keysight 原生 H5INt：`YReference=1` **不能扣**，V = raw×YInc+YOrg（MXR 實測）。本工具寫的檔（有 `/ScopeTool`）才扣。
- HD3：沒有 `:OPERegister:CONDition?`（用 `:RSTate?`）、沒有 INKSaver（程式端 `invertPixels()`）、截圖 1280×800 波形區隨面板變動（偵測 `#282828` 外框裁切）。

## 已知小問題（未處理）

- Infiniium Error 273 只有紙上驗證。
- HD3 `DATA?` 連 1000 點也要約 4 秒。
- 4 通道 × 100M 時記憶體約 7 GB 以上，再大或更多通道要改契約（目前凍結）。
- CSV 時間欄 `.6e` 精度略損；CSV 通道名 `CH1` vs HDF5 `CHAN1` 不一致（待 CSV 規則一起處理）。
- 截圖頁區域選項仍標「(待驗證)」。

## 先讀

| 檔案 | 內容 |
|---|---|
| `RULES.md` | 硬規則（第 5、9 條已被本輪定案取代，見上）：`contracts.py` 不准改、不准裝新套件（**沒有 Pillow**）、只用 PySide6 |
| `scope_tool/contracts.py` | 凍結契約，含 CSV/HDF5 格式 |
| `docs/真機驗證清單.md` | 逐輪實測紀錄 |
| `docs/示波器命令規格書.md`、`docs/reference/` | SCPI 規格與原廠文件 |
| `docs/adr/` | 0001 PySide6；0002 搜尋；0003 HDF5 沿用 Keysight 結構 |

## 環境

- `/opt/anaconda3/bin/python3`（3.13）、pyvisa（macOS `/Library/Frameworks/visa.framework`）、numpy、h5py、PySide6；進入點先 `os.environ["QT_API"]="pyside6"`。
- 實機：HD304MSO `USB0::0x2A8D::0x4704::MY66190300::INSTR`（輸入接地雜訊；使用者設定：RUN、100 µs/div、AUTO、只開 CH1、5 V/div）；DSO-X 3014G `USB0::0x2A8D::0x1768::MY65520038::INSTR`（本輪未接）；MXR254B `USB0::0x2A8D::0x9007::MY63310109::INSTR`（輸入接地雜訊；使用者設定：RUN、100 ns/div、AUTO、RTIM、記憶體深度 AUTO、只開 CH1、5 V/div）。**測試改設定要記下並還原。**
- Codex：`codex exec --sandbox workspace-write ... </dev/null`（**一定要 `</dev/null`**，否則卡在讀 stdin）。Codex 沙箱**連不到 VISA**，實機測試由 Claude 執行。
- 右上角「Codex 任務」面板：mod 在 `~/.claude/dev-mods/<session>/codex-tasks/`，讀 scratchpad 的 `codex_status.json`（路徑寫死本 session）。

## 已定案（仍有效）

- 搜尋：VISA 列表 + zeroconf + 手動 IP；`*IDN?` 判不出系列讓使用者手選一次。
- 截圖頁：檔名自動接時間戳，永不覆蓋；BMP/PNG、正常/反轉、全螢幕/格線區。HD3 反轉為程式端反相、格線區自動偵測（使用者選定）。
- 擷取頁：通道多選，單位是點數，只存 HDF5。「重新觸發」勾選預設關。
- 分析頁：離線；兩條垂直、兩條水平游標，讀值取原始資料；不做自動量測。
- I/O 全在 QThread；逾時截圖 15s、擷取每個 VISA 操作 60s（block 分段讀，單段不會逾時）；Error 273 → 「請關閉遠端桌面」；不做取消。

## 不做

掃網段搜尋、自動量測、傳輸取消、面板 USB CSV 解析、自訂 HDF5 結構。

## 溝通

繁體中文，直白，不長篇大論。沒真機的路徑要說清楚只有紙上驗證。改程式交 Codex，Opus 審。
