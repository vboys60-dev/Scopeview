# 示波器量測演算法 — 實作規格（IMPLEMENTATION_SPEC）

日期：2026-11-12　狀態：草案 v1（尚未經實機驗收）

## 0. 文件說明

### 0.1 來源與可信度標記
| 標記 | 意義 |
|---|---|
| 【官方】 | Keysight Infiniium Offline Analysis Help 的文字或公式圖。頁名寫在「出處」欄（例：`Rise_Time`）。是廠商敘述，不是從程式碼還原的。 |
| 【官方圖】 | 公式只在圖檔，已實際打開圖確認（本次打開：`image100/101`、`image208/209`、`eqn_tie_*`、`eqn_SOPLL_*_freq_nat`；其餘沿用 `ALGORITHMS.md` §8 的確認結果）。 |
| 【設計決定】 | 官方沒寫，由本規格決定。每處都附理由。**不代表 Infiniium 的行為**。 |
| 【推測】 | 由字串、檔名或上下文推得，未驗證。 |
| 【未知】 | 無來源，本規格不定義演算法。 |

信心等級：**高**＝官方專頁文字與公式一致且無矛盾；**中**＝官方有寫但跨頁不一致、或需靠解讀；**低**＝主要靠設計決定或推測。「需實機驗證」＝要用 Infiniium（N8900A 離線版或實機）的輸出比對才能定案。

### 0.2 依據文件
- `/Users/lianshi/Desktop/工作用區/ALGORITHMS.md`（§1–§8）、`HANDOFF.md`（續二–續五）、`MEASUREMENTS.md`、`MEASUREMENT_PARAM_OPTIONS.md`
- 現有實作（唯讀）：`/Users/lianshi/Desktop/claude-cowork/示波器截圖_html/scope_tool/analysis/` 的 `measure.py`、`edge.py`、`eye.py`、`jitter.py`、`clock.py`
- 官方 Help 文字 1,129 頁。本次直接重讀的頁面見各節出處；**沒重讀、只沿用 `ALGORITHMS.md` 的**會標「（轉引）」。

### 0.3 範圍
納入：基本波形量測、眼圖、抖動與雜訊、量測參數。InfiniiScan 只列選項（§7）。
不納入：PAM 專用量測、FFT 量測、Histogram 量測、功率、Mask、均衡（DFE/FFE/CTLE）、PLL 型 clock recovery、相位雜訊。這些只在 §4.14、§5.11、§6.15 列名，不定義演算法。

---

## 1. 總表：已確定 / 待驗證 / 未知

### 1.1 已確定（官方文字明確，信心高）
| 項目 | 內容 | 出處 |
|---|---|---|
| Top/Base 掃描區 | 直方圖上 40% 找 Top、下 40% 找 Base、中間 20% 不掃 | `Calculating_Top_and_Base`、`Top_Voltage`、`Base_Voltage`、`Building_a_Measurement_Histogram`、`dlg_MeasurementThreshold` |
| Top/Base 回退 | 峰的出現次數 < 總數 5% → Top=Vmax、Base=Vmin | `Calculating_Top_and_Base` |
| Top/Base 選項 UI 文字 | Standard（預設）／Histogram／Min, Max／Custom | `dlg_MeasurementThreshold` |
| 閾值定義 | 10/50/90（預設）、20/50/80、自訂 %、自訂電壓 (low, mid, up)、threshold ± hysteresis | `dlg_MeasurementThreshold` |
| 邊緣定義 | 上升沿依序通過 lower→middle→upper，下降沿相反；不完整轉換與突波忽略；閾值交點在兩點間內插 | `Determining_Rising_and_Falling_Edges` |
| 邊緣點數 | Rise/Fall/Slew 的邊緣至少 4 個取樣點（上閾值上 1、下閾值下 1、之間 2） | `Rise_Time`、`Fall_Time`、`Slew_Rate` |
| 時間公式 | Rise=t(upper)−t(lower)；Fall=t(lower)−t(upper)；Period=同極性相鄰邊緣 mid 交越時間差；Freq=1/Period；±Width 用 mid；Duty=+Width/Period×100 | 各專頁、`Timing_Definitions` |
| Vp-p / Vamp | Vp-p=Vmax−Vmin；Vamp=Vtop−Vbase | `Making_Voltage_Measurements` |
| Vrms 公式 | DC=√(Σv²/n)；AC=√(Σ(v−Vavg)²/n) | `RMS_Voltage`【官方圖 image100/101】 |
| Overshoot/Preshoot | 以被量邊緣的極性分支；除以 (Top−Base)×100；量測區間端點為閾值交越與平台中心點 | `Overshoot`、`Preshoot`【官方圖 image105/107/109/111，轉引】 |
| 眼高外插 | (Vtop−3σtop)−(Vbase+3σbase) | `Eye_Height`【官方圖 image210，轉引】 |
| 眼寬外插 | (t₂−3σ₂)−(t₁+3σ₁) | `Eye_Width`【官方圖 image211，轉引】 |
| 眼窗預設 | 40%–60% | `Eye_Height`、`Eye_Crossing`、`Eye_Q-Factor` |
| Eye jitter | RMS=1σcrossing；p-p=6σcrossing | `Eye_Jitter`【官方圖 image212/213，轉引】 |
| Q-factor | (Vtop−Vbase)/(σtop+σbase) | `Eye_Q-Factor` |
| 眼圖 DCD | 時間=\|t_rising50%−t_falling50%\|（取中位數）；%=100×該值/(t_crossing2−t_crossing1) | `Eye_Duty_Cycle_Distortion`【官方圖 image208/209】 |
| TIE | 先 clock recovery，邊緣相對理想位置的時間差；Fully/Semi-Automatic 下平均 TIE=0 | `Jitter_Meas_Data_TIE`、`Clock_Recovery_Constant_Frequency` |
| TIE 濾波一／二階轉移函數 | 見 §6.3 | `Eqn_First/Second_Order_Highpass/Lowpass`【官方圖】 |
| Dual-Dirac 總式 | TJ(pp)=DJδδ+Q·RJrms，Q 由 BER 決定 | `Jitter_Measurements_RJ___DJ_Measurements` |
| EZJIT Plus DCD / ISIpp / DDPWS | 上升與下降緣位置直方圖平均之差的絕對值／上升或下降相關抖動 p-p 取大者／T−min(脈衝寬度) | 同上 |

### 1.2 待驗證（有官方依據但有缺口，或採設計決定）
| 項目 | 缺口 | 信心 | 見 |
|---|---|---|---|
| Top/Base 直方圖的垂直範圍、格數、5% 以單格或峰區計 | 官方未載；結果對此敏感（`ALGORITHMS.md` §7） | 低 | §3.1、N9 |
| 邊緣選取（Measure All Edges 開／關） | 專頁與設定頁說法不同 | 中 | §2.5、N1 |
| 邊緣不足 4 點時的行為 | 官方只說「不量或標可疑」「≤」 | 中 | §4.6 |
| 平台「中心點」的算法（Overshoot/Preshoot 區間） | 官方未載 | 低 | §4.12 |
| Vavg/Vrms 的「uniform sub-sampling」比例 | 官方未載 | 中 | §4.4 |
| 內插方式（線性或其他） | 官方只寫 interpolates | 中 | §4.1 |
| 眼圖量測用原始取樣取代 Color Grade 資料庫 | 設計決定 | 中 | §5.0 |
| Vtop/Vbase「峰」的界定、σcrossing 的迭代縮窗條件 | 官方未載 | 低 | §5.1、§5.3 |
| 眼高／眼寬 Use Measured Data 的欄寬與算法 | 官方只說回報最小值 | 低 | §5.2、§5.4 |
| Q↔BER 換算、Q 單側或雙側 | 官方無表 | 低 | §6.6、N6、N7 |
| RJ/PJ 頻譜分離、Tail Fit、DJδδ 的具體算法 | `.m` 加密，官方只有定性敘述 | 低 | §6.8–§6.10 |
| 記錄長度門檻（128 patterns／30,800 UI／2048／154,000） | 跨頁不一致 | 中 | §6.14、N4 |
| Eye Contour 公式 | 文字與公式圖相反 | 低 | §5.9、N2 |
| TIE 濾波 Rectangular／20/40/60 dB 的實際響應與相位、預設值 | 官方未載 | 低 | §6.3 |

### 1.3 未知（無演算法來源，本規格不定義）
- InfiniiScan 全部模式的判定演算法（離線 Help 無專頁）。
- `OneSrcEval`／`TwoSrcEval`（推測為基本波形量測主體）未取得。
- EZJitMeasure 等 `.ctf` 內加密 `.m` 的公式與參數（Tail Fit 起點、頻譜法非線性閾值、EffBits 方法）。
- 無測試圖樣（Arbitrary）時的 DDJ 算法（官方原文：much more complicated，未說明）。
- BUJ／ABUJ 的分離方法。
- `dspi_edge` 是否內插；`dsps_hist` 本體 `sub_61046d20`。
- `TopBaseAlg` 代號 `PamUserDef` 與 UI 選項的對應；`…TopBaseSens`（靈敏度）的作用。
- "Small amplitude"、"Thresholds?"（上下閾值太近）的數值門檻。

---

## 2. 共通約定

### 2.1 輸入
```
t: float64[n]   時間（秒），嚴格遞增
v: float64[n]   電壓（通道單位）
```
時間類量測不要求等距；FFT／濾波類（§6.3、§6.8）要求等距或先重取樣。

### 2.2 輸入檢查（沿用 `measure.validate`，【設計決定】）
| 條件 | 結果 |
|---|---|
| n=0 或 n<2 | 失敗 `NO_DATA`（對應官方字串 "No data"） |
| `len(t) != len(v)`、非浮點型別 | 失敗 `BAD_INPUT` |
| 含 NaN 或 ±Inf | 失敗 `BAD_INPUT`。**不**自動剔除：剔除會改變時間軸連續性，使邊緣與週期出錯。 |
| t 非嚴格遞增 | 失敗 `BAD_INPUT` |

### 2.3 輸出與狀態
沿用現有 `status.py` 三態，不新增型別【設計決定：重用既有結構】：
| 狀態 | 意義 | 對應官方顯示（`Questionable_or_Missing_Measurement_Results`） |
|---|---|---|
| `VALID` | 正常 | 數值 |
| `LIMITED` | 有值但可疑或只是界限 | `?` 前綴、`≤` 前綴 |
| `INVALID` | 量不出來 | 字串（Edge?、Top = Base…）或 `-------` |

- 逐事件量測回傳 `float64[k]`，並附每個事件的時間 `at[k]`（mid 交越時間）。整段量測回傳長度 1。
- **失敗時回傳值**：核心函式丟 `ScopeError(原因)`；批次介面（`measure_all`）把該筆換成原因字串，不影響其他筆。不回傳 0、不回傳上一次的值。唯一例外是「眼寬 ≤ 0」回傳 NaN 加 `INVALID`（現有行為，保留）。
- 統計欄（目前／平均／最小／最大／範圍／標準差／次數）沿用 `measure.stats`；標準差為母體標準差（ddof=0）。官方未載統計用 ddof，【設計決定】。

### 2.4 失敗原因碼
原因碼的**名稱與意義**取自官方字串表；**觸發條件的數值**若官方沒寫，就是設計決定，條件欄會註明。
| 碼 | 官方字串 | 觸發條件 |
|---|---|---|
| `NO_DATA` | No data | n<2【設計決定】 |
| `BAD_INPUT` | （無對應） | §2.2【設計決定】 |
| `TOP_EQ_BASE` | Top = Base | Top−Base ≤ 0，或 Vmax−Vmin ≤ 256·ULP(max\|v\|)【後者為設計決定：256 格直方圖在較窄範圍可能因浮點邊界重複而失敗，故視同平坦】 |
| `THRESHOLDS` | Thresholds? | upper ≤ lower，或不滿足 lower ≤ mid ≤ upper。官方意義是「上下閾值太近」，**數值門檻未知**，本規格只擋順序錯誤。 |
| `EDGE` | Edge? | 找不到量測所需的邊緣數量 |
| `EDGE_NOT_FOUND` | edge not found | Delta Time 指定的邊緣編號不存在（`Delta_Time`） |
| `FEW_POINTS_ON_EDGE` | `?` 或 `≤` | 邊緣取樣點 < 4（`Rise_Time`） |
| `CLIPPED_HIGH/LOW` | Clipped high／low | 有提供 `clip_range` 且取樣值達到該界限【設計決定，見 §4.2】 |
| `NOT_A_CLOCK` | Not a clock | 時脈型量測套在資料上【設計決定：以使用者宣告的訊號類型判斷，不自動偵測】 |
| `TOO_FEW_POINTS` | Too few points | clock recovery 邊緣 < 3【設計決定，沿用 `clock.recover`】；RJ/DJ 見 §6.14 |
| `ALL_HOLES` | All holes | 抖動量測時沒有任何轉態 |
| `CLOSED_EYE` | Closed eye | 眼高或眼寬 ≤ 0 |
| `NO_PATTERN` | No patn found | 指定 periodic 但折疊後找不到重複圖樣 |
| `MEAS_ALL_EDGES` | Meas all edges? | 需要全部邊緣的量測在 `meas_all_edges=False` 時被要求 |

### 2.5 邊緣選取：Measure All Edges（N1 的實作）
官方（`dlg_MeasurementSetup`）：
- **開**：量整筆擷取的所有邊緣。Duty Cycle、Frequency、Overshoot、Period、Preshoot、Vovershoot、Vpreshoot 需另選 Rising／Falling。
- **關**（官方稱 standard oscilloscope setup）：只量一個邊緣（或一對），統計只累計這一個，其他邊緣忽略。未拖放時「有些量測取最接近時基參考點的邊緣，有些取格線左起第一個邊緣」。**哪些量測用哪一種，官方只明寫 Delta Time 從視窗左緣數起（`Delta_Time`）。**
- 需要全部邊緣的量測（Pulse Count、Edge-Edge、Hold/Setup Time、N-Period、Phase、EZJIT 時脈與資料量測）會自動開啟；開啟 Real-Time Eye 也會強制開啟。

規格：
```
param meas_all_edges: bool = False        # 官方預設狀態為「關」
# 本專案 measure_all 預設 True，以維持 Qt／Web 的全事件統計；單事件須明確傳 False。
param ref_time: float = 時基參考點          # 「關」時用；拖放位置亦以此傳入
param direction: RISING | FALLING          # 只在「開」時對成對量測有意義

events = 該量測在全範圍算出的所有事件（值, at）
if meas_all_edges:
    return events                           # 成對量測只取 direction 的事件
else:
    i = argmin |at − ref_time|               # 同距取較早者
    return events[i:i+1]                     # 極性由該邊緣決定，direction 忽略
```
- 【設計決定】「關」時一律用「最接近 `ref_time`」，Delta Time 除外（§4.11 從左數）。理由：官方沒列出哪些量測用左起第一個，多數專頁寫的是 nearest edge／trigger reference point。
- 【設計決定】核心永遠先算出全部事件再選一個，不另寫單邊緣路徑。現有 `measure.stats(values, ref)` 的「目前」欄已是這個選法。
- 「關」時官方另有 Analyze All Data 開關（關＝只算畫面上的資料，並用保形降取樣）。離線檔沒有「畫面」的概念，本規格以呼叫端傳入的 `t`/`v` 範圍為準，不實作降取樣【設計決定】。

---

## 3. 量測參數

### 3.1 Top / Base
**輸入**：`v`。**輸出**：`(vmin, vmax, top, base)`，單位同 `v`。

**參數**
| 參數 | 選項 | 預設 | 出處 |
|---|---|---|---|
| `top_base_alg` | `STANDARD`／`HISTOGRAM`／`MIN_MAX`／`CUSTOM` | `STANDARD` | `dlg_MeasurementThreshold` |
| `custom_top`, `custom_base` | 電壓，需 top > base | — | 同上 |
| `hist_bins` | 整數 | 256 | 「8 bit」見 `Building_a_Histogram`；用在浮點資料上是【設計決定】 |
| `hist_range` | `DATA`（資料 min–max）／`(lo, hi)`（例如 ADC 滿刻度或畫面範圍） | `DATA` | 【設計決定】官方未載，見 N9 |
| `fallback_fraction` | 0–1 | 0.05 | `Calculating_Top_and_Base` |
| `scan_fraction` | 0–0.5 | 0.40 | 同上 |

內部代號對應【推測】：`histMinMax`=Standard、`histOnly`=Histogram、`minMaxOnly`=Min, Max。`PamUserDef` 與 `Custom` 的關係未知。

**偽程式碼**
```
vmin, vmax = min(v), max(v)
if vmax − vmin <= 256·ULP(max|v|): 視同平坦，levels 回傳 top = base；需要振幅的量測回 TOP_EQ_BASE
if alg == CUSTOM:   return vmin, vmax, custom_top, custom_base
if alg == MIN_MAX:  return vmin, vmax, vmax, vmin

lo, hi = (vmin, vmax) if hist_range == DATA else hist_range
counts = histogram(v, bins=hist_bins, range=(lo, hi))     # 左閉右開，最後一格含右端
cut = floor(hist_bins × scan_fraction)                    # 256 格 → 102 格
kt = 上方 cut 格中 counts 最大者（同高取較低格，靠內側）
kb = 下方 cut 格中 counts 最大者（同高取較高格，靠內側）

def level(k, fallback):
    if alg == STANDARD and counts[k] < fallback_fraction × n: return fallback
    return mean(v 落在第 k 格者)

top  = level(kt, vmax)
base = level(kb, vmin)
```
**設計決定與理由**
- 5% 以**單格**次數計。原文是 "occurrence count less than five percent of the total"，沒說單格或峰區合計。單格是字面最直接的讀法，也是現有實作。信心低。
- `cut` 向下取整、同高峰取內側、格內代表值取格內平均：官方皆未載，沿用現有實作。
- `HISTOGRAM` 選項＝同一直方圖但不做 5% 檢查（官方：without any consideration of whether there is enough information to be statistically valid）。
- `hist_range` 保留為可調參數而不寫死：`ALGORITHMS.md` §7 的實驗顯示含雜訊 PWM 的 Base 會因範圍不同而在「回退 −0.388 V」與「找到 −0.012 V」之間切換。這是實機校準用的旋鈕，定案前不能拿掉。

**邊界條件**
| 情況 | 行為 |
|---|---|
| 常數波形 | `TOP_EQ_BASE` |
| 三角波、正弦、緩升波形 | STANDARD 回退到 Vmax/Vmin（官方明寫三角波如此；正弦是否回退取決於 `hist_range`，見 §7 實驗） |
| 單一尖峰 | 尖峰拉高 Vmax，使直方圖格變寬；平台仍可能被找到或回退，結果不保證。不特別處理。 |
| `hist_range` 小於資料範圍 | 範圍外的取樣不進直方圖，但 `n` 仍用總數（保持 5% 的分母為 total）【設計決定】 |
| `CUSTOM` 且 top ≤ base | 參數檢查失敗 `TOP_EQ_BASE`（官方：不允許 base 高於 top） |

**出處**：`Calculating_Top_and_Base`、`Building_a_Histogram`、`Building_a_Measurement_Histogram`、`Top_Voltage`、`Base_Voltage`、`dlg_MeasurementThreshold`。
**信心**：掃描區與回退規則「高」；直方圖範圍、格數、5% 計法「低」，需實機驗證。

### 3.2 閾值
**輸入**：`top, base, vmin, vmax`。**輸出**：`(lower, mid, upper)`，電壓。

**參數**
| `thresh_method` | 計算 | 出處 |
|---|---|---|
| `PCT_10_50_90`（預設） | base + (top−base)×{0.10, 0.50, 0.90} | `dlg_MeasurementThreshold`、`Calculating_Thresholds` |
| `PCT_20_50_80` | base + (top−base)×{0.20, 0.50, 0.80} | 同上 |
| `CUSTOM_PCT` | 使用者給 3 個百分比 | 同上 |
| `CUSTOM_VOLTS` | 使用者給 (low, mid, up) 電壓，**不經 Top/Base** | 同上 |
| `HYSTERESIS` | mid 電壓 ± hysteresis；Rise/Fall 組不可用 | 同上 |

附屬動作：
- `snap_to_zero: bool`：閾值落在 ±10 mV 內就移到 0（官方數值，`dlg_MeasurementThreshold`）。
- `auto_set()`：mid=(Vmin+Vmax)/2，hysteresis=0.05×(Vmax−Vmin)（官方數值，同頁）。
- 三組獨立設定：General／Rise-Fall／Serial（`MeasDef`、`MeasDefRise`、`MeasDefSerial`）。Rise/Fall 組沒有 mid（見 N12 與 §4.6）。
- `thresh_src`：All Waveforms／Individual Waveforms。

**偽程式碼**
```
if method in (PCT_*, CUSTOM_PCT):
    amp = top − base;  if amp <= 0: fail TOP_EQ_BASE
    lower, mid, upper = base + amp × pct/100
elif method == CUSTOM_VOLTS: lower, mid, upper = 使用者值
elif method == HYSTERESIS:   lower, mid, upper = m − h, m, m + h
if snap_to_zero: 每個 |x| <= 0.010 的閾值設為 0
if not (lower <= mid <= upper and lower < upper): fail THRESHOLDS
```
**邊界條件**：`CUSTOM_VOLTS`／`HYSTERESIS` 下 Top/Base 不參與閾值，但 Overshoot、Preshoot、Vamp 仍用 Top/Base。閾值落在波形範圍外不在此擋，由邊緣偵測回報 `EDGE`（對應官方 "Lower?"／"Upper?"，條件細節未知）。`snap_to_zero` 後若 lower=upper=0 → `THRESHOLDS`。
**失敗**：`TOP_EQ_BASE`、`THRESHOLDS`。
**信心**：高（公式皆官方明寫）。PAM 閾值（`thrPam*`、`thrAutoPam`）不在範圍。

### 3.3 訊號類型 `MeasDefSignalType`
選項（`MEASUREMENT_PARAM_OPTIONS.md`）：Unspecified、NRZ、PAM-3/4/6/8、MIPI C-PHY、DDR5、mmW、Frequency Extension、Spectrum Analysis (DDC)、RTSA、OMA。
規格只支援 `UNSPECIFIED`、`NRZ`，再加【設計決定】`CLOCK`（現有 `ClockSpec.kind="時脈"`；官方清單沒有 Clock 這個訊號類型，時脈／資料的區分在官方是由量測項目決定）。其餘類型回 `INVALID`，原因用官方字串 "Signal type?"。

### 3.4 其他選項
| 選項 | 官方內容 | 本規格 |
|---|---|---|
| Measure All Edges | §2.5 | 實作 |
| Analyze All Data（`WindowAllData`） | 關＝只算畫面資料 | 以傳入範圍代替 |
| Gating（`MeasDefGatingEnable/Start/Stop`） | 只有控制項名稱，無 Help 說明【未知】 | 以傳入範圍代替；不定義語意 |
| Level Qualification | 4 種條件（Above/Below Middle、Between、Not Between）；只檢查量測用到的邊緣那一刻（`dlg_MeasurementLevelQualification`） | 列為低優先；條件語意官方已明確，可照做 |
| `…TopBaseSens`、`MeasDefAnyFunctions`、`DbComp` | 只有名稱【未知】 | 不實作 |

---

## 4. 基本波形量測

### 4.1 邊緣偵測（所有時間量測的基礎）
**輸入**：`t, v, lower, mid, upper`。**輸出**：`Edge[]`，每個含 `rising, t_lo, t_mid, t_hi, a, b`（`a`＝離開原狀態前最後一點的索引，`b`＝進入新狀態第一點的索引）。

**偽程式碼**（即現有 `edge.edges`）
```
state[i] = 0 if v[i] < lower;  2 if v[i] > upper;  否則 1
只看 state != 1 的取樣點，相鄰兩個 state 不同就是一個邊緣：
    a = 前一個（原狀態最後一點）, b = 後一個（新狀態第一點）
    rising = (state[a] == 0)
對每個閾值 thr ∈ {lower, mid, upper}：
    找 a 之後第一個交越：上升 v[j−1] < thr <= v[j]；下降 v[j−1] > thr >= v[j]
    t_thr = t[j−1] + (thr − v[j−1]) / (v[j] − v[j−1]) × (t[j] − t[j−1])
```
- 沒走完三個閾值的轉換不會讓 state 由 0 變 2，自然被忽略；因此回傳的邊緣必為升降交替。
- 取樣值剛好等於閾值：屬於中間狀態，交越記在該點。交越條件一邊嚴格、一邊不嚴格，所以分母不會是 0。
- 【設計決定】線性內插。官方只寫 "interpolates between the two points"。Infiniium 是否先做 sin(x)/x 重建再量，官方此處未載。信心中。
- 【設計決定】邊緣內有振鈴、同一閾值被多次穿越時，取 `a` 之後的**第一次**交越。官方未載。
- `dspi_edge` 反編譯的等號慣例是「前一點 ≤ 準位 < 目前點」，與此處相反；只在取樣值恰等於閾值時差一個取樣間隔內的內插位置，視為無實質差異【推測】。

**邊界條件**：空資料→`NO_DATA`；沒有任何點低於 lower 或高於 upper→回空陣列（由上層回 `EDGE`）；從邊緣中途開始的記錄，第一個不完整邊緣被忽略。
**出處**：`Determining_Rising_and_Falling_Edges`。**信心**：規則高；內插法與多次交越的取法中。

### 4.2 Vmin / Vmax / Vp-p
- **輸出**：電壓。`Vmin=min(v)`、`Vmax=max(v)`、`Vp-p=Vmax−Vmin`。整段量測，與位置無關。
- 官方流程說 Vmin/Vmax 取自直方圖，但 `Building_a_Measurement_Histogram` 也寫直方圖極值不如直接取資料準確。【設計決定】直接取資料極值。
- **削波**：官方會記錄削波並顯示 Clipped high／low。離線浮點資料沒有 ADC 範圍資訊，【設計決定】提供選用參數 `clip_range=(lo, hi)`；有給且取樣值達界限時，值照回，狀態 `LIMITED` 加 `CLIPPED_*`。沒給就不判斷。
- **邊界**：常數波形 Vp-p=0（有效值，不是失敗）。
- **出處**：`Maximum_Voltage`、`Minimum_Voltage`、`Peak-to-Peak_Voltage`、`Making_Voltage_Measurements`。**信心**：高。

### 4.3 Vtop / Vbase / Vamp
- `Vtop, Vbase` 取 §3.1；`Vamp=Vtop−Vbase`。整段量測。
- **失敗**：`TOP_EQ_BASE`。
- **出處**：`Top_Voltage`、`Base_Voltage`、`Amplitude`。**信心**：同 §3.1。

### 4.4 Vavg
**輸入**：`t, v`。**輸出**：電壓。
**參數**：`interval = DISPLAY | CYCLE`。官方未載預設，【設計決定】預設 `DISPLAY`（與現有 `mode="full"` 一致）。
```
if interval == DISPLAY:
    return mean(v)
else:  # CYCLE：單一週期
    es = edges(...);  e0 = 最接近 ref_time 的邊緣
    e1 = e0 之後下一個同極性邊緣；若無 → fail EDGE
    seg = v[ 索引(t >= e0.t_mid) : 索引(t >= e1.t_mid) ]      # 左閉右開
    return mean(seg)
```
- 官方：This measurement uses a uniform sub-sampling of the acquisition data。比例未載，【設計決定】用區間內全部取樣。
- 現有實作的 `mode="cycles"` 是「第一到最後一個同向邊緣之間的所有整數週期」，**不是官方的單一週期**。保留為產品延伸選項 `ALL_CYCLES`，不得標示為官方定義。
- **邊界**：`CYCLE` 下 Top=Base→`TOP_EQ_BASE`；同極性邊緣 < 2→`EDGE`；區間內 0 個取樣→`EDGE`。
- **出處**：`Average_Voltage`（專頁）；`Making_Voltage_Measurements` 寫「第一個週期」，見 N8。**信心**：中。

### 4.5 Vrms
**輸出**：電壓，或 dBm。**參數**：`kind = DC | AC`；`interval` 同 §4.4；`units = VOLT | DBM`；`ref_impedance`（10–200 Ω，Auto 時單端 50、差動 100、共模 25）。
```
DC = sqrt( Σ v[i]² / n )
AC = sqrt( Σ (v[i] − Vavg)² / n )      # Vavg 為同一區間的平均
dBm = 10·log10( Vrms² / R / 1e-3 )     # 【設計決定】標準功率換算；官方頁只說以功率表示，沒列式子
```
- **邊界**：全 0→0 V；dBm 下 Vrms=0→`INVALID`（log 無定義）。
- **出處**：`RMS_Voltage`【官方圖 image100/101】。**信心**：V 單位高；dBm 中。

### 4.6 Rise time / Fall time
**輸出**：秒，逐事件。
**參數**：Rise/Fall 組閾值（lower、upper）；`meas_all_edges`、`ref_time`。
```
es = edges(t, v, lower, mid, upper)
sel = [e for e in es if e.rising == (量 Rise)]
if not sel: fail EDGE
good = [e for e in sel if e.b − e.a + 1 >= 4]
if good:   值 = e.t_hi − e.t_lo（Rise）或 e.t_lo − e.t_hi（Fall）, 狀態 VALID
else:      值 = t[e.b] − t[e.a], 狀態 LIMITED, 前綴 "≤", 原因 FEW_POINTS_ON_EDGE
事件時間 at = e.t_mid
```
- 4 點規則：`a`（lower 下 1 點）＋`b`（upper 上 1 點）＋中間至少 2 點，即 `b − a + 1 >= 4`，與官方「one above the upper, one below the lower, two between」等價。
- 【設計決定】部分邊緣足夠、部分不足時，只回報足夠的，並在診斷資訊記下被略過的數量。全部不足時才回上界。官方原文是「either not made or flagged as questionable」與 `≤`，沒說何時用哪一種。
- **Rise/Fall 組沒有 mid（N12）**：【設計決定】`mid` 取 (lower+upper)/2，只用來產生事件時間 `at`。只要 lower < mid < upper，連續波形由 lower 下方走到 upper 上方必然穿過 mid，所以 mid 取何值不影響「是否成邊緣」。
- **邊界**：單一邊緣可量；`<4` 點如上；Top=Base→`TOP_EQ_BASE`；`meas_all_edges=False` 取最近邊緣。
- **出處**：`Rise_Time`、`Fall_Time`、`Determining_Rising_and_Falling_Edges`、`Questionable_or_Missing_Measurement_Results`。**信心**：公式高；不足點數的處置中。

### 4.7 Slew rate
- **輸出**：V/s。`ΔV/ΔT`，ΔV＝lower 到 upper 的電壓差，ΔT＝§4.6 的時間。下降緣為負值【設計決定，沿用現有】。
- **參數**：Rising／Falling／Both（開或關 Measure All Edges 都要選，`Slew_Rate`）。
- **邊界**：4 點規則同 §4.6；不足時上升斜率為下界、下降斜率為上界（現有行為）。
- **出處**：`Slew_Rate`。**信心**：高。

### 4.8 Period / Frequency
**輸出**：秒／Hz，逐事件。
```
mids = [e.t_mid for e in es if e.rising == direction]
if len(mids) < 2: fail EDGE
period[i] = mids[i+1] − mids[i];   at[i] = mids[i]
frequency = 1 / period
```
- `meas_all_edges=True`：`direction` 由使用者選。`False`：取最接近 `ref_time` 的邊緣，其極性決定 direction，量到下一個同極性邊緣（`Period`）。
- **邊界**：單一邊緣或只有一對異極性邊緣→`EDGE`；period 必 > 0（t 嚴格遞增），不會除以 0。
- **出處**：`Period`、`Frequency`、`Timing_Definitions`。**信心**：高。

### 4.9 +Width / −Width
**輸出**：秒，逐事件。
```
+Width[i] = 下一個下降緣.t_mid − 上升緣.t_mid      # 相鄰一對
−Width[i] = 下一個上升緣.t_mid − 下降緣.t_mid
at = 起始邊緣.t_mid
```
- **邊界**：沒有完整脈衝→`EDGE`。邊緣必為升降交替（§4.1），不需另外配對。
- **出處**：`Positive_Width`、`Negative_Pulse_Width`。**信心**：高。

### 4.10 Duty cycle
**輸出**：%，逐事件。`Duty = +Width / Period × 100`。
```
對每三個連續邊緣 (e0, e1, e2)，e0.rising == direction：
    period = e2.t_mid − e0.t_mid
    pos    = e1.t_mid − e0.t_mid  if direction == RISING  else  e2.t_mid − e1.t_mid
    duty   = pos / period × 100
```
- 「−工作週期」（100 − Duty）是現有產品延伸，官方清單沒有這一項。
- **邊界**：少於 3 個邊緣→`EDGE`。
- **出處**：`Duty_Cycle`、`Timing_Definitions`。**信心**：高。

### 4.11 Delta time
**輸出**：秒。來源 1 的指定邊緣到來源 2 的指定邊緣。
**參數**（每個來源各一組）：`edge_num` 1–65534；`slope` = RISING／FALLING（官方另有 "first on display"，語意未說明，不實作）；`threshold` = LOWER／MIDDLE／UPPER。
```
c1 = 來源1 中 slope 相符的邊緣，從資料左端數起第 edge_num 個，取其 t_{threshold}
c2 = 來源2 同理
if 任一不存在: fail EDGE_NOT_FOUND
return c2 − c1            # 可為負
```
- 官方明寫從**視窗左緣**數邊緣，不是從參考點（`Delta_Time`）。
- 現有 `measure2("延遲")` 是「來源 1 每個邊緣配來源 2 最近的邊緣」，與官方定義不同，保留為產品延伸，不得標為 Delta Time。
- **出處**：`Delta_Time`、`Timing_Definitions`。**信心**：高。

### 4.12 Overshoot / Preshoot
**輸出**：%，逐事件。
| | 上升緣 | 下降緣 |
|---|---|---|
| Overshoot | 100×(局部最大 − Top)/(Top − Base) | 100×(Base − 局部最小)/(Top − Base) |
| Overshoot 區間 | [t_hi, 頂部中心點] | [t_lo, 底部中心點] |
| Preshoot | 100×(Base − 局部最小)/(Top − Base) | 100×(局部最大 − Top)/(Top − Base) |
| Preshoot 區間 | [底部中心點, t_lo] | [頂部中心點, t_hi] |

```
Overshoot（上升緣 e，下一個邊緣 nxt）：
    start = e.t_hi;  end = (start + nxt.t_hi) / 2          # 頂部平台中心【設計決定】
Preshoot（上升緣 e，前一個邊緣 prev）：
    end = e.t_lo;    start = (prev.t_lo + end) / 2         # 底部平台中心【設計決定】
seg = 區間內的取樣，加上兩端點的內插值
依表取 max 或 min 代入公式
```
- 【設計決定】「中心點」＝平台兩端閾值交越時間的中點。官方只說 top/bottom center point，沒有算法。信心低。
- 【設計決定】缺鄰緣（記錄中第一個邊緣的 Preshoot、最後一個邊緣的 Overshoot）不量。若記錄內沒有任何邊緣同時有所需鄰緣→`EDGE`。理由：沒有鄰緣就定不出平台中心，硬用記錄端點會把前一緣的振鈴算進來（`edge.py` 自我檢查有此案例）。Infiniium 對單一邊緣是否能量，未知。
- 【設計決定】結果為負時不截為 0，照公式回報。官方未載。
- 總覽頁 `Making_Voltage_Measurements` 的式子沒有除以 (Top−Base)，且 Preshoot 的分支文字與專頁不同；以專頁與公式圖為準（`ALGORITHMS.md` §1 第 8 點）。
- **Vovershoot / Vpreshoot**：官方只說「回傳 overshoot 的 local voltage，而不是百分比」。是局部極值的絕對電壓，還是與 Top/Base 的電壓差，文字不足以判定。【設計決定】回傳局部極值的絕對電壓；信心低，需實機驗證。
- **邊界**：Top=Base→`TOP_EQ_BASE`；`CUSTOM_VOLTS` 閾值下仍需有效的 Top/Base。
- **出處**：`Overshoot`、`Preshoot`、`Vovershoot`。**信心**：公式高；區間與單邊緣行為低。

### 4.13 現有實作有、官方清單沒有的雙來源項目
「相位」（延遲/週期×360）與「電壓比」（20·log10 的 AC RMS 比）是產品自有定義。官方有 Phase（編號 142，需全部邊緣）但本次未讀其專頁，**不宣稱一致**。

### 4.14 不在本規格的基本量測（只列名）
Pulse count、Burst period/interval/width、T min、T max、T volt、T edge、Edge time、Edge-edge、Edge to all edges、High/Low time、Time >,< level、V time、V upper/middle/lower、Pulse top/base/amplitude、Area、Crossing、Effective bits、全部 FFT 與 Histogram 量測。專頁存在但本次未讀或未整理。

---

## 5. 眼圖量測

### 5.0 資料來源與折疊
官方：所有眼圖量測都做在 Real-Time Eye 開啟時建立的 **Color Grade 資料庫**上（每像素一個計數器）。
【設計決定】本規格用**原始取樣**依還原時脈折疊，不經像素資料庫：
```
ck = clock recovery 結果（§6.1）：ui, t0
phase[i] = ((t[i] − t0) / ui) mod 1          # 0 與 1 是理想轉態位置，0.5 是眼中心
```
理由：(1) 現有 `eye.py` 已如此；(2) 不必猜顯示解析度（N9、N11 的不確定性不會帶進來）；(3) 數值上應比像素量化更接近真值。代價：與 Infiniium 讀值可能差到一個像素的量化量，且 `Start Measurement After`（預設 1，最高命中數門檻）在此無意義，不實作。信心中，需實機驗證差異大小。

共同參數：
| 參數 | 預設 | 出處 |
|---|---|---|
| `eye_window = (start, stop)`，UI 百分比 | (40, 60) | `Eye_Height` |
| `units = SECOND | UI` | SECOND | `Eye_Width`、`Eye_Jitter` |

共同失敗：clock recovery 失敗→沿用其原因；`units=UI` 但沒有還原時脈→`INVALID`（官方：會報錯）。

### 5.1 眼的 Vtop / Vbase / σtop / σbase
**輸出**：`(Vtop, σtop, Vbase, σbase)`，電壓。
官方：在眼窗內建垂直直方圖，Vtop／Vbase 是上／下峰的平均電壓，σ 是該峰的標準差。
```
w = v[ start/100 <= phase <= stop/100 ]
hi = w[w >= ck.mid];   lo = w[w < ck.mid]
if min(len(hi), len(lo)) < 10: fail EYE（樣本不足）
return mean(hi), std(hi), mean(lo), std(lo)
```
- 【設計決定】用中閾值把窗內取樣分成上下兩群，各取平均與標準差。官方沒說「峰」如何界定（峰附近多寬、是否去尾）。眼張開時兩種作法相同；眼接近閉合或有多層準位時會不同。信心低。
- 【設計決定】每群至少 10 個取樣（現有門檻，非官方）。
- **出處**：`Eye_Height`、`Eye_Q-Factor`、`Eye_Crossing`。

### 5.2 Eye height
**輸出**：電壓。
**參數**：`alg = EXTRAPOLATE | MEASURED`；`location = FIND_EYE_OPENING | AT_RECOVERED_CLOCK`；`window_width_pct`（僅 AT_RECOVERED_CLOCK，0＝只取時脈點）。官方未載 `alg`、`location` 的預設，【設計決定】預設 `EXTRAPOLATE`＋`FIND_EYE_OPENING`（與現有行為一致）。
```
EXTRAPOLATE:  (Vtop − 3·σtop) − (Vbase + 3·σbase)

MEASURED:                                           # 官方：窗內實測，回報最小眼高
    把眼窗切成 ncol 欄（預設每 1% UI 一欄）【設計決定】
    每欄 h = min(該欄上群) − max(該欄下群)；空欄略過
    return min(h)

AT_RECOVERED_CLOCK:
    窗 = 50% ± window_width_pct/2                     # 【推測】還原時脈位置＝眼中心
    width = 0 時：每個 UI 在 t0 + (k + 0.5)·ui 內插一個電壓，用這些值代替窗內取樣
```
- **邊界**：結果 ≤ 0→`CLOSED_EYE`（官方字串 "Closed eye"）；窗內樣本不足→同 §5.1。
- **信心**：EXTRAPOLATE 高；MEASURED 的欄寬與 AT_RECOVERED_CLOCK 的位置解讀低。
- **出處**：`Eye_Height`【官方圖 image210，轉引】。

### 5.3 交叉點時間與 σcrossing
**輸出**：`(中心 UI, σ UI, 被剔除點數)`。
官方（`Eye_Jitter`）：建水平時間直方圖找交叉點，**用迭代過程縮窄直方圖視窗**以精確定出交叉點與變異。迭代的收斂條件與窗寬未載。
```
x = ck.tie / ck.ui                       # 指定閾值上的邊緣時間誤差
c, s = median(x), std(x)
repeat ≤ 20 次：
    keep = |x − c| <= 3·s
    若 keep 不變、或 s < 1e-12、或全空：停止
    c, s = mean(x[keep]), std(x[keep])
```
- 【設計決定】±3σ 迭代裁切（現有實作）。被剔除比例 > 1% 時狀態 `LIMITED`（`CROSSING_TRIMMED`，1% 為待校準的產品門檻，非官方）。
- 【設計決定】固定頻率還原下兩個交叉點的分布相同，只算一次，σ₁=σ₂。PLL 還原時不成立，屆時要分開算。
- 信心低，需實機驗證。

### 5.4 Eye width
**輸出**：秒或 UI。
**參數**：`alg = EXTRAPOLATE | MEASURED`；`threshold = AUTOMATIC | MEASUREMENT_THRESHOLD`；`units`。預設【設計決定】`EXTRAPOLATE`＋`MEASUREMENT_THRESHOLD`（現有行為）。
```
EXTRAPOLATE:  (t₂ − 3σ₂) − (t₁ + 3σ₁)  =  ui − 6·σ·ui        # 固定頻率還原下
MEASURED:     ui − (max(tie) − min(tie))                     # 【設計決定】官方只說回報最小眼寬
AUTOMATIC 閾值：官方「在交叉最寬處量」。【設計決定】以 §5.6 的 Vcrossing 當閾值重新取邊緣時間
```
- `Eye_Width` 頁的 Extrapolate 說明文字寫成 "estimates the eye height"，為筆誤（`ALGORITHMS.md` §2）。
- **邊界**：≤ 0→回 NaN、`INVALID`、`CLOSED_EYE`（現有 `EYE_NO_POSITIVE_OPENING`）。
- **信心**：EXTRAPOLATE 高；MEASURED 與 AUTOMATIC 低。
- **出處**：`Eye_Width`【官方圖 image211，轉引】。
- 注意：EZJIT Plus 結果表另有一個「Eye Width」＝UI − TJ(BER)（§6.10），是不同的量測。

### 5.5 Eye jitter
**輸出**：秒或 UI。`RMS = σcrossing`；`p-p = 6·σcrossing`。σ 取 §5.3。
- 現有實作另外提供「原始 σ」與「實測 p-p」（未裁切）；這兩項不是官方定義，介面上要分開標示。
- **出處**：`Eye_Jitter`【官方圖 image212/213，轉引】。**信心**：公式高；σ 的求法低。

### 5.6 Crossing %
**輸出**：%。`100 × (Vcrossing − Vbase) / (Vtop − Vbase)`
官方：用整個畫面的水平直方圖定交叉點的時間位置，再用窄的垂直直方圖定 Vcrossing（交叉點最常出現的電壓）。窄直方圖的寬度未載。
```
c = §5.3 的交叉中心
vc[k] = 每個 UI 在 t0 + (k + c)·ui 內插的電壓
band = vc 中介於 Vbase + 0.1·amp 與 Vtop − 0.1·amp 者       # 去掉沒有轉態的 UI
若 len(band) < 10 → fail；50 格直方圖最高格 < 2×平均 → fail（沒有明顯的峰）
Vcrossing = 最高格內取樣的平均
```
- 【設計決定】以上取法與 10%、10 個、50 格、2 倍等常數全是現有實作的選擇，非官方。信心低。
- **失敗**：`INVALID`，原因對應官方 "Crossing?"。
- **出處**：`Eye_Crossing`【官方圖 image207，未打開，依文字】。

### 5.7 Q-factor
**輸出**：無因次。`(Vtop − Vbase) / (σtop + σbase)`，四個量取 §5.1（固定 40–60% 窗）。
- **邊界**：σtop+σbase=0→回 +Inf（現有行為）。【設計決定】理想無雜訊資料不算失敗。
- **出處**：`Eye_Q-Factor`【官方圖 image214，未打開，依文字】。**信心**：公式高。

### 5.8 眼圖 DCD
**輸出**：秒或 %。
```
time = | median(tie[rising]) − median(tie[falling]) |
pct  = 100 × time / (t_crossing2 − t_crossing1)        # 固定頻率還原下分母＝ui
```
- 取**中位數**；與 §6.7 的 EZJIT Plus DCD（取**平均**）是不同量測，介面名稱要區分。
- 公式圖的變數寫 50% 點，文字說用中閾值（可被使用者改）。【設計決定】用使用者設定的 mid 閾值。
- **邊界**：只有單一極性的邊緣→`EDGE`（時脈訊號要把邊緣設為兩者）。
- **出處**：`Eye_Duty_Cycle_Distortion`【官方圖 image208/209】。**信心**：高。

### 5.9 Eye contour（低優先，低信心）
**輸出**：每個 BER 一條輪廓（點列，時間×電壓）。
官方步驟（`Eye_Contour_generation`）與裁決見 N2。採**文字版**：
```
Vcenter = 累積眼圖最寬處的電壓
SR = Vcenter ± 5 mV 的平均斜率
Rj_c = Vcenter 處量得的 RJrms；Rn_c = 時脈交叉點量得的 RNrms   # scope 項官方設為 0
onlyRj = sqrt( Rj_c² − (Rn_c / SR)² )
對每個 BER、每個電壓點 Vp：
    Rj(Vp) = sqrt( onlyRj² + (Rn_c / SR(Vp))² )
    Tj = Dj(Vp) + ½·Qber·Rj(Vp)         # Dj 取 Vp ± 5 mV 區域的 dual-Dirac
到 Vmintop／Vmaxbot 後改垂直：Tn = Dn + ½·Qber·Rn
```
- Qber 取 §6.6 的雙側值。上半用 one level 的 Rn，下半用 zero level 的 Rn（官方 Note）。
- 根號內為負（雜訊換算的抖動大於量得的抖動）→該點 `INVALID`【設計決定】。
- 官方文字一處把 Vmaxbot 寫成 "Vminbot"，視為筆誤。
- **信心**：低。需實機驗證。Dj(Vp)、Dn 的 dual-Dirac 求法依 §6.10，同樣是設計決定。

### 5.10 眼寬基準、Slicer Sample Timing
`Based on Center Eye`／`Per Eye Level`、`SlicerSampleTiming` 為 PAM 眼圖選項，不在範圍。

### 5.11 不在本規格的眼圖量測（只列名）
Extinction ratio、Eye one/zero level、Optical average power、OMA、全部 PAM 量測。

---

## 6. 抖動與雜訊

### 6.1 Clock recovery — Constant Frequency
**輸入**：`t, v`、閾值、`ClockSpec`。**輸出**：`ui, t0, n[]（每個邊緣的整數 UI 格號）, tie[]`。
**參數**：`mode = FULLY_AUTOMATIC（預設） | SEMI_AUTOMATIC | MANUAL`；`nominal_rate`；`edges = RISING | FALLING | BOTH`（資料一律 BOTH）。
```
times = 參與的邊緣的 t_mid；少於 3 個 → fail TOO_FEW_POINTS
ui0 = MANUAL/SEMI: 1/nominal_rate
      FULLY (時脈): 同向邊緣週期的中位數
      FULLY (資料): 見下方說明
n = cumsum(round(diff(times) / ui))                  # 兩邊時脈：跨度強制為奇數
MANUAL 以外：重複至格號不變（≤ 10 次）
    ui = 最小平方斜率（times 對 n）；重新算 n
t0 = 使 mean(tie) = 0 的截距
tie = times − (t0 + n·ui)
```
- 官方 Fully Automatic：找**最窄脈衝**並假設它是孤立的 1 位元，再推各脈衝位元數；並自承 ISI 大時速率會偏高。
- 【設計決定】資料型全自動的種子**不**取最窄脈衝，改用現有 `rate_seed.seed_ui`（間隔對數直方圖的第一個顯著峰）。理由：避開官方自己指出的弱點。這是有意偏離官方描述，要在介面與文件標明；狀態固定為 `LIMITED`（`RATE_INFERRED`）。
- 「平均 TIE=0」是官方明寫；「最小平方擬合速率」是設計決定，與 `Jitter_Measurements_RJ___DJ_Measurements` 所說的 best fit data rate 一致。
- 診斷門檻（格號衝突 3 個或 0.1%、半 UI 比例 1%／5%、邊緣 < 1000 等）全是現有的待校準產品門檻，非官方。
- 不含：PLL 型（First/Second/Third Order、Explicit、Equalized）、SSC 追蹤。現有 `pll.py` 為原型，本次未審。
- **出處**：`Clock_Recovery_Constant_Frequency`、`Jitter_Meas_Data_data_rate`、`Jitter_Meas_Data_unit_interval`。**信心**：中。

### 6.2 TIE（Clock / Data）
**輸出**：秒，每個邊緣一個值。即 §6.1 的 `tie`。
- Clock TIE：每個週期相對理想時脈。Data TIE：邊緣相對「相鄰兩個時脈位置的中點」；與 `t0 + n·ui` 的格點等價。
- 非 zoom 量全部週期；zoom 只量窗內（以傳入範圍實現）。
- DFE 的 Pre-UI／Post-UI 位置選項不在範圍。
- **邊界**：無轉態→`ALL_HOLES`；邊緣 < 3→`TOO_FEW_POINTS`。
- **出處**：`Jitter_Meas_Clock_TIE`、`Jitter_Meas_Data_TIE`、`Clock_Recovery_TIE_Measurements`。**信心**：高（定義）。

### 6.3 TIE 濾波
**參數**：`type = HIGHPASS | BANDPASS | LOWPASS`；`shape = RECTANGULAR | DB20 | DB40 | DB60 | FIRST_ORDER | SECOND_ORDER`（後二者僅高通、低通）；`start_freq`、`stop_freq`；`damping`（僅二階）。**預設值官方未載**；【設計決定】預設關閉。

【官方圖】轉移函數（s = jω，ω = 2πf）：
```
一階高通  TF = s / (s + ωn)
一階低通  TF = ωn / (s + ωn)
二階高通  TF = s² / (s² + 2ζωn·s + ωn²)
          ωn = ω3dB / sqrt( 2ζ² − 1 + sqrt((2ζ² − 1)² + 1) )
二階低通  TF = (2ζωn·s + ωn²) / (s² + 2ζωn·s + ωn²)
          ωn = ω3dB / sqrt( 2ζ² + 1 + sqrt((2ζ² + 1)² + 1) )
```
ζ 說明（`TIE_Filter`）：<1 欠阻尼、>1 過阻尼、=1 臨界、0.707 為 Butterworth 型。

【設計決定】（官方皆未載，信心低）
- 一階的 ωn = 2π×Start（高通）或 2π×Stop（低通）；二階的 ω3dB 同此對應。
- `RECTANGULAR`：頻域磚牆，通帶 1、阻帶 0。`DB20/40/60`：只定振幅 `min(1, (f/fc)^k)`（高通）或 `min(1, (fc/f)^k)`（低通），k=1/2/3，零相位。官方只說一階「類似 20 dB/decade 但比較彎」，由此推得 DBxx 是折線漸近線。
- TIE 是非等距序列（非轉態的 UI 沒有值）：先以線性內插補到每個 UI 一點的等距序列（取樣率 1/ui），在頻域乘上響應，再取回原邊緣位置的值。
- **邊界**：Start ≥ Stop（帶通）→參數錯誤；頻率 ≥ 1/(2·ui)→參數錯誤；邊緣數 < 16→`TOO_FEW_POINTS`【設計決定】。
- **出處**：`TIE_Filter`、`Eqn_First_Order_Highpass/Lowpass`、`Eqn_Second_Order_Highpass/Lowpass`。

### 6.4 時脈抖動量測
全部需要 Measure All Edges；逐事件輸出。
| 量測 | 輸出 | 定義 | 出處 |
|---|---|---|---|
| N-Period | 秒 | 連續 N 個週期的總時間；每次右移 1 週期 | `N-Period` |
| Period-Period | 秒 | 第二組 N-period − 第一組 N-period；每次右移 1 週期。N=1 即舊稱 cycle-cycle | `Jitter_Meas_Clock_period-period` |
| +Width − +Width | 秒 | 後一週期的正脈寬 − 前一週期的正脈寬 | `Jitter_Meas_Clock_pos_width-pos_width` |
| −Width − −Width | 秒 | 同上，負脈寬 | `Jitter_Meas_Clock_neg_width-neg_width`（未重讀） |
| Duty Cycle − Duty Cycle | % | 後一週期 duty − 前一週期 duty | `Jitter_Meas_Clock_duty_cycle-duty_cycle` |
```
N-Period[i]      = times[i+N] − times[i]                 （同向邊緣）
Period-Period[i] = N-Period[i+N] − N-Period[i]
```
- **Period-Period 的第二組起點**：文字「第一組的 n-period 與第二組相減，之後右移一個週期」可讀成兩組相鄰不重疊（起點差 N），也可讀成起點差 1。現有實作取相鄰不重疊（依圖 image283 的解讀，圖本次未打開）。N=1 時兩種讀法相同。信心中。
- 【設計決定】缺邊不跨：格號差必須剛好等於 N 才配對（現有 `_pairs`）。官方未提缺邊。
- 【設計決定】寬度差的正負號＝後減前。官方文字 "subtracts it from the positive pulse width of the second cycle" 支持此讀法。
- **邊界**：訊號類型不是時脈→`NOT_A_CLOCK`；N 超過可用邊緣數→`EDGE`；`meas_all_edges=False`→`MEAS_ALL_EDGES`。
- N 的範圍：現有 1–20，官方範圍本次未查到。

### 6.5 資料抖動量測
| 量測 | 輸出 | 定義 | 出處 |
|---|---|---|---|
| Unit Interval | 秒 | 官方：找最窄資料脈衝當理想 UI | `Jitter_Meas_Data_unit_interval` |
| Data Rate | Hz（b/s） | 1 / UI；Fully／Semi-Automatic 兩種模式 | `Jitter_Meas_Data_data_rate` |
| N-UI | 秒 | 連續 N 個 UI 的時間；每次右移 1 UI | `Jitter_Meas_Data_N-UI` |
| UI-UI | 秒 | 相鄰兩個 N-UI 之差；每次右移 1 UI | `Jitter_Meas_Data_UI-UI` |
- 【設計決定】Unit Interval、Data Rate 回報 §6.1 擬合出的 `ui` 與 `1/ui`（單一值），不是逐脈衝統計。官方說有 statistics，但逐事件的值怎麼來未載。
- N-UI／UI-UI：【設計決定】只在格號差剛好為 N 的邊緣對上計算（`times[j] − times[i]`，`n[j] − n[i] == N`）。資料中沒有邊緣的 UI 位置官方怎麼處理，未載。信心低。
- Setup time、Hold time、Phase：需雙來源，專頁本次未讀，不在範圍。

### 6.6 BER → Q
**輸入**：`ber`。**輸出**：`Qber`（無因次，雙側）。
**參數**：`ber` 數值，預設 1E-12，範圍 1E-6–1E-18（`Noise_Tab_Measurements`）；另有預設等級 J2／J4／J5／J9 = 2.5E-3／2.5E-5／2.5E-6／2.5E-10（三個對話框，轉引 `ALGORITHMS.md` §8）。
```
Q1(ber)   = −Φ⁻¹(ber)                      # 標準常態分位數；Python: -statistics.NormalDist().inv_cdf(ber)
Qber(ber) = 2 · Q1(ber)
```
參考值（由上式算出，非官方表）：
| BER | Q1 | Qber |
|---|---|---|
| 1E-6 | 4.7534 | 9.5068 |
| 1E-12 | 7.0345 | 14.0690 |
| 1E-18 | 8.7573 | 17.5146 |
| 2.5E-3（J2） | 2.8070 | 5.6141 |
| 2.5E-5（J4） | 4.0556 | 8.1113 |
| 2.5E-6（J5） | 4.5648 | 9.1296 |
| 2.5E-10（J9） | 6.2191 | 12.4382 |

- **整節是【設計決定】，信心低，需實機驗證。** 官方全套文字沒有 Q↔BER 的數值表，也沒有定義 Q 是單側或雙側（N6、N7）。
- 採雙側的理由：RJ/DJ 頁寫 `TJ = DJδδ + Q·RJrms`，Eye Contour 頁寫每一側 `½·Qber·Rj`。把 Q 定為雙側總寬係數，兩頁就一致（1E-12 時 TJ = DJδδ + 14.07·RJ，是業界 dual-Dirac 的常見寫法）。
- 未納入轉態密度（transition density）修正。Infiniium 是否納入，未知。
- J 等級是否就是把 BER 代入同一個 Q 公式，或另有分位數定義（「涵蓋除 2.5E-N 以外的全部分布」），官方文字未載。
- **邊界**：ber 不在 (0, 0.5)→參數錯誤；超出官方範圍 1E-18–1E-6 且不是 J 等級→`LIMITED`。

### 6.7 DDJ / DCD / ISI（Periodic 圖樣）
**輸入**：`tie[], n[], rising[]`、`pattern_length L`（UI）。**輸出**：`DDJ 向量[L]`（秒）、`DDJpp`、`DCD`、`ISIpp`（秒）。
```
slot = n mod L
ddj[s]  = mean( tie[slot == s] )            # 沒有邊緣的 slot 無值
DDJpp   = max(ddj) − min(ddj)
DCD     = | mean(ddj[上升 slot]) − mean(ddj[下降 slot]) |
ISIpp   = max( ptp(ddj[上升 slot]), ptp(ddj[下降 slot]) )
residual = tie − ddj[slot]                  # 不相關的 TIE，給 §6.8 用
```
- 折疊平均取 DDJ 向量、再從 TIE 扣掉，是官方明寫的方法（UTJ 一節）。
- 階層採 N3：DJ = DDJ（DCD＋ISI）＋ BUJ（PJ＋ABUJ）；DDJpp ≠ ISIpp。
- DCD 的原文是「上升緣位置直方圖的平均」與「下降緣位置直方圖的平均」之差的絕對值。【設計決定】直方圖取自 DDJ 向量（每個 slot 一票）；若官方是對所有邊緣（每個邊緣一票）取平均，在各 slot 出現次數相同時兩者相等。
- Edge Direction 選 Rising Only／Falling Only 時 ISIpp 只用該極性；DCD 無法計算→`INVALID`。
- `L` 的取得：使用者給定。自動偵測圖樣長度（`JitAutoPatternLength`）官方未載算法，不實作。
- **Arbitrary（無圖樣）模式：【未知】，不實作**，回 `INVALID`。ISI Filter 屬 Arbitrary 模式（N5），同樣不實作。
- **邊界**：完整圖樣數 < 2→`INVALID`（官方：DCD/ISI/DDJ 至少 2 個完整圖樣）；某極性沒有任何 slot→DCD、ISIpp `INVALID`；折疊後同一 slot 同時有上升與下降緣→`NO_PATTERN`（L 錯誤）【設計決定】。
- **出處**：`Jitter_Measurements_RJ___DJ_Measurements`、`RJ___DJ_Record_Length_Requirements`。**信心**：折疊法高；細節中。

### 6.8 RJ / PJ 分離 — 頻譜法
**輸入**：§6.7 的 `residual`、`n`、`ui`。**輸出**：`RJrms`、`PJrms`（秒）、PJ 的時間序列（給 §6.10）。
**參數**：`rj_bandwidth = NARROW（pink，預設） | WIDE（white）`。
官方（定性，`Questionable_RJ___DJ_Measurements`、轉引 `ALGORITHMS.md` §3）：看抖動頻譜，窄頻尖峰＝PJ，其餘基線＝RJ。Wide 假設基線平坦、寬頻凸起算 PJ；Narrow 用非線性判決閾值跟隨非平坦基線、寬頻凸起算 RJ。
**以下演算法全部是【設計決定】，信心低。官方的實際算法在加密的 `.m` 裡。**
```
x = residual 以線性內插補到每個 UI 一點（長度 M），去平均
X = rfft(x · hann) ；P = |X|²（依視窗能量正規化，使 Σ P = var(x)）
floor = WIDE:   全頻段 P 的中位數 / ln 2（常數）
        NARROW: P 的滑動中位數 / ln 2（窗寬 = M/64 格，至少 33 格）
spur = P > k · floor，k = 10
RJrms = sqrt( Σ 把 spur 格換成 floor 後的 P )
PJrms = sqrt( Σ spur 格的 (P − floor) )
PJ 序列 = irfft(只保留 spur 格的 X)，取回邊緣位置
```
- 中位數除以 ln 2：白雜訊功率譜各格為指數分布，中位數＝平均×ln 2。
- 常數 k=10、窗寬 M/64、Hann 窗都是待校準的產品門檻。
- 補洞用線性內插會把高頻壓低；RJ 可能略為低估。上限：轉態密度低的圖樣誤差較大，要改善須換成 Lomb-Scargle 之類的非等距頻譜法。
- **邊界**：M < 2048 個轉態→依 §6.14；全部都是 spur 或 floor=0→`INVALID`，原因對應官方 "Too much jitter"。
- `JitterScopeRj`（扣除示波器自身 RJ）：`RJ = sqrt(max(RJrms² − ScopeRJ², 0))`【設計決定，RSS 扣除；官方只說 calibrated out】。

### 6.9 RJ / PJ 分離 — Tail Fit（低優先）
官方只說：有串擾或 BUJ 時 Tail Fit 更準；`JitRjPjAlgorithm` = Spectral Only／Tail Fit Only／Spectral & Tail Fit，`JitRjPjReporting` 選報哪一個。`.ctf` 檔名顯示有 nlinfit、walkdown、robust sigma、單／雙／三高斯分類，**公式未知**。
【設計決定】若要實作，用 Q-scale 尾端線性擬合：
```
對 residual 的經驗 CDF，左尾取 p < 0.01、右尾取 p > 0.99 的點
左尾：Q = Φ⁻¹(p) 對 t 做線性回歸 → σL = 1/斜率，μL = 截距換算
右尾同理 → σR, μR
RJrms = (σL + σR) / 2；DJδδ(不相關部分) = μR − μL
```
- 尾端各少於 50 點→`INVALID`。1% 與 50 點為待校準門檻。
- **不宣稱與 Infiniium 的 Tail Fit 等價。** 信心低。BUJδδ、ABUJrms 需要此法才有意義；本規格不定義這兩項的算法（未知）。

### 6.10 Dual-Dirac：TJ / DJδδ / PJδδ / UTJ / UDJδδ / Eye Width
**輸入**：`ddj` 向量、PJ 序列、`RJrms`、`ber`、`ui`。**輸出**：秒（或 UI）。
官方總式：`TJ(pp) = DJδδ + Q·RJrms`；模型是兩個 σ=RJrms、相距 DJδδ 的高斯。UTJ 用同一式子，但套在扣除 DDJ 後的直方圖上。UDJδδ「通常等於 PJδδ」。Eye Width = UI − TJ(BER)。
**DJδδ 怎麼從分量算出來，官方未載。以下是【設計決定】，信心低：**
```
def dual_dirac(bounded_samples, sigma, ber):
    # bounded_samples：有界（確定性）抖動的樣本
    模型分布 = bounded_samples 的經驗分布 ⊗ N(0, sigma)
    tL = 模型 CDF = ber 處的時間；tR = 模型 CDF = 1 − ber 處的時間
        （以混合常態的解析 CDF 求根，不做直方圖數值摺積）
    TJ = tR − tL
    DJdd = TJ − Qber(ber) · sigma
    return TJ, DJdd

TJ,  DJδδ  = dual_dirac( ddj[slot] + PJ序列, RJrms, ber )
UTJ, UDJδδ = dual_dirac( PJ序列,            RJrms, ber )
PJδδ = UDJδδ
EyeWidth_BER = ui − TJ
```
- 這樣定義使官方總式 `TJ = DJδδ + Q·RJrms` 恆成立，且純高斯時 DJδδ=0、TJ=Qber·RJ。
- 兩側各在尾端機率＝ber 處取點，是與 §6.6 `Qber = 2·Q1(ber)` 配套的選擇（純高斯時 tR − tL = 2·Q1(ber)·σ）。若改成兩側各 ber/2，§6.6 也要一起改。
- 官方說「UTJ = TJ − DDJpp 只是近似」，與此處各自獨立計算一致。
- DJpp（官方結果表有此項，定義本次未讀到）：不實作。
- **邊界**：RJrms=0→TJ = 有界部分的 p-p，DJδδ=TJ；樣本 < §6.14 的門檻→依該節；EyeWidth_BER ≤ 0→`CLOSED_EYE`。
- **出處**：`Jitter_Measurements_RJ___DJ_Measurements`。

### 6.11 DDPWS、F/2
| 量測 | 輸出 | 公式 | 出處 |
|---|---|---|---|
| DDPWS | 秒 | `T − min(所有脈衝寬度)`；T 在固定頻率還原下＝best fit data rate 的倒數（即 `ui`）；每次擷取一個值 | `Jitter_Measurements_RJ___DJ_Measurements` |
| F/2（Even/Odd） | 秒 | `| mean(偶數位元邊緣位置) − mean(奇數位元邊緣位置) |`（轉引，專段未重讀） | 同上 |
```
DDPWS = ui − min( 相鄰邊緣的 t_mid 差 )
F/2   = | mean(tie[n 為偶數]) − mean(tie[n 為奇數]) |
```
- 脈衝寬度在使用者指定的閾值上量（官方明寫）。
- F/2 的「邊緣位置」用 TIE 還是用扣除 DDJ 後的值，未載；【設計決定】用 TIE。信心中。
- **邊界**：邊緣 < 2→`EDGE`；DDPWS 可為負（最窄脈衝比 UI 寬），照回。

### 6.12 JNU / JHNU（只記定義，不實作）
JNU：總抖動直方圖扣掉兩側各 10^-N/2 尾巴後的寬度。JHNU：其中的水平分量，用每個邊緣的 dual-Dirac 結果與斜率 1/|SR| 的線性模型分離（轉引 `ALGORITHMS.md` §3；`JHNU_Derivation`、`JHrms_Derivation` 本次未讀）。N 的來源與推導未整理，列為開放問題。

### 6.13 雜訊：RN / PI（低優先）
- 官方：用與抖動相同的頻譜法分離 RN（隨機雜訊）與 PI（週期干擾）。`RN Bandwidth` 預設 **wide（white）**，與 RJ 的預設 narrow 不同。TI（總干擾）與 TJ 用同一個 BER，預設 1E-12。垂直方向的對應式為 `Tn = Dn + ½·Qber·Rn`（每一側）。
- 【設計決定】演算法照 §6.7–§6.10，把「邊緣時間誤差」換成「眼中心取樣電壓相對該準位平均的誤差」，one level 與 zero level 分開算。取樣位置、ISI 的扣除方式官方未整理。信心低。
- **出處**：`Noise_Tab_Measurements`、`Jitter_Noise_Setup_Dialog_controls_Noise`（後者未重讀）。

### 6.14 記錄長度門檻（N4 的實作）
| 條件 | 官方行為 | 出處 |
|---|---|---|
| 單次擷取 UI 數 < 約 30,800 | 顯示 "too few points" | `RJ___DJ_Record_Length_Requirements` |
| 完整圖樣 < 2 | 無法算 DCD／ISI／DDJ | 同上 |
| Periodic 模式轉態 < 2048 | "acquisition skipped"（RJ、PJ、DJ、TJ） | 同上 |
| 累計轉態 < 約 154,000 | 尚不顯示 RJ／PJ／DJ／TJ（顯示 "incomplete"） | 同上 |
| 完整圖樣 < 128 | 顯示 `?` | `Questionable_RJ___DJ_Measurements` |
| 完整圖樣 < 1024 | RJ/PJ 改用 arbitrary 方法 | `Jitter_Graphs`（轉引） |

`Questionable_RJ___DJ_Measurements` 同頁又寫「低於 128 個圖樣顯示 too few points」，與上表第 1、5 列衝突。裁決見 N4。
```
param record_length_policy = OFFICIAL | RELAXED      # 預設 OFFICIAL
OFFICIAL：上表前四列不滿足 → INVALID（原因用官方字串）；圖樣 < 128 → LIMITED
RELAXED ：只有「圖樣 < 2」「轉態 < 2048」為 INVALID；其餘降為 LIMITED 並照算
```
- 【設計決定】加 `RELAXED`。理由：DSO-X 等記錄較短的檔案在官方門檻下幾乎都會被擋掉，離線分析需要一個「照算但標示可疑」的出口。`RELAXED` 的結果不得宣稱符合 EZJIT Plus 規則。
- 圖樣 < 1024 時官方改用 arbitrary 方法；本規格沒有 arbitrary 方法，【設計決定】仍用 periodic 方法並標 `LIMITED`。

### 6.15 不在本規格（只列名）
PLL／Explicit／Equalized clock recovery、SSC、Setup/Hold time、Phase、PAM 抖動、De-emphasis、X-Corr、相位雜訊、Denoise（示波器自身雜訊校正）、BER Bathtub 圖、各種圖形輸出。

---

## 7. InfiniiScan（只列已知選項；演算法全部【未知】）
離線 Help 沒有 InfiniiScan 的演算法頁面（檔名搜尋 InfiniiScan／Zone／Non-monotonic 皆無）。Help 內提到 InfiniiScan 的只有授權與用途說明（`dlg_MeasurementLevelQualification`、`Questionable_or_Missing_Measurement_Results`、`dlg_LimitTestSetup` 等）。`Runt_Trigger`、`Serial_Trigger_Software-Based` 描述的是硬體 Runt 觸發與協定搜尋觸發，**不能當作 InfiniiScan 的演算法來源**。

| 模式（`SwTrigMode`） | 已知參數 | 判定演算法 |
|---|---|---|
| `swTrigOff` | — | — |
| `swTrigMeas`（Measurement Limit） | `SwTrigMeasSetup` | 未知 |
| `swTrigZone`（Zone Qualify） | `SwTrigZoneSigId`、`Mode`、`State`、`CenterTime`、`CenterVolts`、`Width`、`Height`、`Logic`（跨通道邏輯）、`Sel`、`HideAll`、`Delete(All)`、`Summary`；以畫框建立 | 未知（「波形與區域相交／不相交」的判定、取樣點或內插線段、邊界是否含入皆未知） |
| `swTrigSerial`（Generic Serial） | `SwTrigSigId`、`SwTrigSerialDataRateStr`、Search String；需 Clock Recovery | 未知 |
| `swTrigNonMono`（Non-monotonic Edge） | `NonMonotonicHyst`、`NonMonotonicEdgeDir`（rising／falling／either） | 未知 |
| `swTrigRunt` | `RuntUpperLevel`、`RuntLowerLevel` | 未知 |
| `swTrigQualFilterForIVL` | — | 未知 |

其他已知事實：總開關 `TrigSwState`；`HwToSwTrigDelay`（相對硬體觸發的延遲）；啟用時 qualified counter 被禁用；RTSA 模式下選單隱藏；Level Qualification 功能需要 InfiniiScan 授權。
本規格**不定義任何 InfiniiScan 演算法**。若產品要做類似功能，必須另立「產品自有定義」的規格，且不得以 InfiniiScan 相容為名。

---

## 8. 矛盾裁決（N1–N13）

`ALGORITHMS.md` §8 明確編號的只有 N1–N12。HANDOFF 說共 13 項；本規格把 §8「中」級裡唯一沒編號的實質衝突（PAM Eye Opening Probability）列為 **N13**。這個編號是本規格的指定，不是原文件的。

| 編號 | 矛盾 | 裁決（採用版本） | 理由 | 信心 | 需實機驗證 |
|---|---|---|---|---|---|
| N1 | 邊緣選取：專頁「非 zoom 量所有邊緣」vs 設定頁「Measure All Edges 關時只量單一邊緣」 | 採設定頁：實作開／關兩種模式（§2.5），預設關 | 設定頁是唯一說明開關語意的頁面，且 Period、Duty 等專頁本身也分別描述了開與關的行為 | 中 | 是（關時哪些量測取左起第一個邊緣） |
| N2 | Eye Contour：文字（Rj 在 Vcenter 加回等於 Rj-clean）vs 公式圖（用 Rj 而非 Rn、減號、±10 mV） | 採文字版（§5.9）；斜率區間用 ±5 mV | 文字版在 Vcenter 自洽（代回得 Rj_c），圖版不自洽。此判斷來自 `ALGORITHMS.md` §8，本次未重開公式圖 | 低 | 是 |
| N3 | ISI／DDJ 階層：`Jitter_Basics`「ISI 即 DDJ」vs EZJIT Plus 頁 DJ = DDJ(DCD+ISI) + BUJ(PJ+ABUJ) | 採 EZJIT Plus 頁；DDJpp ≠ ISIpp | 結果表分別定義了 DDJpp、DCD、ISIpp 三個不同的量 | 中 | 否（屬定義；數值驗證在 §10） |
| N4 | 128 patterns 同時是 `?` 門檻與 "too few points" 門檻 | 128 只用於 `?`；"too few points" 用約 30,800 UI；其餘門檻見 §6.14 | `RJ___DJ_Record_Length_Requirements` 是專門講門檻的頁面，數字較完整；同一門檻不可能同時觸發兩種顯示 | 中 | 是 |
| N5 | Jitter ISI Filter：`Jitter_Graphs` 說需 Periodic vs `Pattern_Length_Controls` 說屬 Arbitrary | 採 Arbitrary；本規格不實作（§6.7） | 依 `ALGORITHMS.md` §8 的判斷（控制項頁優先）；兩頁本次未重讀 | 中 | 否（不實作） |
| N6 | BER：對話框只列 J2/J4/J5/J9 vs `Noise_Tab` 說可設數值、預設 1E-12、範圍 1E-6–1E-18 | 兩者都支援：數值輸入（預設 1E-12）＋四個 J 等級（§6.6） | 兩種輸入不互斥，可能分屬不同對話框或版本 | 中 | 是（實機 UI 上兩者是否並存） |
| N7 | Q 係數：`TJ = DJδδ + Q·RJ` vs `Tj = Dj + ½Qber·Rj`，皆未定義單側或雙側 | Q 定為雙側：Qber = 2·Q1(BER)；兩式共用同一個 Qber（§6.6） | 這是唯一讓兩頁同時成立的讀法，且 1E-12 時得到業界常見的 14.07 | 低 | 是 |
| N8 | Vavg 範圍：總覽「第一週期」vs 專頁「可選單週期或整個畫面」 | 採專頁：`DISPLAY`／`CYCLE` 兩種（§4.4）；Vrms 同 | 專頁優先；總覽頁是舊流程敘述 | 高（選項存在）／中（預設值未載） | 是（預設值） |
| N9 | 量測直方圖解析度：「8 bit」vs「取自顯示、量化到顯示解析度」 | 不裁決哪個對。實作為可調參數 `hist_bins`（預設 256）、`hist_range`（預設資料 min–max）（§3.1） | 兩頁都沒給垂直範圍；Top/Base 對此敏感，猜錯的代價高 | 低 | 是（最優先） |
| N10 | Extinction Ratio：`?` 條件 > 2 °C vs 重做 dark cal 條件 ±1 °C | 不適用（離線分析沒有探棒溫度，ER 不在範圍）。若日後要做，`?` 用 > 2 °C（`Questionable_or_Missing_Measurement_Results` 明寫） | 兩個數字描述的可能是不同事件（顯示 `?` 與建議重校） | 中 | 否 |
| N11 | Color grade 計數器「53-bit」vs 最大計數 2,097,151（=2²¹−1） | 不採任何一個：本規格的眼圖量測不經像素計數器（§5.0）；色階圖顯示用的計數不設飽和上限 | 量測不依賴它 | 低（哪個數字對）／影響無 | 否 |
| N12 | Rise/Fall 分頁沒有 mid，但邊緣判定要過三個閾值 | Rise/Fall 用該分頁的 lower、upper；mid 取兩者中點，只用於事件時間（§4.6） | 連續波形由 lower 下方到 upper 上方必過其間任一點，mid 不影響邊緣成立與否；不必假設取自 General 分頁 | 中 | 是（僅當 General 的 mid 落在 Rise/Fall 的 lower–upper 之外時有差） |
| N13* | PAM Eye Opening Probability 預設：VEC 段 10⁻⁵ vs 控制項段 1E-02 | 不裁決；PAM 不在範圍 | 原文沒說明兩個數字各自的情境 | 低 | 是（若日後做 PAM） |

`ALGORITHMS.md` §8 其他未編號項目的處置：
| 項目 | 處置 | 信心 |
|---|---|---|
| Top/Base「top 40 percent」vs 同頁「top half」 | 採 40%（圖與 4 個專頁一致） | 高 |
| 兩種 DCD（眼圖用中位數、EZJIT Plus 用平均） | 視為兩個不同量測，分別實作（§5.8、§6.7） | 高 |
| 眼圖 DCD 文字「中閾值」vs 公式圖「50% 點」 | 用使用者設定的 mid | 中 |
| Histogram p-p「欄 vs 列」 | 屬漏寫；Histogram 量測不在範圍 | — |
| PAM 眼高眼寬 zero hits vs 可選機率 | PAM 不在範圍 | — |
| `Eye_Width` 頁把眼寬寫成 eye height | 筆誤 | 高 |
| Preshoot 總覽頁 vs 專頁 | 採專頁與公式圖（§4.12） | 高 |

---

## 9. 與現有 Python 實作的差異

審查範圍：`measure.py`、`edge.py`、`eye.py`、`jitter.py`、`clock.py`。同目錄的 `pll.py`、`filter.py`、`fft.py`、`marker.py`、`mathfn.py`、`peaks.py`、`rate_seed.py`、`slip.py` 只看過檔頭，**未審**；下表的「缺」只代表這五個檔案裡沒有。

### 9.1 已一致
| 項目 | 位置 | 備註 |
|---|---|---|
| Top/Base 40/20/40、5% 回退 | `measure.levels` | 直方圖範圍與格數是假設（N9） |
| 10/50/90、20/50/80 百分比閾值 | `measure.THRESHOLDS` | 核心接受任意百分比 tuple，等於已有 Custom % |
| 三閾值邊緣、線性內插、忽略不完整轉換 | `edge.edges` | |
| Rise/Fall、4 點規則、不足時回界限 | `edge.transition` | 界限符號用 `<`／`>`，官方為 `≤` |
| Slew rate | `edge.transition(slope=True)` | |
| Period／Frequency／±Width／Duty 公式 | `edge.periods/widths/duty` | |
| Overshoot／Preshoot 公式（含 Top−Base 正規化、專頁極性） | `edge.shoot` | 平台中心為假設 |
| Vp-p、Vamp、Vavg（整段）、Vrms DC／AC（整段） | `measure.measure` | |
| 眼高、眼寬（Extrapolate，±3σ／UI−6σ）、眼窗 40–60% | `eye.measure` | 資料來源為原始取樣 |
| Eye jitter RMS=σ、p-p=6σ | `eye`（「裁切 σ」「6σ 估計」） | 名稱與官方不同 |
| Q-factor、Crossing % 公式 | `eye.measure` | Vcrossing 求法為假設 |
| 眼圖 DCD（中位數差的絕對值，時間） | `eye.measure("DCD")` | |
| 固定頻率 clock recovery：三種模式、平均 TIE=0 | `clock.recover` | 全自動資料型的種子有意偏離官方 |
| TIE、N-Period、Period-Period、±Width 差 | `jitter.py` | |
| 「目前」值取最接近參考點的事件 | `measure.stats` | 等同 Measure All Edges 關的選法 |

### 9.2 缺少或不同，與建議優先序
優先序：**P0**＝先做（其他項目的前提，或便宜且直接影響正確性）；**P1**＝核心功能缺口；**P2**＝次要；**P3**＝低信心或依賴未知，最後做。

| 優先 | 項目 | 現況 | 規格 | 工作量 |
|---|---|---|---|---|
| P0 | Top/Base 直方圖範圍實機校準 | 固定資料 min–max、256 格 | §3.1 `hist_range`／`hist_bins` 參數＋§10 的 V1 | 小（參數）＋需實機 |
| P0 | 絕對電壓閾值、Hysteresis 閾值 | 只有百分比入口 | §3.2 `CUSTOM_VOLTS`、`HYSTERESIS`、`snap_to_zero`、`auto_set` | 小 |
| P0 | Top/Base 演算法選項 | 只有 Standard | §3.1 `HISTOGRAM`、`MIN_MAX`、`CUSTOM` | 小 |
| P0 | Measure All Edges 開關 | 一律回全部事件；「目前」欄取最近 | §2.5（多一個旗標決定統計範圍；關時極性跟隨最近邊緣） | 小 |
| P0 | Vavg／Vrms 單一週期 | `cycles`＝多個整數週期 | §4.4 `CYCLE`；現有模式改名 `ALL_CYCLES` | 小 |
| P1 | BER→Q | 無 | §6.6（標準庫一行） | 極小 |
| P1 | DDJ／DCD(EZJIT)／ISIpp | 無 | §6.7 | 中 |
| P1 | RJ／PJ 頻譜分離 | 無 | §6.8 | 中 |
| P1 | TJ／DJδδ／PJδδ／UTJ／UDJδδ／Eye Width(BER) | 無 | §6.10 | 中 |
| P1 | 記錄長度門檻 | 只有邊緣 < 1000 的提示 | §6.14 | 小 |
| P1 | Delta Time（邊緣編號、可選閾值、從左數） | 「延遲」為最近邊緣配對 | §4.11 | 小 |
| P1 | 眼圖 DCD %、眼寬與 Eye jitter 的 UI 單位 | 只有時間 | §5.8、§5.0 | 極小 |
| P1 | 資料型 N-UI、UI-UI；Duty−Duty | 檔頭註明延後 | §6.5、§6.4 | 小 |
| P2 | 眼高／眼寬 Use Measured Data | 無 | §5.2、§5.4 | 小 |
| P2 | 眼高 At Recovered Clock Location；眼寬 Automatic 閾值 | 無 | §5.2、§5.4 | 小 |
| P2 | DDPWS、F/2 | 無 | §6.11 | 極小 |
| P2 | TIE 濾波 | 無（`filter.py` 是波形濾波，未審） | §6.3 | 中 |
| P2 | 削波標示 | 無 | §4.2 `clip_range` | 小 |
| P2 | Vrms dBm 與參考阻抗 | 無 | §4.5 | 極小 |
| P2 | Vovershoot／Vpreshoot | 無 | §4.12 | 極小 |
| P2 | 失敗原因碼對齊官方字串 | 自由文字訊息 | §2.4 | 小 |
| P3 | Tail Fit、BUJ／ABUJ | 無 | §6.9（公式未知） | 大 |
| P3 | 雜訊 RN／PI／TI | 無 | §6.13 | 中 |
| P3 | Eye Contour | 無 | §5.9 | 大 |
| P3 | Level Qualification、Gating | 無 | §3.4 | 小／未知 |
| P3 | JNU／JHNU、Arbitrary 模式 DDJ、ISI Filter | 無 | 未定義 | — |
| — | InfiniiScan | 無 | 不定義（§7） | — |

### 9.3 現有實作有意偏離官方、建議保留並標示的部分
| 項目 | 現有作法 | 官方 |
|---|---|---|
| 資料型全自動速率種子 | 間隔對數直方圖第一個顯著峰 | 最窄脈衝 |
| 眼圖資料來源 | 原始取樣 | Color Grade 資料庫 |
| Vtop／Vbase（眼） | 中閾值分群後取平均 | 垂直直方圖的峰 |
| 「−工作週期」「相位」「電壓比」「延遲」「上升／下降斜率分列」「眼 Jitter 原始 σ／實測 p-p」 | 產品自有項目 | 官方無此項或定義不同 |

---

## 10. 驗證計畫

### 10.1 參考值來源（由可信到不可信）
1. **Infiniium（N8900A 離線版或 Infiniium 實機）載入同一筆波形後的讀值**。這是規格所依據的 Help 對應的軟體，是主要驗收基準。
2. **合成波形的解析真值**。驗證公式與數值實作，不能證明與 Infiniium 一致。
3. **DSO-X（InfiniiVision）面板讀值**。DSO-X 與 Infiniium 是不同的韌體家族，量測定義是否相同**未經確認**；只能當旁證，差異不能直接判為實作錯誤。

已有資料：
- `/Users/lianshi/Desktop/claude-cowork/示波器截圖/N8900A/時間電壓量測研究_20261023_015050/waveforms/*.h5`（第 01–15 案；01 線性 PWM、02/03 正弦、04 三角波、06 含雜訊 PWM、09 單一尖峰、13 截斷上升緣等）
- `/Users/lianshi/Desktop/claude-cowork/示波器截圖/N8900A/DSOX6004A_Jitter驗證_20261024/CH1_10MHz_20261024_113053.h5`
- 這些 `.h5` 能否直接被 N8900A 開啟，**尚未確認**；不行的話要先轉成 Infiniium 可讀的格式。

### 10.2 容差
下表容差全部是【設計決定】的驗收目標，不是官方規格。`dt`＝取樣間隔；`bin`＝(直方圖範圍)/256。

| 編號 | 項目 | 輸入 | 比對對象 | 期望容差 |
|---|---|---|---|---|
| V1 | Top／Base 與直方圖範圍（N9） | 06（含雜訊 PWM）、02/03（正弦）、04（三角波）、09（尖峰），各在 2 種垂直刻度下擷取或載入 | Infiniium 的 Vtop、Vbase | \|差\| ≤ 1 bin。先用它選定 `hist_range`／`hist_bins`：三種假設（資料 min–max、畫面滿刻度、8 bit 量化）中，只有一種應同時通過 06 與 02/03 |
| V2 | Top／Base 選項 | 同上，切換 Standard／Histogram／Min,Max | Infiniium | 同 V1；Min,Max 應完全等於 Vmax／Vmin（≤ 1 LSB） |
| V3 | 閾值 | 01；切換 10/50/90、20/50/80、自訂電壓、±hysteresis | Infiniium 的 V upper／middle／lower | ≤ 0.1% Vamp |
| V4 | Rise／Fall | 01（解析真值 8 µs）；另取每緣 2、3、4、6 點的版本 | 解析真值；Infiniium | ≥ 4 點：\|差\| ≤ 0.1·dt 或 0.5%，取大者。< 4 點：比對 Infiniium 顯示的是 `?`、`≤` 還是不量（記錄行為，不設數值容差） |
| V5 | Period／Frequency／±Width／Duty | 01、07、08、10、12、15（乾淨方波／PWM） | Infiniium；解析真值 | 時間 ≤ 0.1·dt；Duty ≤ 0.01 個百分點 |
| V6 | Measure All Edges（N1） | 一筆含 ≥ 100 個週期、其中一個週期刻意拉長 5% 的波形 | Infiniium 在開／關兩種設定下的 Current、Count、Max | 開：Count 相同、Max 相符。關：Count=1，且選到的邊緣與本規格相同；若不同，記下 Infiniium 選的是左起第一個還是最近參考點 |
| V7 | Vavg／Vrms（N8） | 03（2.3 週期正弦，第一完整週期 Vavg 真值 2.000 V） | Infiniium 的 Display 與 Cycle 兩種設定 | ≤ 0.1% Vp-p。並記下 Infiniium 新增量測時的預設選項 |
| V8 | Overshoot／Preshoot | 加已知過衝（例如 10%）與振鈴的方波；另一筆只有單一邊緣 | Infiniium | ≤ 0.5 個百分點。單一邊緣：記錄 Infiniium 是否有值 |
| V9 | Vovershoot 語意 | 同 V8 | Infiniium | 判斷回傳的是絕對電壓還是差值（定性） |
| V10 | Delta Time | 兩通道已知延遲的方波 | Infiniium（指定邊緣編號與閾值） | ≤ 0.1·dt |
| V11 | Clock recovery／TIE | 合成 NRZ（PRBS7，已知 UI）；`DSOX6004A_Jitter驗證` 的 10 MHz 時脈 | 解析真值；Infiniium 的 Data Rate、TIE 的 Std Dev | 速率相對誤差 ≤ 1e-6（合成）；TIE σ 相對差 ≤ 5% |
| V12 | 眼高／眼寬／Q／Crossing %／Eye jitter／眼圖 DCD | 合成 NRZ：已知雜訊 σ、已知 RJ σ、已知 DCD（30 ps） | 解析值；Infiniium Real-Time Eye 量測（Extrapolate） | 與解析值：眼高 ≤ 2% Vamp、眼寬 ≤ 2% UI、DCD ≤ 1% UI。與 Infiniium：眼高 ≤ 3% Vamp、眼寬 ≤ 3% UI（多留的部分是像素量化） |
| V13 | 眼高／眼寬 Use Measured Data | 同 V12 | Infiniium | 先定性比對（大於或小於 Extrapolate 值、對窗寬的反應），再定容差 |
| V14 | BER→Q（N6、N7） | 合成：純高斯 RJ（σ 已知）、無 DJ、PRBS7 | 解析：TJ(1E-12) 應為 14.069·σ。Infiniium EZJIT Plus：TJ、RJ、DJ | 與解析 ≤ 2%。與 Infiniium：若 TJ/RJ ≈ 14.07 則雙側假設成立；若差異呈固定比例，回頭檢查轉態密度修正 |
| V15 | DDJ／DCD／ISI | 合成 PRBS7：已知 DCD、已知 ISI（一階 RC 通道） | 解析或高解析度模擬；Infiniium | DDJpp、ISIpp、DCD 各 ≤ 5% 或 0.5% UI，取大者 |
| V16 | RJ／PJ 分離 | 合成：RJ σ＋單頻 PJ（已知振幅、頻率）；另一筆雙頻 PJ | 解析：RJrms、PJrms（單頻為振幅/√2）。Infiniium | RJ ≤ 10%、PJrms ≤ 10%。Infiniium 的 PJδδ 與本規格的差異要記錄，預期這裡差異最大 |
| V17 | 記錄長度門檻（N4） | 同一訊號截成 100、200、2,000、31,000、160,000 UI 等長度 | Infiniium 顯示的字串 | 字串種類相符（`?`／too few points／acquisition skipped／incomplete） |
| V18 | TIE 濾波 | 合成 TIE：兩個已知頻率的正弦 PJ，濾掉其一 | 解析（一／二階用 §6.3 的式子）；Infiniium | 一／二階：通過分量振幅 ≤ 2%。其他形狀：只記錄 Infiniium 的衰減量，用來修正 §6.3 的設計決定 |
| V19 | Eye Contour（N2） | 合成：已知 RJ、RN、斜率 | Infiniium 的輪廓 | 先定性：比較文字版與公式圖版何者接近；不設數值容差 |
| V20 | 邊界行為 | 常數波形、單一邊緣、純雜訊、含 NaN、空檔、削波波形 | 本規格 §2.4；Infiniium 顯示的字串 | 本實作：原因碼與 §2.4 完全相符。Infiniium：記錄字串，更新 §2.4 的觸發條件 |

### 10.3 順序
V1 → V3 → V4–V5 → V6–V7 → V11 → V12 → V14 → V15–V16 → 其餘。V1 沒過之前，V4 以後凡是用到含雜訊或無平台波形的項目都不算驗收完成。

### 10.4 回歸
每個模組沿用現有慣例：`_self_check()` 內用合成波形的 assert（`python -m scope_tool.analysis.<模組>`）。新增功能各補一個最小的自我檢查，例如 §6.6 檢查 `Qber(1e-12) ≈ 14.069`，§6.10 檢查純高斯時 `DJδδ ≈ 0`。

---

## 11. 開放問題

**需實機（Infiniium）才能回答**
1. Top/Base 直方圖的垂直範圍（資料 min–max、畫面滿刻度、ADC 滿刻度）與格數；5% 是算單格還是峰區。（N9，最優先）
2. Measure All Edges 關閉時，哪些量測取「最接近時基參考點」、哪些取「格線左起第一個」。（N1）
3. 邊緣少於 4 點時，Rise time 是不量、標 `?`、還是標 `≤`；條件各是什麼。
4. Vavg／Vrms 新增時的預設範圍（Display 或 Cycle）；uniform sub-sampling 的比例與它對數值的影響。（N8）
5. Infiniium 量測前是否對取樣做 sin(x)/x 重建；閾值交越是線性內插還是其他。
6. Overshoot／Preshoot 的「中心點」算法；記錄中只有單一邊緣時能否量測。
7. Vovershoot／Vpreshoot 回傳的是絕對電壓還是與 Top/Base 的差。
8. Q 與 BER 的換算、單側或雙側、是否含轉態密度修正；J2/J4/J5/J9 是否走同一公式。（N6、N7）
9. DJδδ、PJδδ 由分量求出的方法；與本規格 §6.10 的差異量級。
10. RJ/PJ 頻譜法的非線性閾值；Narrow 與 Wide 在數值上的差異。
11. 128／30,800／2048／154,000／1024 各門檻實際觸發的字串。（N4）
12. 眼高／眼寬 Use Measured Data 的欄寬；Automatic 眼寬閾值的定法；At Recovered Clock Location 是否就是眼中心。
13. σcrossing 的迭代縮窗條件；Vtop／Vbase「峰」的界定。
14. TIE 濾波的預設值；Rectangular 與 20/40/60 dB/decade 的實際響應與相位。
15. Eye Contour 文字版與公式圖版何者為真。（N2）
16. "Small amplitude"、"Thresholds?"、"Lower?"／"Upper?" 的觸發條件。
17. `.h5`（DSO-X 匯出）能否直接被 N8900A 開啟。

**需取得其他資料才能回答**
18. `OneSrcEval`／`TwoSrcEval` 的實作（基本波形量測主體）。
19. EZJitMeasure、EyeContour 等加密 `.m` 的內容。
20. InfiniiScan 各模式的判定演算法（需 Infiniium 實機 Help 或使用手冊；離線 Help 沒有）。
21. `dspi_edge` 是否內插；`dsps_hist`（`sub_61046d20`）的格界與範圍處理。
22. `TopBaseAlg` 的 `PamUserDef`、`…TopBaseSens`、Gating 控制項的語意。

**文件尚未核對（`ALGORITHMS.md` §8 列出的未核對頁，加上本次沒重讀的）**
23. `Measurement_Analysis_EZJIT`、`JHrms_Derivation`、`JHNU_Derivation`、PAM 全部、各 PLL 規格頁、DFE/FFE/CTLE、Mask、Burst、`Edge_Time`、`T_Volt`、Phase、Setup/Hold time、`Jitter_Graphs`、`Pattern_Length_Controls`、`Jitter_Noise_Setup_Dialog_controls_Noise`、`dlg_JitterSetup_controls_*`。
24. 公式圖本次未重開、沿用前次確認結果的：image105/107/109/111（Overshoot／Preshoot）、image210/211/212/213（眼高／眼寬／Eye jitter）、Eye Contour 的 eqn_* 圖。未打開過的：image207（Crossing %）、image214（Q-factor）、image283–288（抖動量測示意圖）。

**需產品決策**
25. 預設要不要跟官方走「Measure All Edges 關」（統計只累計單一邊緣），還是維持現有「全部事件＋目前值」的呈現。兩者數值相容，只差統計欄的範圍。
26. 產品自有項目（−工作週期、相位、電壓比、延遲、原始 σ）在介面上如何與「官方定義」的項目區隔。
27. `record_length_policy` 的預設值：`OFFICIAL` 對短記錄會幾乎全擋。

---

## 附錄 A：數值門檻出處一覽
| 數值 | 用途 | 出處 | 性質 |
|---|---|---|---|
| 40% / 20% / 40% | Top/Base 掃描區 | `Calculating_Top_and_Base` 等 5 頁 | 官方 |
| 5% | Top/Base 回退 | `Calculating_Top_and_Base` | 官方（計法未載） |
| 256 格 | 直方圖 | `Building_a_Histogram`「eight bits」 | 官方數字，套用方式為設計決定 |
| 10/50/90、20/50/80 | 閾值 | `dlg_MeasurementThreshold` | 官方 |
| ±10 mV | Snap to 0 | 同上 | 官方 |
| 0.05×(Vmax−Vmin) | Auto set hysteresis | 同上 | 官方 |
| 4 個取樣點 | Rise／Fall／Slew 的邊緣 | `Rise_Time`、`Fall_Time`、`Slew_Rate` | 官方 |
| 1–65534 | Delta Time 邊緣編號 | `Delta_Time` | 官方 |
| 10–200 Ω；50／100／25 Ω | Vrms 參考阻抗 | `RMS_Voltage` | 官方 |
| 40%–60% | 眼窗 | `Eye_Height` | 官方 |
| ±3σ、6σ | 眼高／眼寬外插、Eye jitter p-p | `Eye_Height`、`Eye_Width`、`Eye_Jitter` 公式圖 | 官方 |
| 1 | Start Measurement After | `Eye_Height` | 官方（本規格不用） |
| ±5 mV | Eye Contour 斜率與 Dj 區域 | `Eye_Contour_generation` 文字 | 官方（圖為 ±10 mV） |
| 1E-12；1E-6–1E-18 | BER 預設與範圍 | `Noise_Tab_Measurements` | 官方 |
| 2.5E-3/-5/-6/-10 | J2/J4/J5/J9 | 抖動設定對話框（轉引） | 官方 |
| 0.707 | 二階 TIE 濾波 Butterworth 阻尼 | `TIE_Filter` | 官方（是否為預設未載） |
| 128、約 30,800、2048、約 154,000、1024、2 | 記錄長度門檻 | §6.14 所列各頁 | 官方（彼此有衝突） |
| 1667、1.0 | 二階 PLL Loop BW divisor、damping | `ALGORITHMS.md` §8 預設值表（轉引） | 官方（PLL 不在範圍） |
| 256·ULP | 近常數波形判定 | — | 避免 256 格直方圖的浮點邊界退化 |
| 每群 10 個取樣 | 眼的上下準位 | 現有 `eye.rails` | 設計決定 |
| ±3σ 迭代、20 次、1e-12 UI、1% | σcrossing 裁切與提示 | 現有 `eye.crossing` | 設計決定（待校準） |
| 10%、10 個、50 格、2 倍 | Vcrossing | 現有 `eye.v_cross` | 設計決定 |
| 3 個邊緣、10 次迭代、1000 個邊緣、0.1%、1%／5% | clock recovery 與診斷 | 現有 `clock.py` | 設計決定（待校準） |
| k=10、M/64、Hann | 頻譜法 | §6.8 | 設計決定（待校準） |
| 1%、50 點 | Tail Fit | §6.9 | 設計決定（待校準） |
| 每 1% UI 一欄 | 眼高 Measured | §5.2 | 設計決定 |
| §10.2 全部容差 | 驗收 | — | 設計決定 |
