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
- **未驗證／已知限制**：沒有真機；沒有真人滑鼠手感（拖曳／滾輪）；真正的 pywebview 視窗只確認可啟動 10 秒未崩潰；Win10／WebView2／PyInstaller 打包（`packaging/`、`requirements-web.txt`）完全未驗；剪貼簿與 `<a download>` 在 pywebview 的行為未驗；1000×700 FFT 高度已補 Node 斷言與瀏覽器待驗項；Track Measurements 已接事件座標（實機比對仍待驗）；100M×4 記憶體仍是既有上限。逐項清單：`docs/驗證.md`。
- 後續：真人／真機驗收後勾清單；Win10 打包；大檔 h5py 懶載入（選配）；validate_params 已接 `server.py:86`（登記工作前同步回 BAD_REQUEST）；確認穩定後再決定是否刪除 `ui/` 與 Qt 入口。

## 已完成功能的歷史細節（2026-10-24～28：分析頁 GUI、Marker Table、介面美化、版面編輯器、多檔比對、文件整理匯出、Liquid Glass）

- 原文存於 `docs/archive/HANDOFF_歷史_20261112.md.gz`（`gzip -dc` 讀）。
## 離線分析修正線：Jitter／ΔY/ΔX／草案

- 已 commit：游標表 ΔY/ΔX（`1014c05`）；`marker.py` versus 不給斜率（`52b5c90`）；草案 `docs/archive/草案_Jitter與RMS.md.gz`；`docs/驗證.md`（至第四輪）。
- DSO-X 6004A（10 MHz 方波）：示波器 TIE≈0.842×離線線性擬合 TIE−250.7 ps，σ 對 50% 中點門檻極敏感。頻譜比值檢查（第四輪）：增益各頻帶平坦約 0.85，無追蹤跡象，不能用此樣本校準 PLL 頻寬。原始資料在 `示波器截圖/N8900A/DSOX6004A_Jitter驗證_20261024/`（gitignore、無備份）。
- **契約 v3 先不升**（使用者決定）：要改 L0 檔（`docs/web-api契約.md`、`api_contract.json`、`mock_catalog.js`、`mock_backend.js`、`l0_*.mjs`，不是 `scope_tool/contracts.py`），須同一筆含 mock 同步＋Analysis 3 個 stub，否則 `l0_check`、`selfcheck_node`、`contract_check`、`analysis_check` 失敗。v3 只為 Jitter／眼圖新增 3 個 RPC，與 GUI 的 `view.*` 無關。順序：v3 一筆落地 → Jitter／眼圖後端（`jitter_eval`、`eye_density`、`export_timing`）→ 前端面板。
- 草案要點：revision 以 `Analysis._accept`＋`submit(on_accept=...)` 在 `_tbl_lock` 內配號；`export_timing` `job=false`；`validate_params` 已接 `server.py:86`（錯參同步回覆，`e2e_check` 已同步）；PLL 只接受 `mode=手動`、捕獲 ±1000 ppm、失鎖門檻暫 ±1500 ppm。`analysis/*` 歸 T7。
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
3. 已知剩餘小項：RF 跳峰仍是 O(n) 約 0.1 s（8M bin）；「FFT 快取依賴 `fft.refresh()`／切 log 軸重算／重入被忽略」僅指 Qt。Web `fft_runner.js` 依資料與參數簽章排程、用 token 丟棄舊結果，log 軸僅重畫。
4. 解碼：I3C 真機波形與示波器內建解碼比對（`docs/驗證.md` 第 26 項）；多協定計畫見下方「多協定解碼」與「九協定解碼準則與實作計畫」（`docs/解碼實作計畫_20261112.md`，待使用者核可後開工）。
5. 離線分析 UI 修正：D1～D6 已確認、規則已授權；階段 A～D 全部完成（2026-11-13）；剩真視窗人工確認（見「離線分析 UI 修正第二輪」）。
6. 基本量測真機校準：Top/Base 直方圖範圍與格數（N9），見「基本量測審查與修正」。
8. 分析頁選單與拖放的人工確認與後續（見「分析頁選單與拖放」）：真視窗手感、Qt 版延後；選單 `role="menu"`／方向鍵已完成，`toolbar_check.mjs` 已存在並登記完整 Node 自檢。
7. 可選缺口：已於 2026-11-13 全部做完（W0～W8，見「離線分析可選功能」段）；剩真機比對與 Qt 版。

9. **使用者改進點（2026-11-13，共 8 項，僅 Web，尚未規劃）**：
   1. 框選模式下 Marker 線一移動就變成框選；兩種動作要分開、互不影響（`gestures.js`／`cursors.js`，注意兩檔行數上限）。
   2. 框選開啟時狀態不夠明顯（工具列「框選」鈕開關底色落差小）；開啟時改明顯底色。
   3. 通道別名可自行更改；通道標籤改畫在波形區內（現在在左側欄，見使用者截圖 `Mem1.Function 2`／`Function 1`，不得壓縮波形視窗）；標籤底色可選透明或有底色；以「讓使用者看得見波形」為優先。
   4. Marker Table 標示可連動，也可獨立選用通道，讓使用者明顯標示。
   5. 「解碼」選項也放進「分析 ▾」下拉選單。
   6. FFT 頻譜可手動加入 Marker 點；加入時基準線功能仍保留，且基準線改名為 **Peak Line**。
   7. I2C 讀參考檔（`H5參考波形/i2cdemo.h5` 等）出現「時間軸不一致」而無法解碼（使用者補充：`H5參考波形/i2cdemo.h5` 為實機擷取的 I2C 波形、`i2cdemo.csv` 為示波器的解碼報告，可當期望值對照：12 行，Time 從 -5.02 ms 到 +2.2 ms 以上，含 Start／Restart、Addr 0x50、Ack／Nack、Data 如 `41 47 49 4C 45 4E 54`；待重現：確認是檔案本身 SCL／SDA 時間軸不同，還是解碼器對取樣起點／間隔的檢查過嚴；尚未動程式）。
   8. 解碼表點選事件時，波形區在該事件位置顯示小三角形標示（需先定：畫在哪個通道／格、與既有游標或高亮的關係；與項 3 通道標籤、分格並存時不遮波形）。
   - **已決策（2026-11-13，全採建議）**：命中線拖線、Shift 仍強制框選（中鍵／Space 平移）；別名先只留本次載入；標籤底色逐通道、預設透明；Marker Table 首波只在新增時選通道、保留單一連動 M1；「解碼…」只開設定、仍由使用者按解碼；FFT 手動點上限 10、換來源／換檔清除、Phase 暫不開放。分波：①項 1、2、5、7（7 先重現定位）→②項 4 →③項 6、8 →④項 3（先給 UI 預覽）。
   - **項 7 後續：I2C 自動辨識 SCL／SDA 角色（2026-11-13，使用者「照建議」D1–D7 全採；規劃：scratchpad `out/i2c_roles_plan.md`）**：實機 `i2cdemo.h5` 為 Memory 1＝SDA、Memory 2＝SCL，預設依通道順序帶入會得 0 個位址；對調後 11 筆與 csv 相符（START 時間 csv 晚約 10.8 µs，原因未確認；另有 2 個無位址 frame 待查）。做法：後端 `i2c_roles.py` `estimate_waveforms`（兩方向各解一次比「有位址封包數」，需 ≥2 倍且 ≥1 筆、SCL 邊沿數須多於 SDA，否則「無法判斷」不改）；契約方法／型別／version／store 鍵不動。分兩波：波 A＝「位址位元」旁「辨識角色」按鈕（對調兩下拉，手動門檻連門檻一起換，不做還原鈕）；波 B＝角色為依順序猜且使用者沒動過下拉時，按「解碼」前自動辨識，對調說明常駐警告列並進報告、另跳提示。只做 I2C。授權待開工時登記：新檔 `i2c_roles.py`、`browser_i2c_roles_checks.py`；解凍 `analysis_decode.py` 兩行、`decode_i2c.js`、`mock_decode.js`、`decode.js`（波 B 限 defaultConfig／change／run）、`decode_table.js` 一行（波 B）。波 A 已 commit（`05005bc`）；波 B 已由 Codex 實作、尚未驗收（見檔尾）。

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

## 多協定解碼與 X6000A 實機資料（2026-10-27）

**計畫與狀態**
- 計畫 `docs/archive/多協定解碼計畫.md.gz`（Codex 三輪審查；Q1–Q11 全照建議）。**使用者 2026-10-27 說「可以開工」**：第 0 步與 I2C／UART 接線已完成並 commit，畫面「協定」下拉可選 I3C／I2C／UART。（SPI／CAN 等後續已全部實作，見下方「九協定解碼」。）
- **第 0 步 `47f3985`**：後端 `analysis_decode.NAMES` 依協定匯入模組、`logic.prepare／levels_at`、`synth.py`；前端協定定義檔（`decode_protocols.js` 每協定一行、`decode_i3c.js` 範本）＋資料驅動表單（設定兩列）、標註列雙 lane／bit 代碼 X／S／單取樣欄位、報告與 mock 由定義檔驅動；契約只改 `types_doc` 說明（version 仍 2）。I3C 五組基準指紋（lead 腳本在 session scratchpad，不入庫）前後完全相同。驗證：模組自檢、`selfcheck_node`（含新 `decode_proto_check.mjs`）、`e2e_check`、`browser_check` 全綠。
- 接線 commit：`decode_i2c.js`、`decode_uart.js` 各加一行註冊；UART 預設 8N1、雙 lane（TX／RX）、`invert` 勾選；`browser_check` 的 `protocol_pages()` 對兩者用各自 fixture 實跑（開檔→選協定→解碼→表格→點選跳轉→CSV→標註列→兩種寬度）。
- 修過的小坑：Codex 把 `protocol_pages` 呼叫放進沒有 `out` 的函式；「1000px 設定列必須溢出」的舊斷言在兩列版面不成立（改為不溢出或可捲到）；I2C／UART fixture 通道名要 `CHAN1／CHAN2`；UART fixture 案例間距要 >2 字元否則被分組成一個 frame。`i2c_decode.REQUIRE_EDGES=True` 與計畫「只有 I3C」不同，保留（I2C 整段無轉態本來就無意義）。

**實機資料**（`X6000A-解碼/{I2C,RS-232,CAN}/`，DSO-X 6004A；每組 png／bin／h5／csv，csv＝示波器序列表＝真值；規格與格式表在 `docs/研究_X6000A實機解碼資料分析.md`）
- H5 固定 64516 點、無通道標籤；BIN（`AG10`）＝H5 每 33 點取 1 點（1955 點），只多標籤（SDA1／SCL1／TX1／RX1），**不可用來解碼**。兩者都是螢幕解析度，非記憶體全長。CSV 時間僅 4 位有效數字，比對要容差。
- CAN 約 50 kbps，H5 每位元僅 ~2.6 點，**檔案不可解**，需 SCPI `:WAVeform:POINts:MODE RAW` 取完整記憶體。

**已完成（Codex 實作、Claude 審查，皆已 commit，尚未接 UI／API）**
- **I2C `1ae664f`**：`web/i2c_{decode,synth,vectors,check,real_check}.py`。實機 48 列與 CSV 位址／資料／缺少確認／Restart 全相符；解出時間比 CSV 早約 0.7 取樣，容差放寬 1 取樣並如實列出。CSV 的 `X`＝`ninth=1`（含讀最後 byte 的正常 NACK，不產生 `nack`）。
- **UART `a3c0c15`**：`web/uart_*.py`＋分析文件「附錄：UART 錯誤規則」。實機＝19200 baud、LSB first、**反相**；波形像 8O1，但示波器以 **8N1** 解（第九位當 stop，=0 報錯），故 CSV `Unknown Rx/Tx Error`＝我方 framing；27.68 ms 的 TX `31` 是兩種規則的分辨反例。CSV 時間：字元／空白列＝start＋0.5T，錯誤列＝第一 stop＋9.5T。131 列中 130 列可驗相符，首列 `?/65`（視窗前截斷）無法還原。**預設格式定案 8N1**（baud 必填；X6000A 這份要勾反相）。內部私有 `_levels_at`，第 0 步後改用 `logic.levels_at`。
- **BIN `8143a43`、`0f09887`**：`storage/bin_reader.py`（`read_bin_bytes`／`read_bin_file`；`guess_roles` 僅留自檢引用，為產品路徑死碼，已由 `decode.js defaultConfig`＋來源下拉取代）；與 H5 只差 float32 捨入（≤1.2e-7 V，容差 4e-7；原規格寫「逐點相等」有誤，已更正）。已接 `reader.py` 的 `.bin` 分派（通道名＝標籤，重複加 `#2`）與開檔對話框；`open_waveform` 實測可開。**GUI 開 BIN 的畫面行為未人工驗。**
- 解碼核心照計畫介面（`ROLES／BASE／options／run`）寫成，註冊表接線只需加一行。小項：UART 實機驗收用 h5py（核心只用 numpy）。

**2026-10-27 追加（`f5de088`，使用者已人工確認畫面）**
- **I2C `addr_bits`**（7｜8，預設 7）：只影響顯示（事件表位址欄、標註列、報告、CSV），解碼與 frames 不變；8 模式只套用一般 7-bit 位址 0x08–0x77，10-bit／General Call／START byte／Hs／保留位址維持原顯示。顯示用送出解碼時的選項快照（`decodeResult.options`）；`columns.cell(f,o)`、`fieldText(x,o,f)`、`content(f,o)` 多收選項。計畫 §3.1／§3.5 已改為已做。
- **標註列分列**：事件／（bit，放大到逐 bit 時）／hex／ASCII 各一列；高度依列數動態（`bandHeight(state)`，40／60／80px，取代固定 `BAND_H` 作為版面依據；`tab_analysis.js` 與 `.analysis__decodeband` 高度由 JS 設）。ASCII 開關關閉則無 ASCII 列。UART 最下方一條共用 ASCII 列，TX／RX 重疊時優先 TX。副作用：縮放跨過逐 bit 門檻時列高會跳 20px、主圖微幅伸縮。
- **UART「估計」按鈕**：推翻計畫 Q2「不做自動鮑率」，改為**手動觸發**、填入鮑率欄讓使用者確認。沿用 decode job（options `estimate:true`，後端回 `ok=False`、reason `估計鮑率 N` 或 `無法估計鮑率：…`，前端解析），契約只補說明、無新 RPC。演算法：邊緣間距對標準鮑率表，取**最低**通過者（最短脈寬 ≥0.8T 且 ≥95% 間距為 T 整數倍、誤差 ≤8%）；TX／RX 各估一次取較有把握者。實機 `x6000rs234.h5` 兩通道皆得 19200。已知限制：只含雙 bit 脈寬時估成一半；1000000 估成 921600。估計不清除既有 `decodeResult`／選取（`decode.js` `estimate()`）。
- 測試踩坑：①`browser_decode_checks` I2C 標註列斷言的視窗須 ≥3 ms，1 ms 會進逐 bit 模式不畫位址文字；②UART 估計測試把鮑率改錯會使結果過期、匯出鈕停用，須重新解碼才能接後面的匯出檢查。
- 使用者指出「定義上緣下緣訊號（Pull Low／Pull High 極性）」後自述誤判、撤回，未做；若日後再提，候選是每條訊號線可反相（UART 現有 `invert` 可併入）。

**待辦**
1. 九協定解碼已全部完成；下一步用真機錄 USB PD／CAN FD／eSPI／SPI 波形驗證（見「九協定解碼」的限制）。
2. H5／BIN 已共用 `decode.js defaultConfig`（名稱角色優先、否則依順序）＋來源下拉；`guess_roles` 為死碼。仍待人工看 BIN 開檔畫面。
3. CAN：先決定是否在擷取流程加「取完整記憶體」。**先做真機驗證，再決定要不要改程式**（2026-11-12 查證）：
   - InfiniiVision（`instruments/infiniivision.py:135`）已有 `:WAVeform:POINts:MODE RAW`＋`:WAVeform:DATA?` 直讀。
   - Infiniium（`instruments/infiniium.py`，含 DSO-X 6004A）**沒有**這條命令：`capture()` 走 `:DISK:SAVE:WAVeform ALL,…,H5INt,ON` → `:DISK:GETFILE?` → `:DISK:DELete`，只用 `:WAVeform:POINts?`（第 75 行）查記錄長度並與設定點數比較。註解稱此路徑只在 MXR254B 驗過，6004A 未驗。
   - `:DISK:SAVE` 不吃 `:WAVeform:POINts:MODE`，所以加 MODE 不會讓存檔變完整；只會讓 `POINts?` 在 RAW 時回完整記憶體長度、NORMal 時回螢幕點數，因此**會改變第 77 行的「超過點數即拒絕」判定**。MODE 是設定命令，會動示波器狀態（測試前記下並還原），RAW 需 STOP（`_prepare_capture` 已先 STOP，順序仍須確認）。
   - 待做驗證：在 6004A 上用 `capture()` 擷取一次 CAN 訊號，看回來的 `NumPoints` 與每位元點數（目標 ≥ 8 點／位元）。已是完整記憶體 → 不需改；只有螢幕點數（約 64516）→ 才改用 `:WAVeform` 直讀路徑或調整存檔設定。與 X6000A 手動存檔的 H5（固定 64516 點）無關，那批檔案不可解。

## 離線分析 UI 審查與修正計畫（2026-11-12，計畫已定、尚未編碼）

- 流程：Opus 實測＋Codex 讀碼審查 → Opus 排計畫 → Codex 編碼 → Opus 驗收。審查未改任何程式。
- 計畫書：`docs/離線分析UI修正計畫_20261112.md`（P1～P5，每階段可單獨 commit；含 file:line、須同步更新的測試、三種尺寸驗收條件）。
- 審查結論：整頁無橫捲，但 Horizontal 列（內容 1142px）與 FFT 參數列（1728px）內部溢出；工具列固定兩行；900×600 展開電壓控制會截掉 X 軸刻度；B 區預設 150px 放不下解碼／游標表；量測流程呈 Z 字移動；「關閉」「清除全部」「×」無隔開也無確認。
- 階段：P1 去橫捲＋刪重複「完整時間」＋右側欄門檻 900→1280；P2 工具列縮回一行（來源／範圍／閾值入左欄、Math 變通道列「＋」、「X軸Maker歸位」改「游標置中」）；P3 FFT 次要參數收進「更多…」；P4 按鈕重排與危險動作確認；P5 術語、空狀態、鍵盤操作、解碼分頁自動加高。
- 預設決策 D1～D6（Marker 模式與游標置中留工具列、FFT 開關留工具列、FFT 次要參數進彈窗、危險動作加確認、下方頁籤中文、解碼分頁自動加高）**待使用者確認**；另需使用者授權：RULES.md 補一段（工作跨 L4／L5／L6／L8）與解凍 `decode_table.js`（只為「解碼」鈕移位）。
- 本輪不做：通道欄固定 246px（兩個既有測試鎖定）；1100×700 左欄垂直捲動維持。
- 暫存：工作樹 `../ui-fix`（分支 `ui-fix`，目前與 main 同一提交，無改動）；審查原始報告與量測腳本在本次 session 的 scratchpad，不入庫。

## 離線分析 UI 修正第二輪（2026-11-13，階段 A～D 全部完成；僅 Web）

- **決定**：使用者 D1～D6 全照預設（Marker 模式與游標置中留工具列、FFT 開關留工具列、FFT 次要參數進「更多…」、關閉／清除全部／× 加確認、下方頁籤中文、解碼分頁自動加高），並授權 RULES.md 補段（已貼檔尾）與解凍 `decode_table.js`（只為「解碼」鈕移位）。D7＝停靠門檻 1280（殘留橫捲接受）、D8＝「更多…」內下拉先照做，待真視窗確認。
- **計畫書**：Opus 版 `plan2_opus.md`、Codex 版 `plan2_codex.md` 在上一個 session 的 scratchpad（不入庫）；重點已寫在本段。四階段**依序做、不平行**（都改 `analysis.css`／`toolbar.js`／`results.js`）。
- **階段 A（`4d24553`）**：「完整時間」移到 ↷ 後；「⬚ 框選放大」→「⬚ 框選」；「時間軸位移」→「位置」；範圍讀值去「範圍 」前綴；欄寬 12ch；水平列 `container-type: inline-size`，≤1000px 隱藏讀值、≤820px 隱藏 ◀▶；`DOCK_MIN_VW` 900→1280。
- **階段 B（尚未 commit 時寫入，見 git log）**：FFT 次要參數（阻抗、R、排序、基準線、顯示數量）收進 `更多…` popover（`fft_state.js` 加 `impHost`、`toolbar.js` 掛 `popMenu`）；RBW 狀態文字可縮、title 放全文；「FFT 計算」checkbox 從「分析 ▾」移回工具列（[分析 ▾] 與 Marker 之間），「分析 ▾」只剩「FFT 頻譜 ↗」「Math…」。`browser_check.py:213/215` 原地改（維持 300 行），`browser_menu_checks.py` 加「更多…」三尺寸檢查（132 行）。實測 FFT 列：1400／1280／1100／900(點 FFT 頁籤) 皆單列 40px、無橫捲、可見 label 4 個。
- **階段 B 測試踩坑**：`c.wait()` 的運算式必須回布林，回 DOM 元素會永遠逾時（要加 `!!`）；測 FFT 列要先 `getFftState().setAnalysisOn(true)`，並點 `[data-pane=fft]`（若存在）才會顯示 `.analysis__fftsection`。
- **階段 C（`1108046`）**：「關閉」（有量測／衍生通道／比對槽才問）、「清除全部」「衍生通道 ×」皆用 `ui.confirm`；B 區頁籤移左、「清除全部」加分隔並置末；「解碼」鈕移到參數列最前（`decode_table.js` 一行，1400／1280／1100 皆可見；900 的 B 區預設收折）；Vertical ▲／歸零對調；`browser_check.py` 的分隔條取點改為 lower 取 1/2、fft 取 1/4（FFT 收折鈕在 1/2 處）。
- **階段 D**：結果表空狀態文字、單筆刪除改可 Tab 聚焦的 `button.results__remove`（需 CSS 重置字型／行高，否則 `single` 單行檢查失敗）、水平列按鈕 min-height 24、切到「解碼」頁籤時 B 區自動加高（1400／1280＝240、1100／900＝217，主圖 ≥270）。**依使用者指示不把英文改中文**：`terms.js`、`measure.js` 的「範圍」、`Zoom`、`Measure`／`Marker Table` 頁籤維持原樣。
- **待人工**：真視窗（pywebview）開「更多…」後點裡面的下拉，確認 popover 不會被關掉；若會關，改 `more.popover = 'manual'`（約 +3 行）。
- **殘留限制**：停靠在 1280～1310 時水平列最多多 31px、1280～1367 FFT 列最多多 88px，仍靠原本橫捲；RBW 在 1100／900 只剩約 75px 靠 tooltip。
- **流程備忘**：Codex 提示檔放 scratchpad，`codex exec ... -o 絕對路徑 "請讀並照做此提示檔：<路徑>" </dev/null`（別用 `\$(cat)` 逸出）；量尺寸用 scratchpad 的 `measure_plan.py [fft|fftpane]`（不入庫）。

## 離線分析可選功能（2026-11-13，W0～W8 全部完成並 commit；僅 Web，Qt 延後）

- **計畫**：Opus 規劃（`plan_optional.md`，scratchpad 不入庫）、Codex 實作、Opus 驗收；使用者「照預設」「每波自動 commit」。授權見 `RULES.md` 檔尾「離線分析可選功能」與 W8 追加（`gestures.js` 可記錄 `time_offset`）。
- **W0**（`253c58c`）`Analysis.measure` 搬到 `web/analysis_measure.py`（`MeasureMixin`），54 組指紋逐位元相同。
- **W1**（`e867d6c`）Vmid、上升／下降邊緣計數、±脈衝計數，放新名稱表 `EXTRA`（`analysis/measure_extra.py`），**不併入 `measure.MEASUREMENTS`**（否則 Qt 控制項與 `_TIPS` 自檢會連動）。計數用三閾值完整邊緣；+脈衝＝上升後接下降，只算完整脈衝。
- **W2**（`70488e1`）Delta Time（相位延遲）：各來源可設 `edge_num`／`edge_level`（lower|middle|upper）／方向，從量測範圍左緣數起，回 `t2−t1`。獨立驗算誤差 <1e-13·dt。原「延遲」「相位」仍是最近邊緣配對（產品自訂）。
- **W3＋W4**（`1cdea9a`、`1d077bc`）Track Measurements：`measure.current_index` 抽出；`analysis/measure_marks.py` 只對 `track=true` 的列算標記點（MeasureResult `marks`）；前端選 Track 自動追蹤第一列、點列換、主圖標點。**前端絕不寫 `store.cursors`**（游標區間量測會重算迴圈；瀏覽器檢查驗證工作數歸零）。刪除 `summary.js`。追蹤列在 100 萬點週期量測多約 29 ms。
- **W5**（`b0d5f4b`）FFT Phase 參考（`phase_ref`，顯示時間；null＝舊行為）與 `unwrap`，契約必填、version 仍 2；UI 在「更多…」。**符號與核心 `reference_time` 一致（+360·f·Δ）**，計畫原寫 −360 是錯的，Codex 曾加補償抵消核心，已拿掉。
- **W6**（`6caa7c7`）Marker 表加「基準」欄（Delta To，預設 M1）與 ΔV，跨單位顯示「—」，刪基準回預設。測試踩坑：`S.command('marker.remove', id)` 要傳 id 本身，不是 `{id}`。
- **W7**（`a94ed80`）「分析 ▾」加「分開堆疊」（位置式：自動 V/格＋offset、共用格線，非真正分格）與「疊圖（自動縮放）」，整組一次復原。
- **W8**（`4cc6b03`）比對檔「對齊主檔」：用 Delta Time 對第一個上升緣，整槽通道一起移 `time_offset`，可一次復原；沒邊緣時 toast 不改。
- **驗收**：每波 Python／Node 自檢、`e2e_check`、`browser_check` 皆過；Codex 每波常需提示「全部做完才報告」，W3 第一輪曾提早停。
- **只有紙上驗證／待真機**：Delta Time 對 Infiniium（規格 V10，容差 ≤0.1·dt）；有雜訊或突波時計數是否與面板一致（官方用中閾值兩次穿越，本專案三閾值完整邊緣）；Phase 參考與面板比對；真視窗看「更多…」內下拉、堆疊視覺。
- **未做**：FFT 多頻譜疊圖（後端 `_spec` 只有一份）、真正分格（Infiniium Grids）、Qt 版全部。

## 九協定解碼（2026-11-12，波 0～3 全部完成並併入 main）

- **文件**：`rea/Protocols分析_解碼準則.md`（Keysight 協定 XML 分析，含兩輪審查定案；`rea/Protocols/` 原廠 XML 在 `.gitignore`）、`docs/解碼實作計畫_20261112.md`（界線、偽代碼、向量、D1–D8 決定，全照建議）。SPI／CAN 細部原計畫在 `docs/archive/多協定解碼計畫.md.gz`；舊研究在 `docs/archive/研究_解碼協定.md.gz`。
- **現況**：`analysis_decode.NAMES` = i3c／i2c／spi／uart／can／espi／usbpd。各自一個 squash 提交：SPI、CAN、RS-485（併入 `uart` 的 `tx_n`／`rx_n`＋`DIFF`）、eSPI（單線）、USB PD、CAN FD（沿用 `can`，填 `data_bitrate` 才細解）、I3C HDR-DDR（`i3c_hdr.py`，由 `i3c_decode.decode()` 結尾 `hdr_apply` 呼叫；該檔 299 行，勿再加行）。契約 version 維持 2，列舉已補。功能分支與工作樹已刪除。
- **分工紀錄**：Claude 寫 CAN 解碼器（`can_decode/can_fields`）、CAN FD（`can_fd`＋`Reader.rebase()`）、I3C HDR 解碼器、共享檔與審查；Codex 寫 SPI、RS-485、eSPI、USB PD 與各協定 synth／check／前端。原則：解碼器與真值向量不由同一 agent 產出（SPI／eSPI／USB PD 例外，手寫真值取自計畫常數）。
- **審查改正（勿回退）**：①USB PD 殘值 `zlib.crc32(data+crc_le)`＝0x2144DF1C；②RS-485 極性必須可設定（TIA-485 A<B 為 mark，晶片腳位常相反）；③CAN intermission 3 位（`CAN.xml` 寫 2）；④`addr_bits=8` 不含 `I2CIgnoreRW.xml` 的 10→11 位顯示；⑤CAN FD CRC 含動態填充位與 stuff count、不含固定填充位（CRC-17 共 6、CRC-21 共 7 個），ISO 初值最高位為 1，CRC delimiter／ACK 的 1–2 位是接收器容忍。XML 只有欄位表／列舉／固定值，切割、去填充、CRC 在外部引擎，不能單靠 XML 解波形。
- **參考值**：CRC-15 poly 0x4599（`"123456789"`→0x059E）；eSPI CRC8 0x07（`"123456789"`→0xF4、`25`→0xFB、`21 00 04`→0x34、`08 0F 03`→0x9B）；USB PD `41 01`→CRC32 0xDFBC5C2D；I3C CRC5 x⁵+x²+1 init 0x1F、P1＝奇數位 XOR、P0＝偶數位 XOR 再反相。
- **限制（皆無實機波形；SPI／CAN 只有合成向量與 209 列 CAN CSV 閉環）**：
  - CAN：CRC 末位後若恰 5 個同值仍有填充位（未驗）；`x6000can.csv` 列 ID `0x0296A95D` CSV CRC `0x1171`、計算 `0x1170`，原因未明（檢查保留 CSV 值並預期不通過）；H5 僅 ~2.6 點／位元。
  - CAN FD：**未經外部驗證**；`--mutations` 缺「DATA 末 5 同值多插動態填充位」；CRC delimiter 2 位未處理。
  - eSPI：僅單線；附加通道回應與 PUT_* 細解未做；缺獨立手寫波形真值。
  - USB PD：未檢查 SOP 類型與訊息型別相容、末位無收尾邊沿未補；最容易取得實機資料，建議錄充電器 Source_Capabilities→Request→Accept→PS_RDY（≥10 MSa/s）。
  - I3C HDR-DDR：P1／P0、CRC5 範圍、SCL 邊沿取樣時機皆為對規格的理解；不處理 HDR Restart 後第二筆（現被當 `pattern`）、TSP／TSL／BT 不解。HDR 位元併入 `bits_t`，`i3c_vectors` 的 SDR 檢查略過 hdr 區段，向量 21 改用 `hdr(mode=1)`。
- **測試備忘**：前端 `Object.keys(decode_protocols)` 依字母序，`browser_decode_checks.protocol_pages` 驗完須還原 1400 寬（否則後一協定的標註檢查失敗）；`browser_check` 曾偶發一次 `P2b3 緊湊結果` 失敗，重跑即過；`decode_proto_check.mjs` 通道為 CH1–CH4；`decode_spi.js`／`decode_can.js` 的 `order` 為 3／4。
- 工具備忘：`codex` MCP 連不上，改用 `codex exec --sandbox workspace-write "$(cat prompt.txt)" </dev/null`（逾時用 `perl -e 'alarm N; exec @ARGV'`）；Codex 常在遇到小阻礙時提前結束，提示要寫「全部完成才報告」；zsh 下未加引號的 `--include=*.py` 會出錯。

## 基本量測審查與修正（2026-11-12，已 commit：`d7a338e`、`e31207c`）

- **審查範圍**：基本電壓／時間量測（Vmax／Vmin／Vp-p／Vtop／Vbase／Vamp／Vavg／Vrms／過衝／前衝、上升／下降時間與斜率、週期、頻率、±寬度、工作週期、延遲／相位），不含眼圖、抖動、PAM、FFT。依 `docs/Infiniium演算法研究/`（`ALGORITHMS.md`、`IMPLEMENTATION_SPEC.md`，衝突以後者裁決）。Codex 與 Opus 各自獨立審。
- **結論**：公式、符號、正規化、內插、極性、事件時間 `at` 皆正確；問題在邊界輸入、事件選取與 Top/Base 對雜訊的敏感度。
- **已修（`d7a338e`，核心 `analysis/measure.py`）**：①振幅 ≤256 ULP 視為平坦（`levels()` 仍回 top==base，維持 `web/logic.auto_threshold` 與解碼器契約），避免 `np.histogram` 丟 `ValueError`；`measure()` 對 Vtop／Vbase／Vamp 與需閾值的量測回 `TOP_EQ_BASE`，Vmax／Vmin／Vp-p 與整段 Vavg／Vrms 不受影響。②百分比閾值驗證（`0≤lower≤mid≤upper≤100`、`lower<upper`），`measure`／`measure2` 共用。③`measure_all`／`stats` 的 `meas_all_edges`（False＝只取最近參考點的單一事件，規格 §2.5）。④單週期 Vavg／Vrms（`mode="cycle"`）；`mode` 只認 `full`／`cycles`／`cycle`，其他丟 `ScopeError`。`measure_all` 隔離任何單筆例外。
- **已接 UI（`e31207c`）**：新增共用 `measure_event`（Web／Qt 共用單事件兩極性合併）、`measure_all` 加 `dx`，Qt 與 Web 的參考點都在**顯示時間**比較（範圍含 0 取 0，否則取中點；同距取較早）。Web：`MeasureEntry` 加 `mode="cycle"`（One Cycle）與可選 `all_edges`（缺省 true），前端「全部邊緣」勾選只影響之後新增的量測；`all_edges=false` 時 SLOPED 量測取兩極性最近事件、標籤去箭頭，相位強制全部邊緣；CSV 標籤 One Cycle／Single Event／All Edges。Qt：「全部邊緣」全域開關，**沒有**新增 Vavg 區間選單（所以 Qt 無單週期入口）。`RULES.md` 末段已補授權登記；`docs/Infiniium演算法研究/` 同次納入版本控制。
- **預設行為不變**：舊格式 entry 在 Web 後端與 mock 與修改前逐位元相同；`measure`／`measure_all` 不給新參數時 179200 案例 0 差異。唯一刻意變化：Qt「目前」欄在範圍不含 0 或 `dx≠0` 時改用顯示時間參考點（其他統計欄不變）。
- **驗收**：Opus 三輪獨立驗收，Web 對 Qt（真實 runner 路徑）69472 案例 0 差異；Python／node／Qt offscreen 自檢共 87 項、`browser_check`、`e2e_check` 皆過。抓到過兩次自己引入的問題：`levels()` 改丟例外使解碼器自檢全掛（已改回契約）、Qt 先減 `dx` 再比造成同距選錯事件（已改在顯示時間比）。
- **未解／限制**：①**N9（最重要）**：Top/Base 用 256 格、資料 min–max、5% 以單格計，含雜訊波形易回退到極值——50% 方波 σ≥約 2% 振幅時 Top／Base 皆回退，Vamp 偏大約 14%、過衝變負值；20% 工作週期 σ 1% 就讓 Top 回退。程式符合規格，需 Infiniium 實機資料決定 `hist_bins`／`hist_range`（目前未開放參數）。②mock 未實作過衝／前衝，這兩項只由真後端與核心自檢驗證。③`measure2` 遇平坦資料回「找不到指定方向的邊緣」而非 `TOP_EQ_BASE`。④float32 輸入且振幅不到 256 個 float32 ULP 時 `np.histogram` 仍會丟 `ValueError`（修改前就存在，專案讀檔器都轉 float64）。⑤延遲／相位為「取最近事件」的自訂規則，非官方 Delta Time（官方可指定邊緣編號），Phase 專頁未讀。⑥Qt 與 Web 的「全部邊緣」語意不同（Qt 全域、Web 只影響之後新增）。⑦`analysis_controls.py:144` 的 `app` 未使用（修改前就有）。
- **流程備忘**：Codex 實作、Opus 驗收；Codex 的 `-o file` 取最終回覆，第一次呼叫曾在開頭就提前結束無輸出，重跑即可；Codex 沙箱不能綁埠，`browser_check`／`e2e_check` 由 lead 在沙箱外跑；驗收腳本在該 session 的 scratchpad，不入庫。

## 分析頁選單與拖放（2026-11-12，已 commit；僅 Web，Qt 版延後）

- **緣由**：使用者要求①量測可拖到指定波形、②檔案／分析（FFT、Math、解碼）按鈕收成下拉選單、③結果表右上「⋮」按下去被圖形層遮蔽。Opus、Codex 各自規劃，Fable 排 task，Codex／Sonnet／Opus 實作、互相驗收。使用者指示：**HTML 優先，Qt 以後有空再改**（已存記憶）。授權登記見 `RULES.md` 檔尾「分析頁選單與拖放」。
- **「⋮」**：是結果表「選擇量測欄位」（Current／Mean／Min／Max／Range／Std Dev／Count），只影響顯示。根因（讀碼，headless 與 WKWebView 皆未能重現）：彈出層被父層 `z-index:3` 困住、位置只在開啟時算一次、`<details>` 不會點外面關。改用原生 Popover（top layer），定位算式仍在 `results.js`（`float_check` 變異測試依賴該字串）。
- **選單**：新增共用 `popMenu(button, panel, place)`（`marker_menu.js`，登記 L5）與 `.popmenu`（**必須** `.popmenu:popover-open{display:flex}`，否則作者樣式蓋掉 `[popover]` 預設隱藏，關著也顯示）。工具列改為 `[開啟][檔案 ▾][分析 ▾] Marker 游標置中`；檔案▾＝比對…／檔案資訊／匯出波形 CSV…／匯出 HTML 報告…／關閉（不加確認）；分析▾＝FFT 計算（真 checkbox）／FFT 頻譜 ↗／Math…。範圍、閾值移到左欄 `measure__head`（來源／範圍／閾值）；「X軸Maker歸位」改「游標置中」；工具列「完整時間」移除（水平列已有）。UI 計畫 P2 的 Math／FFT 頻譜搬移改以「分析 ▾」取代。
- **拖放**：量測鈕（`measure.js`）用 Pointer Events 拖到通道列（`[data-channel]`，`chanbar.js`）＝以該通道為來源 1；位移 <6 px 仍是點擊，觸控長按 300 ms；放下不改 `selected`；Esc／pointercancel／lostpointercapture／blur／換 mount 取消；取消與放下後吞緊接的指標 click、不吞鍵盤 click（`detail===0`）。**pointermove／pointerup／pointercancel 必須掛在 window 層**（按鈕上的 pointermove 在快速移出按鈕後收不到；這是 CDP 真滑鼠實測才抓到、Node 假 DOM 測不到）。通道名稱現在可 Tab 聚焦、Enter／Space 選取（原本只能滑鼠）。
- **檢查**：新增 `menu_check.mjs`、`drag_check.mjs`（掛進 `selfcheck_node.js`）、`web/browser_menu_checks.py`、`web/browser_drag_checks.py`（掛進 `browser_check.py`，**放在 `float_panel` 之前**，因 `float_panel` 會關檔；`browser_check.py` 維持 300 行）。`p2b3_check.mjs` 的 M2 變異字串（HEAD 舊債）已同步 `bpanel.js`，`--mutations` 18/18。最終 `browser_check` 34 步全 OK、`e2e_check` 過。
- **已知限制**：①多指標吞 click 已依 pointerId 修正（含 0、鍵盤例外與舊 timer 版本核對），Node 已過，實際互動待主控；**殘餘缺口**：一指被取消仍按著時，另一指在任何量測鈕 pointerdown 會無條件清掉保護（measure.js 的 pointerdown），該指若在原按鈕放開會多新增一筆；②工具列選單 `role="menu"`／方向鍵已完成（表單浮層不套 menu）；③`toolbar_check.mjs` 已存在並納入自檢；④hit test 已補四邊 0.5／1／2 px，依 border-radius 排除透明圓角，原生／fallback 共用 `browser_menu_geom.py`，待主控瀏覽器驗收；⑤主圖波形當放置目標已做：`mainplot.js` 在 canvas 掛 `hitChannel(x,y)`（用 marker 的 `nearestChannel`，8 px 內最近者；重疊時取最近、同距取先列者），`measure.js` 的 `dropChannel(el,x,y)` 回退到它；放在沒有波形處不新增；⑥Qt 全部延後（`analysis_controls.py` 的 `QToolButton`＋`QMenu`、`QDrag`；`analysis_plot.py` 已 299 行無空間）。
- **待人工確認**（headless 驗不到）：macOS pywebview 真視窗的選單、真滑鼠拖放手感、Windows 10 觸控長按、使用者原本回報的「⋮ 被遮蔽」情境（headless 未重現）。
- **流程備忘**：`browser_check` 只在結尾印步驟結果，卡住時看不出停在哪——要加逐步 print 時用 scratchpad 副本，不改專案檔；連續跑被殺掉後要 `pkill -f remote-debugging-port=9222`，否則下一次逾時；Codex 的 `-o` 一律用絕對路徑。

## 已知缺口處理與分割格線（2026-11-13，**全部完成、驗收、已 commit**；僅 Web，Qt 延後）

- **流程**：Opus 規劃、Codex 實作（一律 `codex exec -m gpt-6.1-sol -c model_reasoning_effort=medium --sandbox workspace-write -C <專案> -o <絕對路徑> "$(cat prompt)" </dev/null`）、lead 驗收（Node 自檢、`e2e_check`、`browser_check`，兩次之間 `pkill -f remote-debugging-port=9222`）。提示檔在 scratchpad（`gap_*.md`、`grid1~3.md`、`menu_fix.md`）。注意：背景啟動 Codex 時，「completed」通知可能只是外層 shell 結束，需 `pgrep -f "codex exec"` 確認；直接前景／背景執行 `codex exec` 本身則通知才準。
- **已知缺口 A～D（已 commit）**：A 右側欄停靠需圖區寬 ≥ `DOCK_PLOT_MIN`＝904（實測 FFT 控制列 897 px；約需視窗 ≥1540 px，較窄一律底部）；B 工具列選單 `role=menu`＋方向鍵（「更多…」「⋮」是表單不加）；C 解碼通道預設依名稱 `^角色key\d*$` 帶入，否則依順序；D FFT 前端快照疊圖（≤4 條，不動後端／契約）。
- **分割格線（三波已 commit）**：store 鍵 `grids={n:1|2|4|8,assign}`（不改 store.js）；缺省依通道索引 `% n` 輪流分配，隱藏通道仍佔位；localStorage `scope.analysis.grids.v1` 全域記住；所有變更走 `view.zoomRect`（可帶 grids，與 channels 同一筆歷史、一次復原）。「分析 ▾」有 1／2／4／8 格（目前項 `aria-current` 勾號），通道 chip 有「所在格」下拉（1 格時隱藏）；「分開堆疊」每格各自排、「疊圖」保留格位，兩者與分格共存。測試鉤子 `canvas.gridRect()`。F1 跨格拖把手已驗收並 commit（`cb04ee2`，Opus 13 項變異全抓到；非第一格把手可往上凸出約 8 px，併入 8 格把手排開）：跨格只預覽，放開格位與位置同筆 Undo／Redo，保留抓取偏移；多格圖外放開取消，單格沿用舊行為。8 格時每格約 30 px，把手 20 px 手感待真人看。
- **選單浮層（已 commit，最新）**：使用者視窗（pywebview/WKWebView，可能不支援原生 Popover）下選單變 in-flow、選項像圓角按鈕。修法：`vertical.css` 讓 `.popmenu`／`.results__choices` 一律 `position:fixed`＋z-index、macOS 風格（毛玻璃、無框列、hover 反白、勾號靠左、`hr`）；`popover_fallback.js` 在不支援時以 `hidden`／`data-open` 補 show/hidePopover、點外面與 Esc 關閉，並處理「⋮」的 stacking 祖先；`popMenu` 下方放不下才向上翻。驗收：`browser_menu_checks.fallback_checks`（Page.addScriptToEvaluateOnNewDocument 刪 `HTMLElement.prototype.popover` 後重載，檢查 fixed、鄰近控件 rect 不變、遮擋取樣、hover、鍵盤；用原始擷取檔 `cap['path']` 重開檔）。
- **待使用者實機確認**：重開程式看三個選單是否為浮層；在視窗 Web Inspector 執行 `'popover' in HTMLElement.prototype`（false＝走替代路徑）。若仍有問題請其給截圖。尚未在真實 WKWebView 實測。
- **行數／限制**：`browser_check.py` 必須剛好 300 行（只原地改）；已超限不可再加：`jobs.py` 301、`server.py` 304、`api.py` 326、`fft_marker_check.mjs` 319、`gestures.js` 253、`cursors.js` 267 維持不增。RULES.md 已登記各波授權。
- **另案待辦**：FFT 疊圖若要原解析度改方案 C（後端保留，動 L0 契約）；Qt 版全部延後；8 格把手排開；跨格拖把手已完成（`cb04ee2`）。

## 剩餘小項第一波（2026-11-13，已 commit `93823d4`）

- 事件原因 trim 後為空時不顯示括號；零尺寸主圖不留 pending，匯出立即提示「請先切回波形分頁再匯出」，有效尺寸才等包絡。Node 涵蓋空白原因、零尺寸、pending 逾時與載入完成。
- 交錯指標與選單邊緣檢查見上段；`browser_fft_checks.py` 新增分析頁及獨立 FFT 的 1000×700 高度保底 ≥220px（實測 230，未達原估 240；窄視窗頻譜仍偏矮）、FFT 分頁匯出 <1s。只跑 Node 與 Python 編譯，未啟動瀏覽器／示波器；`browser_check.py` 未改。

## 1000×700 頻譜偏矮（2026-11-13，已 commit）

- 方案 A 完成：`layout.js` `FFT_TAB_MIN=320`、`clampLayout` 新參數 `fftTab`；窄版（tabbed）FFT 分頁把展開的 B 區壓到 ≥92px，使頻譜 ≥280px（B-0 實測 230→280）。壓縮只存在 effective：壓縮狀態（`steps` 含 `lowerTab`）下 lower splitter／`layout.resize` 停用、點「解碼」頁籤不 resize，不寫回 prefs。
- 已知限制：通道列展開（多約 72px）時預算不足，頻譜仍約 230px 且圖區會捲動；測試先收折通道列。B 區收折時頻譜約 391px。
- Opus 驗收兩項必修已修（prefs 污染、下限斷言）；`p2b_check.mjs` 297 行，下次新增需拆檔。`float_check.mjs` 為此補 `activeTab` 參數（RULES.md 已登記）。
- `browser_check`「替代選單浮層」偶發失敗（reload 後停在資料截取分頁）基線亦會，未根治。

## 改進第一波（2026-11-13，已 commit）

- 完成項 1（框選模式命中游標線拖線，Shift 一律強制框選含壓在 Marker 上；把手／邊緣仍優先）、項 2（框選／平移按下實色）、項 5（「分析 ▾」加「解碼…」）、項 7（`validate_time` 容差 0.01×中位 dt）。Opus 驗收必修（授權）已補。
- 已知未解：browser_check「替代選單浮層」在乾淨 HEAD 也穩定失敗（⋮ 在 899×600 找不到／reload 後停在資料截取），非本波造成。Fable 調查被中途停止；其第 5 輪曾全過但修改未保留，根因未定。
- Opus 未處理建議：i3c_quality 測試資料太對稱（中位數改平均抓不到）、加 0.009／0.011 dt 邊界與 other 含 NaN 案例；toolbar_check 加 FFT 分頁＋lowerTab 情境；瀏覽器層補「不按修飾鍵在線上拖線」；Shift 鍵按下時 hover 不更新；觸控無 Shift 時線附近 ±12px 無法框選。
- 下一步：I2C 自動辨識角色（見項 7 後續）→項 4 →項 6、8 →項 3。

## I2C 角色辨識 波 A（已 commit）
- 後端 `web/i2c_roles.py` `estimate_waveforms`：兩方向各解一次比較有位址封包數（≥2 倍且 ≥1）＋SCL 邊沿較多才建議對調／維持，否則「無法判斷」；估計不動快照。`i2c_decode.options` 接受布林 `estimate`。
- 前端 `decode_i2c.js`「辨識角色」鈕（位址位元旁）：對調時交換 SCL／SDA 下拉與手動門檻；維持／無法判斷只顯示訊息。i2cdemo.h5 驗過：對調後 11 筆位址封包與 csv 相符。
- Opus 驗收通過、無必修。備註：`analysis_decode.py` 第 61 行寫死 `('uart','i2c')`，I3C 接入時要同步改。
- 待做：波 B（按「解碼」前自動辨識，依通道順序猜的且未手選才執行，警告列＋toast）；瀏覽器尚未驗「無法判斷」下拉不變。

## 項 3／4／6 決策（2026-11-13，使用者回答；規劃檔在 scratchpad out/item4_plan.md、item6_plan.md、item3_preview.html）
- 項 4：全採 Opus 建議（下拉第一項「目前通道」；隱藏通道標「（隱藏）」並提示；換檔同名保留否則退回；右鍵不加；圖上標籤不改）。
- 項 6：全採建議（M1–M10、＋Marker 鈕加在目前 RF 位置、吸附最近頻格、可拖動 ±8px 放開讀值、上限 10 第 11 次 toast、與峰同表不受篩選、換來源／檔清除、清除全部不確認、Peak Line 只改 UI 文字）。
- 項 3：標籤擺放選**方案 B（貼波形起點）**（非 Opus 推薦的 A）；別名細節全採建議。B 方案需在規劃時重新處理：左緣把手縮減、疊圖時標籤避讓、「+N」收合是否仍適用、與項 8 三角形（下緣）／游標字樣不互蓋。
- 項 4、6 實作要等 I2C 波 B commit 後再開（共用 selfcheck_node.js／docs/驗證.md／RULES.md）。

## 改進項目現況總表（2026-11-13 更新）
- 已 commit：項 1、2、5、7（`dd7c016`）；I2C 角色辨識波 A（`05005bc`）。
- **I2C 角色辨識波 B（已 commit）**：解碼前若角色是依通道順序猜的且使用者未動過，先估計；判斷接反就對調（含手動門檻）、toast、說明附加到警告列與報告（`report.js` 解碼報告附 `summary.warnings`，所有協定皆適用）；只辨識一次。Opus 驗收通過。備註：換協定再換回會還原該協定快取設定，`guessed` 維持上次狀態（只有換檔才重算）；未驗：無法判斷／估計期間換檔的瀏覽器案例、手動門檻 DOM 回填的 Node 覆蓋、估計回 ok:true 分支。授權見 RULES.md「波 B 授權」。
- 待實作（決策已定，見上節）：項 4（Marker Table 選通道，規劃 `out/item4_plan.md`，約 10 行）→ 項 6（FFT 手動標記，規劃 `out/item6_plan.md`）→ 項 8（解碼事件三角形，**尚未規劃**，需與項 3 方案 B 一併考量）→ 項 3（別名＋標籤方案 B，需先重新規劃；UI 預覽 `out/item3_preview.html`）。開工前各自登記 RULES.md 授權；一次只做一波（共用 `selfcheck_node.js`／`docs/驗證.md`）。
- 未結小項：browser_check「替代選單浮層」原因未明（clean HEAD 同樣失敗；Fable 調查已停）；Opus 第一波未處理建議（i3c_quality 對稱資料、validate_time 0.009／0.011 dt 與 NaN／inf、FFT 分頁＋lowerTab 情境、無 Shift 拖線瀏覽器測試、Shift hover 重繪、觸控 ±12px 限制）；波 A 備註：`analysis_decode.py:61` 寫死 `('uart','i2c')`，I3C 接入須同步；波 A「無法判斷」下拉不變尚未在瀏覽器驗；i2cdemo START 時間偏移約 10.8 µs 原因未明；`H5參考波形` 新檔與 `HD5擷取歷史` 刪除是否追蹤待使用者決定；真機／Win10／WKWebView 未驗；Qt 延後。
- **項 4 已 commit**：Marker Table 工具列加「獨立點通道」下拉（第一項「目前通道（CHx）」，隱藏通道標「（隱藏）」並 toast，換檔同名保留），只改 `marker_table.js`。備註：隱藏通道提示僅 Node 覆蓋，瀏覽器未實測；下拉未套 `.select`。下一步：項 6（規劃 `out/item6_plan.md`）。
- **項 6 已 commit**：FFT 手動 Marker（`fft_manual.js` 新檔；＋Marker／清除鈕、M1–M10、拖動 ±8px、上限 10、換來源／檔清除、Peak Line 改名）。驗收追加：dock 模式 fftbar 允許換行（analysis.css）、「清除」鈕縮短。已知：換頻譜時在途新增會提示「頻譜已更新，請再試」；`fft_overlay_check.mjs` 已正式登記進 FILES。下一步：項 8、項 3 規劃已完成（`out/item8_item3_plan.md`，Codex 審查中），待使用者拍板後開工。
