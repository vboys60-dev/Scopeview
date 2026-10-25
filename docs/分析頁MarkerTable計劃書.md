# 分析頁 Marker Table 計劃書

2026-10-25 起。使用者已確認需求與版面（預覽僅供排版，不入庫）。Opus／Codex 雙研究結論已併入。**契約不升版**：只用現有 `cursor_readout`／`marker_eval`／`fft`／`fft_track_rf`；新 store 鍵 `markerTable`、`fftMarker` 比照 `markerResult` 前例，不在凍結契約內。

## 已確認決定

1. 版面：**A 底部並列**（B 區「游標｜Marker」左右分兩欄，B 寬≥1200px 且高≥150px；游標表 8 欄實需此寬，其餘改分頁）與 **C 右側欄**（圖右側固定直欄，兩表上下疊）都要，可切換；<900px 兩者皆自動收成底部抽屜／分頁，沿用既有規則且不覆寫偏好。**不做**獨立雙浮窗（既有 floatpanel 搬整個 B 區，頁籤做好後自然可用）。
2. 時域 Marker：
   - **連動組**＝以 **M1 的時間點**，每個通道各列一列（該通道在此時間的讀值）；拖 M1，各通道同步。各通道各自吸附到自己的取樣點，落在該通道時間軸外顯示「—」。
   - **獨立點**＝使用者在單一通道上自己加的點；**每通道最多 10 點**（連動組的各通道列不計入）。
   - 表格欄：`# ｜通道｜時間｜電壓｜Δt vs M1｜註記｜刪除`。註記直接在儲存格編輯（Enter 確認、Esc 取消）；圖上標籤截 12 字。
   - 不存讀值，只存 `{id, ch, t_src, link:boolean, note}`（連動組存顯示時間 `t`）；換檔（gen 變動）就清空。吸附一律走後端全精度，不用前端降採樣資料。
3. 互動：主圖**右鍵**在指標時間、最近曲線上新增（點不到曲線用 selected 通道，`preventDefault`）；雙擊不可用（已佔用）；拖曳只水平移動、命中 6 px，順序在游標把手之後、游標線之前；放開才向後端吸附，防抖 40 ms。點表格列→圖上高亮，點不在畫面內則移畫面置中（可 Undo）；滑過圖上的點→表格對應列反白；Delete／✕ 刪除。
4. **FFT Marker Table**：
   - 一條**基準線**（水平虛線，±4 px 命中優先於平移，可拖曳）；高於基準線的峰（嚴格高於，沿用 `peaks.py` 規則）列入表單。
   - 工具列：基準線值＋**單位選單**（取 `catalog.fft_units`，去掉 `Phase`：dBm／Vrms／dBV／dBmV／dBµV／Watt）、顯示數量 n、排序（`catalog.peak_sorts`）。換單位時基準線自動換算（dBm 依阻抗）；線與輸入框雙向同步。
   - **峰值不收註記**（重算後峰 id 不穩）。不開放內插開關（後端寫死 `interpolate=True`），表格加註腳「頻率已內插」。
   - 表格欄：`# ｜頻率｜振幅｜高於基準線`；峰數超過抓取上限時顯示「已截斷」。點峰值列→沿用 `rf.intent` 標示。
   - 效能：改基準線／n 不再重跑 FFT。以寬鬆參數抓一次（`peak_count=1000`、Decreasing Magnitude、level＝目前最低基準），之後在前端依基準線過濾、排序、取前 n；只有基準線拉到抓取值以下才重抓。RF 跳峰門檻改跟基準線一致。
5. 與既有游標分開：`store.cursors` 只由 `cursors.js` 寫入，Marker 不碰；X1/X2 的 ΔY/ΔX 維持現狀。JSON 匯出入只帶 time／ch／link／note。

## 分階段

- **P1 時域 Marker 資料與圖上繪製**：新檔 `markers.js`（模型＋吸附，呼叫 `cursor_readout`／`marker_eval`）、`marker_layer.js`（主圖繪製／命中／右鍵／拖曳），gestures／mainplot 只加掛鉤。
- **P2 時域 Marker Table 與版面 A**：`marker_table.js`；bpanel 加 `marker` 頁籤（`TABS`），≥820 與游標並列。
- **P3 FFT 基準線與 FFT Marker Table**：`fft_markers.js`＋基準線繪製／拖曳；toolbar 的門檻／數量改接 `fftMarker`，峰表前端過濾。
- **P4 版面 C 右側欄**：layout 加側欄模式與切換鈕，<900px 收抽屜。
- 每階段：Codex 編碼→沙箱外跑 `selfcheck_node.js`、`e2e_check`、`browser_check`→Opus 唯讀審查→提交。每階段留 `*_check.mjs`（lane L8）。

## 檔案與 lane（使用者 2026-10-25 授權本計劃跨 lane，比照 P3b-2／gui-float）

- 新檔：`markers.js`、`marker_layer.js`、`marker_table.js`、`fft_markers.js`（L5 風格，各 ≤300 行）、`marker_check.mjs`（L8）。
- 小改（僅掛鉤）：L4 `gestures.js`／`mainplot.js`／`fftpane.js`／`layout.js`／`tab_analysis.js`；L5 `bpanel.js`／`toolbar.js`／`results.js`；`css/analysis.css`。
- 不動：L0 契約檔、`scope_tool/analysis/*`、`contracts.py`。`store.js` 屬 L0：若需新鍵先確認 `store.set` 是否接受未登記鍵（markerResult 前例），否則停下回報。
- 新 command：`marker.add`／`marker.move`／`marker.remove`／`marker.note`／`marker.link`／`fftMarker.level`／`fftMarker.unit`／`fftMarker.count`／`layout.markerSide`，皆為 `store.command` 字串。

## 已知風險

`cursors.js`(256)、`gestures.js`(244) 近上限，邏輯一律放新檔。`axes.js`／`gestures.js` 各存一份 `zoomKind` 的既有風險（見 HANDOFF）不在此範圍。真人滑鼠手感與 WKWebView 行為仍需使用者實測。
