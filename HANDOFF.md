# Handoff：示波器截圖與波形擷取工具（HTML 版工作資料夾）

目錄：`/Users/lianshi/Desktop/claude-cowork/示波器截圖_html`（獨立 git repo，main，無 remote）
- 2026-10-22 從穩定版 `../示波器截圖`（Qt 版，HEAD `b358334`）複製，**未含 `N8900A/`**；之後 HTML 化只改這裡，原資料夾不動。
- 備份：`../示波器截圖_備份_20261022_223504.tar.gz`（含 N8900A 與 git 歷史）。
- 參考資料在 `../示波器截圖/N8900A/`（gitignore，無版本備份）。`InfScopeDLL_decompiled` 與 Infiniium Help 已是同名 `.tar.gz`，引用前先 `tar -xzf`。

## 現況（2026-10-22）

- 離線分析（Stage 0～3：量測、Marker、FFT、Track RF）已完成；`analysis/` 為純 numpy，規格 `docs/離線分析功能規格.md`。Jitter／眼圖已移出 GUI（程式保留未接線）。
- **只有 offscreen／headless 自檢，沒有真機驗證**；待比對項目在 `docs/真機驗證清單.md`。已上機：DSO-X 6004A／3014G、HD304MSO、MXR254B、MSO-X 4154G、MSO9254A（僅連線讀取）；3000T、EXR、S 系列未上機。
- 啟動：`啟動示波器截圖.command`（Web 版）；Qt 版 `啟動示波器截圖_qt.command`；有「測試儀器（模擬）」。
- 啟動：Mac 雙擊 `啟動示波器截圖.command`（Web 版）；Qt 版 `啟動示波器截圖_qt.command`；有「測試儀器（模擬）」按鈕。

## Web 版（pywebview）現況（2026-10-22，已切為預設入口）

- 啟動：`啟動示波器截圖.command`（= `python -m scope_tool.web.app`）；舊 Qt 版保留為 `啟動示波器截圖_qt.command`，git tag `qt-final`（`bfba82c`）為純 Qt 最終狀態。`scope_tool/ui/`、`main.py` 未刪（PySide6 仍因 `QImage` 為執行期相依）。
- 權威規格：`docs/pywebview-GUI規劃建議書.html`（決策 D1–D6 皆採建議值）、`docs/web-api契約.md`＋`scope_tool/web/static/api_contract.json`（凍結契約，只有 lead 能改；附錄記錄審查後裁決）。檔案擁有權表在 `RULES.md` 末段。
- 架構：pywebview 只當視窗；daemon 執行緒跑 stdlib HTTP server（127.0.0.1＋token）；RPC／long-poll 事件／二進位 `/wave` `/fft`；前端為 ES modules＋自繪 Canvas，傳輸全藏在 `bridge.js`，`?mock=1` 可離線開發。VISA 一律經 `web/jobs.py` 儀器執行緒＋全域儀器鎖。
- 驗證指令：後端 `QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.{decimate,analysis_api,jobs,server,api,e2e_check,browser_check}`；前端 `node scope_tool/web/static/js/selfcheck_node.js`（或開 `static/selfcheck.html`）。`browser_check` 用 headless Chrome＋CDP 實跑連線→擷取→開檔→游標→量測→FFT（已通過、console 無錯誤）。
- **未驗證／已知限制**：沒有真機；沒有真人滑鼠手感（拖曳／滾輪）；真正的 pywebview 視窗只確認可啟動 10 秒未崩潰；Win10／WebView2／PyInstaller 打包（`packaging/`、`requirements-web.txt`）完全未驗；剪貼簿與 `<a download>` 在 pywebview 的行為未驗；1000×700 視窗開 FFT 時頻譜被壓縮需圖區內捲動；Track Measurements 因契約無事件座標而標「尚未支援」；100M×4 記憶體仍是既有上限。逐項清單：`docs/web版驗收清單.md`。
- 後續：真人／真機驗收後勾清單；Win10 打包；大檔 h5py 懶載入（選配）；validate_params 尚未接到 server（參數錯誤目前走可重試的 job 錯誤）；確認穩定後再決定是否刪除 `ui/` 與 Qt 入口。

## 分析頁 GUI 改善（2026-10-24 完成並合入 main；2026-10-25 垂直框選修正 `285838c`）

- 計劃書：`docs/分析頁GUI改善計劃書.md`。範圍：A 量測欄、B 結果、C 主圖；操作模型參考 N8900A。標籤 `p1-gui`→`p2a-gui`→`p2b-gui`→`p2b3-gui`→`p3a-gui`→`p3b1-gui`→`p3b2-gui`→`float-gui`（`fb12038`），皆已 fast-forward 合入 main。
- 行為：拖曳＝平移、滾輪＝縮放時間；框選放大（Shift 暫時框選、Space／中鍵暫時平移）、種類 `[水平｜垂直｜雙向]`（`view.zoomKind`，`vzoom.js`）；Undo／Redo；Horizontal／Vertical 列（單位/格、位置、適配、dx 徽章）；左軸顯示目前通道電壓；三條 splitter、`clampLayout`（<900 窗改分頁／抽屜）；B 區頁籤 `量測｜游標｜FFT 峰值`；浮動量測面板（`floatpanel*.js`）。偏好只存記憶體＋localStorage。
- **垂直框選修正**：V/格原本吸附到檔位表下一檔，選框 >約 40–50% 高時看似沒反應；`verticalZoom` 改連續 V/格＝選框高度÷10（夾在檔位上下限），已實測。Codex 指出未修的結構風險：`axes.js`／`gestures.js` 各存一份 `zoomKind` 且 `store.command` 不重播，掛載順序不同會不同步；`channel.scale_intent` 唯一 handler 在 `chanbar.js`，未掛載則指令靜默消失。
- 檔案 lane（已登記 RULES.md）：L4 `gestures axes layout splitter voltage vzoom floatpanel*`；L5 `vertical bpanel summary cursor_table`；L8 各 `*_check.mjs`、`web/browser_*_checks.py`。`view.*`／`layout.*` 是前端 command 字串，不在凍結契約。
- 驗證：`selfcheck_node.js`（含變異測試）、`e2e_check`、`browser_check` 通過；後兩者 Codex 沙箱不能綁 localhost，須 Claude 在沙箱外跑。
- 已知小項：Track Measurements 仍 disabled（契約無事件座標）；500 µV V/div 下限與需求文字的 1 mV 不同；FFT 分隔線拖曳仍重取頻譜；複製在 WKWebView 的 await 後 user gesture 未真機驗；`browser_check` 曾偶發「寬版點 FFT 峰值分頁未切換」一次；真機未驗 Mac 觸控板手感、Windows 899px 斷點。
- **量測問題（使用者 2026-10-25 擱置）**，重現檔 `wave6000-10Mhz_20261022_125915.h5`：①上升／下降時間、斜率顯示「—」：取樣間隔 2.5 ns、邊緣僅 2～3 點，`edge.transition` 要求 ≥4 點（`edge.py:58`），設計門檻非計算錯誤；②等約 30 秒：每次新增量測重算全部、分析執行緒僅一條（`jobs.py` `ThreadPoolExecutor(1)`）且舊請求不可取消、各項各自做邊緣偵測。可能修法：只算新增項、共用邊緣偵測、丟棄舊請求。
- **3000G 量測研究（`ad2bf07`）**：`docs/研究_3000G量測計算比對.md`。4 點門檻與 40%／5% 直方圖只在 Infiniium 手冊；與手冊不同五處（缺 −Duty、Vavg／RMS 缺 N Cycles／Full Screen、「目前」取最左、統計單位、範圍是整檔）。取消 4 點門檻會高估 38～44%，故保留門檻並輸出 `<`／`>` 上界標記。方波噪聲約 2% 時 Top／Base 會懸崖式退回極值，需真機比對。
- **3000G 量測實作（`633ab61` 起）**：Rise／Fall／Slew 點數不足輸出標記上界、新增 `-工作週期`、Vavg／Vrms 加 `mode`；雙來源 `延遲`／`相位`／`電壓比`（`MeasureEntry` 加 `channel2`／`rising2`，`measure.measure2`）；「目前」改取最靠近 t=0 的事件。契約新增可選欄位 `mode`、`bound`、`channel2`、`rising2`。未做：可見範圍量測、Top/Base 真機比對。
- 工作方式：Codex 編碼 → 沙箱外跑 `e2e_check`／`browser_check` → Opus 唯讀審查 → Claude 提交。

## 分析頁 Marker Table（2026-10-25，P1～P4 已 commit，main HEAD `e9785dd`）

- 計劃書：`docs/分析頁MarkerTable計劃書.md`（決定、分階段、檔案 lane 皆在內；契約不升版，新 store 鍵 `markerTable`／`fftMarker`）。commit：`99cc40a` P1/P2 → `2b583bb` P3＋右鍵選單 → P4 `03447e3` → `86a6a04` 獨立點按鈕 → `08f364e` 右鍵／拖曳修正 → `e9785dd` WKWebView 選單點選修正。
- 行為：
  - 時域 Marker：連動組 M1（各通道同一時間）＋每通道最多 10 個獨立點。新增＝表格「新增／移動連動 M1」、「＋ 獨立點（目前通道）」，或主圖右鍵選單（含刪除）。拖曳＝點中後跟滑鼠任意移動，放開才向後端吸附到實際取樣點，獨立點拖出範圍夾回曲線端點。註記在表格內編輯。
  - FFT：水平基準線（可拖、單位可選＝`fft_units` 去 Phase，超出畫面時貼邊並標示），峰表一次抓 1000 峰後前端過濾／排序／取前 n，免重跑 FFT；峰不收註記。
  - 版面：B 區頁籤 `量測｜游標｜Marker｜FFT 峰值`；寬≥1200 游標／Marker 並列；標題列「⇥ 右側欄」＝版面 C（`layout.markerSide`，340px 直欄，≥900px 才啟用，窄版／浮動自動退回底部且不改偏好）。
- 新檔：`markers.js marker_layer.js marker_menu.js marker_table.js fft_markers.js fft_runner.js fft_marker_{controls,layer,table}.js`；檢查 `marker_check.mjs fft_marker_check.mjs dock_check.mjs`、`web/browser_marker_checks.py`（`dock_layout`、`marker_add_button`、`marker_rightclick`）。新 command `marker.*`、`fftMarker.*`、`layout.markerSide` **尚未登記 RULES.md**（lead 管理）。
- 驗證：`selfcheck_node.js`、`e2e_check`、`browser_check` 通過。
- 踩過的坑：WKWebView 點 button 不給焦點，mousedown 使 `focusout` 的 `relatedTarget=null`，舊 focusout 直接關選單 → 點選項無效（headless Chrome 測不出，靠 `marker_check.mjs` 斷言）；選單 `focusout` 在 `menu.remove()` 時同步重入 `close()` 也會使點選無效（已修，靠 `marker_rightclick`）。Mac Ctrl+左鍵在 `gestures.js` 交給 contextmenu（Windows 的 Ctrl+左鍵因此無作用，低風險未處理）。`peaksTruncated` 要「抓滿上限且基準線低於最小峰值」才算。
- **使用者決定不做 JSON 匯出入**（2026-10-25）。未做：右側欄寬度固定不可拖；真人滑鼠手感（右鍵、拖曳 Marker、拖曳基準線）使用者已在 pywebview 驗過獨立點按鈕與右鍵選單點選（`e9785dd` 修正後正常，2026-10-25）；拖曳 Marker 與拖曳 FFT 基準線也已實測正常。Marker Table 全部功能真機驗收完成。
- 工具備註：Codex 曾卡死（CPU 近 0、無檔案變動），原因是 `codex exec` 在等 stdin（輸出停在「Reading additional input from stdin...」），**背景呼叫必須加 `< /dev/null`**；本機 Claude Code mod `task-progress`（`~/.claude/local-mods`）可看任務進度條。

## 介面美化（2026-10-25，`660d643`～`d58b1af`）
- 範圍＝預覽稿 A（token／對比／版面）＋B 的圖區部分（虛點格線、主圖中央十字軸、琥珀重點色）。**不做整套深色主題**（RULES.md「明確不做」）；C 案棄用。
- 通道色改 Okabe–Ito（`#F0E442 #56B4E9 #E58FC4 #3DD6A3 #E69F00 #b79cff`），來源 `api_contract.json` `channel_colors`（L0，與 `mock_catalog.js`、`tab_analysis.js`／`toolbar.js` fallback 同步）；chip 加 ●▲■◆。Qt `ui/` 未動。
- canvas 色值讀 CSS token（`app.css` `--c-amber --c-fft-* --c-ov-*`，經 `plotcore.js plotColors()`）；`drawGrid` 的 `colors.center` 開中央軸（僅主圖）。
- `analysis.css` 的 `12.5px` 不可改：`p2b_check`／`p2b3_check`／`p3b_check` 斷言寫死。`clampLayout` 的 40／28px 未動。工具列 `.field` 同行、量測鈕 `.field:has(.btn--small)` 兩欄（需 Safari／WKWebView ≥15.4）。
- 修舊 bug：①數學通道要同時進 `file.channels` 與 `channels`（`toolbar.js` 現為單次 `store.set`，同名通道會被擋），否則 `fetchTargets` 不抓、不繪圖；②視窗太矮時 `clampLayout` 收掉預覽，`layout.state`／`layout.query` 皆帶 `blocked`，勾選改停用並提示。
- `browser_check` 兩處測試修正：「P2b 多尺寸」先確保 B 區收折再測展開（工具列變矮後不再自動收折）；「P3b-2 垂直框選」`fit` 加 0.025 格容差（整數像素框選貼 ±5 格邊界會差 1e-6）。
- 審查未處理：`browser_check` 收折後未斷言 `aria-expanded`；`:has(.btn--small)` 範圍偏寬（可改專屬 class）。

## 主圖包絡修正與版面編輯器（2026-10-26，`f59a4b2`、`d6648aa`）
- **包絡破圖**：10000 點 10 MHz 方波全視圖時每桶約 6–7 點，走 `decimate.py` mode 1（min/max 包絡）。舊 `plotcore.js drawPixels` 每桶各畫獨立垂直線，平頂變虛線、邊緣變雙線；與每像素點數相關，約 4.6 點／px 尚可、6.4 點／px 明顯破。已改為相鄰有限桶補連線（NaN 桶仍斷線、單桶最小高 1px）；`analysis/envelope_check.mjs` 已加入 `selfcheck_node.js`。`decimate.py` 未動。
- **版面編輯器** `docs/版面編輯器/layout_editor.html`：雙擊開啟（file://，免伺服器）。58 個部件，可拖曳／縮放／隱藏／鎖定／註解、復原重做、localStorage 自存、匯入 JSON；輸出 `layout_*.json` 與 `layout_summary_*.md`（現況→新位置、註解、建議修改檔）。部件以 `shots/`（3 尺寸×5 狀態，共 15 張）裁切真實 GUI 畫面顯示，「顯示真實畫面」可切回色塊；`shots/` 需與 HTML 同資料夾。
- 座標為 2000×1290、1400×900、1000×800 三尺寸實測；看不到的部件為等比佔位（`measured:false`）。app 版面改動後須重量測、重截圖、更新 `components.json` 並重嵌入 HTML（腳本在 session scratchpad，未入庫）。
- 命名：程式的「B 區」＝`bpanel.js` 下方結果區；左側量測欄是 `measure.js`（文件稱 A 區）。
- 未驗證：真人滑鼠手感、pywebview／WKWebView、剪貼簿與下載實際寫入；奇數寬部件中線吸附差 0.5px。
- **待使用者**：排好版面後貼回 JSON／Markdown，再照它改真實 GUI（寫程式交 Codex）。
- Codex CLI 0.163.0 無 `--full-auto`，用 `codex exec --sandbox workspace-write -C "$PWD" - < prompt`；其沙箱禁綁 localhost，browser_check 須自己跑。

## 分析頁版面微調（2026-10-26，`0aed7a5`、`fa18727`、`a0666cc`）
- 水平控制列（`axes.js`）移到通道列正下方；「位置（中心）」改名「時間軸位移」；游標摘要（`analysis__cursorSummary`、`summary.js` 的 `mountSummary`）已移除；Zoom 勾選框（原工具列「預覽」，`preview.visible`）移到水平列末，class `analysis__preview`。
- 下方結果區 Marker 分頁改名「Marker Table」（`bpanel.js`）。「回中央」改名「X軸Maker歸位」，由 `cursors.js centerButton` 提供，現放在**工具列** Marker 欄右側；通道列與游標數值面板的舊按鈕已刪（「放在 marker 區塊」是照工具列解讀，使用者若指 Marker Table 分頁需再搬）。
- 通道列（`chanbar.js`／`vertical.js`／`vertical.css`／`app.css`）：單列 grid、每通道一欄固定 236px（`--chanbar-col`），放不下橫向捲動、不換行，chip 不因 scale 文字位移。每欄含 chip＋自己的 vertical（單位/格、offset［原「中心電位」］、dx＋適配），綁通道名稱、不跟 selected 切換；vertical 不再自行訂閱 store，由 chanbar `sync()` 驅動。電壓控制**預設收折**，最左全域鈕展開／收折，狀態存 localStorage。dx＝該通道時間位移（`time_offset`，會影響游標區間量測與 FFT，非 0 時 chip 顯示 dx 徽章）。
- 測試斷言已同步：`p1_check`、`p2_check`、`p2b2_check`、`p2b3_check`（游標輸入格 6→5）、`p3_check`、`browser_analysis_checks.py`；`browser_check.py` 的 splitter 取點改為分隔條 1/4 處（原點位會被 FFT 收折鈕／側欄鈕蓋住，非介面壞掉）。
- 已知：通道多時右側被橫向捲動切掉且無提示；1000 寬水平列尾端（範圍／完整時間）被截斷；展開電壓控制後通道列約 100px，主圖變矮（1400×900 主圖 395px，下限 270px）。
- 版面編輯器 `docs/版面編輯器/` 的 `components.json`／`shots/` 是這批改動**之前**的快照，現況已不同；使用者排版前若要對得上需重量測、重截圖。

## 離線分析修正線：Jitter／ΔY/ΔX／草案

- 已 commit：游標表 ΔY/ΔX（`1014c05`）；`marker.py` versus 不給斜率（`52b5c90`）；草案 `docs/草案_Jitter眼圖Web契約.md`、`docs/草案_RMS縮放與相位追蹤定義.md`；`docs/DSOX6004A_Jitter驗證紀錄.md`（至第四輪）。
- DSO-X 6004A（10 MHz 方波）：示波器 TIE≈0.842×離線線性擬合 TIE−250.7 ps，σ 對 50% 中點門檻極敏感。頻譜比值檢查（第四輪）：增益各頻帶平坦約 0.85，無追蹤跡象，不能用此樣本校準 PLL 頻寬。原始資料在 `示波器截圖/N8900A/DSOX6004A_Jitter驗證_20261024/`（gitignore、無備份）。
- **契約 v3 先不升**（使用者決定）：要改 L0 檔（`docs/web-api契約.md`、`api_contract.json`、`mock_catalog.js`、`mock_backend.js`、`l0_*.mjs`，不是 `scope_tool/contracts.py`），須同一筆含 mock 同步＋Analysis 3 個 stub，否則 `l0_check`、`selfcheck_node`、`contract_check`、`analysis_check` 失敗。v3 只為 Jitter／眼圖新增 3 個 RPC，與 GUI 的 `view.*` 無關。順序：v3 一筆落地 → Jitter／眼圖後端（`jitter_eval`、`eye_density`、`export_timing`）→ 前端面板。
- 草案要點：revision 以 `Analysis._accept`＋`submit(on_accept=...)` 在 `_tbl_lock` 內配號；`export_timing` `job=false`；`validate_params` 須接上 server（`e2e_check.py:126-128` 將由 job 事件改同步）；PLL 只接受 `mode=手動`、捕獲 ±1000 ppm、失鎖門檻暫 ±1500 ppm。`analysis/*` 歸 T7。
- 已完成：RMS 2 冪縮放（`ef6936f`；公開 `measure` 在 ~1.8e308 資料會卡在 top/base 直方圖，已知限制）；PLL 事件層原型 `analysis/pll.py`＋`pll_check.py`（印 OK；只有事件層，未接 clock／眼圖／GUI／契約，門檻待校準，1400 ppm 重鎖一次、2000 ppm 失鎖）。
- 待使用者下令：契約 v3＋Jitter／眼圖 Web 實作（PLL 接線另案）、push（無 remote）。詳見研究目錄 `HANDOFF_分析修正.md`。

## Windows 打包

- `RULES.md` 允許 Windows 版 PyInstaller（Win10／Win11，onedir）；目標機自行安裝 NI-VISA 或 Keysight IO Libraries（PyInstaller 不打包）。
- 草稿已備：`packaging/scope_tool_web.spec`、`packaging/build_win.bat`、`requirements-web.txt`（PySide6 不可排除）。凍結後 static 路徑已用 `sys._MEIPASS`。**全部待 Win10 實機驗證。**

## FFT 頻譜分頁與資料截取分頁（2026-10-26，`3488ba5`、`cd61728`、`522f70a`、`fb165c7`、`a9563dc`）

- 計畫書：`docs/FFT頻譜分頁計畫.md`（含「使用者決定」節）、`docs/資料截取合併計畫.md`。
- **FFT P1（後端）**：`fft` RPC 追加 `rbw`、`vbw`（可為 null），`FFTResult` 追加 `segments`、`vbw`；契約 `version` 維持 2。新檔 `web/fft_rbw.py`（Welch 分段平均＋VBW 頻率軸平滑），`rbw=null` 走原 `fftmod.spectrum`、結果不變。`analysis/*` 仍凍結。前端目前固定送 `rbw:null, vbw:null`。
- **FFT P2（前端）**：新增頂層「FFT 頻譜」分頁（`analysis/tab_fft.js`），與分析頁**共用單一 runner／參數**（`analysis/fft_state.js`），兩處控制項互相同步。**分析頁內嵌 FFT 窗格、B 區「FFT 峰值」頁籤、「FFT 計算」勾選都保留**（使用者決定），工具列加「FFT 頻譜 ↗」（command `tab.select`）。不在 FFT 分頁且勾選關時只標 dirty、不算。新分頁的 fftpane 視窗狀態仍是本地，尚無 `fftView`。
- **資料截取**：「截圖」與「波形擷取」合併為頂層分頁「資料截取」（`tab_datacapture.js` 左右並排、窄窗上下；內部 id 沿用 `capture`，舊兩個模組保留為內部模組）。頂層分頁剩：資料截取／離線分析／FFT 頻譜。`main.js` 預設 activeTab 改 `capture`。兩組存檔設定鍵分開；兩邊同時動作靠既有 BUSY 提示。
- **使用者決定**：RBW=Auto 要**隨 Span 自動連動**（與計畫書原建議相反；P4 設計需納入，N 待定、Span 變動要 debounce）；FFT 範圍與量測共用 `rangeMode`；Start/Stop 等不存 localStorage。
- **FFT P3**：store 鍵 `fftView`＝{f0,f1}（Hz）或 null（全頻寬）；`fftpane.js` 的 `clampView`／`applySpanEdit`（四欄聯動：輸入值不動，Center 碰邊縮 span、Span 碰邊移中心；夾 0～Nyquist、最小 span＝10·df）；FFT 分頁有 Start／Center／Stop／Span＋「全頻寬」；分析頁與 FFT 分頁兩個 fftpane 共用 `fftView`；`fft_markers.js` 峰值／基準線只看畫面內（前端過濾、不重跑 FFT）；RF 跳到畫面外時平移入界、保留 span。限制：峰快取是全頻譜前 1000 大峰，放大到小峰區可能漏列（腳註提示）。
- **FFT P4**：FFT 分頁有 RBW／VBW 輸入（`fft_state.js` 的 `mountBandwidthControls`，兩處共用參數）；**RBW=Auto 隨 Span 連動**（≈span/1000，debounce 300 ms，Auto RBW 變動 ≥5% 才重算以防迴圈；手動輸入即停止連動）；VBW 預設 Auto＝不平滑；狀態列顯示實際 RBW／段數／VBW，Phase 單位停用兩欄。
- **未做**：P5（清死碼，選做）。Welch／VBW 尚未真檔肉眼比對。
- **已知版面小缺（2026-10-26 截圖）**：FFT 分頁右欄最上方的「排序／基準線」看起來掉出參數列；最左峰的標籤與右下 `1 GHz` 刻度被裁切。尚未處理。
- **未驗**：FFT 分頁輸入 Start／Stop 後圖與峰表只剩範圍內峰（無人手動測）；資料截取並排版面無人看過；資料截取同頁搶儀器鎖需真機；Qt 版仍是兩個分頁。
- 驗證：`selfcheck_node.js`、`e2e_check`、`browser_check` 皆通過（Codex 沙箱跑不了後兩者，須在沙箱外跑）。

## 後續待辦

1. 真機比對：量測數值與面板讀數、Bessel 低通群延遲補償、Marker／FFT 清單項目。
2. 上機：HD304 四通道 100M 與 `:DIGitize`（先確認設定已還原）、MXR Error 273／LAN／慢時基、3000T、MSO9254A 截圖／擷取／分析、DSO-X 6004A 的 GUI 全流程與 Single／Normal／`:DIGitize`。
3. 已知剩餘小項：RF 跳峰仍是 O(n) 約 0.1 s（8M bin）；FFT 快取依賴所有改資料路徑呼叫 `fft.refresh()`；切 log 頻率軸會重算 FFT；重入呼叫被忽略而非延後。
4. 解碼：I3C 真機波形與示波器內建解碼比對（`docs/真機驗證清單.md` 第 26 項）；多協定計畫見下方「多協定解碼」。
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

## Liquid Glass P1（2026-10-26）

- 使用者同意計畫 §6 十項預設與跨 lane 授權。Web 採深色單一主題，Qt 不動；`app.css` 負責 tokens、全域元件、toggle 與系統偏好降級。`--c-surface`／`--c-overlay-solid` 保持實心，圖區 tokens 與既有幾何不變。
- `glass.css` 最後載入；P1 只補分析頁 segmented、Marker 選中列、垂直 badge 對比。凍結 token 名稱及「分析頁／FFT 頁／浮層（P3）」分段；P2 其餘套色、P3 blur／效能／三宿主實機驗收尚未實作。
- `browser_check.py` 新增 `glass_smoke`，瀏覽器端計算放在 `static/js/glass_smoke.js`：含漸層最亮停點的祖先 alpha 合成對比、實際 Tab／Space、兩尺寸分析頁幾何與高對比／強制色彩。分頁基線由同瀏覽器暫套原始規則量測，並將 margin 納入總高度；分頁上下 margin 採 3px 以符合基線＋2px 預算（計畫範例 6px 會超出）；不取代實作前的截圖基線。
- 本次沙箱不跑 browser_check；實際截圖、FFT 邊界、WKWebView／WebView2／QtWebEngine 由後續驗收。Node 一般自檢通過；`--mutations` 停在既有 p2b3 M2「寬版峰值混入其他面板」，未修改 HEAD 匯出副本亦重現。offscreen e2e 已執行，因沙箱禁止 localhost bind 而中止（PermissionError），待沙箱外驗收。

## Liquid Glass P2/P3 與軸刻度（2026-10-26）

- P2（分析頁／FFT 頁套色）、P3（`.dlg`／toast／`results__choices`／tooltip 毛玻璃，雙前綴 blur＋實心降級）皆已合入 main。浮動面板不加圓角（右下角縮放熱區在 3px 內）。
- P3 效能：headless Chrome 1400×900、浮層疊圖上拖曳 5 秒×3 次，main 與 P3 皆 60fps（P95 16.7ms、0 掉幀），增幅 0%。限制：非 WKWebView／WebView2、非 10M 點檔；實機驗收見驗收清單 #26，**尚未做**。
- 軸刻度 `tickLabel`：格距超過三位有效數字時只取兩位、電壓換 mV（`1440 mV`），時間軸不換單位；整齊格距行為不變。
- 先前「版面小缺：峰標籤與 1 GHz 刻度被裁切」已於 e968c24／77b38a0 修好。

## I3C P2（2026-10-26）

- 契約 version=2 追加 decode（job）／decode_frames／decode_bits／export_decode 與七個 Decode／Addr 型別；固定 mock 拆 `mock_decode.js`，l0_sem 經 call 驗四方法型別、BAD_REQUEST／STALE。沒有 UI 修改。JSON 原有超過 300 行，改按方法／型別各一行排版，既有內容不變。
- `analysis_decode.py` 提供鎖內快照／gen 檢查、任何解碼失敗使舊 id STALE、完整時間軸驗證、實際 bit 時間切片（含兩端／反序／4096 上限）與完整 UTF-8 BOM CSV。來源路徑／通道／門檻／選項／解碼時間固定於快照；analysis_api 僅三處接線。
- analysis_decode、analysis_api（含 analysis_check）與 Node 一般自檢通過；P1 i3c_check 全綠（10M×2：3.833 s；單次／連續五次峰值 RSS 686.8／684.6 MiB）。e2e_check 由 lead 於沙箱外實跑通過。
- HTTP 檢查含小型合成波形完整四 RPC、同步缺鍵 BAD_REQUEST／巢狀 job BAD_REQUEST、失敗／換檔後三方法 STALE；100k fields 使用從實際解碼結果擴充的合成快照，隔離量測序列化與 HTTP 成本，非解碼效能。lead 實跑（Apple M5）：100k fields 往返 0.146 s、回應 14,478,303 bytes；e2e_check／browser_check 全過；無實測／未與原廠解碼比對。
- 額外 Node `--mutations` 停在既有 `p2b2_check.mjs`「格距忽略最末有效位：找不到變異位置」；另以 `git archive HEAD` 的未修改靜態檔副本執行，同樣失敗。未更動該測試或軸刻度實作。

## I3C P3（2026-10-26）

- B 區新增「解碼 (N)」分頁（decode.js／decode_table.js）：設定列、摘要＋篩選、事件表（≤2000 列，點列跳轉）、位址表、設定變更黃色提示、CSV 匯出。標註列勾選只存設定，P4 接繪圖。
- B 區頁籤群組改靠標題列右側（使用者同意）：多了「解碼」後頁籤會蓋到 lower 分隔線拖曳點，靠右留出左側拖曳空間。
- selfcheck_node、e2e_check、browser_check（含新「I3C 解碼分頁／CSV／尺寸／過期設定」）全過。


## I3C P4（2026-10-26，`9b475ed`；位址顯示修正 `2dbcdc6`）

- 主圖下方新增黑底 40px 標註列：狀態色 transaction、hex／第九位標記、白色選框、逐 bit 與 SCL 取樣刻度；共用 plotRect、SCL dx、解碼模型；開關不使解碼過期。chrome 加 40px，窄版 FFT 分頁隱藏；工具列、glass.css、vertical.css 與 analysis.css 原有行未動。
- 報告由有效快照建解碼段落（不依賴分頁可見性），包含目前篩選事件 ≤2000 列、內容 64 字元＋省略號、位址 ≤256 列、可見標註列圖；await 後再比對 file.gen／decodeResult 參照，避免換檔／重算／設定變更競態。
- Node 全套：`web js self-check OK`；`decode_check.mjs --mutations` 通過（含 visibleFrames 左邊界變異）；analysis_decode 與 browser_decode_checks 合成資料自檢通過。report_check 以 2000 列滿 64 字元、256 列位址、1400×40 高熵 PNG，另含兩張 1400×400 PNG 組完整請求：7,291,883 bytes < 8,000,000。
- 與計畫文字的小差異：field.t0／t1 是首末取樣時間，bit 間距以寬度÷(nbits−1) 判斷 10px；格界取相鄰實際取樣點中點。這樣非等距 SCL 仍對準刻度。密集的同狀態細 frame／同品質細 field 合併，避免縮小時重複畫同像素；合併區不顯示單筆內容。
- lead 沙箱外必跑 browser_check／e2e_check；新增瀏覽器檢查涵蓋實際像素左緣差 ≤1px、主圖 ≥270px、單 byte 9 bit／RPC、標註列點選表格、開關與窄版 FFT、真 HTML 匯出、5000 frames 單次 draw <30ms。此輪未啟動 localhost，以上像素／耗時／截圖尚未實跑，請特別看 B 區字體、lower 拖曳命中與 1400／1000 截圖。
- 額外全套 `selfcheck_node.js --mutations` 停在既有 p2b2_check.mjs「格距忽略最末有效位：找不到變異位置」；另取 HEAD 乾淨靜態檔副本重跑，同樣 exit 1。P4 的 `decode_check.mjs --mutations` 單獨通過；未修改既有軸刻度或該變異測試。
- 無實測波形；取得實測波形後與示波器內建 I3C 解碼比對（事件、時間、第九位、DAA／IBI、錯誤判定）。真機清單原有 357 行，本次只壓縮標題／表格邊界空行以符合每檔 ≤300 行，歷史文字保留。
- 上述 browser_check／e2e_check 已由 lead 沙箱外實跑通過（左緣差 0px、5000 frames draw 約 13–15ms、報告約 7.3MB）。`2dbcdc6`：byte 模式位址改顯示「7E W」（與預覽一致，非原始 8-bit）；第九位小標放不下就不畫。
- p2b2 `--mutations` 失敗已解（`dcecaa7`）：`6c969e4` 改寫 plotcore 格距精度後，變異搜尋字串過期；改為 `Math.min(floor - 1, last)`，21/21 通過。軸刻度行為未變。

## 多協定解碼（2026-10-27，計畫審畢、等預覽核可）

- 目標：第 0 步把共用層（`analysis_decode.py:28` 寫死 i3c、decode.js 只有 scl/sda、標註列以 SCL dx 對齊）改為依協定註冊，I3C 行為不變；之後 I2C／SPI／UART（RS-232/485）／CAN 解碼核心各開 worktree 並行，接線逐一合併、每次跑全套驗證。建議分組：先 I2C+UART，再 SPI+CAN。
- 計畫 `docs/多協定解碼計畫.md`（未 commit）：Codex 三輪唯讀審查，第三輪結論「可開工」（審查輸出在 session scratchpad `codex_multi_review{,2,3}_out.txt`，計畫內有「審查修訂紀錄」）。2026-10-27 使用者決定 §12 Q1–Q11 全部照建議（CAN FD 不解只跳過、UART 不做自動鮑率也不提示、TX/RX 雙 lane、RS-485 不相減、SPI 無 CS 選填閒置分框、雙線不逐 bit、I2C 範圍照列、設定列兩列以 V1 定案、預覽一次送、契約 version 維持 2、CAN 錯誤／過載旗標不區分）。
- **目前卡在預覽閘門**：V1–V11 預覽 https://claude.ai/artifact/C7MuiLcS9mdPJoyCfUgMd8 （原始檔在 scratchpad `multi_decode_preview.html`，合成示意資料）。使用者要先開實機對照，說「可以開工」後才做第 0 步（main，序列），再依 §7 分兩波（I2C+UART、SPI+CAN）開 worktree。
- I3C §12 明確不做項目（HDR 內容、CRR、時序合規、glitch 濾波、自動偵測通道、游標區間解碼等）維持不做。

## X6000A 實機解碼資料分析（2026-10-27）

- 實機檔在 `X6000A-解碼/{I2C,RS-232,CAN}/`（DSO-X 6004A，每組 png／bin／h5／csv；csv＝示波器序列表匯出＝解碼真值）。I2C 檔原放在 `CAN/`，已移到 `I2C/`。**未 commit。**
- 完整分析與給 Codex 的派工規格：`docs/研究_X6000A實機解碼資料分析.md`（BIN `AG10` 欄位表、CSV 欄位、驗收方式）。
- 結論：①BIN＝H5 每 33 點取 1 點（1955 點，偏移 0），只多了通道標籤（SDA1／SCL1／TX1／RX1），**不可用來解碼**；H5 固定 64516 點、無標籤。②兩者都是螢幕解析度，非記憶體全長。③I2C 用 H5 解碼與 CSV 逐筆相符；UART 約 19200 baud、大致可解；CAN 約 50 kbps、H5 每位元僅 ~2.6 點，**檔案不可解**，需 SCPI `:WAVeform:POINts:MODE RAW`。④CSV 時間僅 4 位有效數字，比對須用容差。
- **已完成並 commit（皆為獨立新檔，尚未接 UI／API／檔案分派）**（Codex 實作、Claude 審查；使用者 2026-10-27 明示先派 I2C，等於對這三項放行，**第 0 步共用層與 UI 仍等預覽核可**）：
  - I2C `1ae664f`：`web/i2c_{decode,synth,vectors,check,real_check}.py`。實機 48 列與 `x6000i2c3.csv` 位址／資料／缺少確認／Restart 全相符；時間偏早約 0.7 取樣（H5 1.55 µs 對示波器 20 MSa/s），容差放寬 1 取樣並如實列出。CSV 的 `X`＝`ninth=1`（含讀最後 byte 的正常 NACK，不產生 `nack`）。
  - UART `a3c0c15`：`web/uart_*.py`＋分析文件「附錄：UART 錯誤規則」。實機訊號 19200 baud、LSB first、**反相**，波形支持 8O1，但示波器 CSV 以 **8N1** 解（第九位當 stop，=0 就報錯），故 CSV 的 `Unknown Rx/Tx Error`＝我方 framing、不是 parity；27.68 ms 的 TX `31` 第九位為 1 是兩種規則的分辨反例。CSV 時間：字元／空白列＝start 中心（邊沿＋0.5T），錯誤列＝第一 stop 中心（＋9.5T）。131 列中 130 列可驗相符，首列 `?/65` 無法還原。內部私有 `_levels_at`，**第 0 步完成後改用 `logic.levels_at`**。
  - BIN `8143a43`：`storage/bin_reader.py`（`read_bin_bytes`／`read_bin_file`／`guess_roles`）。BIN＝H5 每 33 點取 1 點，電壓差僅 float32 捨入（≤1.2e-7 V，容差 4e-7）；規格原寫「逐點相等」是錯的，已更正。**尚未接進 `storage/reader.py` 的副檔名分派**（該檔凍結，由 lead 改）。
- 待辦：①第 0 步共用層（等預覽核可）→ 接線 I2C／UART（UART 預設格式已定案＝**8N1**，照示波器；`options()` 預設即 bits=8／parity=N／stop=1／invert=False，baud 必填。實機波形像 8O1，使用者要驗奇偶時自行改 parity；X6000A 這份資料要勾反相才能解）；②`reader.py` 接 BIN；③SPI（無實機資料）；④CAN：H5 每位元僅 ~2.6 點不可解，需 SCPI `:WAVeform:POINts:MODE RAW` 取完整記憶體；⑤H5 無標籤時的通道指派 UI（BIN 標籤可 `guess_roles`）。
- 與上一節「多協定解碼」計畫的關係：解碼核心照該計畫介面（`ROLES／BASE／options／run`）寫成，註冊表接線時只需加一行。審查未處理的小項：UART 實機驗收用 h5py（核心只用 numpy）。
