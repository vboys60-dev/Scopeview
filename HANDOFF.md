# Handoff：示波器截圖與波形擷取工具（HTML 版工作資料夾）

目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖_html`（獨立 git repo，main，無 remote）
- 2026-10-22 從穩定版 `../示波器截圖`（Qt 版，HEAD `b358334`）複製，**未含 `N8900A/`**；之後 HTML 化只改這裡，原資料夾不動。
- 備份：`../示波器截圖_備份_20261022_223504.tar.gz`（含 N8900A 與 git 歷史）。
- 參考資料在 `../示波器截圖/N8900A/`（gitignore，無版本備份）。`InfScopeDLL_decompiled` 與 Infiniium Help 已是同名 `.tar.gz`，引用前先 `tar -xzf`。

## 現況（2026-10-22）

- 離線分析已完成並 commit：Stage 0 Jitter／眼圖移出 GUI（`analysis/{clock,jitter,eye}.py`、`ui/analysis_{jitter,eye}.py` 保留未接線）；Stage 1 時間／電壓量測；Stage 2 Marker（B 級，`analysis/marker.py`）；Stage 3 FFT（補零／RBW／阻抗／Phase、`analysis/peaks.py`、Track RF）；`fc3d229` 修 Codex 審查 5 項（游標重吸附重算、RF 跳峰精度與效能、FFT 峰表快取、runner 防抖）。
- 分析核心 `scope_tool/analysis/` 為純 numpy；UI 為 PySide6 + pyqtgraph（`scope_tool/ui/analysis_*.py`、`tab_analysis.py`）。規格 `docs/離線分析功能規格.md`。
- **只有 offscreen 自我檢查，沒有真機／真人滑鼠驗證。** 待真機比對項目累積在 `docs/真機驗證清單.md`（階段 1~3 區段）。
- 已上機：DSO-X 6004A、DSO-X 3014G、HD304MSO、MXR254B、MSO-X 4154G、MSO9254A（僅連線讀取）。3000T、EXR、S 系列未上機。
- 啟動：Mac 雙擊 `啟動示波器截圖.command`（Web 版）；Qt 版 `啟動示波器截圖_qt.command`；有「測試儀器（模擬）」按鈕。

## Web 版（pywebview）現況（2026-10-22，已切為預設入口）

- 啟動：`啟動示波器截圖.command`（= `python -m scope_tool.web.app`）；舊 Qt 版保留為 `啟動示波器截圖_qt.command`，git tag `qt-final`（`bfba82c`）為純 Qt 最終狀態。`scope_tool/ui/`、`main.py` 未刪（PySide6 仍因 `QImage` 為執行期相依）。
- 權威規格：`docs/pywebview-GUI規劃建議書.html`（決策 D1–D6 皆採建議值）、`docs/web-api契約.md`＋`scope_tool/web/static/api_contract.json`（凍結契約，只有 lead 能改；附錄記錄審查後裁決）。檔案擁有權表在 `RULES.md` 末段。
- 架構：pywebview 只當視窗；daemon 執行緒跑 stdlib HTTP server（127.0.0.1＋token）；RPC／long-poll 事件／二進位 `/wave` `/fft`；前端為 ES modules＋自繪 Canvas，傳輸全藏在 `bridge.js`，`?mock=1` 可離線開發。VISA 一律經 `web/jobs.py` 儀器執行緒＋全域儀器鎖。
- 驗證指令：後端 `QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.{decimate,analysis_api,jobs,server,api,e2e_check,browser_check}`；前端 `node scope_tool/web/static/js/selfcheck_node.js`（或開 `static/selfcheck.html`）。`browser_check` 用 headless Chrome＋CDP 實跑連線→擷取→開檔→游標→量測→FFT（已通過、console 無錯誤）。
- **未驗證／已知限制**：沒有真機；沒有真人滑鼠手感（拖曳／滾輪）；真正的 pywebview 視窗只確認可啟動 10 秒未崩潰；Win10／WebView2／PyInstaller 打包（`packaging/`、`requirements-web.txt`）完全未驗；剪貼簿與 `<a download>` 在 pywebview 的行為未驗；1000×700 視窗開 FFT 時頻譜被壓縮需圖區內捲動；Track Measurements 因契約無事件座標而標「尚未支援」；100M×4 記憶體仍是既有上限。逐項清單：`docs/web版驗收清單.md`。
- 後續：真人／真機驗收後勾清單；Win10 打包；大檔 h5py 懶載入（選配）；validate_params 尚未接到 server（參數錯誤目前走可重試的 job 錯誤）；確認穩定後再決定是否刪除 `ui/` 與 Qt 入口。

## 分析頁 GUI 改善（2026-10-24，P1／P2a／P2b／P3a／P3b／浮動面板 已完成、實測並全部合入 main，HEAD `fb12038`）

- 計劃書：`docs/分析頁GUI改善計劃書.md`（§8 決策已定案）。範圍：A 區量測欄、B 區結果、C 區主圖；操作模型參考 N8900A。
- 已 commit／標籤：`p1-gui`（`5ed726b` 小修）→ `p2a-gui`（`82d02a9` 模式列／框選放大／Undo-Redo／Horizontal 列）→ `p2b-gui`（P2b-1 版面、P2b-2a Vertical 欄位與左軸電壓，合併於 `49d155f`）→ `8848ff5` FFT 控制列標籤同行 → `p2b3-gui`（`e18bf96` B 區縮小與頁籤）→ `p3a-gui`（`346664d` 游標來源脫鉤／Y 物理值真值／最近優先命中／摘要列）→ `p3b1-gui`（`4bfbfc3` 游標分頁 Marker 結果表／TSV 複製／觸控 ±12px）→ `p3b2-gui`（`0b8b61d` 垂直／雙向框選）。→ `float-gui`（`fb12038` 浮動量測面板）。以上皆已 fast-forward 合入 main；舊階段分支已刪。
- 目前行為摘要：拖曳＝平移、滾輪＝縮放時間；「框選放大」模式／Shift 暫時框選／Space 或中鍵暫時平移；Ctrl/Cmd+Z、Shift+Z、Ctrl+Y；Horizontal 列（時間/格、位置±1 格、完整時間）；Vertical 列（單位/格 微調與粗調、中心電位 O=−position×scale、歸零、適配＝以畫面中心為基準、dx 徽章）；左軸顯示目前通道實際電壓（通道色），零位把手對齊 0 V；三條 splitter（A｜圖區、圖區｜B、主圖｜FFT）、`clampLayout`（`layout.js`，門檻用視窗尺寸、預算用容器尺寸；窄於 900 視窗改「波形／FFT」分頁與窄軌抽屜）；B 區頁籤 `量測｜游標｜FFT 峰值`（B 實際寬度≥820 並排，否則分頁；寬版點「游標」分頁會獨佔全寬，量測面板暫隱）、量測表欄位選單（預設隱藏範圍／次數）、游標緊湊網格。偏好只存記憶體＋localStorage（不保證跨啟動）。
- 新檔與 lane（已登記 RULES.md）：L4 `gestures axes layout splitter voltage`；L5 `vertical bpanel summary cursor_table`＋`css/vertical.css`；L4 另有 `vzoom`；L8 `p1_check p2_check p2b_check p2b2_check p2b3_check p3_check p3b_check p3b2_check`、`web/browser_analysis_checks.py`、`web/browser_marker_checks.py`。新 command（`view.*`、`layout.*`）是前端 `store.command` 字串，不在凍結契約。
- 驗證現況：`selfcheck_node.js` 含各階段變異測試全過；`e2e_check`、`browser_check`（含多尺寸、splitter、Vertical 列、B 區尺寸斷言）在沙箱外通過。Codex 沙箱不能綁 localhost，這兩項必須由 Claude 在沙箱外跑。
- 已知／待辦：
  - P3 已完成：游標來源與 `selected` 脫鉤（私有狀態在 `cursors.js`，隱藏／刪除時依單位回退、重新可見還原使用者選擇）；Y 真值＝來源通道＋物理值，`store.cursors.y` 仍是格數投影（來源 scale/position 變動以變更前換算重投影）；最近優先命中（線 ±8 px、觸控 ±12 px）；Horizontal 摘要列（`summary.js`）；游標分頁 Marker_Results 表與 TSV 複製（`cursor_table.js`）；框選種類 `[水平｜垂直｜雙向]`（`view.zoomKind`，`vzoom.js`：最小合法檔位、整個 10 格適配、雙向一次 Undo、視圖歷史只記實際改動的通道）。Track Measurements 仍 disabled（契約無事件座標）。
  - 已知小項：複製在 WKWebView 的 await 後 user gesture 未真機驗；`browser_check` 曾偶發一次「寬版點 FFT 峰值分頁未切換」（4/5 次通過後未再重現，原因未查）；種類＝垂直時 Shift 暫時框選沿用該種類。
  - 浮動量測面板（`float-gui`／`fb12038`，已合 main）：同節點搬移 B 頁籤／動作列／內容，Pointer Capture 拖移與四邊／四角縮放、鍵盤移動／縮放、停靠／內容收折、<900 自動停靠，獨立記憶體＋localStorage 偏好。`floatpanel_math.js`／`floatpanel.js` 歸 L4；`float_check.mjs`／`browser_float_checks.py` 歸 L8。浮動時主圖視為 B 收折；量測全欄預設，窄框欄內換行且不縮字；停靠欄位偏好保留。Node 自檢＋浮動變異 40/40、`e2e_check`、`browser_check`（連跑 5 次）通過；Opus 審查已修（鍵盤事件不再被吞、自動停靠／夾回不覆寫偏好、欄位選單不溢出、不蓋頁籤列）。偶發 console `/fft 409` 為測試步驟與開檔的競態（防抖重取），已在測試端等待消除；產品端已加固（`700e95e`：`fftpane.js` 開檔中 `store.opening` 時不重取，開檔結束補取）。已實測。
  - 小項（收折列 ΔX 格式、測試檔行數已於 P3 解決）：500 µV V/div 下限與需求文字的 1 mV 不同（沿用 P1）；FFT 分隔線拖曳時仍重取頻譜（既有行為）。
  - 真機：Mac 觸控板手感、Windows 899px 斷點與中鍵自動捲動；WKWebView 捏合可能不送 `ctrl+wheel`。
- 工作方式：Codex 編碼（`codex exec -s workspace-write -C <dir> -o <out.md> "$(cat brief.md)" < /dev/null`，背景執行）→ 沙箱外跑 `e2e_check`／`browser_check` → Opus 唯讀審查（含變異測試）→ Codex 修正輪 → Claude 提交與標籤。平行任務用 git worktree。

## 離線分析修正線：Jitter／ΔY/ΔX／草案（2026-10-24）

- 已 commit：`1014c05` 游標表 ΔY/ΔX（Web `cursors.js`＋Qt `analysis_results.py`，空單位顯示 `1/s`）；`52b5c90` `marker.py` versus 模式不給斜率；`e928c31`、`4b7840d` 兩份草案 `docs/草案_Jitter眼圖Web契約.md`、`docs/草案_RMS縮放與相位追蹤定義.md`（Opus 兩輪複審後修訂，僅文件）；`35fd551`、`4b7840d` `docs/DSOX6004A_Jitter驗證紀錄.md`。
- DSO-X 6004A 驗證（10 MHz 方波）：Clock TIE 只用上升緣；示波器 TIE≈0.842×離線線性擬合 TIE−250.7 ps；σ 對 50% 中點門檻極敏感。先前「參考時脈可能含追蹤」證據不足（恆等式，σ 比與頻率無關），PLL 開工前先用 `scope_trend_1M.json` 比對頻譜比值。原始資料在 `示波器截圖/N8900A/DSOX6004A_Jitter驗證_20261024/`（gitignore、無備份）。
- **契約 v3 先不升**（使用者決定）：要改的是 L0 檔（`docs/web-api契約.md`、`api_contract.json`、`mock_catalog.js`、`mock_backend.js`、`l0_*.mjs`），不是 `scope_tool/contracts.py`（儀器契約，禁改）；只改 JSON 會讓 `l0_check.mjs`、`selfcheck_node.js`、`api.py contract_check`、`analysis_check.py` 失敗，合入須同一筆含 mock 同步＋Analysis 3 個 stub。**更正（2026-10-24）**：GUI P2 的 `view.undo`／`view.redo`／`layout.*` 是前端 `store.command` 字串，不在凍結契約內（`f2ed9ec` 已登記於 RULES.md），與 v3 無共用契約改動，不需一起升版；v3 只為 Jitter／眼圖新增 3 個 RPC。草案 `草案_Jitter眼圖Web契約.md` 已同步改成此說法（2026-10-25 確認）。
- 建議順序：①GUI P2 先做完並 commit（它在改 `tab_analysis.js` 等 L4 檔，Jitter 面板會動同批檔）→ ②v3 一筆落地（`api_contract.json`、`web-api契約.md`、`mock_catalog.js`、`mock_backend.js`＋Analysis 3 個 stub）→ ③Jitter／眼圖後端（`jitter_eval`、`eye_density`、`export_timing`）與前端面板分開實作。
- 草案要點：revision 以私有 `Analysis._accept`＋`submit(on_accept=...)` 在 `_tbl_lock` 內配號；刪等待槽；`export_timing` `job=false`；`validate_params` 須接上 server（`e2e_check.py:126-128` 的 BAD_REQUEST 將由 job 事件改同步）；PLL 只接受 `mode=手動`、捕獲 ±1000 ppm、w 失鎖門檻另訂（暫 ±1500 ppm）；RMS 2 冪縮放驗收 ≤5e−15·|a|。`analysis/*` 歸 T7。
- 待使用者下令：RMS 2 冪縮放實作（P3）、頻譜比值檢查→PLL 事件層原型、契約 v3＋Jitter／眼圖 Web 實作、push（無 remote）。詳見研究目錄 `HANDOFF_分析修正.md`。

## Windows 打包

- `RULES.md` 允許 Windows 版 PyInstaller（Win10／Win11，onedir）；目標機自行安裝 NI-VISA 或 Keysight IO Libraries（PyInstaller 不打包）。
- 草稿已備：`packaging/scope_tool_web.spec`、`packaging/build_win.bat`、`requirements-web.txt`（PySide6 不可排除）。凍結後 static 路徑已用 `sys._MEIPASS`。**全部待 Win10 實機驗證。**

## 後續待辦

1. 真機比對：量測數值與面板讀數、Bessel 低通群延遲補償、Marker／FFT 清單項目。
2. 上機：HD304 四通道 100M 與 `:DIGitize`（先確認設定已還原）、MXR Error 273／LAN／慢時基、3000T、MSO9254A 截圖／擷取／分析、DSO-X 6004A 的 GUI 全流程與 Single／Normal／`:DIGitize`。
3. 已知剩餘小項：RF 跳峰仍是 O(n) 約 0.1 s（8M bin）；FFT 快取依賴所有改資料路徑呼叫 `fft.refresh()`；切 log 頻率軸會重算 FFT；重入呼叫被忽略而非延後。
4. 可選缺口（使用者未定）：Vmid／相位延遲／邊緣脈衝計數、Track Measurements 真實位置、Phase 參考／unwrap UI、多組 Marker UI、疊圖／分開堆疊切換、多檔疊圖比較。

## 工作流程

- **GUI 測試由使用者主導**：使用者逐步手測，Claude 只記錄編號、不改程式，直到使用者說「沒有其他問題」才規劃→實作→審查→重開。
- 寫程式交 Codex，Opus 審。Codex：`codex exec -s workspace-write -C "$PWD" "<prompt>" < /dev/null > log 2>&1`（**一定要 `< /dev/null`**；背景啟動器的「completed」不等於 Codex 完成，log 結尾自加 `finished` 再輪詢）。Codex 沙箱連不到 VISA，實機由 Claude 執行。
- 繁體中文，直白。沒真機的路徑要說清楚只有紙上驗證。
- commit 結尾加 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` 與 `Claude-Session: https://claude.ai/code/session_0123DNaqbpGaCSVhdH7aNrA5`。

## 自我檢查

系統 `python3` 沒有 numpy，用 `/opt/anaconda3/bin/python3`（3.13）：
`for m in instruments.base instruments.infiniivision instruments.infiniium instruments.fake instruments.registry storage.writer storage.reader storage.csv_export ui.worker ui.tab_capture ui.tab_screenshot analysis.measure analysis.edge analysis.filter analysis.fft analysis.mathfn analysis.peaks analysis.marker analysis.clock analysis.jitter analysis.eye ui.analysis_chanbar ui.analysis_plot ui.analysis_overview ui.analysis_results ui.analysis_export ui.analysis_controls ui.analysis_runner ui.analysis_fftplot ui.analysis_marker ui.analysis_jitter ui.analysis_eye ui.analysis_math ui.analysis_layout ui.tab_analysis ui.main_window contracts; do QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.$m; done`（皆應印 OK）。
注意 `registry.py` 自檢不會 import `infiniium`，抓不到「忘了註冊」；要 import `scope_tool.ui.main_window` 後 `driver_for` 驗證。

## 擷取規則（已寫入 RULES.md 第 5、9 條）

- 示波器只因「使用者手動」或「按下擷取」而停止。擷取時若在 RUN：等 `10×時基+1` 秒再 `:STOP`，讀完**維持 STOP**；原本 STOP 直接讀；`retrigger` → `:DIGitize`。
- 一律存 HDF5（uint16 原始整數 + group attrs `YInc/YOrg/YReference`；無 preamble 才存 float64 電壓）；CSV 只能從分析頁匯出（`storage/csv_export.py`）：範圍全部／游標區間，可縮點（上限預設 10M），欄名 `CH1(V)`，時間位數依最小相異間隔。
- `max_points()`：HD3 100M、3000G 4M、Infiniium 查 `:ACQuire:POINts:MAXimum?`。InfiniiVision 的點數由時基決定（20 ns/div 只有 2000 點），`:ACQuire:POINts` 設了無效。
- Infiniium 存檔轉取整筆記錄（`:DISK:SAVE ALL` → `GETFILE?` → `DELete`），「點數」只當上限，超過丟 ScopeError，不改使用者記憶體深度。

## 真機踩到的坑（已修，勿回退）

- pyvisa `query_binary_values` 傳輸 > 約 64 MiB 會卡死：`_query_binary` 手動分段讀 IEEE 488.2 block（每段 4 MiB）。
- InfiniiVision `:HARDcopy:AREA GRAT` 回 `-221`，**不要送**；格線區由 driver 依截圖尺寸查表裁：800×512 (16,52,642×400)、800×632 (16,92,642×480)，其他回全圖。
- `:ACQuire:POINts:MAXimum?` 在 InfiniiVision／HD3 不存在（-113 + 逾時）。
- `bytes(np.array)` 會把每個位元組展開成 8 倍 → 檔案損壞。
- `channels()` 探測不存在通道會逾時並留 `-113`：探測期間 timeout 1 秒，之後 `*CLS`。
- 沒有完整採集（Single/Normal 等觸發、剛 RUN 就 STOP）：3000G PREamble 卡死（5 秒逾時 + device clear），HD3 回空欄位；都丟明確 ScopeError。等不到觸發時 `:DIGitize` 的 `*OPC?` 會 60 秒逾時，`_prepare_capture` 逾時後 device clear 並丟 ScopeError。
- `*OPC?` 在 Single 等待觸發時不回應：`*CLS` 用 `_write_nowait`。
- HDF5 attrs 在 **group** 上；reader 先讀 group，退回 dataset。Keysight 原生 H5INt：`YReference=1` **不能扣**，V = raw×YInc+YOrg；本工具寫的檔（有 `/ScopeTool`）才扣。
- HD3：沒有 `:OPERegister:CONDition?`（用 `:RSTate?`）、沒有 INKSaver（程式端 `invertPixels()`）、截圖波形區隨面板變動（偵測 `#282828` 外框）；`DATA?` 連 1000 點也要約 4 秒。
- MXR：沒有 `:WAVeform:POINts <n>`／`:WAVeform:UNSigned`、PREamble 24 欄 → 直讀路線已刪。
- 4154G：每次 `:DISPlay:DATA?` 後跳「Remote operation completed.」約 5 秒 → 截圖前送 `:DISPlay:MESSage:CLEar`。
- InfiniiVision `:DISPlay:DATA?` 調色盤參數會殘留在儀器上 → 每次送 `<fmt>,COLor`（HD3 帶第二參數會逾時，不帶）。
- 新 driver 模組底部必須 `register(...)`；`main_window.py` 載入 driver 時 `try/except: pass`，漏註冊或 import 失敗都會靜默，只表現為「無法辨識型號」（MSO9254A 曾因此漏註冊）。
- pyqtgraph 0.14 自動降採樣在 x 為秒時會丟光資料：TIE 趨勢圖不開降採樣。
- 4 通道 × 100M 記憶體約 7 GB 以上，再大要改契約（凍結）。

## 先讀

| 檔案 | 內容 |
|---|---|
| `RULES.md` | 硬規則：`contracts.py` 不准改、不准裝新執行期套件（**沒有 Pillow**）、只用 PySide6、打包規則 |
| `scope_tool/contracts.py` | 凍結契約，含 CSV／HDF5 格式 |
| `docs/真機驗證清單.md` | 逐輪實測紀錄（append-only） |
| `docs/離線分析功能規格.md` | 離線分析規格 |
| `docs/示波器命令規格書.md`、`docs/reference/` | SCPI 規格與原廠文件、手冊整理 |
| `docs/adr/` | 0001 PySide6；0002 搜尋；0003 HDF5 沿用 Keysight 結構、存原始整數 |
| `docs/archive/PLAN.md.gz` | 舊開發計畫（T1~T11 皆完成），`zcat` 可讀 |

## 實機（輸入皆接地雜訊；**測試改設定要記下並還原**）

| 機台 | VISA | 使用者設定 |
|---|---|---|
| HD304MSO | `USB0::0x2A8D::0x4704::MY66190300::INSTR` | RUN、100 µs/div、AUTO、只開 CH1、5 V/div |
| DSO-X 3014G | `USB0::0x2A8D::0x1768::MY65520038::INSTR` | RUN、5 ms/div、AUTO、4 通道全開、1 V/div、INKSaver 1（輸入平 DC，Single/Normal 不會觸發） |
| DSO-X 6004A | （未記錄） | 測完維持 STOP、20 ns/div、記憶體深度 AUTO |
| MXR254B | `USB0::0x2A8D::0x9007::MY63310109::INSTR` | RUN、100 ns/div、AUTO、RTIM、記憶體深度 AUTO、只開 CH1、5 V/div |
| MSO-X 4154G | `USB0::0x2A8D::0x17BC::MY65060120::INSTR` | RUN、100 µs/div、AUTO、只開 CH1、5 V/div、INKSaver 1 |
| MSO9254A | `USB0::0x2A8D::0x900E::MY53130146::INSTR` | 僅讀取；設定未記錄，測試前先確認 |

## 已定案

- 搜尋：VISA 列表 + zeroconf + 手動 IP；`*IDN?` 判不出系列讓使用者手選一次。
- 截圖頁：檔名自動接時間戳、永不覆蓋；BMP／PNG、正常／反轉、全螢幕／格線區。
- 擷取頁：通道多選，單位是點數，只存 HDF5；「重新觸發」預設關。
- 分析頁：離線；示波器式每通道 V／格＋位置（只改顯示）；讀值取原始資料；四游標吸附第一通道取樣點；量測、FFT、數學在背景執行（`worker.Job`），過期結果丟棄。
- I/O 全在 QThread；逾時截圖 15 s、擷取每個 VISA 操作 60 s；Error 273 → 「請關閉遠端桌面」；不做取消。
- 不做：掃網段搜尋、傳輸取消、面板 USB CSV 解析、自訂 HDF5 結構。
