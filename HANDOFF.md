# Handoff：示波器截圖與波形擷取工具（HTML 版工作資料夾）

目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖_html`（獨立 git repo，main，無 remote）
- 2026-10-22 從穩定版 `../示波器截圖`（Qt 版，HEAD `b358334`）複製，**未含 `N8900A/`**；之後 HTML 化只改這裡，原資料夾不動。
- 備份：`../示波器截圖_備份_20261022_223504.tar.gz`（含 N8900A 與 git 歷史）。
- 參考資料在 `../示波器截圖/N8900A/`（gitignore，無版本備份）。`InfScopeDLL_decompiled` 與 Infiniium Help 已是同名 `.tar.gz`，引用前先 `tar -xzf`。

## 現況（2026-10-22）

- 離線分析（Stage 0～3：量測、Marker、FFT、Track RF）已完成；`analysis/` 為純 numpy，規格 `docs/離線分析功能規格.md`。Jitter／眼圖已移出 GUI（程式保留未接線）。
- **只有 offscreen／headless 自檢，沒有真機驗證**；待比對項目在 `docs/驗證.md`。已上機：DSO-X 6004A／3014G、HD304MSO、MXR254B、MSO-X 4154G、MSO9254A（僅連線讀取）；3000T、EXR、S 系列未上機。
- 啟動：`啟動示波器截圖.command`（Web 版）；Qt 版 `啟動示波器截圖_qt.command`；有「測試儀器（模擬）」。

## Web 版（pywebview）現況（2026-10-22，已切為預設入口）

- 啟動：`啟動示波器截圖.command`（= `python -m scope_tool.web.app`）；舊 Qt 版保留為 `啟動示波器截圖_qt.command`，git tag `qt-final`（`bfba82c`）為純 Qt 最終狀態。`scope_tool/ui/`、`main.py` 未刪（PySide6 仍因 `QImage` 為執行期相依）。
- 權威規格：`docs/web-api契約.md`＋`scope_tool/web/static/api_contract.json`（凍結契約，只有 lead 能改；附錄記錄審查後裁決）。檔案擁有權表在 `RULES.md` 末段。
- 架構：pywebview 只當視窗；daemon 執行緒跑 stdlib HTTP server（127.0.0.1＋token）；RPC／long-poll 事件／二進位 `/wave` `/fft`；前端為 ES modules＋自繪 Canvas，傳輸全藏在 `bridge.js`，`?mock=1` 可離線開發。VISA 一律經 `web/jobs.py` 儀器執行緒＋全域儀器鎖。
- 驗證指令：後端 `QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.{decimate,analysis_api,jobs,server,api,e2e_check,browser_check}`；前端 `node scope_tool/web/static/js/selfcheck_node.js`（或開 `static/selfcheck.html`）。`browser_check` 用 headless Chrome＋CDP 實跑連線→擷取→開檔→游標→量測→FFT（已通過、console 無錯誤）。
- **未驗證／已知限制**：沒有真機；沒有真人滑鼠手感（拖曳／滾輪）；真正的 pywebview 視窗只確認可啟動 10 秒未崩潰；Win10／WebView2／PyInstaller 打包（`packaging/`、`requirements-web.txt`）完全未驗；剪貼簿與 `<a download>` 在 pywebview 的行為未驗；1000×700 視窗開 FFT 時頻譜被壓縮需圖區內捲動；Track Measurements 因契約無事件座標而標「尚未支援」；100M×4 記憶體仍是既有上限。逐項清單：`docs/驗證.md`。
- 後續：真人／真機驗收後勾清單；Win10 打包；大檔 h5py 懶載入（選配）；validate_params 尚未接到 server（參數錯誤目前走可重試的 job 錯誤）；確認穩定後再決定是否刪除 `ui/` 與 Qt 入口。

## 分析頁 GUI 改善（2026-10-24～25，已合入 main）

- 計劃書：`docs/archive/分析頁GUI改善計劃書.md.gz`。範圍：A 量測欄、B 結果、C 主圖；操作參考 N8900A。
- 行為：拖曳＝平移、滾輪＝縮放；框選放大（Shift 暫時框選、Space／中鍵暫時平移）、`view.zoomKind`＝水平｜垂直｜雙向；Undo／Redo；`clampLayout`（<900 窗改分頁／抽屜）。垂直框選改連續 V/格＝選框高÷10。
- 結構風險未修：`axes.js`／`gestures.js` 各存一份 `zoomKind` 且 `store.command` 不重播，掛載順序不同會不同步。
- 檔案 lane 已登記 RULES.md（L4／L5／L8）。`browser_check`／`e2e_check` 須在沙箱外跑。
- 已知小項：Track Measurements 仍 disabled；500 µV V/div 下限；FFT 分隔線拖曳仍重取頻譜；複製在 WKWebView 的 user gesture 未真機驗。
- **量測問題（使用者 2026-10-25 擱置）**，重現檔 `wave6000-10Mhz_20261022_125915.h5`：①上升／下降時間、斜率顯示「—」：邊緣僅 2～3 點，`edge.transition` 要求 ≥4 點（`edge.py:58`），是設計門檻；②新增量測等約 30 秒：每次重算全部、分析執行緒僅一條（`jobs.py` `ThreadPoolExecutor(1)`）且舊請求不可取消。可能修法：只算新增項、共用邊緣偵測。
- **3000G 量測**：研究見 `docs/研究_3000G量測計算比對.md`。點數不足輸出 `<`／`>` 上界標記；新增 `-工作週期`、Vavg／Vrms 加 `mode`；雙來源 `延遲`／`相位`／`電壓比`；「目前」取最靠近 t=0 的事件。未做：可見範圍量測、Top/Base 真機比對。

## 分析頁 Marker Table（2026-10-25，已完成並真機驗收）

- 計劃書：`docs/archive/分析頁MarkerTable計劃書.md.gz`；契約不升版，store 鍵 `markerTable`／`fftMarker`。
- 時域：連動組 M1＋每通道最多 10 個獨立點，右鍵選單；FFT：可拖水平基準線，峰表一次抓 1000 峰前端過濾。B 區頁籤 `量測｜游標｜Marker｜FFT 峰值`；「⇥ 右側欄」＝`layout.markerSide`（340px，≥900px）。
- **使用者決定不做 JSON 匯出入**。右側欄寬度固定不可拖。
- 坑：WKWebView 點 button 不給焦點，`focusout` 的 `relatedTarget=null` 會使選單點選無效；`menu.remove()` 同步重入 `close()` 也會。headless Chrome 測不出，靠 `marker_check.mjs`。
- **Codex 背景呼叫必須加 `< /dev/null`**，否則卡在等 stdin。

## 介面美化（2026-10-25）

- 範圍＝token／對比／版面＋圖區（虛點格線、中央十字軸、琥珀重點色）。**不做整套深色主題**（RULES.md）。
- 通道色 Okabe–Ito，來源 `api_contract.json` `channel_colors`（與 `mock_catalog.js`、`tab_analysis.js`／`toolbar.js` fallback 同步）；canvas 色值讀 CSS token（`plotcore.js plotColors()`）。
- `analysis.css` 的 `12.5px` 不可改（`p2b_check`／`p2b3_check`／`p3b_check` 斷言寫死）。
- 數學通道要同時進 `file.channels` 與 `channels`，否則不繪圖；視窗太矮 `clampLayout` 會收掉預覽（`layout.state` 帶 `blocked`）。

## 主圖包絡修正與版面編輯器（2026-10-26）

- 包絡破圖已修：`plotcore.js drawPixels` 相鄰有限桶補連線；`envelope_check.mjs` 在 `selfcheck_node.js`。
- 版面編輯器 `docs/版面編輯器/layout_editor.html`（file:// 雙擊）。`shots/` 截圖已於 2026-10-28 整理時刪除，`components.json` 為版面微調**之前**的快照，使用前需重量測。程式的「B 區」＝`bpanel.js` 結果區，左側量測欄是 `measure.js`（A 區）。
- **待使用者**：排好版面後貼回 JSON／Markdown，再照它改 GUI。
- Codex CLI 0.163.0 無 `--full-auto`，用 `codex exec --sandbox workspace-write -C "$PWD" - < prompt`；其沙箱禁綁 localhost。

## 分析頁版面微調（2026-10-26）

- 水平控制列在通道列正下方；「X軸Maker歸位」在工具列 Marker 欄；B 區 Marker 分頁叫「Marker Table」。
- 通道列每通道一欄（固定 236px，`--chanbar-col`），含 chip＋自己的 vertical；電壓控制預設收折；vertical 由 chanbar `sync()` 驅動。
- 已知：通道多時右側被切掉無提示；1000 寬水平列尾端被截斷；展開電壓控制後主圖變矮。

## 離線分析修正線：Jitter／ΔY/ΔX／草案

- 已 commit：游標表 ΔY/ΔX（`1014c05`）；`marker.py` versus 不給斜率（`52b5c90`）；草案 `docs/草案_Jitter與RMS.md`；`docs/驗證.md`（至第四輪）。
- DSO-X 6004A（10 MHz 方波）：示波器 TIE≈0.842×離線線性擬合 TIE−250.7 ps，σ 對 50% 中點門檻極敏感。頻譜比值檢查（第四輪）：增益各頻帶平坦約 0.85，無追蹤跡象，不能用此樣本校準 PLL 頻寬。原始資料在 `示波器截圖/N8900A/DSOX6004A_Jitter驗證_20261024/`（gitignore、無備份）。
- **契約 v3 先不升**（使用者決定）：要改 L0 檔（`docs/web-api契約.md`、`api_contract.json`、`mock_catalog.js`、`mock_backend.js`、`l0_*.mjs`，不是 `scope_tool/contracts.py`），須同一筆含 mock 同步＋Analysis 3 個 stub，否則 `l0_check`、`selfcheck_node`、`contract_check`、`analysis_check` 失敗。v3 只為 Jitter／眼圖新增 3 個 RPC，與 GUI 的 `view.*` 無關。順序：v3 一筆落地 → Jitter／眼圖後端（`jitter_eval`、`eye_density`、`export_timing`）→ 前端面板。
- 草案要點：revision 以 `Analysis._accept`＋`submit(on_accept=...)` 在 `_tbl_lock` 內配號；`export_timing` `job=false`；`validate_params` 須接上 server（`e2e_check.py:126-128` 將由 job 事件改同步）；PLL 只接受 `mode=手動`、捕獲 ±1000 ppm、失鎖門檻暫 ±1500 ppm。`analysis/*` 歸 T7。
- 已完成：RMS 2 冪縮放（`ef6936f`；公開 `measure` 在 ~1.8e308 資料會卡在 top/base 直方圖，已知限制）；PLL 事件層原型 `analysis/pll.py`＋`pll_check.py`（印 OK；只有事件層，未接 clock／眼圖／GUI／契約，門檻待校準，1400 ppm 重鎖一次、2000 ppm 失鎖）。
- 待使用者下令：契約 v3＋Jitter／眼圖 Web 實作（PLL 接線另案）、push（無 remote）。詳見研究目錄 `HANDOFF_分析修正.md`。

## Windows 打包

- `RULES.md` 允許 Windows 版 PyInstaller（Win10／Win11，onedir）；目標機自行安裝 NI-VISA 或 Keysight IO Libraries（PyInstaller 不打包）。
- 草稿已備：`packaging/scope_tool_web.spec`、`packaging/build_win.bat`、`requirements-web.txt`（PySide6 不可排除）。凍結後 static 路徑已用 `sys._MEIPASS`。**全部待 Win10 實機驗證。**

## FFT 頻譜分頁與資料截取分頁（2026-10-26，已完成）

- 計畫：`docs/archive/FFT頻譜分頁計畫.md.gz`、`docs/archive/資料截取合併計畫.md.gz`。
- 後端 `web/fft_rbw.py`（Welch＋VBW）；`fft` RPC 追加 `rbw`／`vbw`，契約 version 維持 2。頂層分頁剩：資料截取／離線分析／FFT 頻譜；FFT 分頁與分析頁**共用單一 runner／參數**（`fft_state.js`），分析頁內嵌 FFT 窗格都保留。
- `fftView`＝{f0,f1}；RBW=Auto 隨 Span 連動（≈span/1000，debounce 300 ms，變動 ≥5% 才重算）；FFT 範圍與量測共用 `rangeMode`。
- 未做：P5 清死碼；Welch／VBW 未真檔肉眼比對；資料截取並排版面無人看過；同頁搶儀器鎖需真機。

## 多檔比對（2026-10-28，已合入 main）

- 計畫書：`docs/archive/分析頁多檔比對計畫書.md.gz`。槽位 Mem1～Mem4，各檔以觸發零點為 0 再用 dx 微調；通道改名 `Mem1.CHAN1` 併入 `_waves`；槽位資料在 store 鍵 `slots`／`dataRev`，**不寫 `file`**（否則清量測與游標）。後端 `web/analysis_slots.py`。
- 限制：解碼要求同軸，跨檔拒絕；游標吸附主檔第一通道；FFT 一次一個來源；二元數學不含 dx（另立小案）；CSV 只匯出主檔；開新檔／關閉清空槽位。解碼鎖外存回競態已修（鎖內核對來源物件，`StaleError`）。
- GUI：Mem 通道零位標籤縮短為 `M1·1`；通道列每通道加底框；通道顏色可自訂（`channel_colors.js`，localStorage 鍵 `scopeChanColor:<通道名>`）。
- 未驗證：真人手感、WKWebView 對話框與色盤、大檔載入、不同取樣率跨檔量測、改色後游標／Marker 是否全跟著變；清單見 `docs/驗證.md`。
- 流程：worktree 分支開發後 fast-forward 合入；Codex 實作、Opus 審查、e2e／browser_check 由 Claude 沙箱外跑。

## 文件整理與離線分析匯出（2026-10-28）
- 文件整理：已完成計畫書與 3000G 原始報告壓成 `docs/archive/*.md.gz`（`zcat` 讀）；解碼研究、草案、驗證、`docs/reference/` 的 infiniium／infiniivision／N8900A 各合併為單檔（原樣接起，未去重）；刪 `docs/版面編輯器/shots/` 與 `pywebview-GUI規劃建議書.html`（見 git 歷史）。Qt 舊版未動。
- 量測／數學名詞畫面改英文：對照表在 `static/js/analysis/terms.js`（`T()`），後端、契約、存檔仍用中文 key；量測 CSV 的表頭與名稱在 `analysis_export.py` 另有一份 `EN`，改譯名兩處都要改。量測 tooltip、報告章節標題、波形／解碼 CSV 欄位仍是中文。
- 匯出（波形 CSV、量測 CSV、解碼 CSV、HTML 報告）一律先 `ui.pickPath` 選資料夾，取消即中止；檔名仍自動（來源檔名＋類型＋時間戳）。
- HTML 報告字級放大並加 `@page A4`，列印時表格可換行。

## 全專案審查與修正（2026-10-28，已 commit）

- 審查：Opus 審 Python 後端、Codex 三路唯讀審全專案，交叉驗證後排出優先序；授權項目 1～4、7、8 已全部完成並經 Opus 審。Codex 寫入模式兩次卡死無改動，改由 Claude 自己改、Opus 審。
- ①RPC 入口 `validate_params`（型別／null／列舉，在 `jobs.request` 與碰儀器前擋，BAD_REQUEST）＋ capture 通道白名單 `CHAN[1-8]` 且不得重複。
- ②`writer.timestamped` 以 `open("x")` 原子保留檔名。
- ③寫檔 tmp＋`os.replace`（`writer._atomic`，失敗清 tmp 與佔位空檔）；截圖／擷取碰儀器前 `_check_writable`，儀器擷取後寫入失敗改存 `<系統暫存>/scope_tool`（只寫 log，回傳無旗標）；`map_error` 把 OSError 對應 BAD_REQUEST。
- ④`analysis_api.open_waveform` 金字塔先建在區域變數，鎖內只換狀態。
- ⑦`config.load` 逐鍵型別驗證、`save` 原子寫＋`strict`（Qt 沿用預設不拋）；`api.save_config` 存檔成功才換記憶體設定，失敗拋 OSError。
- ⑧通道名正規化 `writer._unique_names`：僅完整符合 `(CHAN|CH|Channel ?)\d+` 轉 `CH{n}`／`Channel {n}`，SDA1／SCL1 保留，撞名改回原名；已用真 X6000A BIN 驗 CSV 讀回。
- 測試同步：`e2e_check` 錯參走同步 `rpc`；`browser_check` 系列改 "Frequency"／"Count"，匯出步驟要填 `pickPath` 的頁內 `<dialog>`。
- 已知小項（Opus 列、未修）：`config.load` 不驗清單／enum／points<=0；`_shutdown` 存檔不持鎖；`add_manual_ip`／`connect` 存檔失敗不回滾；撞名改回原名後 CSV 讀回可能再撞；CSV 表頭未加引號。
- 需真機、未授權：device clear／`_check_error` 解析、VISA 斷線後 `_drv` 未清、DIGitize 逾時與無上限 sleep、離開時卡住。
- 前端：`fft_track_rf` level 換算得 NaN 已修（`cursors.js` 改用 `peak_level`）。主圖快取競態（`mainplot.js` 切回已快取範圍時作廢在途請求）與擷取鈕鍵盤重複送出（`tab_capture.js` 原生 disabled＋handler 防護）已修。其餘 Codex 前端項目已修（Opus 規劃、Opus／Sonnet／Haiku 並行實作、Opus 審）：
  - 報告一致性（`report.js`）：選資料夾後記 `reportKey`（17 個鍵），收集完再比，變動即中止；收集前等主圖 `canvas.dataset.pending`（`mainplot.js` 設，最多 3 秒，讀取失敗會清掉）。
  - 解碼來源版本（`decode.js`）：解碼／`decode_frames`／estimate 前後比對來源槽物件參照，被換掉就不寫結果；來源選單隨可解碼通道增減重建（`decode_table.js` `fillSources`），選中通道消失才清。
  - 事件連線（`bridge.js`）：403／404／BAD_REQUEST 視為永久錯誤、停止事件迴圈並讓工作失敗（要重開程式）；其他錯誤連續 5 次通知 desync，仍每秒重試；刻意不加工作逾時（大量點數擷取可跑數分鐘）。
  - 擷取設定存檔失敗改 toast（`tab_capture.js`）。
  - 小項未修：主圖 canvas 0 尺寸時匯出會等 3 秒；事件失敗原因為空字串時文案「（）」。`browser_slot_checks` 已補「載入 Mem1 後解碼來源選單有 Mem1.CHAN1」。

## 後續待辦

1. 真機比對：量測數值與面板讀數、Bessel 低通群延遲補償、Marker／FFT 清單項目。
2. 上機：HD304 四通道 100M 與 `:DIGitize`（先確認設定已還原）、MXR Error 273／LAN／慢時基、3000T、MSO9254A 截圖／擷取／分析、DSO-X 6004A 的 GUI 全流程與 Single／Normal／`:DIGitize`。
3. 已知剩餘小項：RF 跳峰仍是 O(n) 約 0.1 s（8M bin）；FFT 快取依賴所有改資料路徑呼叫 `fft.refresh()`；切 log 頻率軸會重算 FFT；重入呼叫被忽略而非延後。
4. 解碼：I3C 真機波形與示波器內建解碼比對（`docs/驗證.md` 第 26 項）；多協定計畫見下方「多協定解碼」與「九協定解碼準則與實作計畫」（`docs/解碼實作計畫_20261112.md`，待使用者核可後開工）。
5. 可選缺口（使用者未定）：Vmid／相位延遲／邊緣脈衝計數、Track Measurements 真實位置、Phase 參考／unwrap UI、多組 Marker UI、疊圖／分開堆疊切換、多檔疊圖比較。

## 工作流程

- **GUI 測試由使用者主導**：使用者逐步手測，Claude 只記錄編號、不改程式，直到使用者說「沒有其他問題」才規劃→實作→審查→重開。
- 寫程式交 Codex，Opus 審。Codex：`codex exec -s workspace-write -C "$PWD" "<prompt>" < /dev/null > log 2>&1`（**一定要 `< /dev/null`**；背景啟動器的「completed」不等於 Codex 完成，log 結尾自加 `finished` 再輪詢）。Codex 沙箱連不到 VISA，實機由 Claude 執行。
- 繁體中文，直白。沒真機的路徑要說清楚只有紙上驗證。
- commit 結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 與 `Claude-Session: https://claude.ai/code/session_01XpTZuJrncCtdhRkN9fnF48`。**使用者明說才 commit。**
- 「照舊流程」：Opus 子代理寫計畫（docs/，唯讀）→ Codex 審 → Codex 在 worktree 逐階段實作 → lead 驗證（沙箱外跑 e2e_check／browser_check）。UI 功能實作前先給使用者看預覽，說可以才開工。

## 自我檢查

系統 `python3` 沒有 numpy，用 `/opt/anaconda3/bin/python3`（3.13）：
`for m in instruments.base instruments.infiniivision instruments.infiniium instruments.fake instruments.registry storage.writer storage.reader storage.csv_export ui.worker ui.tab_capture ui.tab_screenshot analysis.measure analysis.edge analysis.filter analysis.fft analysis.mathfn analysis.peaks analysis.marker analysis.clock analysis.jitter analysis.eye ui.analysis_chanbar ui.analysis_plot ui.analysis_overview ui.analysis_results ui.analysis_export ui.analysis_controls ui.analysis_runner ui.analysis_fftplot ui.analysis_marker ui.analysis_jitter ui.analysis_eye ui.analysis_math ui.analysis_layout ui.tab_analysis ui.main_window contracts; do QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.$m; done`（皆應印 OK）。
注意 `registry.py` 自檢不會 import `infiniium`，抓不到「忘了註冊」；要 import `scope_tool.ui.main_window` 後 `driver_for` 驗證。

## 擷取規則（已寫入 RULES.md 第 5、9 條）

- 示波器只因「使用者手動」或「按下擷取」而停止。擷取時若在 RUN：等 `10×時基+1` 秒再 `:STOP`，讀完**維持 STOP**；原本 STOP 直接讀；`retrigger` → `:DIGitize`。
- 一律存 HDF5（uint16 原始整數 + group attrs `YInc/YOrg/YReference`；無 preamble 才存 float64 電壓）；CSV 只能從分析頁匯出（`storage/csv_export.py`）：範圍全部／游標區間，可縮點（上限預設 10M），欄名 `CH1(V)`，時間位數依最小相異間隔。
- `max_points()`：HD3 100M、3000G 4M、Infiniium 查 `:ACQuire:POINts:MAXimum?`。InfiniiVision 的點數由時基決定（20 ns/div 只有 2000 點），`:ACQuire:POINts` 設了無效。
- Infiniium 存檔轉取整筆記錄（`:DISK:SAVE ALL` → `GETFILE?` → `DELete`），「點數」只當上限，超過丟 ScopeError，不改使用者記憶體深度。
- Web 擷取頁（`tab_capture.js`）通道選項一律列 CHAN1～8（EXR 最多 8 通道），`capture_info` 回報已開啟者預設勾選，其餘不勾；後端本就收 CHAN1–8。勾選關閉中的通道行為未驗；Qt 版 `ui/tab_capture.py` 未改（仍只列開啟通道）。

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
| `docs/驗證.md` | 逐輪實測紀錄（append-only） |
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

## Liquid Glass（2026-10-26，P1～P3 已合入 main）

- 計畫：`docs/archive/LiquidGlass風格計畫.md.gz`。Web 採深色單一主題，Qt 不動；`app.css` 放 tokens，`glass.css` 最後載入。浮動面板不加圓角。`browser_check.py` 有 `glass_smoke`。
- 效能：headless Chrome 浮層拖曳 60fps，增幅 0%。**WKWebView／WebView2 實機驗收尚未做**（`docs/驗證.md` #26）。
- 軸刻度 `tickLabel`：格距超過三位有效數字只取兩位、電壓換 mV。

## I3C（2026-10-26，P2～P4 已完成）

- 計畫：`docs/archive/I3C解碼計畫.md.gz`。契約 version=2 加 decode（job）／decode_frames／decode_bits／export_decode；`analysis_decode.py` 鎖內快照＋gen 檢查；B 區「解碼 (N)」分頁（`decode.js`／`decode_table.js`）；主圖下方標註列（狀態色 transaction、hex／第九位、逐 bit）。報告含解碼段落，完整請求約 7.3 MB < 8 MB。
- **無實測波形**，待與示波器內建 I3C 解碼比對（事件、時間、第九位、DAA／IBI、錯誤判定）。

## 多協定解碼與 X6000A 實機資料（2026-10-27）

**計畫與狀態**
- 計畫 `docs/archive/多協定解碼計畫.md.gz`（Codex 三輪審查；Q1–Q11 全照建議）。**使用者 2026-10-27 說「可以開工」**：第 0 步與 I2C／UART 接線已完成並 commit，畫面「協定」下拉可選 I3C／I2C／UART。SPI／CAN 尚無模組，後端回「此協定尚未實作」。
- **第 0 步 `47f3985`**：後端 `analysis_decode.NAMES` 依協定匯入模組、`logic.prepare／levels_at`、`synth.py`；前端協定定義檔（`decode_protocols.js` 每協定一行、`decode_i3c.js` 範本）＋資料驅動表單（設定兩列）、標註列雙 lane／bit 代碼 X／S／單取樣欄位、報告與 mock 由定義檔驅動；契約只改 `types_doc` 說明（version 仍 2）。I3C 五組基準指紋（lead 腳本在 session scratchpad，不入庫）前後完全相同。驗證：模組自檢、`selfcheck_node`（含新 `decode_proto_check.mjs`）、`e2e_check`、`browser_check` 全綠。
- 接線 commit：`decode_i2c.js`、`decode_uart.js` 各加一行註冊；UART 預設 8N1、雙 lane（TX／RX）、`invert` 勾選；`browser_check` 的 `protocol_pages()` 對兩者用各自 fixture 實跑（開檔→選協定→解碼→表格→點選跳轉→CSV→標註列→兩種寬度）。
- 修過的小坑：Codex 把 `protocol_pages` 呼叫放進沒有 `out` 的函式；「1000px 設定列必須溢出」的舊斷言在兩列版面不成立（改為不溢出或可捲到）；I2C／UART fixture 通道名要 `CHAN1／CHAN2`；UART fixture 案例間距要 >2 字元否則被分組成一個 frame。`i2c_decode.REQUIRE_EDGES=True` 與計畫「只有 I3C」不同，保留（I2C 整段無轉態本來就無意義）。

**實機資料**（`X6000A-解碼/{I2C,RS-232,CAN}/`，DSO-X 6004A；每組 png／bin／h5／csv，csv＝示波器序列表＝真值；規格與格式表在 `docs/研究_X6000A實機解碼資料分析.md`）
- H5 固定 64516 點、無通道標籤；BIN（`AG10`）＝H5 每 33 點取 1 點（1955 點），只多標籤（SDA1／SCL1／TX1／RX1），**不可用來解碼**。兩者都是螢幕解析度，非記憶體全長。CSV 時間僅 4 位有效數字，比對要容差。
- CAN 約 50 kbps，H5 每位元僅 ~2.6 點，**檔案不可解**，需 SCPI `:WAVeform:POINts:MODE RAW` 取完整記憶體。

**已完成（Codex 實作、Claude 審查，皆已 commit，尚未接 UI／API）**
- **I2C `1ae664f`**：`web/i2c_{decode,synth,vectors,check,real_check}.py`。實機 48 列與 CSV 位址／資料／缺少確認／Restart 全相符；解出時間比 CSV 早約 0.7 取樣，容差放寬 1 取樣並如實列出。CSV 的 `X`＝`ninth=1`（含讀最後 byte 的正常 NACK，不產生 `nack`）。
- **UART `a3c0c15`**：`web/uart_*.py`＋分析文件「附錄：UART 錯誤規則」。實機＝19200 baud、LSB first、**反相**；波形像 8O1，但示波器以 **8N1** 解（第九位當 stop，=0 報錯），故 CSV `Unknown Rx/Tx Error`＝我方 framing；27.68 ms 的 TX `31` 是兩種規則的分辨反例。CSV 時間：字元／空白列＝start＋0.5T，錯誤列＝第一 stop＋9.5T。131 列中 130 列可驗相符，首列 `?/65`（視窗前截斷）無法還原。**預設格式定案 8N1**（baud 必填；X6000A 這份要勾反相）。內部私有 `_levels_at`，第 0 步後改用 `logic.levels_at`。
- **BIN `8143a43`、`0f09887`**：`storage/bin_reader.py`（`read_bin_bytes`／`read_bin_file`／`guess_roles`）；與 H5 只差 float32 捨入（≤1.2e-7 V，容差 4e-7；原規格寫「逐點相等」有誤，已更正）。已接 `reader.py` 的 `.bin` 分派（通道名＝標籤，重複加 `#2`）與開檔對話框；`open_waveform` 實測可開。**GUI 開 BIN 的畫面行為未人工驗。**
- 解碼核心照計畫介面（`ROLES／BASE／options／run`）寫成，註冊表接線只需加一行。小項：UART 實機驗收用 h5py（核心只用 numpy）。

**2026-10-27 追加（`f5de088`，使用者已人工確認畫面）**
- **I2C `addr_bits`**（7｜8，預設 7）：只影響顯示（事件表位址欄、標註列、報告、CSV），解碼與 frames 不變；8 模式只套用一般 7-bit 位址 0x08–0x77，10-bit／General Call／START byte／Hs／保留位址維持原顯示。顯示用送出解碼時的選項快照（`decodeResult.options`）；`columns.cell(f,o)`、`fieldText(x,o,f)`、`content(f,o)` 多收選項。計畫 §3.1／§3.5 已改為已做。
- **標註列分列**：事件／（bit，放大到逐 bit 時）／hex／ASCII 各一列；高度依列數動態（`bandHeight(state)`，40／60／80px，取代固定 `BAND_H` 作為版面依據；`tab_analysis.js` 與 `.analysis__decodeband` 高度由 JS 設）。ASCII 開關關閉則無 ASCII 列。UART 最下方一條共用 ASCII 列，TX／RX 重疊時優先 TX。副作用：縮放跨過逐 bit 門檻時列高會跳 20px、主圖微幅伸縮。
- **UART「估計」按鈕**：推翻計畫 Q2「不做自動鮑率」，改為**手動觸發**、填入鮑率欄讓使用者確認。沿用 decode job（options `estimate:true`，後端回 `ok=False`、reason `估計鮑率 N` 或 `無法估計鮑率：…`，前端解析），契約只補說明、無新 RPC。演算法：邊緣間距對標準鮑率表，取**最低**通過者（最短脈寬 ≥0.8T 且 ≥95% 間距為 T 整數倍、誤差 ≤8%）；TX／RX 各估一次取較有把握者。實機 `x6000rs234.h5` 兩通道皆得 19200。已知限制：只含雙 bit 脈寬時估成一半；1000000 估成 921600。估計不清除既有 `decodeResult`／選取（`decode.js` `estimate()`）。
- 測試踩坑：①`browser_decode_checks` I2C 標註列斷言的視窗須 ≥3 ms，1 ms 會進逐 bit 模式不畫位址文字；②UART 估計測試把鮑率改錯會使結果過期、匯出鈕停用，須重新解碼才能接後面的匯出檢查。
- 使用者指出「定義上緣下緣訊號（Pull Low／Pull High 極性）」後自述誤判、撤回，未做；若日後再提，候選是每條訊號線可反相（UART 現有 `invert` 可併入）。

**待辦**
1. 依下方「九協定解碼實作計畫」P1 起做（SPI 為第一項；無實機資料，只有合成向量）。
2. H5 無標籤時的通道指派 UI（BIN 可 `guess_roles`）；人工看 BIN 開檔畫面。
3. CAN：先決定是否在擷取流程加「取完整記憶體」。**先做真機驗證，再決定要不要改程式**（2026-11-12 查證）：
   - InfiniiVision（`instruments/infiniivision.py:135`）已有 `:WAVeform:POINts:MODE RAW`＋`:WAVeform:DATA?` 直讀。
   - Infiniium（`instruments/infiniium.py`，含 DSO-X 6004A）**沒有**這條命令：`capture()` 走 `:DISK:SAVE:WAVeform ALL,…,H5INt,ON` → `:DISK:GETFILE?` → `:DISK:DELete`，只用 `:WAVeform:POINts?`（第 75 行）查記錄長度並與設定點數比較。註解稱此路徑只在 MXR254B 驗過，6004A 未驗。
   - `:DISK:SAVE` 不吃 `:WAVeform:POINts:MODE`，所以加 MODE 不會讓存檔變完整；只會讓 `POINts?` 在 RAW 時回完整記憶體長度、NORMal 時回螢幕點數，因此**會改變第 77 行的「超過點數即拒絕」判定**。MODE 是設定命令，會動示波器狀態（測試前記下並還原），RAW 需 STOP（`_prepare_capture` 已先 STOP，順序仍須確認）。
   - 待做驗證：在 6004A 上用 `capture()` 擷取一次 CAN 訊號，看回來的 `NumPoints` 與每位元點數（目標 ≥ 8 點／位元）。已是完整記憶體 → 不需改；只有螢幕點數（約 64516）→ 才改用 `:WAVeform` 直讀路徑或調整存檔設定。與 X6000A 手動存檔的 H5（固定 64516 點）無關，那批檔案不可解。

## 九協定解碼準則與實作計畫（2026-11-12，只有文件，尚未寫任何程式；文件已 commit `fad2e7d`、`5f29f26`）

- **使用者要求**：先分析 `rea/Protocols/`（Keysight Infiniium 協定 XML，untracked）可用的解碼準則，涵蓋 I2C／I3C／SPI／eSPI／CAN／CAN FD／RS-232／RS-485／USB PD；再規劃實作。**使用者明講「不要對任何程式編寫，先將計劃寫好後續再安排」**——§11 已由使用者回覆（見下），下一步等使用者**明確下令開工**（波 0 → 波 1）。
- **產出兩份文件（已 commit；`rea/Protocols/` 原廠 XML 已進 `.gitignore`，不入庫）**：
  - `rea/Protocols分析_解碼準則.md`：Opus 與 Codex 各自分析＋交叉比對；「〇之二」是 Claude 與 Codex 兩輪審查後的定案（附錄 A 已就地改正，附錄 B 保留 Codex 原文）。
  - `docs/解碼實作計畫_20261112.md`：每協定的界線（做／不做／可動檔案）、介面、偽代碼、向量與 `--mutations`、共享檔變更表、排程閘門、使用者決定 D1–D8。SPI／CAN 細部仍以 `docs/archive/多協定解碼計畫.md.gz` §4／§6 為準。
- **準則要點**：XML 只有欄位表／列舉／固定值檢查，位元切割、去填充、CRC 都在外部引擎與 `agProtocols.dll`，不能單靠 XML 解波形；SPI／RS-232／RS-485 沒有 XML。
- **審查改正的五個錯誤（勿回退）**：①USB PD 殘值用 `zlib.crc32(data+crc_le)` 是 0x2144DF1C（0xC704DD7B 是另一種暫存器表示）；②RS-485 極性：TIA-485 是 A<B 為 mark，晶片腳位命名常相反 → 極性必須可設定；③CAN intermission 是 3 位（`CAN.xml` 寫 2 位，不照 XML）；④`addr_bits=8` 不含 `I2CIgnoreRW.xml` 的 10-bit→11-bit 顯示；⑤CAN FD 的 CRC delimiter／ACK 1–2 位是接收端容差。
- **已實算**：CAN CRC-15（0x4599、初值 0、去填充後 SOF..DATA）對 `X6000A-解碼/CAN/x6000can.csv` 208/209 列吻合（CSV 212 列、209 列有 CRC）；eSPI CRC8（0x07、初值 0）`"123456789"`→0xF4、`25`→0xFB、`21 00 04`→0x34、`08 0F 03`→0x9B；USB PD header `41 01` → CRC32 0xDFBC5C2D。
- **有規格依據、待向量驗證**：CAN FD CRC 含動態填充位與 stuff count、不含固定填充位（CRC-17 共 6 個、CRC-21 共 7 個），ISO 初值最高位為 1；I3C HDR-DDR CRC5（x⁵+x²+1、初值 0x1F）、P1＝奇數位 XOR、P0＝偶數位 XOR 再反相；eSPI 固定上升緣取樣。
- **計畫順序**：P1 SPI → P2 CAN → P3 RS-485 → P4 CAN FD → P5 eSPI → P6 USB PD → P7 I3C HDR-DDR（P3／P4／P5 可在 P2 後並行）。I2C／I3C SDR／RS-232 不需工作。
- **2026-11-12 使用者已決定 D1–D8 全部照建議（計畫 §11）**；尚未下令開工。**開工順序**：波 0（Opus 一次改共享檔：`espi`／`usbpd` 加入 `NAMES`＋契約列舉＋`docs/web-api契約.md`＋`mock_catalog.js`／`mock_backend.js`／`l0_*.mjs`，跑 `l0_check`、`selfcheck_node`、`contract_check`、`analysis_check`）→ 波 1（SPI∥CAN∥RS-485 各開 worktree，diff 只能含自己的檔案＋`decode_protocols.js` +1 行＋規格文件自己那節）→ 依序合併並全套驗證 → 波 2（eSPI 需 SPI 已合併、CAN FD 需 CAN 已合併、USB PD 獨立）→ 波 3 I3C HDR（可選）。給 Codex 的提示須寫明 `</dev/null`，手寫真值（CRC 參考值）由計畫提供、Codex 不自行推導，解碼器與真值向量不由同一 agent 產出。分工建議：共享檔／CAN 狀態機／CAN FD／USB PD BMC／I3C HDR／審查合併／真機驗證由 Opus；SPI、RS-485、eSPI、各協定周邊與前端、突變檢查由 Codex；波 1 可並行 SPI∥CAN∥RS-485，合併一次一個。
- **已定案的設計**：RS-485 併入 `uart`（加 `tx_n`／`rx_n`＋`DIFF`，極性沿用 `invert`）；CAN FD 沿用 `can`（填 `data_bitrate` 才細解，**推翻舊計畫 Q1「不做」**）；eSPI／USB PD 要新增協定名 `espi`／`usbpd`，須 lead 一筆改 L0 契約檔（version 維持 2）；eSPI 第一版只做單線、USB PD 第一版 Data Object 只列原值。
- **風險**：SPI／eSPI／CAN FD／I3C HDR 沒有實機資料，合成器與解碼器同源，閉環測不出共同誤解；CAN FD 需至少一筆外部真值，否則標「未經外部驗證」；CAN H5 約 2.6 點／位元不足以驗判位，要 RAW 重錄（≥8 點／位元）；USB PD 最容易取得實機資料（充電器交涉序列，≥10 MSa/s）。
- **SPI 進度**：使用者曾說「依照此準則開始實作 SPI 解碼」，讀完範本（`uart_*.py`、`decode_uart.js`、`decode_proto_check.mjs`、`protocol_pages()`）後被改為先寫計畫；**SPI 檔案一個都還沒建**。契約的 `spi` 列舉已存在、`NAMES` 已含 `spi`，不必動共享檔。
- 工具備忘：`codex` MCP 連不上，改用 `codex exec --sandbox read-only "$(cat prompt.txt)" </dev/null`（逾時用 `perl -e 'alarm N; exec @ARGV'`）；zsh 下 `echo ====`、未加引號的 `--include=*.py` 會出錯。
