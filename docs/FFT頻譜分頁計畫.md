# FFT 頻譜分頁計畫（頻譜儀式參數、畫面內基準線、獨立分頁）

2026-10-26 起草。分工：Claude 規劃／審查，Codex 實作。本文件可直接照做；標「預設」的地方是開放問題的建議值，使用者沒回覆就照預設做。

使用者需求：
1. FFT 參數改成頻譜儀式：可設 Start／Center／Stop／Span 頻率，RBW、VBW 可調。
2. 基準線（Peak Level 門檻，`peak_level`）只看畫面上（目前顯示頻率範圍）的曲線。
3. FFT 改成頂層獨立分頁（與 截圖／波形擷取／離線分析 並列）。

## 使用者決定（2026-10-26，覆寫下文建議）

- Q1：新增 FFT 獨立分頁，分析頁要有按鈕跳轉。**分析頁內嵌 FFT 窗格是否移除：未明確，P2 開工前再確認。**
- Q8：同意契約只追加鍵、`version` 維持 2（先決條件 A 通過；B、C 一併授權）。
- Q4：**RBW 要隨 Span 自動連動**（改變原建議）。RBW=Auto 時由 span 推導（如 RBW≈span/N，N 於 P4 定案）；Span 變動即重算（debounce）。P1 後端不受影響，P4 設計需納入。
- Q2：FFT 範圍與量測共用 `rangeMode`。
- 其餘開放問題採計畫書建議預設。

---

## 0. 先決條件（Codex 開工前，lead 要先處理）

| # | 事項 | 原因 |
|---|---|---|
| A | **使用者同意改契約**：`fft` 多兩個參數 `rbw`、`vbw`，`FFTResult` 多兩個欄位 `segments`、`vbw` | `RULES.md` 規定契約（L0）凍結，只有 lead 能改；HANDOFF 記錄「v3 先不升」是 Jitter 的事。本案建議 **`version` 維持 2**，只追加可為 null 的鍵（舊行為＝全部傳 null），不佔用 v3 編號。 |
| B | RULES.md 檔案 lane 表登記新檔：`web/fft_rbw.py`（L1b）、`static/js/analysis/tab_fft.js`（L4）；新 store 鍵 `fftView`；新 command `tab.select` | 新檔沒登記不能改 |
| C | 授權本案跨 lane：L0（`index.html`、`main.js`、`mock_backend.js`、契約兩檔）、L1b、L4、L5、L8 | 同 P3b／float 的前例，寫進 RULES.md 的授權段 |

`analysis/*`（含 `analysis/fft.py`、`analysis/peaks.py`）是凍結檔，**本案不改**。新演算法寫在 web 層的新檔，`rbw=null` 時直接呼叫原本的 `fftmod.spectrum`，舊路徑結果逐位元相同。

---

## 1. 現況摘要

### 1.1 計算（後端）
- `scope_tool/analysis/fft.py` `spectrum()`：整段資料（`_cut` 依範圍／dx 切出）乘窗 → 前後補零到下一個 2 的冪 `M` → `rfft / Σw`。`rms = |z|·√2`（DC、Nyquist 不乘 √2），再經 `magnitude()` 換單位。
  - `df = Fs/M`；`enbw_bins = n·Σw²/(Σw)²`（Hann 1.5、Flattop 3.77…）；`rbw = df × enbw_bins`（Infiniium 手冊的定義，用補零後的 M）；`enbw = enbw_bins·Fs/n`（實際雜訊頻寬，用原始 n）。補零只加密頻格，不改實際解析度。
  - 所以**現在 RBW 不能調**：完全由「範圍內點數 n＋視窗」決定，唯一能改它的方法是改游標範圍。
- `web/analysis_fft.py` `FftMixin.fft()`：驗參數 → `spectrum()` → `peaks.peaks(freq, mag, peak_count, lobe, level=peak_level, sort, interpolate=True, amplitude=rms)` → 頻譜存進 `self._spec = {id, gen, freq, mag}`（只留最近一份）→ 回 `FFTResult`。
- `fft_track_rf(spectrum_id, x, direction, level)`：在 `_spec` 上用 `marker.track_rf` 吸附／跳峰，**搜整條頻譜**，不看畫面。
- `/fft?id&f0&f1&px&log`：`decimate.spectrum()` 只把 `[f0,f1]` 內的頻格分桶成每像素 min/max 包絡。
- 參數驗證：`analysis_params.validate_params` 要求鍵集合與契約完全相同（目前**沒接到 server**）；mock 的 `KEYS` 則一定逐鍵比對。

### 1.2 前端
- 參數狀態 `p`（`toolbar.js` FFT 段）：`on, source, window, unit, imp, manualR, peakCount, peakLevel, peakSort`。控制列在 toolbar 建好後用 MutationObserver 塞進 fftpane 的 `.analysis__fftbar`。
- `fft_runner.js` `createFft()`：`p.on` 為真時，`file／rangeMode／cursors／channels` 變動 → 防抖 150 ms → `bridge.job("fft")`。換檔時 `p.on=false`＋`onReset`。
- `fft_markers.js` `fftMarkerModel`（每個 store 一份，WeakMap 快取）＝基準線唯一真值 `store.fftMarker {level, unit, count, sort, r, preview, shown}`。**峰表策略（Marker Table P3）**：一律向後端要 `peak_count=1000`、`Decreasing Magnitude`、`peak_level=floor`，之後在前端 `selectPeaks()` 依基準線過濾、排序、取前 n；只有基準線拉到 floor 以下才重抓（`needsRefetch`）。`peaksTruncated` 判斷可能截斷。
- `fftpane.js`：頻率視窗 `view {f0,f1}` 是**模組內區域變數**（不在 store），滾輪縮放、拖曳平移、雙擊重設；`spectrum_id` 換了就 `view=null`。峰三角形只畫視窗內的（`p.x` 在 `f0..f1`），**但峰表與數量 `shown` 用的是全頻譜**——這就是需求 2 的落差。Y 範圍 `yRange(env)` 已經只看畫面內包絡。
- `fft_marker_layer.js`：基準線繪製與拖曳（±4 px 命中優先於平移）。`fft_marker_table.js`：B 區「FFT 峰值」頁籤的表，點列發 `rf.intent`。
- `cursors.js` 處理 `rf.intent` → `fft_track_rf`（level 取 `fftMarkerModel.displayLevel`）→ 寫 `store.rfPos`。

### 1.3 與分析頁的耦合點
| 耦合 | 位置 |
|---|---|
| `store.command('fft.visible', on)` | toolbar 勾選發出；`tab_analysis.js` 接收設 `fftOn` → `clampLayout({fftOn})` 分配高度、顯示 `.analysis__fftsection`、窄窗時「波形／FFT」分頁；`browser_check`、`browser_float_checks` 用它控版面 |
| `store.fftResult` | runner 寫；fftpane、fft_markers、fft_marker_table、`lowerSummary`、`resultTabs.update({count})`、toolbar 的 RF 重新吸附監聽讀 |
| `store.rfPos` | cursors.js 寫；fftpane 畫；toolbar 在新頻譜時重發 `rf.intent(direction 0)` |
| `store.fftMarker` | fft_markers 寫；layer、table、controls、tab_analysis（count）讀 |
| 範圍 | `store.rangeMode`＋`cursors.x1/x2`＋每通道 `time_offset`（dx）；量測與 FFT **共用** |
| B 區頁籤 `peaks` | `bpanel.js TABS`、`results.js` 掛 `mountFftMarkerTable`、`tab_analysis.js` 的 `.analysis__peaks` |
| store 本身 | `main.js` 只有一個全域 `store` 給所有分頁 → 新分頁天然共用 file／channels／cursors／rangeMode |

---

## 2. 設計

### (a) Start／Center／Stop／Span 聯動

**唯一真值**：新 store 鍵 `fftView: {f0, f1} | null`（null＝全頻寬 `f_min..f_max`）。Center／Span 不存，一律由 f0／f1 推導顯示（center=(f0+f1)/2、span=f1−f0）。只存一對就不會有「兩組互斥」的衝突。

**規則：使用者剛輸入的那個值保持不變，其他值推導；碰到邊界時改的是「非輸入值」。**
邊界：`0 ≤ f0 < f1 ≤ nyq`，`nyq = fftResult.f_max`；最小 span `minSpan = 10·df`（`df` 取 `fftResult.df`）。

| 改 | 保持 | 推導 | 碰邊處理 |
|---|---|---|---|
| Start=s | s | f1 不動 | s 夾到 `[0, nyq−minSpan]`；若 `s+minSpan > f1` → `f1 = min(nyq, s+minSpan)` |
| Stop=e | e | f0 不動 | e 夾到 `[minSpan, nyq]`；若 `e−minSpan < f0` → `f0 = max(0, e−minSpan)` |
| Center=c | c | span 不變 | c 夾到 `[minSpan/2, nyq−minSpan/2]`；`span' = min(span, 2c, 2(nyq−c))`（**縮 span**，保住中心） |
| Span=w | w | center 不變 | w 夾到 `[minSpan, nyq]`；f0<0 → 平移成 `[0,w]`；f1>nyq → `[nyq−w, nyq]`（**移中心**，保住 span） |
| 全頻寬鈕 | — | `fftView = null` | — |

- 滾輪／拖曳／雙擊（fftpane 既有手勢）改寫 `fftView`，同樣過 `clampView()`（夾邊界與 minSpan）。
- 對數頻率軸：Center／Span 仍用算術值（不做幾何中心）；`freqWindow()` 既有的「log 時 f0 至少 df」保留。
- 輸入格式：`fmt.parseSI`（`1M`、`200k`）；非法或 ≤0 → 還原顯示值。無頻譜時四格停用。使用者正在輸入時不覆寫（沿用 `fft_marker_controls.js` 的 `document.activeElement` 判斷）。
- 生命週期：**換檔** → `fftView=null`；**新頻譜**（換範圍、改 RBW…）→ 保留 fftView，只做 `clampView`（夾完 f0≥f1 才回 null）。現況是新頻譜就重設，改成保留才符合頻譜儀手感。
- Start／Stop **只是顯示範圍**，不做 zoom-FFT：後端永遠算 0～Nyquist。

純函式介面（放 `fftpane.js` 並 export，`tab_fft.js` 與 fftpane 手勢共用）：
```js
export function clampView(view, { nyq, minSpan }) // → {f0,f1} | null
export function applySpanEdit(view, edit, { nyq, minSpan }) // edit = {start}|{stop}|{center}|{span}；view 為 null 時以 {0,nyq} 為起點
```

### (b) RBW：Welch 分段平均

可行性判斷：
- **zero-padding**：只加密頻格，不改 RBW——現況已經在做，不能當 RBW 旋鈕。
- **縮短資料**：RBW 會變寬，但丟掉資料、雜訊方差大，不像頻譜儀。
- **Welch（選用）**：把範圍內 n 點切成長度 L 的段、50% 重疊，每段加窗＋補零到 2 冪做 FFT，**功率平均**。RBW＝每段的 ENBW＝`enbw_bins·Fs/L`。RBW 變寬時雜訊底上升、雜訊抖動變小，就是頻譜儀加大 RBW 的行為；穩態正弦振幅不變（每段都用 Σw 做 CG 校正）。可驗證、只用 numpy。

規格：
- 段長 `L = round(enbw_bins · Fs / rbw)`，夾到 `[L_MIN, n]`，`L_MIN = 64`。`enbw_bins` 用該窗的解析倍率（`n·Σw²/(Σw)²` 對大 n 收斂，直接用 `window(L)` 計算即可）。
- 跳距 `hop = L // 2`；段數 `K = 1 + (n − L) // hop`；尾端不足一個 hop 的樣本捨棄（最多 hop−1 點，註解寫明）。
- 每段 `z_k = rfft(pad(seg·w, 到 M=下一個 2 冪(L)，前後置中補零同現況)) / Σw`；`P = mean_k |z_k|²`；`rms = √(2P)`（DC、Nyquist 為 `√P`）；`mag = fftmod.magnitude(rms, unit, R)`。
- 記憶體：段要分塊處理（每塊 ≤ 2²² 樣本，用 `np.lib.stride_tricks.sliding_window_view(v, L)[::hop]` 取塊）累加 `|z|²`，不得一次建 K×M 矩陣（16M 點會吃到 GB 級）。
- 上下限：
  - **下限（最細）** `RBW_min = enbw_bins·Fs/n`（L=n，即整段一次 FFT）。要求更細 → L=n。
  - **上限（最粗）** `RBW_max = enbw_bins·Fs/64`。要求更粗 → L=64。
  - **點數不足**：n < 64 → 只能 L=n，K=1。
  - 夾住時不報錯，回實際值；前端比對「要求值 vs `result.rbw`」差 >1% 就在 RBW 欄旁顯示「已限制為 …」，tooltip 顯示可設範圍。前端算範圍不需新欄位：`Fs = df·effective_n`，`RBW_min = enbw_bins·Fs/n`、`RBW_max = enbw_bins·Fs/64`（**`n` 必須回傳範圍內總點數**，不是實際用到的點數）。
- `rbw = null`（預設「Auto」）→ 直接呼叫 `fftmod.spectrum()`，結果與現在完全相同，`rbw` 欄位維持舊定義（`df×enbw_bins`），`segments=1`。
- `rbw` 有值 → 回傳 `rbw = enbw = enbw_bins·Fs/L`（實際雜訊頻寬，兩欄相等）、`df = Fs/M`、`effective_n = M`、`lobe = ceil(窗項數·M/L)`、`segments = K`、`power_correction = M/L·enbw_bins`。即使夾到 L=n 也用這個定義（同一模式內一致）。
- **Phase 單位不支援 RBW**（相位不能功率平均）：後端收到 `unit="Phase"` 且 `rbw` 非 null → `BAD_REQUEST`；前端選 Phase 時 RBW 欄停用並送 null。
- 不做 RBW 隨 span 自動耦合（每次縮放都要重算整段 FFT）；見開放問題 Q4。

### (c) VBW：顯示軌跡的頻率軸平滑

- 語意：頻譜儀 VBW 是對檢波後軌跡的低通（視訊濾波），效果是把雜訊抖動抹平、不改穩態正弦峰值。FFT 版模擬：對 `mag` 沿頻率軸做移動平均。
- 平滑域：**輸出單位域**——dB 類單位在 dB 上平均（等同頻譜儀 log 視訊平均），Vrms／Watt 在線性上平均。直接對 `mag` 陣列做即可，不必分情況。
- 平滑窗：`VBW ≥ RBW` → 不平滑（`vbw` 欄回 null）；`VBW < RBW` → 方框寬 `W = RBW²/VBW`（Hz），點數 `k = max(1, round(W/df))`，強制奇數、上限 `len(mag)`。RBW 用本次結果的 `rbw` 欄（與畫面顯示的數字一致）。
  - 這是本工具的模擬做法，非頻譜儀等效公式（掃描式頻譜儀的平滑寬約 ∝ RBW²/VBW，常數依掃描時間而定），註解與規格文件都要寫明。
- 邊緣：兩端窗縮短、以實際點數正規化（cumsum 做，O(N)，與 k 無關）。
- 預設 `vbw = null`（Auto＝VBW 跟 RBW 相同＝不平滑）。
- **峰值偵測、基準線、Track RF 一律用平滑後的軌跡**（`_spec.mag` 存平滑後，`/fft` 與 `fft_track_rf` 自然一致＝畫面看到什麼就標什麼，與頻譜儀 marker 相同）。平滑時 `peaks(..., interpolate=False)`：頻率取格心，不用原始 rms 做拋物線內插（平滑後峰格與原始峰形不對應）。
- Phase 不支援 VBW（同 RBW 處理：BAD_REQUEST／前端停用）。
- VBW 改變目前會重跑整個 FFT（後端沒有「只重平滑」的入口）。`# ponytail: VBW 變更重跑全 FFT；大檔慢時再加快取原始 mag`。

### (d) 基準線只看畫面內

- 「畫面」＝ 目前 `fftView`（null＝全頻寬）的 `[f0, f1]`。
- **前端過濾、不重跑**（沿用 Marker Table P3）：`fft_markers.js` 的 `rows()` 與 `patch()` 算 `shown` 時，先 `peaks.filter(p => p.x >= f0 && p.x <= f1)`，再 `selectPeaks`。`fftView` 變動 → 只重算表（`store.on(['fftView'])` → `patch({})`），不發 RPC。
  - 加純函式 `inView(peaks, view)`（view 為 null 回原陣列），`selectPeaks` 不改。
- 縮放／平移後自動更新：是（訂閱 `fftView`，零成本）。
- Y 軸範圍已經只看畫面內包絡（`yRange(env)`），不用改。峰三角形本來就只畫畫面內。
- 截斷：快取仍是「全頻譜前 1000 大峰」。放大到小峰區域時，畫面內的峰可能不在全頻譜前 1000 名內。`peaksTruncated` 條件不變，但腳註改成「已截斷（全頻譜達 1000 峰上限，畫面內可能漏列）」。`# ponytail: 峰快取是全頻譜前 1000；需要時加 fft_peaks(spectrum_id,f0,f1,...) RPC 在 _spec 上取畫面內的峰`。
- Track RF 上一峰／下一峰：後端仍搜整條（契約不加 f 範圍）。預設：RF 落在畫面外時，fftpane 把視窗平移到以 RF 為中心、span 不變（`applySpanEdit(view,{center:rf.x})`）。見 Q5。

### (e) 獨立分頁

**推薦：FFT 整個搬到新分頁，分析頁移除 FFT 窗格與 B 區「FFT 峰值」頁籤，工具列勾選改成「FFT 頻譜 ↗」按鈕（切到新分頁）。**

理由：
1. 只留一個 runner、一個頻譜畫布、一份 `fftView`，不會出現兩個畫面視窗不同、峰表各說各話。
2. 主圖不再被 FFT 擠壓（`docs/分析頁GUI改善計劃書.md` 一開始的痛點），`clampLayout` 的 FFT 退讓／分頁邏輯不再觸發。
3. 代價：失去「同一畫面拖游標、看頻譜」（GUI 改善計劃書第 79 行的舊決定）。補法：FFT 分頁放「範圍」選單與 X1／X2 數值框（發既有的 `cursor.intent`），不用切回分析頁也能改時間範圍。見 Q1。

分頁 DOM（`index.html`）：
```html
<button class="tab" role="tab" data-tab="fft" aria-selected="false">FFT 頻譜</button>   <!-- 放在「離線分析」後 -->
<section id="tab-fft" class="page" role="tabpanel" hidden></section>
```
`main.js`：`MODULES` 加 `fft: { el: "tab-fft", src: "./analysis/tab_fft.js" }`（放在 analysis 之後）；加 `store.onCommand("tab.select", (n) => { if (n in MODULES && n !== "connbar") selectTab(n); })`。

`tab_fft.js` 版面（CSS 寫在 `analysis.css`，class 前綴 `fftpage`）：
```
┌ .fftpage__source ── 來源[CH▼]  範圍[全部|游標區間]  X1[ ] X2[ ]  （無檔時：「請先在離線分析開啟波形檔」＋切換鈕）
├ .fftpage__params ── Start[ ] Center[ ] Stop[ ] Span[ ] [全頻寬]  RBW[Auto] VBW[Auto]  視窗[▼] 單位[▼] 阻抗[▼][Ω]
├───────────────────────────────────────┬ .fftpage__side（寬 ≥1100：右欄 340px；窄：放下方）
│ .fftpage__plot.analysis__fft           │ 基準線[ ] 顯示數量 n[ ] 排序[▼]
│   ← fftpane.mount（自帶 .analysis__fftbar：│ 峰表（mountFftMarkerTable）
│     對數頻率、◀上一峰／吸附／下一峰▶、狀態） │ 腳註（RBW 實際值、段數、VBW、截斷）
└───────────────────────────────────────┴
```
- 繪圖區用 CSS flex 撐滿（`min-height: 240px`），不走 `clampLayout`、不要 splitter。
- 單位選單仍是 `fft_marker_controls.js` 綁的那顆（換單位＝換基準線單位＝換 FFT 輸出單位，維持現況）。

計算時機（取代「FFT 計算」勾選）：
- `p.on = (目前分頁是 fft) && 有檔`。`store.onCommand('tab.activated', name => …)`：切進 fft 分頁 → `p.on=true`，若 `dirty` 或無結果 → `fft.schedule()`；切出 → `p.on=false`（**不清** `fftResult`，回來還在）。
- 不在 fft 分頁時，`file／rangeMode／cursors／channels` 變動只設 `dirty=true`，不算（避免在分析頁拖游標時背景一直跑 16M 點 FFT）。
- 注意 `fft_runner.run()` 在 `p.on=false` 時會把 `fftResult` 設 null——切出分頁不要呼叫 `run()`，只改 `p.on`；`invalidate()` 照用。換檔仍走既有 `onReset`（清結果、`fftView=null`）。

重用，不複製：
| 模組 | 處理 |
|---|---|
| `fftpane.js` | 原封掛到 `.fftpage__plot`；只改「view 改讀寫 `store.fftView`」＋ export `clampView/applySpanEdit`＋狀態列加段數／VBW |
| `fft_runner.js` | 照用；`fftParams` 加 `rbw/vbw` |
| `fft_markers.js` | 照用；加 `inView` 過濾 |
| `fft_marker_layer.js`、`fft_marker_controls.js` | 不改 |
| `fft_marker_table.js` | 照用；`fftInfo` 從 `results.js` 搬進來（results 不再管 FFT）；腳註文字改 |
| `toolbar.js` FFT 段（`p`、控制列、`bindFftMarkerControls`、RF 重新吸附監聽） | **整段搬到 `tab_fft.js`**，toolbar 只留「FFT 頻譜 ↗」按鈕 |
| `cursors.js` 的 `rf.intent` | 不動（分析頁一直掛著，store 共用） |

---

## 3. 契約變更（同一筆 commit 完成，否則 `l0_check`／`selfcheck_node` 會紅）

`api_contract.json` `methods.fft.params` 追加（放最後）：
```json
{"name":"rbw","type":"float","required":true,"nullable":true,"doc":"Hz；null＝Auto（整段一次 FFT，舊行為）；有值＝Welch 段長 L=round(enbw_bins·Fs/rbw) 夾到 [64,n]、50% 重疊、功率平均；unit=Phase 時必須 null"},
{"name":"vbw","type":"float","required":true,"nullable":true,"doc":"Hz；null 或 ≥RBW＝不平滑；<RBW＝輸出單位域沿頻率移動平均，寬 RBW²/VBW；unit=Phase 時必須 null"}
```
`types.FFTResult` 追加：`"segments": "int|null"`、`"vbw": "float|null"`。`types_doc.FFTResult` 補：「rbw 參數為 null 時 rbw＝df×窗 ENBW 倍率（舊定義）；有值時 rbw＝enbw＝實際雜訊頻寬。segments＝平均段數（Auto 為 1）。vbw＝實際套用的 VBW，未平滑為 null。n＝範圍內總點數。峰值、基準線、Track RF 與 /fft 都使用平滑後的軌跡。ok=false 時 segments、vbw 為 null。」

`docs/web-api契約.md`：第 74 行參數表加 `rbw, vbw`；FFT 節加上述語意與 BAD_REQUEST 條件（rbw／vbw 非有限或 ≤0、Phase 帶非 null）。

後端：`FftMixin.fft(..., peak_sort, rbw: float | None = None, vbw: float | None = None)`（Python 用預設值，既有位置參數呼叫不破）。

mock（`mock_backend.js`）：`KEYS.fft` 加 `rbw vbw`；驗證同後端（非 null 須有限 >0、Phase 必須 null）；`specInfo` 加 `segments: 1, vbw: null`；`rbw` 有值時回 `rbw: Math.max(p.rbw, 150)`、`enbw` 同值、`segments: Math.max(1, Math.round(p.rbw/150))`；`vbw` 有值且 < 回傳 rbw 時回該值（不真的平滑，mock 只驗流程）。

---

## 4. 檔案清單

| 檔案（lane） | 改什麼 |
|---|---|
| `web/fft_rbw.py`（L1b，**新**） | `welch(t, v, window_name, unit, r_ohm, source_unit, rbw) -> dict`（鍵同 `fftmod.spectrum` ＋ `segments`）；`video_smooth(mag, rbw, vbw, df) -> (mag, vbw_applied|None)`；常數 `L_MIN=64`、`BLOCK=2**22`；`__main__` 自檢印 `web.fft_rbw self-check OK`。只 import `analysis.fft` 的 `window/magnitude/WINDOWS/MAX_POINTS/reference_impedance` 與 `analysis.measure.uniform_dt/validate`。 |
| `web/analysis_fft.py`（L1b） | `fft()` 加 `rbw/vbw`；驗證；`rbw is None` → `fftmod.spectrum`，否則 `fft_rbw.welch`；之後 `video_smooth`；平滑時 `interpolate=False`；`_spec.mag` 存平滑後；回傳加 `segments/vbw`；`fail()` 加兩個 null 欄。 |
| `web/analysis_check.py`（L1b） | 加 RBW/VBW 案例（見 P1）。 |
| `web/e2e_check.py`（L8） | fft 呼叫補 `rbw=None, vbw=None`；加一次 `rbw=5e4` 走 HTTP。 |
| `static/api_contract.json`、`docs/web-api契約.md`、`static/js/mock_backend.js`（L0） | 第 3 節。 |
| `docs/離線分析功能規格.md` | FFT 段補 Welch／VBW 定義與「本工具做法、待真機比對」字樣（RULES 第 11 條：定義以規格文件為準）。 |
| `static/index.html`、`static/js/main.js`（L0） | 新分頁按鈕＋section；`MODULES.fft`；`tab.select` command。 |
| `static/js/analysis/tab_fft.js`（L4，**新**，≤300 行） | 分頁骨架、來源／範圍／X1X2、Start/Center/Stop/Span、RBW/VBW、視窗／單位／阻抗、掛 fftpane、峰表與基準線控制、計算時機、RF 重新吸附監聽（從 toolbar 搬來）。 |
| `static/js/analysis/fftpane.js`（L4） | view → `store.fftView`；export `clampView/applySpanEdit`；手勢過 clampView；新頻譜不重設 view（只夾）；換檔重設；狀態列 `RBW …（K 段）｜VBW …`；RF 出界時置中（Q5 預設）。 |
| `static/js/analysis/fft_runner.js`（L5 風格） | `fftParams` 加 `rbw: p.unit==='Phase' ? null : p.rbw ?? null`、`vbw` 同理。 |
| `static/js/analysis/fft_markers.js` | `inView`；`rows()`／`patch()` 先過濾；訂閱 `fftView`；`store.on(['file'])` 時一併 `fftView: null`（或交給 fftpane，擇一，不要兩處寫）。 |
| `static/js/analysis/fft_marker_table.js` | 收 `fftInfo`（含 segments／VBW）；腳註截斷文字。 |
| `static/js/analysis/toolbar.js`（L5） | 刪 FFT 段與 `createFft/fftParams` re-export；加「FFT 頻譜 ↗」按鈕（`store.command('tab.select','fft')`）。`closeFile` 的 patch 加 `fftView: null`。 |
| `static/js/analysis/tab_analysis.js`（L4） | 刪 `.analysis__fftsection`、`.analysis__peaks`、FFT splitter、「波形／FFT」plotTabs、`fft.visible` 監聽；`fftOn` 固定不傳（`clampLayout` 預設 false）；`lowerSummary` 拿掉「FFT 峰值」段；`openPatch` 加 `fftView: null`。**注意** `float_check.mjs` 用正規式從本檔抓 `resultTabs.update(...)` 與 `effective = clampLayout(...)` 原文，這兩行改了就要同步改 float_check。 |
| `static/js/analysis/bpanel.js`、`results.js`（L5） | `TABS` 去掉 `peaks`（舊偏好 `tab:'peaks'` 會被 `validate` 退回 measure）；results 不再掛 FFT 表。 |
| `static/js/analysis/layout.js`（L4） | 本案不改。`clampLayout` 的 `fftOn` 分支變成只剩測試在用，加 `// ponytail: fftOn 分支已無產品呼叫者，P5 再刪` |
| `static/css/analysis.css`（L4） | `.fftpage*` 版面；`.analysis__fftbar/.analysis__fft/.analysis__fftplot` 規則**保留**（fftpane 沿用，`p2b_check` 斷言寫死）。 |
| 檢查（L8） | 見各階段。 |

---

## 5. 分階段（每階段可獨立驗證、獨立 commit）

共同驗證指令：
```
node scope_tool/web/static/js/selfcheck_node.js
QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.<模組>      # 見各階段
QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.e2e_check
QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.browser_check
```
本專案**沒有 pytest**（RULES 第 10 條：每模組 `__main__` 自檢）。`e2e_check`／`browser_check` 要綁 localhost，Codex 沙箱跑不了，由 Claude 在沙箱外跑。

### P1 後端＋契約：RBW／VBW（無 UI）
做：第 3 節契約三檔＋mock；`web/fft_rbw.py`；`analysis_fft.py`；`analysis_check.py`；`e2e_check.py` 補鍵；`l5_check.mjs` 第 118 行手寫的 fft 參數補 `rbw:null, vbw:null`；`fft_runner.fftParams` 先固定送 `rbw:null, vbw:null`（讓前端在 mock 下不被 KEYS 擋）；規格文件。

`fft_rbw` 自檢必須包含（失敗即紅）：
1. `rbw` 夾到 L=n 時，`mag` 與 `fftmod.spectrum` 相同（`allclose`，同窗同單位）。
2. 1 Vrms 正弦落在格心：Welch（K≥8）峰值 dBV 在 ±0.01 dB；半格偏移在各窗 scalloping 上限內（沿用 `fft.py` 自檢的 `loss` 表）。
3. 白雜訊 σ=1、Fs=1：兩個 RBW（如 L=256、L=4096）下，`mean(rms²[1:-1])` 各與 `2·rbw/Fs` 差 <5%；兩者雜訊底差與 `10·log10(rbw1/rbw2)` 差 <0.5 dB。
4. 夾限：rbw 很小 → `segments==1` 且 `rbw==enbw_bins·Fs/n`；rbw 很大 → L=64；n=50 → K=1。
5. `video_smooth`：vbw≥rbw 回原陣列且 `vbw_applied is None`；常數陣列平滑後不變；單點脈衝（線性）平滑後總和不變、寬度 k；k 為奇數；兩端正規化正確。
6. 分塊：n=2²⁰、L=64 時峰值記憶體不超過一塊（用結果正確＋不爆即可，不量記憶體）。

`analysis_check` 加：rbw/vbw=None 結果與改前相同（`rbw`、`peaks` 不變）；`rbw=…` 回 `segments>1`、`rbw==enbw`；Phase＋rbw → BadRequest；rbw≤0／NaN → BadRequest；vbw 生效時 `/fft` 包絡與 `fft_track_rf` 讀的是平滑後值（同一頻格 y 相同）。

驗收：`web.fft_rbw`、`web.analysis_check`、`web.analysis_api`、`web.decimate`、`analysis.fft`、`analysis.peaks` 自檢 OK；`selfcheck_node.js`（含 `l0_check` 契約／mock 鍵比對）、`e2e_check` 通過。UI 無變化。

### P2 搬到獨立分頁（功能不變，只換位置）
做：`index.html`、`main.js`（分頁＋`tab.select`）；`tab_fft.js`（先只放既有控制：來源、範圍、X1/X2、視窗、單位、阻抗、基準線、n、排序；掛 fftpane 與峰表）；`toolbar.js`、`tab_analysis.js`、`bpanel.js`、`results.js`、`fft_marker_table.js`（收 fftInfo）、`analysis.css`。

測試同步：
- `l5_check.mjs`、`fft_marker_check.mjs`：`createFft` 改從 `./fft_runner.js` import。
- `p3b_check.mjs` 114／116 行：`lowerSummary` 期望值拿掉「FFT 峰值 0／」。
- `float_check.mjs`：若 `tab_analysis.js` 的 `resultTabs.update(...)`／`clampLayout(...)` 原文有變，更新正規式與注入參數；第 139 行 `fftPeaks` 參數刪。
- `browser_check.py`：FFT 步驟改成點 `[data-tab=fft]` 後等 `fftResult.ok`；刪分析頁 FFT 窗格／FFT splitter／「波形／FFT」分頁的尺寸斷言（約 201–270 行），改為 FFT 分頁在 2000×1290、1400×900、1000×800 三尺寸：`.analysis__fftbar` 不被裁切、`.analysis__fftplot` 高 ≥240、峰表可見；截圖 `08_fft.png` 改拍新分頁。
- `browser_analysis_checks.py` 206–225 行：刪 peaks 頁籤相關、`lowerSummary` 正規式改。
- `browser_float_checks.py` 43、210 行：刪 `fft.visible` 指令。
- 新增 node 檢查（寫在 `fft_marker_check.mjs` 末尾即可，不開新檔）：用假 DOM 掛 `tab_fft.js`，`tab.activated('analysis')` 時改 cursors 不發 fft job；`tab.activated('fft')` 時發一次；切出再切回且無變動不重發；換檔清 `fftResult`。

驗收：分析頁不再有 FFT 窗格與 FFT 峰值頁籤；工具列「FFT 頻譜 ↗」切到新分頁；新分頁有檔時自動算、拖基準線／改 n／排序／點峰表列 RF 照舊；`selfcheck_node`、`browser_check` 通過、console 無錯誤。

### P3 Start／Center／Stop／Span ＋ 畫面內基準線
做：`fftpane.js`（`store.fftView`、`clampView`、`applySpanEdit`、新頻譜保留 view、RF 出界置中）；`tab_fft.js` 四個頻率欄＋全頻寬鈕；`fft_markers.js` `inView`；`fft_marker_table.js` 腳註；`openPatch`／`closeFile` 清 `fftView`。

測試（`fft_marker_check.mjs` 或 `l4_check.mjs` 追加）：
- `applySpanEdit` 表格逐列：第 2(a) 節每一列的正常值與碰邊值（start 撞 stop、center 靠 0、span 大於 nyq、span 靠右邊界平移…），以及 `view=null` 起點。
- `clampView`：f0<0、f1>nyq、span<minSpan、f0≥f1 回 null。
- `inView`＋`rows()`：view 只含部分峰時 `shown`、表列只剩畫面內；view 變動不發 RPC（`bridge.calls` 計數不變）。
- `l4_check.mjs` 154–163 行的 FFT 滾輪測試改成檢查 `store.fftView` 變化（仍斷言 deltaY=0 不重抓）。
- `browser_check`：在新分頁輸入 Start=1k、Stop=10k → 圖的 x 軸範圍與峰表只含此範圍內的峰。

驗收：四欄雙向同步（拖曳／滾輪後四欄更新、輸入後圖更新）；縮放後峰表與數量即時變、無 FFT 重算；換游標範圍後視窗保留。

### P4 RBW／VBW 輸入接線
做：`tab_fft.js` 加 RBW、VBW 欄（空字串／「Auto」＝null；`parseSI`；Phase 時停用）；`p.rbw/p.vbw`；`fftParams` 改送實際值；狀態列與 `fftInfo` 顯示「RBW 實際值（K 段）｜VBW」；要求值與實際值差 >1% 顯示「已限制為 …」，tooltip 顯示可設範圍（由 `df、effective_n、n、enbw_bins` 算）。

測試：`fftParams` 在 Phase 時兩鍵為 null、其他單位帶值；改 RBW 觸發一次 job（`markers.key` 含 rbw → 換 key 重抓峰快取）；mock 下「已限制」提示出現條件；`browser_check` 填 RBW=1k 後 `fftResult.segments>1`。

驗收：RBW 變寬 → 雜訊底上升、抖動變小（真檔肉眼確認）；VBW 小於 RBW → 軌跡變平滑、峰表跟著變；設回 Auto 結果與 P1 前相同。

### P5（選做）清理死碼
`clampLayout` 的 `fftOn` 分支、`FFT_*` 高度常數與 `p2b_check`／`p2b3_check`／`dock_check` 中 `fftOn:true` 案例一起刪。只有在 P2 上線、使用者確認不再要分析頁 FFT 窗格（Q1）之後才做。

建議順序：P1 → P2 → P3 → P4。P1 與 P3 互不相依，可先做 P3（純前端）讓使用者先試縮放手感。

---

## 6. 風險

| 風險 | 處置 |
|---|---|
| Welch 大檔慢（16M 點、L 小、K 大） | 分塊；FFT 只在 FFT 分頁算；慢時再考慮快取 |
| RBW 兩種定義（Auto 用 Infiniium 的 df×倍率，手動用實際 ENBW）讓使用者困惑 | 畫面標「RBW（手冊定義）」vs「RBW（實際）」；Q3 |
| 畫面內峰被全頻譜前 1000 名擠掉 | 腳註提示；升級路徑 `fft_peaks` RPC |
| VBW 平滑後峰值頻率只有格心精度 | 文件寫明；RBW 小時格距本來就細 |
| 移除分析頁 FFT 窗格，破壞「同時看波形＋頻譜」 | FFT 分頁放 X1/X2 與範圍；Q1 |
| `float_check` 以原文正規式綁 `tab_analysis.js` | P2 明列同步 |
| 指令無 handler 會靜默消失（HANDOFF 已知） | 刪 `fft.visible` 時 grep 全部發送點一起刪 |
| `rangeMode` 量測與 FFT 共用，FFT 分頁改範圍會影響量測 | tooltip 寫明；Q2 |
| 全部只有 offscreen 驗證，未與頻譜儀／示波器比對 | 加進 `docs/真機驗證清單.md` 待比對項（Welch 雜訊底、VBW 平滑） |

---

## 7. 開放問題（附建議預設）

| # | 問題 | 預設 |
|---|---|---|
| Q1 | 分析頁的 FFT 窗格要移除，還是保留一份迷你頻譜？ | **移除**，工具列換成「FFT 頻譜 ↗」；FFT 分頁有 X1/X2 可直接改範圍 |
| Q2 | FFT 分頁的「範圍（全部／游標區間）」要跟量測共用，還是 FFT 自己一份？ | **共用**（沿用現行語意，零新狀態），tooltip 註明 |
| Q3 | RBW＝Auto 時顯示哪個值？ | 維持現行（手冊定義 df×窗倍率），旁邊加註「實際 ENBW」 |
| Q4 | RBW 要不要像頻譜儀隨 Span 自動耦合？ | **不要**（每次縮放都要重算全段 FFT）；Auto＝最細 |
| Q5 | 上一峰／下一峰要不要只在畫面內找？ | 不限（後端搜整條），但 RF 跳到畫面外時視窗自動置中跟過去 |
| Q6 | VBW 平滑在 dB 域還是線性功率域？ | **輸出單位域**（dB 單位＝log 平均，同頻譜儀預設） |
| Q7 | 峰值／基準線／RF 用平滑前還是平滑後軌跡？ | **平滑後**（畫面看到什麼就標什麼） |
| Q8 | 契約只追加鍵、`version` 不升（不佔 Jitter 的 v3），可以嗎？ | 可以，維持 2 |
| Q9 | FFT 參數（RBW、VBW、Start/Stop）要不要記在 localStorage？ | **不要**（與「只存版面、不存分析設定」一致） |
| Q10 | 頻率欄位只在有頻譜時可用，還是允許先打好 Start/Stop 再算？ | 有頻譜才可用（需要 Nyquist 才能夾邊界） |
