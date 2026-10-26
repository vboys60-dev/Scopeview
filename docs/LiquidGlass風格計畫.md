# Liquid Glass 深色風格計畫

日期：2026-10-26。狀態：**規劃稿，尚未實作**（唯讀規劃；本檔是唯一產出）。
參考圖：`~/Desktop/截圖 2026-10-26 下午3.20.19.png`。深藍灰漸層背景；卡片、按鈕、搜尋框、toggle、segmented 都是半透明玻璃，上緣亮、下緣暗，白字，圓角大，陰影柔和。

> **前提（要使用者拍板）**：`RULES.md` §三「明確不做：深色主題」、`docs/web-api契約.md` §8「淺色主題…不做深色主題」、§9「深色主題」都寫明不做。本案要先推翻這三處，P1 會同步改文件（見 §6 決定 1）。

---

## 0. 現況盤點（實作者先讀）

| 項目 | 現況 | 對本案的影響 |
|---|---|---|
| 樣式檔 | `css/app.css`（L6，115 行，tokens＋全域元件）→ `css/analysis.css`（L4）→ `css/vertical.css`（L5），`index.html` 依序載入 | 分析頁的 selector 覆寫必須放在**最後載入**的新檔 |
| 變異測試 | `p2b_check`、`p2b3_check`、`p3_check`、`p3b_check` 對 **analysis.css 原文**做字串替換 | analysis.css／vertical.css **原有行一律不改**；覆寫寫在新檔，且不得碰那些測試管的幾何屬性（否則變異測試會「改了也測不出」） |
| 版面斷言 | `browser_check.py`：分析頁 `.analysis__fftbar` ≤40px、主圖 ≥240、plotTabs ≥28、抽屜側欄 36px；`layout.js clampLayout` 寫死 28／40px；`chrome` 由 chanbar 實高＋28 算 | 分析頁內控制項高度、padding、gap 不動 |
| Canvas 色 | `plotcore.js plotColors()` 讀 `--c-plot-* --c-cursor* --c-amber --c-fft-* --c-ov-*`；`handles.js` 黑字配通道色底、白框配 `#333`；`fftpane.js` 白 RF 線；`marker_layer.js` 白 active 點 | 圖區 tokens 全不動；canvas 內寫死色是刻意對比組合，不動 |
| 內聯色 | `marker_menu.js:31` 用 `var(--c-surface)` 等 inline style；`chanbar.js:89`、`results.js:86` 文字設通道色；`tab_screenshot.js:56` 預覽 `#000` | `--c-surface` 維持**實心**，這些自動變成不透明深色，JS 不用改 |
| 寫死亮色 | `.legacy-warning #fff8c5`、tooltip `#222`、`.analysis__plotTabs [aria-selected] accent 底＋white`、`.analysis__horizontal [aria-pressed] var(--c-primary,#1676c0)`（`--c-primary` 未定義）、`.analysis__markers tr.is-selected` 用 `--c-focus` 當底、`.vertical__badge var(--c-warning,#946000)`（`--c-warning` 未定義）、`.analysis--drawer box-shadow #0003` | P1 必須一起修，否則換 token 當下就不可讀（Codex 算：plotTabs 白字 1.83:1、danger 白字 2.20:1、badge 2.65:1） |
| 原生 checkbox | `label.check>input`（擷取頁重新觸發／通道、fftpane 對數頻率、results 欄位選單）；`input.check`（chanbar 顯示、toolbar FFT 計算、匯出縮點、axes Zoom） | toggle 化要排除 chip 內與欄位選單內的勾選框 |
| 視窗引擎 | macOS＝pywebview cocoa（**WKWebView**，不是 Qt）；Windows＝WebView2；qt 退路＝PySide6 QtWebEngine（本機 Chromium 130.0.6723）；自動測試＝headless Chrome | 支援度與效能要分三宿主驗，Chrome 通過不代表其他通過 |
| 已用的新 CSS | `color-mix()`、`:has()`、container query | 已要求 Safari ≥16.2／Chromium ≥111，本案不再抬高門檻 |

---

## 1. 設計 tokens

### 1.1 核心原則（與 Codex 討論後定案）

1. **兩層材質**：
   - **外框層（玻璃）**：直接坐在背景漸層上的元素——connbar、頂層分頁、資料截取卡片、分析頁工具列／側欄外框、按鈕。用 `--glass-fill`（白 7%）＋上緣高光＋下緣暗邊＋柔和陰影。
   - **內容層（實心）**：表格、chanbar、B 區結果、sticky 元件、浮動面板、圖區。用實心 `--c-surface`／`--c-bg`。理由：sticky 透明會透出捲動內容、浮層透明會透出 canvas、通道色文字對比會隨底變動。
2. **玻璃不疊玻璃**：玻璃卡片裡的控制項（input、select、按鈕）改用「實心 `--c-surface` 底＋高光／暗邊」，不再疊一層 .12 白（Codex 算：.12 疊 .12 時 dim 3.43、accent 3.11，不合格）。
3. **backdrop-filter 只給小面積短暫浮層**（`.dlg` 本體、`.toast`、`.results__choices`、tooltip），P3 才開。背景是平滑漸層，對大面板模糊看不出差別卻有成本；`.analysis__float`、抽屜側欄、`marker-menu` 疊在 canvas 上，不做 blur。`::backdrop` 全窗不 blur，只用實心暗化。
4. **`--c-surface` 名稱與「實心」語意不變**：所有既有用法（含 JS inline）自動安全。玻璃是 opt-in。
5. **`--radius` 維持 4px**（圖區 `.analysis__plot` 等沿用），控制項與卡片改用新圓角 token；圖區容器不改圓角、不加 overflow（避免裁到 FFT 刻度／峰標籤，`77b38a0`／`e968c24` 剛修過）。
6. **對比比參考圖優先**：背景比參考圖暗（最亮處 #343a4a，參考圖約 #4a5163）。原因：在 #4a5163 上疊 7% 白，dim 字只有 3.46、accent 2.98，不合格。

### 1.2 Token 表（`app.css :root`）

既有名稱**改值不改名**；新增的列「新」。

| Token | 現值 | 新值 | 用途／對應 |
|---|---|---|---|
| `color-scheme`（屬性） | — | `dark`（新） | 原生 select 下拉、捲軸、number spinner、`input[type=color]` 變深色（OS 色彩選擇器／檔案對話框不保證） |
| `--bg-app` | — | 新：`radial-gradient(120% 80% at 15% 0%, #343a4a 0%, transparent 60%), linear-gradient(160deg, #2b3040 0%, #1d212c 55%, #12141b 100%)` | 掛在 `.app`（`body` 只放實心 `--c-bg` 防白閃），不用 `background-attachment: fixed` |
| `--c-bg` | `#f3f4f6` | `#1b1f29` | 實心底：表頭、splitter、resultTabs、floatBar／floatHome |
| `--c-surface` | `#fff` | `#262b38` | **實心**內容面：表格、chanbar、浮層、sticky、marker-menu |
| `--c-surface-hi` | — | 新：`#303645`（實心） | 實心控制項 hover、表格選中列、chip 選中 |
| `--c-overlay` | — | 新：`rgba(30,34,44,.94)` | P3 浮層（有 blur 時） |
| `--c-overlay-solid` | — | 新：`#1e222c`（alpha 1） | 所有降級分支、無 blur 時 |
| `--c-border` | `#d0d7de` | `rgba(255,255,255,.16)` | 一般邊框 |
| `--c-border-strong` | — | 新：`rgba(255,255,255,.40)` | prefers-contrast、toggle 軌道、forced 以外的高對比 |
| `--glass-fill` | — | 新：`rgba(255,255,255,.07)` | 外框層填色 |
| `--glass-fill-hover` | — | 新：`rgba(255,255,255,.12)` | hover |
| `--glass-fill-active` | — | 新：`rgba(255,255,255,.18)` | segmented／tab 選中（只配 `--c-text` 白字） |
| `--glass-hi` | — | 新：`inset 0 1px 0 rgba(255,255,255,.22)` | 上緣高光 |
| `--glass-lo` | — | 新：`inset 0 -1px 0 rgba(0,0,0,.25)` | 下緣暗邊 |
| `--shadow-glass` | — | 新：`0 6px 20px rgba(0,0,0,.30)` | 卡片／外框陰影（靜態，不做動畫） |
| `--shadow-dlg` | `0 8px 28px rgba(0,0,0,.28)` | `0 12px 36px rgba(0,0,0,.50)` | 對話框、toast、浮動面板 |
| `--c-text` | `#1f2328` | `#f2f4f8` | |
| `--c-text-dim` | `#57606a` | `#c3c9d4` | |
| `--c-accent` | `#0969da` | `#8cc4ff` | 文字／邊框／指示用（不當白字底色） |
| `--c-accent-text` | `#fff` | `#0b1220` | 若有 accent 實心底時的字色（10.2:1） |
| `--c-primary-fill` | — | 新：`rgba(10,132,255,.50)` | `.btn--primary` 藍色調玻璃＋白字 |
| `--c-danger` | `#cf222e` | `#ff8f87` | 文字／邊框 |
| `--c-danger-fill` | — | 新：`rgba(255,69,58,.45)` | `.btn--danger` 紅色調＋白字 |
| `--c-ok` | `#1a7f37` | `#62dd98` | |
| `--c-warn` | `#9a6700` | `#f7cd5f` | 也供 `.vertical__badge`、`.legacy-warning` |
| `--c-focus` | `#0969da` | `#9cc8ff` | 焦點外框（對最亮底 6.55:1） |
| `--radius` | `4px` | **不變** | 圖區、表格等既有用法 |
| `--radius-ctl` | — | 新：`8px` | input、select、chip 以外的小控制項 |
| `--radius-lg` | — | 新：`16px` | 卡片、對話框、工具列外框 |
| `--radius-pill` | — | 新：`999px` | 按鈕、分頁、segmented、toggle |
| `--sp-*`、`--fs-*`、`--font-*`、`--h-control` | | **不變** | 分析頁幾何被測試鎖住；字級沿用（`analysis.css` 的 12.5px 不可動） |
| `--c-plot-*`、`--c-ch1..6`、`--c-cursor*`、`--c-amber`、`--c-fft-*`、`--c-ov-*` | | **不變**（`--c-plot-bg` 保持 `#000`） | Canvas |

### 1.3 對比矩陣（sRGB alpha 合成後計算；Codex 獨立驗算一致）

| 底 | 層 | 白字 `--c-text` | dim | accent | danger | warn | ok |
|---|---|---|---|---|---|---|---|
| 最亮漸層 #343a4a | .07 | 8.32 | 5.51 | 5.00 | 4.16 ✗ | 6.05 | 5.38 |
| 最亮漸層 #343a4a | .12（hover） | 7.13 | 4.72 | 4.28 ✗ | 3.56 ✗ | 5.18 | 4.61 |
| 最亮漸層 #343a4a | .18（選中） | 5.94 | 3.93 ✗ | 3.57 ✗ | 2.97 ✗ | 4.31 ✗ | 3.83 ✗ |
| 實心 #262b38 | — | ≥10 | 6.85 | 6.22 | 5.17 | 7.52 | 6.68 |
| 實心 #262b38 | .18（選中） | 7.19 | 4.76 | 4.32 ✗ | — | — | — |

規則（由上表推出）：
- 玻璃層上只放 `--c-text`、`--c-text-dim`；**accent／danger／ok 文字只放實心面**；選中態（.18）只放白字。
- 主要按鈕 `--c-primary-fill` 疊最亮底＋白字 6.49；danger 7.08。
- 通道色文字（chanbar 名稱、results 首欄）只在實心 `--c-surface` 上：CH1–6 6.10～10.69。使用者自選暗色通道是既有問題，不在本案。
- toggle：白 thumb 對未勾軌道 5.8、對勾選藍軌 3.65（非文字 ≥3 合格）；軌道外框用 `--c-border-strong`（2.83，配 thumb 位置雙重指示）。
- `.is-disabled／:disabled` 的 opacity .5 保留（WCAG 對停用控制項有例外）；但 `.is-busy` 的 .7 不得套在仍要閱讀的狀態文字上（現況未套，實作時別擴大範圍）。

---

## 2. 元件改造清單

檔案分工：**`app.css`**（L6）改 tokens、全域元件、降級 media query，原地編輯；**新檔 `css/glass.css`**（歸 L6，`index.html` 與 `styleguide.html` 在最後一行 `<link>`）只放對 `analysis.css`／`vertical.css` selector 的覆寫。兩檔各 ≤300 行（RULES 行數上限）。

### 2.1 屬性白名單（Codex 第二輪修正後）

- **一般 selector 可寫**：`color`、`background`／`background-color`／`background-image`、`border-color`、`border-style`、`border-radius`、`box-shadow`、`outline`／`outline-color`／`outline-offset`／`outline-width`（禁止 `outline: none`）、`backdrop-filter`／`-webkit-backdrop-filter`（只限 §1.1-3 的浮層）、`accent-color`、`color-scheme`、`opacity`、`font-weight`、`transition`（只 `background-color`／`border-color`，120ms）。
- **幾何例外（具名）**：`.tabs`（`width: fit-content`、`padding`、`margin`）、`.tab`（`padding`、`border-width`）、`input[type=checkbox]` toggle（`appearance`、`width`、`height`、`position`、`flex-shrink: 0`、`::before` 偽元素）。
- 驗收不靠 grep 判對錯，靠 §5 的 browser_check 幾何斷言＋新 `glass_smoke`；grep 只用來快速找可疑行。

### 2.2 清單

| # | 元件 | Selector（檔） | 做法 |
|---|---|---|---|
| 1 | 根／背景 | `:root`、`html, body`、`.app`（app.css） | `:root{color-scheme:dark}`；`body{background:var(--c-bg)}`；`.app{background:var(--bg-app)}` |
| 2 | 頂層分頁 → segmented | `.tabs`、`.tab`、`.tab:hover`、`.tab--active`（app.css） | `.tabs`：`width:fit-content; margin:6px var(--sp-3); padding:3px; border-radius:pill; background:--glass-fill; box-shadow:hi,lo; border:1px solid --c-border`，去掉 `border-bottom`；`.tab`：`border-radius:pill; border-width:0; padding:4px 14px; color:--c-text-dim`；`.tab--active`：`background:--glass-fill-active; color:--c-text; box-shadow:hi`。**總高度不得高於改前＋2px**（先量基線）。`main.js` 只切 class／aria，不動 |
| 3 | 連線列 | `.connbar`（app.css） | 透明底＋下緣 `1px solid --c-border`；不加 blur |
| 4 | 按鈕 | `.btn`、`:hover`、`:active`、`.btn--primary`、`.btn--danger`、`.btn--small`、`a.btn`（app.css） | 高度、padding 不變；`border-radius:pill`；底：在玻璃卡片內用實心 `--c-surface`＋hi/lo，在 connbar 上用 `--glass-fill`（以 `.connbar .btn` 區分）；hover 升一階；`:active` 去高光改 `inset 0 1px 2px rgba(0,0,0,.35)`；primary＝`--c-primary-fill`＋白字＋600 字重；danger＝`--c-danger-fill`＋白字；`filter:brightness` 改成 fill 升階 |
| 5 | 輸入框 | `.input`、`.select`、`:focus`（app.css） | `border-radius:--radius-ctl`；實心 `--c-surface`＋`--glass-lo` 內陰影（凹槽感）；**改寫現有 `.input:focus, .select:focus { outline:none }`** 為 `outline:2px solid var(--c-focus); outline-offset:1px`，box-shadow 不再承擔焦點 |
| 6 | select 下拉 | `.select option`（app.css） | `background:--c-overlay-solid; color:--c-text`（原生下拉在 Chromium 會用它；WKWebView 走系統選單，靠 `color-scheme`） |
| 7 | checkbox → pill toggle | `input[type=checkbox]:not(.chip input):not(.results__choices input)`（app.css） | `appearance:none; width:30px; height:18px; flex-shrink:0; position:relative; border-radius:pill; background:rgba(255,255,255,.22); border:1px solid --c-border-strong`；`::before` 白色 14px 圓 thumb；`:checked` 軌道 `#0a84ff`、thumb 右移；`:focus-visible` 2px 外框；`:disabled` opacity。排除項保留原生＋`accent-color:#0a84ff`。高度 18 < 現有 22～24px 列高，不撐高 fftbar／水平列 |
| 8 | 卡片／面板（資料截取） | `.dcap__card`、`.dcap__title`（app.css） | `border-radius:--radius-lg; background:--glass-fill; box-shadow:hi,lo,--shadow-glass; border-color:--c-border` |
| 9 | 分析頁外框 | `.analysis__toolbar`、`.analysis__side`（app.css 原地） | 同卡片但圓角 `--radius-ctl`（窄、密）；`.analysis__results` 保持實心 |
| 10 | 表格 | `.table`、`.table th`、`.table td`、`.table tr.is-selected td`、`.table tbody tr:hover td`（app.css） | 實心 `--c-surface`；th 用 `--c-bg`（sticky 仍實心）；選中列 `background:--c-surface-hi` 加左緣 `box-shadow: inset 3px 0 0 var(--c-accent)` 於首格；只上色在 `td`，避免 `tr`／`td` 雙重疊色 |
| 11 | chip | `.chip`、`.chip--selected`、`.chip__remove:hover`（app.css） | 實心 `--c-surface`（通道色字要實心底）；radius 已 12px 改 `--radius-pill`；selected＝`--c-surface-hi`＋`border-color:--c-accent` |
| 12 | 對話框 | `.dlg`、`.dlg::backdrop`、`.dlg__title`、`.dlg__actions`（app.css） | `border-radius:--radius-lg; background:--c-overlay-solid; box-shadow:--glass-hi,--shadow-dlg`；`::backdrop{background:rgba(5,7,12,.55)}`（不 blur）；P3 才讓 `.dlg` 本體改 `--c-overlay`＋blur(16px) |
| 13 | toast | `.toast`、`--info/--ok/--error`（app.css） | 實心 `--c-overlay-solid`＋`--radius-ctl`＋左色條保留；P3 加 blur |
| 14 | tooltip | `[data-tip]:hover::after`（app.css） | `#222`→`--c-overlay-solid`、`color:--c-text`、`border:1px solid --c-border` |
| 15 | 警示列 | `.legacy-warning`（app.css） | `background:color-mix(in srgb, var(--c-warn) 15%, var(--c-surface)); color:--c-warn; border-color:--c-warn`（6.3:1） |
| 16 | 狀態 class | `.is-error`、`.is-selected`、`.muted`（app.css） | `.is-selected` 改 `--c-surface-hi`＋accent 邊；`.is-error` 用新 `--c-danger`（實心面 5.17） |
| 17 | 分析頁 segmented | `.analysis__plotTabs`、`[aria-selected=true]`；`.analysis__resultTabs`、`[aria-selected=true]`；`.analysis__horizontal [aria-pressed=true]`；`.analysis__dockbtn[aria-pressed=true]`（glass.css） | 選中＝`--glass-fill-active` 疊實心底＋白字（7.19）＋hi；**移除 accent 底＋white 與 `#1676c0` fallback**。容器高度不變 |
| 18 | 分析頁控制列 | `.analysis__chanbar`、`.analysis__horizontal`、`.analysis__hmodes`（sticky）、`.analysis__fftbar`、`.chanbar__toggle`（sticky）（glass.css） | 維持實心 `--c-surface`（sticky 必實心）；只改邊框色、下緣 `--glass-lo` |
| 19 | splitter | `.analysis__splitter`、`::before`（glass.css） | 底 `--c-bg`；把手 `::before` 改 `rgba(255,255,255,.18)`，hover `.30` |
| 20 | B 區 | `.analysis__lower`、`.analysis__cursors`、`.analysis__markers`、`.analysis__markers tr.is-selected`、`.results__table td:last-child`（sticky）、`.results__choices`（glass.css） | 實心；`tr.is-selected` 原本 `--c-focus` 當底 → 改 `--c-surface-hi`（否則深色下變亮藍底白字） |
| 21 | 浮動面板／抽屜 | `.analysis__float`、`.analysis__floatBar`、`.analysis__floatHome`、`.analysis--drawer .analysis__sidepanel`（glass.css） | 實心、不 blur；`border-radius:--radius-ctl`；`box-shadow:--glass-hi,--shadow-dlg`；抽屜 `#0003`→`rgba(0,0,0,.5)` |
| 22 | 垂直欄 | `.vertical__badge`（glass.css） | `color:var(--c-warn)`（取代未定義的 `--c-warning`） |
| 23 | FFT 分頁 | `.fftpage__source`、`.fftpage__params`、`.fftpage__markers`、`.fftpage__side`（glass.css） | 外框玻璃卡片（同 #8）；內部表格實心 |
| 24 | 圖區容器 | `.analysis__plot`、`.analysis__main`、`.analysis__overview`、`.analysis__fftplot` | **不改**（`--c-plot-bg` `#000`、`--radius` 4px） |
| 25 | marker 右鍵選單 | `marker_menu.js` inline | **不改**：`--c-surface` 實心，自動深色 |
| 26 | 狀態列／狀態文字 | `.muted`（connbar 狀態、擷取狀態）、`.results__fftinfo`、`.field__hint` | 只靠 tokens；在玻璃卡片上是 dim 5.51 合格 |

### 2.3 降級（P1 一起做，app.css 檔尾）

```css
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) { /* 浮層改 --c-overlay-solid */ }
@media (prefers-reduced-transparency: reduce), (prefers-contrast: more) {
  :root { --glass-fill: var(--c-surface); --glass-fill-hover: var(--c-surface-hi); --c-overlay: var(--c-overlay-solid); --c-border: var(--c-border-strong); }
  /* 浮層 backdrop-filter: none */
}
@media (forced-colors: active) { input[type=checkbox] { appearance: auto; width: auto; height: auto; } input[type=checkbox]::before { content: none; } }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
```

- macOS 的 WKWebView **不會**送 `prefers-reduced-transparency`（WebKit bug 175497 仍 NEW）；本設計只有「漸層上 7% 白」與少數浮層 blur，透明不影響可讀性，因此**不做手動實心模式**（§6 決定 6）。
- `:focus-visible` 全域 2px 外框保留，改用新 `--c-focus`；任何 selector 不得設 `outline: none`。

---

## 3. Canvas 圖表（波形、FFT）

- **保留不透明 `#000` 繪圖區**。理由：量測可讀性（通道色、游標、格線都以黑底調過）、與示波器面板一致、canvas 上不疊任何半透明或 blur 層，重繪不牽動合成。
- 格線 `--c-plot-grid #3a3a3a`（對黑 1.85）**不調**：它是背景參考，調亮會干擾波形；軸 `#8a8a8a`（6.08）、文字 `#d4d4d4`（14.17）都合格。
- canvas 內寫死的 `#000`／`#fff`／`#333`（`handles.js`、`fftpane.js`、`marker_layer.js`）是刻意對比組合，**不換成 UI token**。
- 圖區容器不加大圓角、不加 overflow；玻璃感只做在外框（工具列、側欄、卡片）。
- 圖區四周改深色後，黑底與 `#1b1f29`／`#262b38` 之間要有 1px `--c-border` 分界（容器已有 border 的地方沿用）。
- **FFT 邊界驗收**（每階段截圖都看）：Vrms 長單位左軸、0 Hz 與末端（如 1 GHz）刻度、貼邊峰標籤、RF 標籤。`fftpane.js:88` RF 文字 `x+4` 未夾回是既有問題，只觀察不改。

---

## 4. 風險與退路

| 風險 | 說明 | 退路／對策 |
|---|---|---|
| 宿主支援度 | WKWebView（macOS 26）：backdrop-filter（Safari 18 起免前綴）、prefers-contrast、color-scheme、自繪 checkbox、dialog 皆支援；**prefers-reduced-transparency 不支援**。WebView2：Evergreen 近期版皆支援，但 Fixed Version 要記版本。QtWebEngine Chromium 130：CSS 皆支援，但 Qt 是否把 OS 偏好傳進來須實測 | 雙寫 `-webkit-backdrop-filter`；`@supports` 不支援時實心；每宿主實機看一次並記版本（WebView2 Runtime 版號寫進驗收清單） |
| backdrop-filter 副作用 | 會建立 stacking context、改變 absolute／fixed 後代的 containing block；WebKit 有 overflow 裁切舊 bug | 只加在**沒有定位後代**的葉節點浮層（toast、tooltip、results__choices、dlg 本體）；不加在任何祖先容器；marker-menu 維持掛 body 且不 blur |
| `<dialog>` top layer | `showModal()` 在 top layer，body 浮層 z-index 再高也蓋不過 | 不依賴 z-index；dialog 單獨驗收：開關、Esc、焦點還原、輸入、縮放 |
| 重繪效能 | 拖曳／滾輪時 canvas 每幀重繪；若 blur 浮層下方取樣區有 canvas，濾鏡結果每幀要更新（toast、tooltip 同樣可能） | blur 只限小面積、半徑 ≤16px、不巢狀、不做 shadow／filter 動畫、不濫加 `will-change`；P3 量 frame time，P95 增 >20% 就拿掉該浮層 blur |
| 大面積陰影 | 多層 box-shadow 靜態可快取，但卡片很多時首繪變慢 | 外框只用一組 `--shadow-glass`；chip、表格列不加外陰影 |
| 文字對比 | 見 §1.3 | 玻璃層只放白／dim 字；accent／danger 文字只放實心；`glass_smoke` 自動算 |
| 焦點環 | 既有 `.input:focus{outline:none}` 靠 box-shadow，玻璃 box-shadow 會蓋掉 | P1 改成 outline；`glass_smoke` 斷言 Tab 到控制項時 outline-width ≥2px |
| 測試漏測 | 變異測試只看 analysis.css 原文；glass.css 覆寫壞版面它測不出 | glass.css 不碰幾何（白名單）；靠 browser_check 實測 computed 版面 |
| toggle 撐版 | 30px 寬比原生 13px 寬 | 排除 chip 與欄位選單；fftbar／水平列本就允許橫捲；`glass_smoke` 驗分析頁不出現頁面級橫捲 |
| Windows 高對比 | forced-colors 下陰影消失、自繪 toggle 失效 | 退回原生 checkbox；邊框一律實線存在 |
| 規則衝突 | RULES §三、契約 §8／§9 寫「不做深色主題」 | P1 第一件事改文件（lead 權限，需使用者同意） |
| 全面退回 | 若真機不滿意 | `index.html` 拿掉 `glass.css` 一行＋`git revert` P1 的 app.css；因 token 名稱不變、JS 未動，可一筆退回 |

---

## 5. 分階段

共 **3 階段**。每階段一個 git worktree（`git worktree add ../lg-pN -b lg-pN`），Codex 實作（`codex exec -s workspace-write -C <worktree> - < prompt < /dev/null`），Claude 在沙箱外跑 `e2e_check`／`browser_check`，Opus 唯讀審查後 commit、fast-forward 合入 main。

### 共通驗收（每階段都跑）

1. `node scope_tool/web/static/js/selfcheck_node.js` 與 `node scope_tool/web/static/js/selfcheck_node.js --mutations`（變異測試要帶旗標）。
2. `QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.e2e_check`。
3. `… -m scope_tool.web.browser_check <截圖目錄>`（**一律串行**：CDP 埠 9222 寫死，並行 worktree 會撞埠）。
4. **真實截圖比對**：P1 動手前先在 main 用 browser_check 截一組基線（1400×900、1360×860、900×600、1000×700；資料截取、分析頁開檔＋FFT、FFT 分頁、一個對話框），之後每階段同條件重截，人工並排看；另記錄基線 `.tabs`、connbar 高度。
5. 圖區 FFT 邊界四項（§3）肉眼檢查。

### 新增檢查 `glass_smoke`（L8，P1 加進 `browser_check.py`，一個函式）

- (a) 約 12 個樣本元素（`.tab--active`、`.tab`、`.btn`、`.btn--primary`、`.btn--danger`、`.input`、`.muted`、`.field__hint`、`.dcap__title`、`.table td`、`.chip__name`、`.legacy-warning`）：文字色對「祖先鏈 alpha 合成後的背景」≥4.5。**合成必須含背景漸層**（`.app` 的 `background-image` 取最亮停點 #343a4a 當保守底，不能把 `transparent` 當沒背景）。
- (b) Tab 鍵移到 `.btn`／`.input`／toggle 時 computed `outline-width` ≥2px；Space 能切換 toggle。
- (c) 僅**分析頁**：1360×860、900×600 下 `.analysis__fftbar` ≤40px（獨立 FFT 頁刻意允許換行，不套）；`.tabs` 高度 ≤ 基線＋2px；`document.documentElement.scrollWidth ≤ clientWidth`（只驗頁面級，不驗允許橫捲的 fftbar／水平列／chanbar）。
- (d) 用 CDP `Emulation.setEmulatedMedia` 模擬 `prefers-contrast: more` 與 `forced-colors: active`：樣本背景 alpha=1；toggle 退回原生且偽元素不遮住勾選狀態。

### P1：tokens＋全域元件＋降級＋文件（必須先做、單獨完成）

- 範圍：§1.2 全部 tokens；§2.2 第 1～16、26 項（app.css 原地）；第 17、20（`tr.is-selected`）、22 項（glass.css，因為不先修就不可讀）；§2.3 降級；新建 `css/glass.css`（先切好段落註解 `/* == 分析頁 == */`、`/* == FFT 頁 == */`、`/* == 浮層（P3） == */`），`index.html`、`styleguide.html` 各加一行 `<link>`；`styleguide.html` 補齊 toggle、segmented、primary／danger、disabled、busy、error、dialog 各狀態。
- 文件：`RULES.md` §三刪「深色主題」並在 lane 表登記 `css/glass.css` 歸 L6；`docs/web-api契約.md` §8 改「Liquid Glass 深色單一主題；圖區黑底」並列新 tokens，§9 刪「深色主題」；`HANDOFF.md` 加一節。
- 跨 lane：`index.html`（L0）、`browser_check.py`（L8）、契約（L0）需使用者授權（同 `資料截取合併計畫.md` 的做法）。
- 驗收：共通 1～5＋`glass_smoke`。完成後**凍結 token 名稱與 selector 分段**。

### P2：分析頁／FFT 頁套色（glass.css「分析頁」「FFT 頁」段）

- 範圍：§2.2 第 18、19、20（其餘）、21、23 項；確認第 24、25 項維持不變。
- 驗收：共通 1～5；`glass_smoke`；額外截 B 區浮動、抽屜（900×600）、版面 C（右側欄）、Marker 選中列、FFT 分頁峰表。

### P3：浮層 blur＋效能量測＋三宿主驗收（glass.css「浮層」段）

- 範圍：`.dlg` 本體、`.toast`、`.results__choices`、tooltip 改 `--c-overlay`＋`backdrop-filter: blur(16px) saturate(140%)`（雙寫前綴），`@supports`／降級分支切回實心。
- 效能：Chrome DevTools Performance，固定裝置與視窗（1400×900）、同一 10 M 點檔、主圖同一路徑連續拖曳 5 秒，各量 3 次取中位數，比較「main 基線（無本案）／P2 後／P3 開 toast＋results__choices」三組 frame time P95 與掉幀數；P3 相對 P2 的 P95 增 >20% 就拿掉該浮層 blur。WKWebView 用 Safari「開發 → 連線的 WebView」或目測拖曳順暢度。
- 三宿主：macOS pywebview（WKWebView）、Windows WebView2（記 Runtime 版號）、`webview.start(gui="qt")`（PySide6）各開一次，看資料截取、分析頁、FFT 頁、對話框、toggle、select 下拉、捲軸。
- 驗收：共通 1～5＋上述量測紀錄寫進 `docs/web版驗收清單.md`。

### 並行

- P1 必須先完成並合入（tokens／selector 是 P2、P3 的共同依賴，且 P1 不做就有不可讀的地方）。
- **P2 與 P3 可並行寫碼**（各自 worktree，寫 glass.css 不同段落，git 合併不衝突）；但 cascade 衝突不會被段落隔開，**由整合者合併後統一重跑**共通驗收；browser_check 串行。
- 三宿主實機驗收在 P2＋P3 都合入後做一次即可。

---

## 6. 需要使用者決定的事項（括號內為建議預設）

1. 推翻 RULES §三與契約 §8／§9「不做深色主題」，並授權 P1 跨 lane 改 `index.html`、契約、`browser_check.py`（建議：同意）。
2. 是否保留淺色主題可切換（建議：不做，只有一套深色）。
3. 繪圖區底色（建議：維持 `#000`，不改深藍黑）。
4. 背景漸層亮度（建議：比參考圖暗，最亮 #343a4a，換取文字對比）。
5. 主要按鈕色（建議：藍色調玻璃＋白字；其餘按鈕中性玻璃）。
6. 是否做手動「實心模式」開關（建議：不做；透明度本就很低，且 macOS WKWebView 抓不到系統「降低透明度」）。
7. 勾選框改 pill toggle 的範圍（建議：設定類改 toggle；通道列顯示勾與欄位選單保留勾選框）。
8. 輸入框造型（建議：8px 圓角，不做膠囊；按鈕／分頁／segmented 才膠囊）。
9. 毛玻璃模糊範圍（建議：只在對話框、toast、欄位選單、tooltip；大面板與疊在圖上的浮動面板不 blur）。
10. 舊 Qt 版 `scope_tool/ui/` 是否跟著改（建議：不動）。

---

## 6.1 使用者決定（2026-10-26）

§6 十項全部採用括號內建議預設。

## 7. 與 Codex 的討論紀錄（兩輪，唯讀沙箱）

**第一輪 Codex 反對、已採納：**
- 白字按鈕／分頁在新 token 下立即不可讀（plotTabs 1.83、danger 2.20、badge 2.65）→ 這些併入 P1，不留給 P2。
- 巢狀玻璃會把 dim／accent 壓到 3.1～3.4 → 改「玻璃不疊玻璃」，卡片內控制項用實心底。
- `rgba(…,.94)` 不是實心 → 新增 alpha=1 的 `--c-overlay-solid` 給所有降級分支。
- macOS WKWebView 抓不到 `prefers-reduced-transparency` → 寫明，並因透明度很低而不做手動開關（列入使用者決定）。
- 全域 radius 4→8 會改變圖區裁切 → `--radius` 維持 4px，另設 `--radius-ctl／-lg／-pill`。
- 「只改上色」與 toggle／分頁需求矛盾、grep 不可靠 → 改成具名屬性白名單＋具名幾何例外，驗收靠 computed 版面。
- `--c-overlay` 與 blur 也會被 toast、tooltip 下方的 canvas 拖累 → blur 限小面積、量 P95、超標就拿掉。
- 契約 §9 也寫「深色主題不做」、glass.css 要登記 lane、≤300 行、CDP 9222 撞埠 → 都寫進 P1／驗收。

**爭議與結論：**
- marker-menu inline style：Codex 建議改 class 或 `!important`；結論是 `--c-surface` 維持實心，inline 自動變深色，**不改 JS**（Codex 第二輪接受）。
- 頂層與大面板要不要 backdrop-filter：Codex 未反對「只浮層 blur」，補充浮層也有成本 → 以 P3 量測門檻決定去留。
- 第二輪 Codex 修正驗收定義三處（已改進 §5）：合成背景須含漸層、fftbar ≤40 只限分析頁、scrollWidth 只驗頁面級並用 clientWidth；並要求明確覆寫現有 `outline:none`（已列 §2.2 第 5 項）。第二輪結論：**無新的阻斷性問題**。
