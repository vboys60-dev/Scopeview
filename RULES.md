# 開發規則與界線

**寫任何一行程式碼前先讀完這份。違反硬規則的產出一律退回重做。**

先備知識：`CONTEXT.md`（術語）、`docs/示波器命令規格書.md`（權威 SCPI 規格）、`scope_tool/contracts.py`（契約）。

---

## 一、硬規則（不可協商）

1. **`scope_tool/contracts.py` 不准改。** 它是所有並行任務的唯一共同依賴，改它會讓別人的工作全部作廢。覺得非改不可 → 停下來回報，不要自己動。
2. **不准安裝新的第三方套件。** 可用的只有：`pyvisa`、`pyqtgraph`、`numpy`、`h5py`、`zeroconf`、`PySide6`、`pywebview==6.2.1`（Web 版視窗；平台相依 macOS pyobjc、Windows pythonnet／clr_loader，及 bottle、proxy_tools、typing_extensions），以及 Python 標準函式庫。缺什麼就用標準庫湊。前端不得依賴 CDN；第三方 JS 若要引入（如 uPlot），須放 `static/vendor/` 並附版本、授權、SHA-256。
3. **Qt 綁定只能用 PySide6。** 機器上 PyQt5 / PyQt6 / PySide6 三套並存，混用會直接 crash。程式進入點必須在 `import pyqtgraph` **之前**執行 `os.environ["QT_API"] = "pyside6"`。任何模組都不准 `import PyQt5` 或 `import PyQt6`。Web 入口（`scope_tool/web/`）不啟動 Qt GUI，但 `web/app.py` 開頭同樣先設 `QT_API=pyside6`（防 pywebview 退到 qt 時三套綁定相撞）；`instruments/infiniivision.py` 仍用 `QImage`，故 PySide6 在 Web 版仍是執行期相依。
4. **UI 執行緒不准做 VISA I/O。** 所有 `driver.*()` 呼叫一律丟進 `ui/worker.py` 的 QThread，結果用 signal 回傳。UI 裡出現 `self.res.query(...)` 就是錯的。**Web 入口：** `driver.*()` 只能以函式參照交給 `web/jobs.py` 的 `submit()`，由專用儀器工作執行緒執行（全域儀器鎖，搶不到回 BUSY）；HTTP 請求執行緒與 pywebview 主執行緒不得做 VISA I/O。驗收：`grep -nE "driver\.(screenshot|capture|channels|max_points)\(" scope_tool/web/*.py` 必須 0 筆。
5. **擷取一律存 HDF5。** 擷取頁沒有格式選單、不自動轉檔。CSV 只能從分析頁把已開啟的波形檔匯出：範圍選「全部」或「兩條垂直游標之間」；可勾「縮點」並輸入點數上限（預設 10,000,000），超過就每 N 點取 1 點；欄名照契約 `Time(s),CH1(V)`；數值一律科學記號，位數依資料自動決定（不損失、不出現浮點尾巴）。
6. **檔名一律加時間戳，永不覆蓋。** 格式 `{name}_{YYYYMMDD}_{HHMMSS}.{ext}`。
7. **VISA 例外一律轉成 `ScopeError` 子類別再往外丟。** UI 只 catch `ScopeError`。SCPI Error 273 必須轉成 `RemoteDesktopError`。
8. **寫入型 SCPI 命令後要 `*OPC?`。** 逾時：截圖 15 秒、大檔傳輸 60 秒。逾時或失敗前，要清掉自己在儀器上留下的暫存檔（`:DISK:DELete`）。
9. **示波器只因「使用者手動」或「按下擷取」而停止。** 擷取時若在 RUN：先等一整筆（`10×時基+1` 秒）再 `:STOP`；勾「重新觸發」則 `:DIGitize`。擷取後**維持 STOP**，不准自動 `:RUN`。除此之外不准改使用者的採集設定（例如記憶體深度）。
10. **每個模組留一個 `if __name__ == "__main__":` 自我檢查**，用 `assert`。不要 pytest、不要 fixture、不要測試框架。執行方式一律 `python3 -m scope_tool.<模組路徑>`，必須印出 `xxx self-check OK` 且 exit code 0。前端 JS 例外：用 `node scope_tool/web/static/js/selfcheck_node.js` 或 `static/selfcheck.html`，同樣印 `xxx self-check OK`（Node 僅開發機輔助，不進產品）。
11. **離線分析只作用於已開啟的檔案，不碰儀器。** 量測、FFT、數學／濾波的定義照 `docs/離線分析功能規格.md`（定義以此規格文件為準，參考 Infiniium 手冊）；與手冊有差異的地方要在畫面或註解標明。衍生波形（F1、F2…）不進 CSV 匯出。只用 numpy，不准用 scipy。

## 二、風格規則

- 註解、docstring、UI 文字全部**繁體中文**。變數與函式名用英文。
- 函式簽章寫型別註記。`from __future__ import annotations` 放檔案最上面。
- 不寫只有一個實作的介面、不寫工廠、不為固定值寫設定。`contracts.py` 裡的 `ScopeDriver` 是唯一允許的抽象，因為它真的有兩個以上實作。
- 檔案路徑一律用 `pathlib.Path`。SCPI 裡的 Windows 路徑一律用 raw string（`r"C:\temp\x.h5"`）。
- 單一檔案超過 300 行就是設計有問題，停下來回報。

## 三、明確不做（別自作主張加回去）

掃網段搜尋、傳輸中途取消、示波器面板存到 USB 的 CSV 解析、自訂的 HDF5 結構、非 Keysight 機型、多語系。

> 打包：Mac 維持 `啟動示波器截圖.command`；Windows 版允許用 PyInstaller 打包成 exe（使用者 2026-10-22 同意，於 Win10 上打包）。PyInstaller 僅是打包工具，不隨程式執行；其餘硬規則（不新增執行期第三方套件）不變。

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
| `scope_tool/storage/writer.py`、`csv_export.py` | T4 |
| `scope_tool/storage/reader.py` | T5 |
| `scope_tool/ui/main_window.py`、`ui/worker.py` | T6 |
| `scope_tool/ui/tab_analysis.py`、`analysis_*.py`、`scope_tool/analysis/*.py` | T7 |
| `scope_tool/ui/tab_screenshot.py` | T8 |
| `scope_tool/ui/tab_capture.py` | T9 |
| `scope_tool/main.py` | T10 |

## 五、交付前自我驗收

1. `python3 -m scope_tool.<你的模組>` 印出 OK、exit 0。
2. `git diff --stat`（或 `ls`）確認沒動到別人的檔案。
3. 沒真機的路徑，在 docstring 裡寫明 `# 待真機驗證`，不要假裝驗證過。
4. 回報格式：改了哪些檔、自我檢查結果、哪些行為只有紙上驗證。三行以內。

### Web 版（pywebview）檔案擁有權（2026-10-22 起；原規劃建議書已刪，見 git 歷史）

只准改自己 lane 名下的檔案；契約（L0 檔案）凍結後只有 lead 能改，其他 lane 提需求不自行加欄位。

| Lane | 擁有 |
|---|---|
| L0 契約 | `docs/web-api契約.md`、`web/static/api_contract.json`、`static/index.html`、`static/js/{bridge,mock_backend,mock_catalog,mock_dsp,ui,fmt,main}.js`、`static/js/{l0_check,l0_util,l0_sem}.mjs`、`static/js/analysis/{store,scales}.js` |
| L1a 後端橋接 | `web/{__init__,app,server,jobs,api}.py` |
| L1b 分析服務 | `web/{analysis_api,analysis_util,analysis_fft,analysis_export,analysis_check,analysis_params,decimate,fft_rbw}.py` |
| L2 連線列＋截圖＋資料截取容器 | `static/js/{connbar,tab_screenshot,tab_datacapture}.js`；2026-10-26 使用者授權：本案跨 L0 `index.html`/`main.js`/契約 §7、L6 `app.css` 檔尾、L8 `browser_check.py`/驗收清單，見 docs/archive/資料截取合併計畫.md.gz |
| L3 擷取頁 | `static/js/tab_capture.js` |
| L4 圖表核心 | `static/js/analysis/{tab_analysis,plotcore,mainplot,overview,fftpane,handles,gestures,axes,layout,splitter,voltage,vzoom,floatpanel,floatpanel_math}.js`、`static/css/analysis.css` |
| L5 表格／側欄／游標 | `static/js/analysis/{chanbar,vertical,bpanel,toolbar,results,measure,cursors,summary,cursor_table}.js`、`static/css/vertical.css` |
| L6 樣式 | `static/css/app.css`、`static/css/glass.css`、`static/styleguide.html` |
| L7 打包 | `packaging/**`、`requirements-web.txt`、`啟動示波器截圖_web.command` |
| L8 驗證 | `web/e2e_check.py`、`static/selfcheck.html`、`static/js/selfcheck_node.js`、`static/js/analysis/{l4_check,l5_check,p1_check,p2_check,p2b_check,p2b2_check,p2b3_check,p3_check,p3b_check,p3b2_check,float_check}.mjs`、`web/browser_check.py`、`web/browser_analysis_checks.py`、`web/browser_marker_checks.py`、`web/browser_float_checks.py`、`docs/驗證.md` |

分析頁 GUI 新 command（`view.undo`／`view.redo`／`view.mode`／`view.history`／`view.historyGroup`／`layout.*`）屬 `store.command` 字串，不在凍結契約內，命名由 lead 於 `docs/archive/分析頁GUI改善計劃書.md.gz` 管理。

凍結（所有 Web lane 唯讀）：`contracts.py config.py instruments/* storage/* analysis/* ui/* main.py`。JS 檔同樣 300 行上限（vendor 豁免）。

P3b-1（gui-p3b，使用者授權）：L5/L8 修正沿用 P3b 範圍；L4 `tab_analysis.js` 僅修正 `lowerSummary` 回傳行與必要的 fmt 匯入，採 SI 格式且僅 Y 模式隱藏 ΔX，其餘 L4 實作不動。

P3b-2（gui-p3b2，使用者授權）：L4 axes／gestures／vzoom 框選種類與合併歷史；L8 p3b2_check.mjs、browser_marker_checks.py。新指令 view.zoomKind／view.zoomRect 為 store.command 字串；凍結檔唯讀。

浮動面板（gui-float，使用者授權）：L4 floatpanel.js／floatpanel_math.js；L8 float_check.mjs／browser_float_checks.py。接線可改 L4 tab_analysis／layout、L5 results，樣式限浮動面板。

FFT P1（2026-10-26，使用者授權，先決條件 A／B／C）：同意 Web 契約追加 fft.rbw／vbw 與 FFTResult.segments／vbw，version 維持 2；登記新檔 `web/fft_rbw.py` 為 L1b。本階段跨 lane 限 L0 契約／mock／`l0_sem.mjs` 契約自檢、L1b FFT 後端與自檢、L5 `fft_runner.fftParams` 固定補 null、L8 `e2e_check.py`／`l5_check.mjs`及相關規格文件。不做 UI；`analysis/*` 仍凍結。P2～P4 的新檔／狀態／command 留待該階段登記。

FFT P2（2026-10-26，使用者授權）：跨 L0／L4／L5／L8 新增獨立 FFT 大檢視，保留分析頁 FFT 窗格、峰值頁籤及控制列。登記 `static/js/analysis/tab_fft.js`（L4）、`static/js/analysis/fft_state.js`（L5）、`web/browser_fft_checks.py`（L8）；`tab.select` 為 store command。共用單一 runner／參數，不新增 fftView；Python `analysis/*` 仍凍結。

Liquid Glass P1（2026-10-26，使用者授權）：§6 十項採建議預設，Web 改深色單一主題，Qt 不動；跨 L0 index.html／契約、L8 browser_check.py，新增 static/js/glass_smoke.js（L8）。L6 glass.css 分段與 token 名稱於 P1 後凍結；analysis.css／vertical.css 原有行不改，P2／P3 另行實作。

HTML 報告（2026-10-26，使用者授權）：新增 `static/js/analysis/report.js`（L5）、`analysis/report_check.mjs`（L8）；L5 toolbar 的「匯出 CSV…」按鈕改為「匯出…」下拉（波形 CSV…／HTML 報告…）；L0 契約／mock 追加 `export_report`；L1b `analysis_export.py`；L8 `e2e_check.py`／`selfcheck_node.js`。

I3C 解碼（2026-10-26，使用者授權，依 docs/archive/I3C解碼計畫.md.gz §0／§6，§11 全採預設）：同意 Web 契約追加 decode（job）／decode_frames／decode_bits／export_decode 與 Decode* 型別，version 維持 2。登記新檔 L1b `web/{logic,i3c_ccc,i3c_decode,i3c_events,i3c_fields,i3c_synth,i3c_vectors,i3c_quality,i3c_check,analysis_decode}.py`、L5 `static/js/analysis/{decode,decode_table}.js`、L4 `static/js/analysis/decode_band.js`、L8 `static/js/analysis/decode_check.mjs`／`web/browser_decode_checks.py`；新 store 鍵 decodeResult／decodeSel／plotRect。跨 lane 限計畫 §6 所列：L0 契約兩檔／mock／`l0_sem.mjs`、L1b `analysis_api.py` 三行、L4 `tab_analysis.js`／`mainplot.js` 一行／`analysis.css` 檔尾、L5 `bpanel.js`／`report.js`、L8 `e2e_check.py`／`browser_check.py`／`selfcheck_node.js`／驗收清單。`analysis/*`、`storage/*`、`contracts.py` 仍凍結；glass.css 不改。

I3C P2（2026-10-26，沿用上段授權）：L0 固定解碼 mock 拆至 `static/js/mock_decode.js`；P2 只追加契約／mock／自檢與 Analysis 接線、HTTP 檢查，不做 UI。`analysis_api.py` 僅 import、基底、reset 三處；既有凍結範圍不變。

多協定解碼（2026-10-27，使用者「可以開工」，依 docs/archive/多協定解碼計畫.md.gz §0／§2／§7，Q1–Q11 全採建議）：同意契約**只改說明文字**（`api_contract.json` 的 `types_doc`、`docs/web-api契約.md`），方法、參數、型別結構、version 不變。登記新檔：L1b `web/{synth,i2c_decode,i2c_synth,i2c_vectors,i2c_check,i2c_real_check,uart_decode,uart_synth,uart_vectors,uart_check,uart_real_check,spi_decode,spi_synth,spi_check,can_decode,can_synth,can_check}.py`，備案檔（超出行數才建）`web/{i3c_waveforms,decode_registry_check,browser_proto_checks,spi_fields,uart_fields,can_fields}.py`；L5 `static/js/analysis/{decode_protocols,decode_i3c,decode_i2c,decode_uart,decode_spi,decode_can}.js`，備案 `decode_form.js`／L4 `decode_lanes.js`；L8 `static/js/analysis/decode_proto_check.mjs`、`storage/bin_reader.py` 屬 storage（已另行授權，唯一可新增者）。第 0 步跨 lane 檔案清單＝計畫 §2.6（含 `i3c_decode.py` 檔尾介面、`i3c_synth.py` 改 import、`decode.js／decode_table.js／decode_band.js／report.js／mock_decode.js／analysis.css` 檔尾、`decode_check.mjs`／`report_check.mjs`／`browser_decode_checks.py`／`e2e_check.py` 機械修改）；第 0 步後這些檔凍結，各協定線只准動自己的新檔＋`decode_protocols.js` 一行＋`docs/離線分析功能規格.md` 自己那節。`analysis/*`、`contracts.py` 仍凍結；`storage/reader.py` 已於 2026-10-27 接 `.bin`／H5 `Channel N Data`。

多檔比對（2026-10-28，使用者「可以，開始實作」，依 docs/archive/分析頁多檔比對計畫書.md.gz）：契約追加 add_waveform（job）／remove_slot 與 SlotSummary，version 維持 2。槽位 Mem1～Mem4，通道改名 `MemN.原名`；新 store 鍵 `slots`／`dataRev`（唯一寫入者 `slots.js`，槽位變動不寫 `file`）。登記新檔：L1b `web/analysis_slots.py`；L5 `static/js/analysis/slots.js`；L8 `static/js/analysis/slot_check.mjs`、`web/browser_slot_checks.py`。跨 lane：L0 契約兩檔／`mock_backend.js`／`l0_sem.mjs`；L1b `analysis_api.py`／`analysis_export.py`／`analysis_util.py`／`analysis_fft.py`；L4 `tab_analysis.js`／`mainplot.js`／`overview.js`；L5 `toolbar.js`／`measure.js`／`fft_runner.js`；L8 `e2e_check.py`／`browser_check.py`／`selfcheck_node.js`／`l4_check.mjs`／`l5_check.mjs`／驗收清單。`decode*.js`、`analysis/*`、`storage/*`、`contracts.py` 仍凍結。

多檔比對追加授權（2026-10-28，使用者「修」）：允許修改 `web/analysis_decode.py` 存回快照前核對來源物件（競態），及 `toolbar.js`／`mainplot.js` 讓加數學通道不再當換檔；其餘凍結不變。

基本量測修正與 UI 接線（2026-11-12，使用者「把 UI 接線也做完」，依 Codex／Opus 審查結論，審查與驗收紀錄見本次 session）：核心 `analysis/measure.py`（＋`measure_check.py`）解凍修改——近常數資料視為平坦、閾值驗證、`measure_all`／`stats` 單事件模式（`meas_all_edges`，預設 True＝舊行為；`measure_all` 另加 `dx`，新增 `measure_event` 供 Web／Qt 共用單事件極性合併）、單週期 Vavg／Vrms（`mode="cycle"`，含 `ref_time`／`dx`）；`analysis/*` 其餘仍凍結。契約追加 MeasureEntry `mode="cycle"`（One Cycle）與可選欄位 `all_edges`（缺省 true），version 維持 2。跨 lane：L0 `api_contract.json`／`docs/web-api契約.md`／`mock_backend.js`／`mock_measure.js`／`mock_measure2.js`／`l0_check.mjs`／`l0_util.mjs`／`mock_current_check.mjs`；L1b `analysis_api.py`／`analysis_params.py`／`analysis_export.py`／`analysis_check.py`／`analysis_current_check.py`；L5 `measure.js`／`results.js`；L8 `p2b3_check.mjs`；Qt `ui/{analysis_controls,analysis_layout,analysis_results,analysis_runner,analysis_fftplot,tab_analysis}.py`（Qt 加「全部邊緣」開關、參考點改用顯示時間含 dx；不新增區間選擇 UI）；文件 `docs/離線分析功能規格.md`／`docs/驗證.md`。`contracts.py`、`storage/*` 不動。

分析頁選單與拖放（2026-11-12，使用者「決定的事 1.照建議 2.3.照建議」「照預設」，依 plan_opus §4／tasks_fable T1；**僅 Web，Qt 版全部延後、`ui/*` 不動**）：「⋮」欄位選單與工具列「檔案 ▾／分析 ▾」改用 Popover（top layer）；量測鈕可拖到通道列（Pointer Events，鍵盤替代為通道名稱可聚焦選取）。UI 計畫 P2 的 Math／FFT 頻譜搬移改以「分析 ▾」取代，以本段為準；P2 其餘（來源／範圍／閾值移左欄、「游標置中」改字）照做，工具列「完整時間」一併移除；「關閉」不加確認，只放「檔案 ▾」底部並以分隔線隔開。登記 `static/js/analysis/marker_menu.js` 為 L5（新增 `popMenu`）；新檔 L8 `web/browser_menu_checks.py`、`web/browser_drag_checks.py`、`static/js/analysis/menu_check.mjs`、`static/js/analysis/drag_check.mjs`。跨 lane 限：L4 `analysis.css` 的 `.results__menu*`／`.results__choices` 三行（原地改）；L5 `results／toolbar／measure／chanbar／cursors.js`、`vertical.css`；L8 `browser_analysis_checks.py`（原地改字）、`browser_float_checks.py`、`browser_check.py`（合併 import 騰行，總行數不增）、`selfcheck_node.js` 一行、`float_check.mjs`／`p1_check.mjs`／`p2b3_check.mjs` 原地改、`docs/驗證.md`。契約、store 鍵、後端、`analysis/*`、`glass.css`、`app.css`、`decode*.js` 不動。

離線分析 UI 修正第二輪（2026-11-13，使用者確認 D1～D6 全照預設，依 docs/離線分析UI修正計畫_20261112.md 與 plan2；**僅 Web，Qt 延後**）：跨 L4 `axes.js`／`layout.js`／`fftpane.js`／`tab_analysis.js`／`analysis.css`；L5 `toolbar.js`／`fft_state.js`／`results.js`／`chanbar.js`／`vertical.js`／`bpanel.js`／`measure.js`、`terms.js`（原無擁有者，登記 L5）；L6 列入授權但本輪無實際修改（通道列 Math「＋」取消，以「分析 ▾」為準）；L8 `browser_check.py`（原地改，維持 300 行）、`browser_analysis_checks.py`、`browser_decode_checks.py`、`browser_marker_checks.py`（docstring）、`browser_menu_checks.py`（可選加「更多…」檢查）、`dock_check.mjs`（註解）、`p2b2_check.mjs`、`p2b3_check.mjs`。`decode_table.js` 解凍一行：「解碼」鈕移到參數列最前，其餘仍凍結。右側欄門檻 `DOCK_MIN_VW` 改 1280。不新增 store 鍵／command（不新增 `math.open`）。契約、後端、`analysis/*`、`glass.css`、其他 `decode*.js` 不動。

離線分析可選功能（2026-11-13，使用者「可選功能全都要做」，依 plan_optional；**僅 Web，Qt 延後、`ui/*` 不動**）：
核心解凍：`analysis/measure.py` 僅限把 `stats` 的目前事件選取抽成公開 `current_index(values, ref)`（行為不變）；登記新檔 `analysis/measure_extra.py`（Vmid、上升／下降邊緣計數、±脈衝計數、Delta Time，名稱表 `EXTRA` 不併入 `MEASUREMENTS`）與 `analysis/measure_marks.py`（Track Measurements 事件座標），歸 T7；`analysis/*` 其餘仍凍結。
契約追加，version 維持 2：catalog.measurements 追加 Vmid、上升邊緣計數、下降邊緣計數、+脈衝計數、-脈衝計數、Delta Time；MeasureEntry 可選欄位 `edge_num`、`edge_num2`（int，缺省 1，範圍 1–65534）、`edge_level`、`edge_level2`（`lower|middle|upper`，缺省 middle）、`track`（bool，缺省 false）；MeasureResult 可選欄位 `marks`（`[float,float,str][]|null`，顯示時間、通道單位值、通道名；僅 track 列有值）；`fft` 追加參數 `phase_ref`（float|null，顯示時間，null＝來源時間 0 的舊行為）、`unwrap`（bool）；`optional_fields`、`types_doc` 同步。
登記新檔：L1b `web/analysis_measure.py`（MeasureMixin，自 `analysis_api.py` 搬出 measure）；L8 `web/analysis_more_check.py`、`web/browser_measure_more_checks.py`、`static/js/analysis/measure_more_check.mjs`、`static/js/analysis/view_more_check.mjs`；L5 補登既有 `markers.js`、`marker_table.js`、`marker_layer.js`、`cursor_table.js`；刪除 `summary.js`。
跨 lane：L0 契約兩檔／`mock_catalog.js`／`mock_backend.js`（fft 參數）／`mock_measure.js`／`mock_measure2.js`／`l0_check.mjs`（第 50 行原地改）／`l0_sem.mjs`；L1b `analysis_api.py`、`analysis_fft.py`、`analysis_params.py`、`analysis_check.py`；L5 `measure.js`、`results.js`、`cursors.js`、`toolbar.js`、`vertical.js`、`slots.js`、`fft_runner.js`、`fft_state.js`、`markers.js`、`marker_table.js`；L8 `e2e_check.py`（原地改）、`browser_check.py`（合併 import 騰行，總行數不增）、`browser_marker_checks.py`、`browser_menu_checks.py`、`browser_fft_checks.py`、`browser_slot_checks.py`、`selfcheck_node.js`、`l5_check.mjs`（原地改）、`p3_check.mjs`、`marker_check.mjs`、`slot_check.mjs`、`docs/驗證.md`；文件 `docs/離線分析功能規格.md`。新 store command `measure.track`；不新增 store 鍵。

可選功能 W8 追加授權（2026-11-13，lead 補登）：`gestures.js` 的 snapshot／apply／zoomRect 擴充為可記錄 time_offset，讓「對齊主檔」可一次復原；原有 name／scale／position 項目的行為不變。

已知缺口第一波（2026-11-13，使用者「已知缺口 opus 規劃 codex 做 opus 驗收」，依 plan_gaps；**僅 Web，Qt 延後、`ui/*` 不動**）：L4 `layout.js`（停靠改依圖區寬度，新增 `DOCK_PLOT_MIN`）、`dock_check.mjs`；L5 `marker_menu.js`（選單 `role=menu` 與方向鍵）、`toolbar.js`（`role=menu`、`aria-haspopup="menu"`）；L8 新檔 `static/js/analysis/toolbar_check.mjs`，並更新 `menu_check.mjs`、`browser_menu_checks.py`、`browser_marker_checks.py`、`selfcheck_node.js`（FILES 增一項）。不涉及凍結檔。

已知缺口第二波追加授權（2026-11-13，使用者選「預設帶入更聰明」「FFT 疊圖方案 A」「分格可手動指派」）：解凍 L5 `decode.js` 僅限 `defaultConfig` 的來源預設帶入（通道名稱符合 `^角色key\d*$`（不分大小寫）就帶入，找不到才照順序），其餘不動；登記 L4 新檔 `fft_overlay.js`（前端頻譜快照，不改後端與契約）並更新 `fftpane.js`、L8 `fft_overlay_check.mjs`、`browser_fft_checks.py`、`decode_check.mjs`、`decode_proto_check.mjs`。

## 選單修正（Popover 替代做法）
- 授權新增：`scope_tool/web/static/js/analysis/popover_fallback.js`、`popover_fallback_check.mjs`；修改 `marker_menu.js`（popMenu 呼叫替代）、`css/vertical.css`（`.popmenu[data-open]`）、`selfcheck_node.js`（登記）。


## 分割格線授權
使用者授權 Web 分割格線；新檔 `static/js/analysis/grids.js`、`grid_check.mjs`、`web/browser_grid_checks.py`；新 store 鍵 `grids`，localStorage 鍵 `scope.analysis.grids.v1`。
本波修改 `mainplot.js`、`handles.js`、`marker_layer.js`（nearestChannel 分格篩選）、`cursors.js`（markerResult 加 ch）、`selfcheck_node.js`、`browser_check.py`（原地改、維持 300 行）。
後續波追加 `gestures.js`（原地）、`vzoom.js`、`toolbar.js`、`chanbar.js`、`vertical.css`、`toolbar_check.mjs`、`menu_check.mjs`、`browser_menu_checks.py`、`docs/驗證.md`。
語意變更：分開堆疊改為每格各自堆疊（n=1 不變）。不動 L0、`analysis/*`、`ui/*`、後端、`marker_menu.js`；本波不動 gestures。

## 選單浮層樣式授權
使用者授權僅 Web：L5 `static/css/vertical.css`、`static/js/analysis/marker_menu.js`（僅 popMenu 向上翻）、`popover_fallback.js`（堆疊祖先 class）及 `popover_fallback_check.mjs`；L8 `menu_check.mjs`、`web/browser_menu_checks.py`（≤260 行）、`web/browser_check.py`（原地一行、維持 300 行）、`docs/驗證.md`。
不動 `app.css`／`glass.css`／`analysis.css`／`toolbar.js`／`results.js`／契約／store／後端／`ui/*`；非 vendor 檔 ≤300 行。只跑 Node 自檢與 Python 編譯檢查，瀏覽器驗收由主控執行。

## 剩餘小項第一波授權（2026-11-13，使用者「照建議」，依 Opus／Codex 兩份規劃；僅 Web，Qt 延後、`ui/*`、`analysis/*`、後端、契約形狀不動）
- L0：`bridge.js` 第 140 行事件失敗文案（原因空白時不顯示括號）、`l0_check.mjs` 加對應斷言。
- L4：`mainplot.js`（`pending` 在零尺寸時不設）、`report.js`（零尺寸匯出立即提示「請先切回波形分頁再匯出」，不等 3 秒；有效尺寸才等 pending）、`report_check.mjs`。
- L5：`measure.js`（吞 click 保護改依 pointerId，原地改、不增行）、`drag_check.mjs`（補交錯案例）。
- L8：`browser_menu_checks.py` 最外圈 hit test 補邊緣取樣，並抽共用幾何到新檔 `web/browser_menu_geom.py`，原檔降至 ≤260 行；`browser_fft_checks.py` 補 1000×700 FFT 高度斷言與零尺寸匯出計時；`p2b_check.mjs` 補 1000×700 fftOn 斷言；`selfcheck_node.js` 如需登記。
- 文件：`HANDOFF.md` 更新過期項目（validate_params 已接 server、toolbar Node 測試已存在、FFT 快取／log 軸重算／重入僅 Qt）、`docs/驗證.md`。
- 決策：A 只加「依通道順序帶入，請確認角色」提示留待下一波；D 的 RF 快取、h5py 懶載入、FFT 疊圖方案 C 不做。F1 另排第二波。非 vendor 檔 ≤300 行；`browser_check.py` 維持 300 行不動。瀏覽器驗收由主控執行。

## 第二波授權（2026-11-13，使用者「F1 要做，完成後接著處理 1000×700 頻譜偏矮；Opus 規劃、Codex 做、Opus 驗收」；僅 Web，Qt 延後）
- F1 分割格線跨格拖把手：L4 `handles.js`（新增 `handleDrop`、`dragHandle`、`commitHandle`、`drawDrop`）、`gestures.js` 原地改（**維持 253 行**）；L8 `grid_check.mjs`、`browser_grid_checks.py`、`docs/驗證.md`。不動 `grids.js`、`cursors.js`、`browser_check.py`、契約、store 鍵、後端、`ui/*`。語意：n>1 圖外放開取消（不再能拖出 ±5 div）；n=1 不變。
- 頻譜偏矮（方案 A，F1 驗收後才開工）：L4 `layout.js`（`FFT_TAB_MIN`、`clampLayout` 加 `fftTab`）、`tab_analysis.js` 原地改；L8 `p2b_check.mjs`、`browser_fft_checks.py`、`docs/驗證.md`。不動 `browser_check.py`。
- 頻譜偏矮追加授權：`float_check.mjs` 僅補測試用 Function 參數 `activeTab`（`tab_analysis.js` 新增 `fftTab: activeTab === 'fft'` 所致），不改斷言。

## 改進第一波授權（2026-11-13，使用者「開始第一波」，項 1、2、5、7 決策全採建議；僅 Web，Qt 延後）
- 項 1 框選與游標線分開：L4 `gestures.js` 原地改（**維持 253 行**；框選模式命中游標線時拖線，Shift 仍強制框選，中鍵／Space 平移不變）、hover 提示放寬；L8 `p2_check.mjs`（舊斷言隨語意修改）、`browser_drag_checks.py` 或新 helper。`cursors.js` 不增行。
- 項 2 框選開啟色：L4 `analysis.css` 檔尾（高 specificity 局部規則，不動 `glass.css`）。
- 項 5 「分析 ▾」加「解碼…」：L5 `toolbar.js`（目前 155 行）、必要時 `bpanel.js`／`tab_analysis.js` 原地小改（只開 B 區解碼頁籤並展開加高，仍由使用者按解碼）；L8 `toolbar_check.mjs`、`browser_menu_checks.py`（≤260 行，超出則放新 helper）、`docs/驗證.md`。
- 項 7 I2C 時間軸：L1b `logic.py` `validate_time` 兩通道時間軸比較改容差（`max|Δt| ≤ 0.01×中位取樣間隔`，長度仍須相等；實機 `i2cdemo.h5` 兩通道 XOrg 差 16 ps＝0.0008 dt）；L8 `i2c_real_check.py`／`i3c_quality.py`／`analysis_slots.py` 補/改測試；新增以 `H5參考波形/i2cdemo.h5` 對照 `i2cdemo.csv`（檔案不存在則略過）。解碼只用 base 時間軸，不動資料。
- 不動 `browser_check.py`、契約、store 鍵、`glass.css`、後端其他檔、`ui/*`。
- 第一波追加授權（Opus 驗收必修）：L8 `browser_analysis_checks.py`、`browser_marker_checks.py`（框選測試改按 Shift 強制框選）、`browser_grid_checks.py`、`browser_menu_checks.py`（分析選單清單加「解碼…」），皆原地改、行數不增。
- 第一波追加授權：`menu_check.mjs` 第 72 行正規表示式隨「解碼…」併入 `menu("分析", …)` 同步；`gestures.js` 改為 Shift 一律強制框選（含壓在 Marker 上），`p2_check.mjs` 同步。

## I2C 角色自動辨識 波 A 授權（2026-11-13，使用者「照建議」D1–D7、「開始波 A」；僅 Web，Qt 延後）
- 後端：新檔 `web/i2c_roles.py`（L1b，含 `__main__` 自檢）；`web/i2c_decode.py`（options 接受布林 `estimate`、一行 import）；`web/analysis_decode.py` 解凍兩行（estimating 分支改依 `hasattr(mod,'estimate_waveforms')`／protocol 含 i2c，行數維持）；`web/i2c_real_check.py`。
- 前端：`static/js/analysis/decode_i2c.js`（`estimatedRoles` 與「辨識角色」action，交換 SCL/SDA 下拉與手動門檻）、`static/js/mock_decode.js`（i2c 接受 estimate）、`decode.js` 至多一行（estimate 必填檢查放寬）、`decode_proto_check.mjs`。
- 契約僅說明文字：`static/api_contract.json`、`docs/web-api契約.md` 各加一句；`docs/驗證.md`、`docs/離線分析功能規格.md` I2C 節。
- 不動 `decode_table.js`、store、契約形狀／version、`analysis/*`、`ui/*`。非 vendor 檔 ≤300 行。瀏覽器驗收由主控執行。

## I2C 角色自動辨識 波 B 授權（2026-11-13，使用者「波B開工」；僅 Web，Qt 延後）
- 前端：`static/js/analysis/decode.js`（限 `defaultConfig` 標記 `guessed`、`change` 角色變動清旗標、`run()` 前置估計並附加警告；≤300 行）；`decode_table.js` 一行（`render` 讓角色下拉跟上 `p.ch`）；`decode_i2c.js`（若需提供 `estimateRoles` 套用函式）、`mock_decode.js`（如需）；`decode_check.mjs`、`decode_proto_check.mjs`。
- 新檔 `web/browser_i2c_roles_checks.py`（L8，≤300 行，不接入 browser_check.py）。
- 後端、契約、store 鍵、`analysis/*`、`ui/*` 不動；`analysis_decode.py` 不動。
- 瀏覽器驗收由主控執行。
- 波 B 驗收追加（lead，依 Opus M1）：`report.js` 解碼報告 caption 附加 `summary.warnings`（原僅 I2C 對調說明經 `decode_i2c.js` summary 帶入，造成警告列重複，已撤回）；toast 改在對調當下跳。

改進第二波 項 4（2026-11-13，使用者「開工」，Q1–Q5 全採建議，僅 Web，Qt 延後、`ui/*` 不動）：Marker Table 工具列加「獨立點通道」下拉，新增獨立點時可選通道，不改 `store.selected`；連動 M1 行為不變；不提供改既有 Marker 通道。可改：L5 `static/js/analysis/marker_table.js`；L8 `static/js/analysis/marker_check.mjs`、`web/browser_marker_checks.py`（原地擴充，≤300 行；超出改新檔 `web/browser_marker_add_checks.py`，不接入 `browser_check.py`）、`docs/驗證.md`。不動 `markers.js`／`marker_menu.js`／`marker_layer.js`／`cursors.js`／`gestures.js`／`browser_check.py`／`selfcheck_node.js`／CSS／契約／store 鍵與 command／後端／`analysis/*`；**不碰 `decode*.js`、`mock_decode.js`、`decode_check.mjs`（已 commit，不需動）**。非 vendor 檔 ≤300 行。實作者只跑 Node 自檢與 `python -m py_compile`，瀏覽器驗收由主控執行。

改進第三波・項 6 FFT 手動 Marker（2026-11-13，使用者「項6開工」，D1–D10 全採建議；**僅 Web，Qt 延後、`ui/*` 不動**）：登記新檔 L5 `static/js/analysis/fft_manual.js`、L8 `static/js/analysis/fft_manual_check.mjs`。修改 L4 `fftpane.js`（工具列兩鈕）；L5 `fft_marker_layer.js`、`fft_marker_table.js`、`fft_state.js`（第 89 行原地改名）；L8 `fft_marker_check.mjs`（第 124 行原地，行數不增）、`selfcheck_node.js`（FILES 原地加一項）、`web/browser_fft_checks.py`、`docs/驗證.md`；文件 `docs/離線分析功能規格.md` FFT 段。`store.fftMarker` 新增欄位 `manual`（寫入者只有 `fft_manual.js`），不新增 store 鍵／command。契約、後端、`mock_backend.js`、`report.js`、`cursors.js`、`fft_markers.js`、`fft_runner.js`、`analysis/*`、`decode*`、`mock_decode.js`、`glass.css`、`app.css` 不動。非 vendor 檔 ≤300 行。實作者只跑 Node 自檢與 Python 編譯，瀏覽器驗收由主控執行。計畫：scratchpad `out/item6_plan.md`。
- 項 6 驗收追加（lead）：`css/analysis.css` 加一條 `.analysis--dock .analysis__fftbar` 允許換行（新增兩鈕使 Dock 模式工具列溢出，P4 版面檢查失敗）；`fftpane.js`「清除 Marker」鈕文字縮為「清除」（title 保留全名）；`browser_fft_checks.py` 峰表步驟後切回「量測」分頁以免污染後續選單檢查。

改進第四波・項 8 解碼事件三角標記（2026-11-13，使用者核可 v2；**僅 Web，Qt 延後、`ui/*` 不動**）：L4 `mainplot.js`（新增 export `decodeMarks`、監聽 `decodeResult`／`decodeSel` 但不重抓波形、測試鉤子 `canvas.decodeMarks`）；L5 `report.js` `KEYS` 原地加 `decodeSel`；登記新檔 L8 `static/js/analysis/decode_mark_check.mjs`、`web/browser_mark_checks.py`（不接入 `browser_check.py`）；L8 `selfcheck_node.js`（FILES 原地加一項）、`docs/驗證.md`；文件 `docs/離線分析功能規格.md` 解碼節。來源或基準通道不存在時不畫。不動 `decode*.js`、`mock_decode.js`、`gestures.js`、`cursors.js`、`handles.js`、`grids.js`、`slots.js`、CSS、契約、store 鍵與 command、後端、`analysis/*`、`fft*`。非 vendor 檔 ≤300 行。實作者只跑 Node 自檢與 Python 編譯，瀏覽器驗收由主控執行。

改進第四波・項 3 波 3A 波形內標籤版面 B（2026-11-13，使用者核可 v2 並下令開工；**僅 Web，Qt 延後、`ui/*` 不動**）：登記新檔 L4 `static/js/analysis/chanlabels.js`、L8 `static/js/analysis/chanlabels_check.mjs`、`web/browser_label_checks.py`（不接入 `browser_check.py`）。修改 L4 `mainplot.js`（刪每格標題、先配置後繪製的標籤／游標文字、Y 讀值改右緣、hover 與 title、測試鉤子 `canvas.labelLayout`）、`handles.js`（把手文字改形狀＋序號、回傳 title）、`gestures.js` **僅第 180 行原地**改讀 title（不增行）；L5 `report.js`（`collectReport` 前清 hover，+1 行）、`vertical.js`（標籤底下拉）、`slots.js` 第 23 行原地（加 `labelBg`）、`static/css/vertical.css`；L8 `p1_check.mjs`（250–252 原地）、`p2b2_check.mjs`（137 原地）、`selfcheck_node.js`（FILES 原地加一項）、`docs/驗證.md`；文件 `docs/離線分析功能規格.md`。通道記錄新增可選欄位 `labelBg`、`alias`（3A 只讀 alias）；不新增 store 鍵／command。不動 `cursors.js`、`voltage.js`、`grids.js`、`decode*`、`fft*`、契約、後端、`analysis/*`、`glass.css`、`app.css`。非 vendor 檔 ≤300 行。只跑 Node 自檢與 Python 編譯，瀏覽器驗收由主控執行。項 8 已 commit（ae472bd）。
項 3A 驗收追加（lead，2026-11-13）：把手文字變「形狀＋序號」使舊快照失效，追加授權原地更新 L8 `p3b_check.mjs:129`（命中座標，分欄把手 24px 後不再重疊，改測各取自己）與 `grid_check.mjs:58–59`（把手文字／寬度／title 快照），行數不變。

改進第四波・項 3 波 3B 通道別名（2026-11-13，使用者「開始 3B，三組並行交給 Codex」；**僅 Web，Qt 延後、`ui/*` 不動**）：登記新檔 L5 `static/js/analysis/alias.js`、L8 `alias_check.mjs`（純函式，lead 已寫）、`alias_chanbar_check.mjs`（A 組）、`alias_tables_check.mjs`（B 組）、`alias_misc_check.mjs`（C 組）、`web/browser_label_checks.py` 追加 B7–B9（lead 於整合階段）。三組分工（檔案互不重疊）：A＝`chanbar.js`、`vertical.css`、`handles.js`（title）、`chanlabels.js`（文字改 `chLabel`，並含 3A 建議 S2／S3／S4）、`slots.js`（23 行原地，同槽同路徑才沿用 alias）、`chanlabels_check.mjs`（S4）；B＝`measure.js`（118、209）、`results.js`（87–88）、`cursors.js`（**維持 267 行**）、`cursor_table.js`、`marker_table.js`；C＝`fft_state.js`（96–97）、`decode_table.js`（**解凍**，僅 22–27、55、106、108、110 與 import）、`toolbar.js`（74）、`report.js`（105、146、波形段對照表）。`alias` 寫入者只有 `chanbar.js`；所有 option value 維持原名。lead 專屬：`selfcheck_node.js`、`docs/驗證.md`、`RULES.md`、`browser_check.py`。不動 `gestures.js`、`fftpane.js`、`fft_marker_*.js`、`fft_manual.js`、`decode.js`、`decode_band.js`、`mock_decode.js`、`tab_analysis.js`、契約、store 鍵與 command、後端、`analysis/*`。非 vendor 檔 ≤300 行。各組只跑自己的 Node 自檢與 `node --check`／`py_compile`，瀏覽器驗收由 lead 執行。
- 3A 建議 S1 補記：`p1_check.mjs:125`、`p2b2_check.mjs:193` 於 3A 驗收時原地修改（`p2b2_check.mjs:193` 斷言偏弱，A 組改為檢查標籤文字）。授權 A 組原地改這兩檔對應行（行數不增）。

GUI-1 右側欄停靠解碼頁溢出修正（2026-11-13，使用者「現在修」；僅 Web）：只改 `static/css/analysis.css`（dock 下 `.analysis__resultTabs` 換行；`.decode__form`／`.decode__params` 加 `flex-wrap`、`min-width:0`）；`docs/驗證.md`、`HANDOFF.md`。不動 JS、契約、其他 CSS。

GUI-1b 右側欄頁籤列仍溢出（2026-11-14，使用者回報截圖，Opus＋Codex 找根因）：只改 `static/css/analysis.css` 第 152 行（dock 下 `.analysis__resultTabs` 覆寫 `flex:0 0 auto`，加 `min-width:0;max-width:100%`）；`docs/驗證.md`。不動 JS、契約、其他 CSS。

窄版 B 區標頭與 ⓘ（2026-11-14，使用者「先修正題2與題3」；僅 Web，Qt 延後、`ui/*` 不動；分支 `fix/narrow-fft-header`）：題 2＝lowerTab 下 B 區標頭照常顯示、只停用拖曳與雙擊重設，▾ 仍可收折。可改 L4 `splitter.js`（`host.hidden` 只對 fft、加 `data-resize`、雙擊在停用時不重設）、`tab_analysis.js`（`layout.toggle` 僅 fft 停用時擋、`lowerHeader.tabIndex`）；`css/analysis.css`（`[data-resize="off"]` 游標）；新檔 L8 `static/js/analysis/lowertab_check.mjs`、`selfcheck_node.js`（FILES 原地加一項）；`web/browser_menu_checks.py` 只改 `load()` 的等待（維持 ≤260 行）。題 3＝移除 `results.js` 的 ⓘ，說明搬到 Current 表頭（title＋aria-label）；可改 `results.js`、`analysis.css`（刪 `.results__info`）、`p2b3_check.mjs`（note 斷言改到表頭、動作列子節點索引）、`float_check.mjs`（142／146 索引）。不動契約、store 鍵與 command、後端、`analysis/*`、`layout.js`、`marker_menu.js`、`popover_fallback.js`。非 vendor 檔 ≤300 行。「⋮ 要拉很低才有用」根因未明，本次不改。

⋮ 選單被 B 區裁掉（2026-11-14，使用者實測：Console 將 `.analysis__lower` 的 overflow 改 visible 後選單出現）：只改 `static/css/analysis.css` 的 `.analysis__lower`（`overflow:hidden`→`visible`）；`docs/驗證.md`、`HANDOFF.md`。不動 JS、契約、其他 CSS。
