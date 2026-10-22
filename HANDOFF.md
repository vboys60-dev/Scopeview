# Handoff：示波器截圖與波形擷取工具

目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖`（git repo，main，無 remote）

## 2026-10-22 階段 2：Marker（B 級，未 commit）

- 新增純 numpy `analysis/marker.py`（五種模式、觸發參考範圍、差值與 Delta To、數位限制）；UI 沿用四游標，由 `ui/analysis_marker.py` 接線，預設「現行 X1/X2」保留舊行為。預設 Results 保留 HEAD 的 t1/t2/Δt/1/Δt/v1/v2/ΔV 列名與 @t1/@t2 通道欄名，不加 Delta To；非預設模式才顯示 X1/X2/ΔX/1/ΔX/Y1/Y2/ΔY 與 Delta To，並清空通道表。
- Track Measurements 接口接受呼叫端位置並唯讀顯示；量測引擎尚無位置輸出，因此尚未自動追蹤最近新增量測。不得從統計值猜位置。真機比對項目已補至 `docs/真機驗證清單.md`；C 級同值峰次序留階段 3。
- Opus 意見修正：追蹤波形允許重複時間戳，遞減／非有限時間軸回不可用與原因；吸附限定窗內資料點，量測位置過濾 NaN／inf，切換模式後重算量測與讀值。手冊未載明的差值符號、數位來源整組不可用取捨已註明；未實作項目與效能限制只記錄於真機清單。
- 指定 19 個模組 offscreen 自我檢查皆印 OK，預設模式與 git HEAD 版對照 5 組情境輸出逐字相同，`git diff --check` 通過；未做真機／真人滑鼠驗證，未動 jitter/clock/eye 五檔，未 commit。

## 2026-10-22 本輪：DSO-X 6004A（X6000A）上機、已 commit 16240ff

- 註冊前綴 `DSO-X 6`／`MSO-X 6`（`infiniivision.py`）；截圖、擷取、離線分析讀檔實測通過，細節在 `docs/真機驗證清單.md` 第九輪。
- **點數由時基決定**：20 ns/div 只有 2000 點，200 µs/div 為 1M；`:ACQuire:POINts` 設了無效。擷取頁在實際點數少於要求時狀態列提示。`max_points()` 的 4M 仍是固定值（未量到上限）。
- 測試後示波器維持 STOP、20 ns/div、記憶體深度 AUTO。
- 未測：GUI 全流程、Single／Normal、`:DIGitize`、LAN。

## 2026-10-19 本輪：MSO9254A（9000A）加入、已 commit

- **9000A 系列**：`instruments/infiniium.py` 的 `model_prefixes` 加 `MSO9`、`DSO9`，沿用 EXR 命令（待真機驗證）。
- **漏註冊 bug 已修**：`infiniium.py` 原本沒有 `register(InfiniiumDriver)`，GUI 搜尋到 MSO9254A 仍跳「無法辨識型號」。現已在類別後補上。
- **已連線（GUI，USB）**：`USB0::0x2A8D::0x900E::MY53130146::INSTR`，`*IDN?` → `KEYSIGHT TECHNOLOGIES,MSO9254A,MY53130146,05.50.0006`；`:SYSTem:ERRor?` → 0；`:ACQuire:POINts:MAXimum?` → 41000000。只做讀取，示波器狀態未動。
- **未測**：截圖（`:DISPlay:DATA?`）、擷取（`:DISK:SAVE`／GETFILE）、分析頁讀真實波形。
- 新增 `啟動示波器截圖.command`（專案根目錄，雙擊執行 `scope_tool/main.py`；未實際雙擊測試，第一次可能要在隱私權設定放行）。
- 自我檢查注意：`registry.py` 自檢不會 import `infiniium`，所以它抓不到「忘了註冊」；要靠 GUI 載入路徑或 `import scope_tool.ui.main_window` 後 `driver_for` 驗證。
- `docs/真機驗證清單.md` 尚未補這輪紀錄。

## 離線分析＋新版面：已實作、使用者 GUI 實測無問題、已 commit

- **GUI 測試流程（使用者定）**：使用者一步步手動測試，每步回報一個問題；Claude **只記錄、編號、簡短確認，不改程式**，直到使用者說「沒有其他問題」才規劃（給版面／做法表，等使用者回「照這樣做」）→ 實作 → 審查＋自我檢查 → 重開 GUI。
- 2026-10-17：Claude 與 Codex（唯讀）讀 Infiniium Offline 手冊討論定案，規格在 `docs/離線分析功能規格.md`，使用者說「可以編碼」後實作完成；上一輪 GUI 改善三項（10 格、V/格查表、縮放判斷）已併入。全部自我檢查通過；Codex 唯讀審查 5 項已修；使用者 GUI 實測「目前暫無問題」後 commit。

## Jitter／眼圖：已實作、尚未 GUI 實測、尚未 commit

- 2026-10-22 已移出 GUI，clock/jitter/eye 與 analysis_jitter/analysis_eye 保留未接線。
- 2026-10-17：使用者問單檔能否做 Jitter、眼圖 → Claude × Codex 兩輪討論定案（規格 `docs/離線分析功能規格.md`「Jitter／眼圖」節），使用者說「可以編碼」後實作。
- 新增 `analysis/{clock,jitter,eye}.py`、`ui/analysis_{jitter,eye,runner,layout}.py`；MeasureRunner 從 controls 搬到 runner（並修：重算／防抖期間表上顯示「…」不留舊值、舊結果不回填、計算中不可匯出），版面／接線從 tab_analysis 搬到 layout。
- pyqtgraph 0.14 自動降採樣在 x 為秒時會丟光資料：TIE 趨勢圖不開降採樣。

## 現況（2026-10-17）

- 最新 commit 9c15896。分析頁改進已 commit：新增 `scope_tool/analysis/`（measure、edge、filter、fft、mathfn）與 `ui/analysis_{chanbar,controls,plot,fftplot,results,math,overview,export}.py`；改 `ui/tab_analysis.py`、`storage/reader.py`（`read_file_info`）、`RULES.md`（第 11 條離線分析、刪「不做自動量測」、擁有權表）、本檔。`analysis_readout.py` 已刪（併入 `analysis_results.py`）。
- 已上機：DSO-X 6004A、DSO-X 3014G、HD304MSO、MXR254B（Infiniium 首次）、MSO-X 4154G。3000T、EXR、S 系列沒上機。逐輪紀錄在 `docs/真機驗證清單.md`。
- 自我檢查：`for m in instruments.base instruments.infiniivision instruments.infiniium instruments.fake instruments.registry storage.writer storage.reader storage.csv_export ui.worker ui.tab_capture ui.tab_screenshot analysis.measure analysis.edge analysis.filter analysis.fft analysis.mathfn analysis.clock analysis.jitter analysis.eye ui.analysis_chanbar ui.analysis_plot ui.analysis_overview ui.analysis_results ui.analysis_export ui.analysis_controls ui.analysis_runner ui.analysis_fftplot ui.analysis_jitter ui.analysis_eye ui.analysis_math ui.analysis_layout ui.tab_analysis ui.main_window contracts; do QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -m scope_tool.$m; done`（系統 `python3` 沒有 numpy）。
- 啟動：`python main.py`（在 `scope_tool/`），有「測試儀器（模擬）」按鈕。或雙擊根目錄 `啟動示波器截圖.command`。

## 下一步

1. 真機比對：量測數值與示波器面板讀數、Bessel 低通是否與原廠一樣補償群延遲。
2. 上機：HD304 重測四通道 100M、`:DIGitize` 四通道（上次 USB 斷線；接上先確認設定已還原）；MXR 補 Error 273（遠端桌面）、LAN、慢時基、GUI 全流程；3000T。
3. （CSV 匯出已在 GUI 實測：3014G 4M 檔，全部 1M 點與游標區間縮點 1 萬點，與原檔逐點比對正確。縮點時時間位數依縮點後間隔，觸發次取樣偏移會被捨去，使用者確認不改。）
4. 分析頁後續階段（使用者先前已定需求）：
   - ~~第 2 階段 游標區間統計~~：已被離線分析功能取代（量測範圍＝游標區間／全部）。
   - 延後項目見 `docs/離線分析功能規格.md`「延後」。
   - **第 3 階段**：疊圖／分開堆疊兩種模式可切換（現在每通道可獨立 V/格與位置，可能已部分涵蓋，做之前跟使用者確認）。
   - **第 4 階段**：多檔疊圖比較（曲線名「檔名 CH1」、各用自己時間軸）；多檔時 CSV 選一個檔匯出。

## 分析頁現況（Infiniium 風格版面，2026-10-17 實作，使用者 GUI 實測無問題）

- 版面：上方工具列（開啟、檔案資訊、重設視圖、通道歸位、游標歸位、匯出 CSV 選單、數學…、FFT、閾值、量測範圍、預覽、點數／取樣率）；左側直立分頁「時間量測／電壓量測」＋邊緣方向；通道列色塊（勾選、V/格查表、位置格數、雙擊換色、點選＝量測與游標換算來源、F 通道有 ×）；中央分隔：預覽→主波形 10×10 格→FFT 格；水平列（時間/格、中心）＋操作說明；下方結果區（量測表／游標表／FFT 峰值，寬並排、窄於 900 px 改分頁）。
- 游標、示波器模式互動同前（四條游標、吸附第一通道取樣點、滾輪換 V/格、拖曳位移）；滾輪放大前判斷會不會超出 ±5 格，縮放以波形中心為準。
- 量測／FFT／數學在背景執行（`worker.Job`），過期結果丟棄；CSV 匯出只含原始通道。
- 只有紙上驗證：真人滑鼠手感、大檔拖曳流暢度、原生 QColorDialog／QMessageBox、量測數值與真機面板比對、Bessel 低通是否與原廠一樣補償群延遲。

## 擷取規則（使用者定案，已寫入 RULES.md 第 5、9 條）

- **示波器只因「使用者手動」或「按下擷取」而停止。** 擷取時若在 RUN：等 `10×時基+1` 秒再 `:STOP`，讀完**維持 STOP**。原本 STOP 直接讀。`retrigger` → `:DIGitize`。
- **一律存 HDF5**；CSV 只能從分析頁匯出（`storage/csv_export.py`，RULES 第 5 條）：範圍全部／游標區間；可勾縮點、上限預設 10M（每 N 點取 1）；欄名照契約 `CH1(V)`；科學記號、每欄位數依「最小相異間隔」自動決定（誤差 < 間隔/10）。存到來源檔同資料夾、加時間戳。實測 4 通道 10M 列約 11 秒、668 MB。
- **HDF5 存原始整數**：uint16 + group attrs `YInc/YOrg/YReference`；無 preamble 才存 float64 電壓。
- `max_points()`：HD3 100M、3000G 4M、Infiniium 查 `:ACQuire:POINts:MAXimum?`（MXR 200M）。
- **Infiniium 一律存檔轉取整筆記錄**（`:DISK:SAVE ALL` → `GETFILE?` → `DELete`），「點數」只當上限：記錄點數 > 設定點數就丟 ScopeError，不改使用者記憶體深度。存檔維持 `ALL`，原生檔含所有顯示中通道。

## 真機踩到的坑（已修，勿回退）

- pyvisa `query_binary_values` 傳輸 > 約 64 MiB 會卡死：`_query_binary` 手動分段讀 IEEE 488.2 block（每段 4 MiB）。
- InfiniiVision `:HARDcopy:AREA GRAT` 回 `-221`，**不要送**。格線區由 driver 依截圖尺寸查表裁：800×512（3014G）(16,52,642×400)、800×632（4154G）(16,92,642×480)，其他尺寸回全圖。
- `:ACQuire:POINts:MAXimum?` 在 InfiniiVision/HD3 不存在（-113 + 逾時）。
- `bytes(np.array)` 會把每個位元組展開成 8 倍 → 檔案損壞。
- `channels()` 探測不存在通道會逾時並留 `-113`：探測期間 timeout 1 秒，之後 `*CLS`。
- 沒有完整採集（Single/Normal 等觸發、剛 RUN 就 STOP）：3000G PREamble 卡死（5 秒逾時 + device clear），HD3 回空欄位；都丟明確 ScopeError。HD3 無法查採集是否完成。
- `*OPC?` 在 Single 等待觸發時不回應：`*CLS` 用 `_write_nowait`。
- HDF5 attrs 在 **group** 上；reader 先讀 group，退回 dataset。
- Keysight 原生 H5INt：`YReference=1` **不能扣**，V = raw×YInc+YOrg。本工具寫的檔（有 `/ScopeTool`）才扣。
- HD3：沒有 `:OPERegister:CONDition?`（用 `:RSTate?`）、沒有 INKSaver（程式端 `invertPixels()`）、截圖波形區隨面板變動（偵測 `#282828` 外框）。
- MXR：沒有 `:WAVeform:POINts <n>`/`:WAVeform:UNSigned`、PREamble 24 欄 → 直讀路線已刪。
- 4154G：每次 `:DISPlay:DATA?` 後畫面跳「Remote operation completed.」約 5 秒，連續截圖會拍到 → 截圖前送 `:DISPlay:MESSage:CLEar`（3014G 也接受）。
- InfiniiVision `:DISPlay:DATA?` 的調色盤參數會保留在儀器上（`:HARDcopy:PALette?` 看不出來），被設成灰階後截圖一直是灰階 → 每次送 `<fmt>,COLor`（問題在 4154G 發現，修正在 3014G 驗證；HD3 帶第二參數會逾時，不帶）。
- 新 driver 模組底部必須 `register(...)`。`ui/main_window.py` 載入 driver 模組時用 `try/except: pass` 包住，漏註冊或 import 失敗都會靜默，只表現為「無法辨識型號」。
- 等不到觸發時 `:DIGitize` 的 `*OPC?` 會 60 秒逾時，之後示波器不回應 → `_prepare_capture` 逾時後 device clear 並丟明確 ScopeError（3014G 實測；Infiniium 未測）。

## 已知小問題（未處理）

- Infiniium Error 273 只有紙上驗證。
- HD3 `DATA?` 連 1000 點也要約 4 秒。
- 4 通道 × 100M 記憶體約 7 GB 以上，再大要改契約（凍結）。
- 調色盤修正（`,COLor`）4154G 未重測。

## 先讀

| 檔案 | 內容 |
|---|---|
| `RULES.md` | 硬規則：`contracts.py` 不准改、不准裝新套件（**沒有 Pillow**）、只用 PySide6 |
| `scope_tool/contracts.py` | 凍結契約，含 CSV/HDF5 格式 |
| `docs/真機驗證清單.md` | 逐輪實測紀錄 |
| `docs/示波器命令規格書.md`、`docs/reference/` | SCPI 規格與原廠文件 |
| `docs/adr/` | 0001 PySide6；0002 搜尋；0003 HDF5 沿用 Keysight 結構、存原始整數 |

## 環境

- `/opt/anaconda3/bin/python3`（3.13）、pyvisa（macOS `/Library/Frameworks/visa.framework`）、numpy、h5py、PySide6；進入點先 `os.environ["QT_API"]="pyside6"`。
- 實機（輸入皆接地雜訊；**測試改設定要記下並還原**）：

| 機台 | VISA | 使用者設定 |
|---|---|---|
| HD304MSO | `USB0::0x2A8D::0x4704::MY66190300::INSTR` | RUN、100 µs/div、AUTO、只開 CH1、5 V/div |
| DSO-X 3014G | `USB0::0x2A8D::0x1768::MY65520038::INSTR` | RUN、5 ms/div、AUTO、4 通道全開、1 V/div、INKSaver 1（輸入平 DC，Single/Normal 不會觸發） |
| MXR254B | `USB0::0x2A8D::0x9007::MY63310109::INSTR` | RUN、100 ns/div、AUTO、RTIM、記憶體深度 AUTO、只開 CH1、5 V/div |
| MSO-X 4154G | `USB0::0x2A8D::0x17BC::MY65060120::INSTR` | RUN、100 µs/div、AUTO、只開 CH1、5 V/div、INKSaver 1 |
| MSO9254A（9000A） | `USB0::0x2A8D::0x900E::MY53130146::INSTR` | 2026-10-19 GUI 已連線，僅讀取查詢；設定未記錄，測試前先確認 |

- Codex：`codex exec --sandbox workspace-write ... </dev/null`（**一定要 `</dev/null`**）。Codex 沙箱連不到 VISA，實機測試由 Claude 執行。

## 已定案（仍有效）

- 搜尋：VISA 列表 + zeroconf + 手動 IP；`*IDN?` 判不出系列讓使用者手選一次。
- 截圖頁：檔名自動接時間戳，永不覆蓋；BMP/PNG、正常/反轉、全螢幕/格線區。HD3 反轉為程式端反相、格線區自動偵測。
- 擷取頁：通道多選，單位是點數，只存 HDF5。「重新觸發」預設關。
- 分析頁：離線；示波器式每通道 V/格＋位置（只改顯示）；讀值取原始資料；CSV 從分析頁匯出原始資料。自動量測只會開放「游標區間統計」（第 2 階段），其餘不做。
- I/O 全在 QThread；逾時截圖 15s、擷取每個 VISA 操作 60s；Error 273 → 「請關閉遠端桌面」；不做取消。

## 不做

掃網段搜尋、自動量測、傳輸取消、面板 USB CSV 解析、自訂 HDF5 結構。

## 溝通

繁體中文，直白，不長篇大論。沒真機的路徑要說清楚只有紙上驗證。改程式交 Codex，Opus 審。
