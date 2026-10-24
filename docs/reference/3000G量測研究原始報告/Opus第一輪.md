# 3000G 使用手冊第 15 章「量測」vs 本專案實作（唯讀研究，第 1 輪）

- 手冊：Keysight InfiniiVision 3000G X-Series User's Guide，第 15 章，PDF 頁 249–282（頁碼＝PDF 頁＝印刷頁，兩者一致）。
- 程式：`scope_tool/analysis/measure.py`、`edge.py`、`rms.py`、`scope_tool/web/analysis_api.py`、`scope_tool/web/static/js/analysis/measure.js`（另參考 `scope_tool/ui/analysis_controls.py` 的 `_TIPS`、`measure_check.py`）。
- 對照基準：`docs/reference/Infiniium手冊-量測功能與算法.md`（以下簡稱「Infiniium 整理」）。
- 數值例子：除特別註明為解析計算者外，皆由 scratchpad 內的 `sim.py`、`sim2.py`、`sim3.py` 呼叫本專案 `measure`／`edge` 實際跑出（未改專案檔）。
- 標記：「手冊未載明」＝3000G 手冊文字與公式圖都沒寫；「推測」＝本報告的推論，非手冊斷言。
- 先說結論：**3000G 手冊對演算法的描述比 Infiniium 手冊簡略很多**。直方圖 40%／5% 規則、邊緣最少 4 點、過衝區間（遠端閾值到平台中點）等，都**只出現在 Infiniium 手冊**，3000G 手冊沒有。所以本專案多數實作「與 3000G 手冊不矛盾，但細節只能靠 Infiniium 或真機補」。手冊與實作真正有落差的地方集中在四處：**統計語意**、**「目前值取哪個邊緣」**、**量測區間（Full Screen／N Cycles）**、**−Duty**。

---

## 一、總覽表

判定欄：一致／不同／本專案沒有／手冊未載明（＝3000G 手冊沒寫到能比對的程度）。

| 量測項 | 3000G 手冊定義（頁） | 本專案 | 判定 | 影響 |
|---|---|---|---|---|
| Vmax／Vmin | 波形「顯示範圍」內最高／最低值（p257） | 範圍內原始樣本 max／min | 一致（資料來源不同，見 §2.0） | 低 |
| Vp-p | Max − Min（p257） | vmax − vmin | 一致 | 低 |
| Top | 上半部的眾數；眾數「不明確」時＝Max（p258） | 256 格直方圖，上 40% 取最高格；峰值 < 5% 總數就改用 Max；格內平均 | 手冊未載明細節（大方向一致） | **中**：噪聲約 2% 時會從眾數跳到 Max（§特別問題 b） |
| Base | 下半部的眾數；不明確時＝Min（p259） | 同 Top 的對稱做法 | 同上 | 中 |
| Amplitude | Top − Base（p258） | top − base | 一致 | 跟著 Top/Base |
| Overshoot | 上升：(局部極大 − Top)/Amp×100；下降：(Base − 局部極小)/Amp×100；量**最靠近觸發參考點**的那一個邊緣（p259） | 公式相同；**所有**同向邊緣都量，區間是遠端閾值到平台中點；「目前」取最左邊緣 | 公式一致；邊緣選擇不同 | **中** |
| Preshoot | 文字式與 Overshoot 完全相同（疑似手冊誤植）；圖 p261 顯示上升＝Base − 局部極小、下降＝局部極大 − Top；量最靠近觸發點的邊緣（p260–261） | 上升：base − min；下降：max − top；區間是平台中點到近端閾值 | 與**圖**一致；與文字式不一致（手冊自相矛盾） | 中 |
| Average | Σxᵢ/n；分 Full Screen 與 N Cycles 兩種；N Cycles 是「整數個週期」，少於 3 個邊緣顯示 "No edges"（p261） | **只做一個週期**（最左的完整同向邊緣對）；沒有完整週期就退回整段平均；沒有 Full Screen 選項 | **不同** | **中高**（例：2.5 週期方波，0.5 vs 0.6） |
| DC RMS | √(Σxᵢ²/n)；Full Screen／N Cycles（p261–262） | 只有整段（範圍內全部樣本） | 不同（缺 N Cycles） | 中（非整數週期最多差約 2%） |
| AC RMS | 扣掉 DC 的 RMS；N Cycles／Full Screen（Std Deviation），母體標準差 /N（p262–263） | 整段、扣同段平均、/N | Full Screen 一致；缺 N Cycles | 中 |
| Ratio | 兩個來源 AC RMS 的比值，以 dB 表示（p263） | 沒有 | 本專案沒有 | 低 |
| Y at X | 指定 X 處的 Y（p257） | 沒有量測項（游標讀值 `cursor_readout` 取最近樣本，類似） | 本專案沒有（游標近似） | 低 |
| Period | 兩個相鄰同極性邊緣在中閾值的時間差；中閾值交越必須同時穿過下、上閾值（濾掉 runt）（p264） | 相同（遲滯三閾值、線性內插）；所有週期都量 | 一致（邊緣選擇不同） | 低–中 |
| Frequency | 1/Period（p265） | 逐週期算 1/週期，再取統計 | 一致（平均值的語意略有差異） | 低 |
| Counter | 硬體計頻器，用觸發比較器，閘時間 0.1–10 s（p266） | 沒有（離線做不到） | 本專案沒有 | 無（做不到） |
| +Width／−Width | 上升中點到下一個下降中點／反之（p266） | 相同 | 一致 | 低 |
| Burst Width | 螢幕上第一個邊緣到最後一個邊緣（p266） | 沒有 | 本專案沒有 | 低 |
| Duty Cycle | +Duty = +Width/Period×100；−Duty = −Width/Period×100（p267） | 選「上升緣」：+Width/Period；選「下降緣」：**仍然是 +Width**，只是週期從下降緣起算 | **不同**（沒有 −Duty） | **中高**（25% 脈波：3000G −Duty＝75%，本專案「下降緣」＝25%） |
| Bit Rate | 1/（所有正負脈寬中最小的那個）（p267） | 沒有 | 本專案沒有 | 低 |
| Rise／Fall Time | 下閾值交越到上閾值交越的時間差（p267） | 相同，但**邊緣至少要 4 點** | 手冊未載明最少點數 | **高**（10 MHz 例全部顯示「—」） |
| Slew Rate | 最靠近時基參考點那個邊緣的 ΔY/ΔX，用上下閾值（p274） | 上升斜率／下降斜率＝(hi−lo)/上升時間；所有邊緣；也要 ≥4 點 | 公式一致，邊緣選擇不同 | 中 |
| Time at Edge | 50% 加少量遲滯（不受中閾值設定影響）；Auto 取最靠近參考點的邊緣（p268） | 沒有 | 本專案沒有 | 低 |
| Delay／Phase | 兩個來源之間；Phase = Delay/Period(來源 1)×360（p268–270） | 沒有 | 本專案沒有 | 中（雙通道需求） |
| X at Max Y／X at Min Y | 從左邊數第一次出現最大／最小值的 X（p271） | 沒有 | 本專案沒有 | 低（一行就能做） |
| +/−Pulse Count、Rising/Falling Edge Count | 只寫「count」（p272–273） | 沒有（但 `edges()` 已經有邊緣清單） | 本專案沒有 | 低 |
| Area | 波形與接地之間的面積，接地以下取負；Full Screen／N Cycles（p273） | 沒有 | 本專案沒有 | 低 |
| FFT：Channel Power／OBW／ACPR／THD | 頻帶功率；OBW 預設 99%；ACPR 1H–5H/1L–5L；THD 頻帶寬＝f₀/2（p274–276） | FFT 有，但沒有這四種量測 | 本專案沒有 | 低–中 |
| 閾值 | 預設 10/50/90% of Top–Base；可設 %（下 0–98、中 1–99、上 2–100）或絕對值；每個通道各自設定（p264、276–278） | 只有 10/50/90 與 20/50/80 兩組預設，全部通道共用 | 部分一致 | 中 |
| 量測視窗 | Auto／Main／Zoom／Gated by Cursors（p278） | 「全部」（**整個檔案**，不是可見畫面）或游標區間 | 部分一致 | 中 |
| 統計 | 目前、平均、最小、最大、σ、次數；**以擷取次數為單位**；σ 用 /N；有 Max Count、Relative σ（p279–280） | 以**同一筆記錄內的事件**為單位；另多一欄「範圍」；σ 用 /N（`np.std`） | **語意不同**（公式一致） | **高**（數值意義不同） |

---

## 二、逐項細節

### 2.0 共通前提（影響所有項目）

- **量測的對象是「顯示的資料」**：「Measurements and math functions are performed on displayed data」，縮放會影響解析度（p250）。手冊沒寫「顯示資料」有多少點、是否經過 sin(x)/x 內插或抽點（手冊未載明）。
  - 本專案：用範圍內的**全部原始樣本**（`measure.py:93` 註解寫明不做次取樣）。
  - 推測：真機的 Vmax／Vmin 可能來自抽點或峰值偵測後的顯示紀錄，跟原始樣本的極值會差幾個 LSB。
- **解析度不足時不給數字，改給訊息**：顯示 "No Edges"、"Clipped"、"Low Signal"、"< value"、"> value"（p250）。門檻約為滿刻度的 4%（p250，這是垂直解析度的條件）。
  - 本專案：拋出 `ScopeError`，前端顯示原因文字。沒有「< value」這種上下界輸出，也沒有 4% 滿刻度的 Low Signal 判斷（離線檔通常也沒有滿刻度資訊）。
- **一次量一個邊緣或一段**：只有 Overshoot、Preshoot（p259–260）、Time at Edge（p268）、Slew Rate（p274）、Delay Auto（p269）明確寫「edge closest to the trigger/timebase reference point」。Period／Width／Rise 只說「X cursors show the portion being measured」，**取哪一個週期或邊緣，手冊未載明**。
  - 本專案：每個事件都量，`stats()` 的「目前」＝最左邊的事件（`measure.py:134`）。

### 2.1 電壓類

**Vmax／Vmin／Vp-p（p257）**
- 手冊：Max 是「highest value in the waveform display」，Min 同理；Vp-p = Max − Min。
- 本專案：`levels()` 取 `v.max()`／`v.min()`。
- 判定：一致。差異只來自資料來源（顯示紀錄 vs 原始樣本），見 §2.0。

**Top／Base／Amplitude（p258–259）**
- 手冊：Top 是「the mode (most common value) of the upper part of the waveform」，眾數不明確時等於 Maximum；Base 對稱；Amplitude = Top − Base。
- 手冊未載明：
  - 「upper part」從哪裡切。
  - 直方圖的格數與格寬（ADC 碼？）。
  - 「not well defined」的判準。
  - 眾數取格中心還是格內平均。
- 本專案（`measure.py:56-74`）：
  - 在 [vmin, vmax] 之間切 256 格，上下各取 40%（向下取整，102 格）。
  - 峰值次數 < 5% 總數時退回 Max／Min。
  - 眾數取該格樣本的平均；同高的峰取內側。
  - 這套規則全部來自 Infiniium 整理（A-3），3000G 手冊沒有。
- 判定：手冊未載明（方向一致）。數值差異見特別問題 b。

**Overshoot（p259）／Preshoot（p260–261）**
- 見特別問題 d。

**Average（p261）**
- 手冊：
  - 公式 Average = Σxᵢ/n，n 是量測區間內的點數。
  - Full Screen 用所有顯示點。
  - N Cycles 用「an integral number of periods of the displayed signal」，少於 3 個邊緣顯示 "No edges"。
  - 手冊在 p276 把 Average 列為「改閾值會影響結果」的量測之一，因為 N Cycles 要靠邊緣決定區間。
- 手冊未載明：
  - N 怎麼選：是螢幕上能放下的最多整數週期，還是固定 1 個。
  - 起點在哪裡：最左邊的邊緣，還是靠近觸發點的邊緣。
  - 推測：「integral number」指能放下的最多整數週期。
- 本專案（`measure.py:108-117`）：
  - 只取**一個**週期：最左邊的完整邊緣到下一個同向邊緣的中閾值交越，右端不重複計入。
  - 沒有完整週期時，**退回整段平均**（3000G 會顯示 "No edges"）。
  - 沒有 Full Screen 選項。
- 數值例子：0/1 V、50% 方波取 2.5 個週期，本專案 Vavg＝0.500；整段平均（3000G Full Screen）＝0.600（`sim.py`）。對穩定的週期訊號，1 個週期和 N 個週期接近；遇到調幅、漂移或低頻漣波時，1 個週期的值會隨起點不同而跳動（`measure_check.py:44` 也驗證了各週期平均確實不同）。
- 判定：**不同**。

**DC RMS／AC RMS（p261–262）**
- 手冊：
  - DC RMS = √(Σxᵢ²/n)，說明文字寫「over one or more full periods」。
  - DC 與 AC 都有 Full Screen 與 N Cycles 兩種。
  - AC 的 Full Screen 標成「(Std Deviation)」，也就是顯示電壓的標準差。σ 公式用 /N（p263）。
- 本專案（`rms.py`）：
  - 只有整段：DC = √mean(v²)，AC = √mean((v−mean)²)。
  - 與 Full Screen 一致（用 /N 一致）。
  - 缺 N Cycles。
- 數值差異（解析計算）：
  - 振幅 1 的正弦取 1.3 個週期：整段 DC RMS = √(0.5 − sin(5.2π)/(8π·1.3)) ≈ 0.694；N Cycles 應為 0.7071，差 −1.8%。
  - 0/1 方波取 2.5 個週期：AC RMS 整段 = √(0.6·0.4) = 0.490；整數週期為 0.500，差 −2%。
- 判定：Full Screen 一致；N Cycles 本專案沒有。

**Ratio（p263）**
- 手冊：兩個來源 AC RMS 比值的 dB 值。手冊沒寫是 20·log 還是 10·log（手冊未載明；推測是電壓比 20·log）。
- 本專案：沒有。

**Y at X（p257）**
- 手冊：指定 X 處的值；X 必須在螢幕上；時間以觸發點為參考。內插方式手冊未載明。
- 本專案：沒有這個量測項；`cursor_readout` 取最近樣本（`analysis_api.py:119-127`）。

### 2.2 時間類

**Period／Frequency（p264–265）**
- 手冊：
  - 兩個相鄰同極性邊緣在中閾值的交越時間差。
  - 中閾值交越必須同時穿過下、上閾值（排除 runt）。
  - Frequency = 1/Period。
  - 手冊未載明：用上升還是下降緣、取哪一個週期、交越點怎麼內插。
- 本專案：
  - `edges()` 依狀態 0／1／2 做遲滯：只有從「低於下閾」走到「高於上閾」才算邊緣，runt 被濾掉，與 p264 一致。
  - 中閾值交越取第一次越過並線性內插（`edge.py:26-32`）。
  - 使用者可以選上升或下降緣。
  - 頻率是逐週期 1/週期，所以統計「平均」是 mean(1/T)，不是 1/mean(T)。jitter 1% 時兩者只差約 1e-4（推測，屬 Jensen 不等式的二階項）。
- 判定：一致；邊緣選擇見 §2.0。

**+Width／−Width（p266）**
- 手冊：上升中點到下一個下降中點；−Width 反之。
- 本專案：`widths()` 相同。
- 判定：一致。

**Duty Cycle（p267）**
- 手冊公式：+Duty = +Width/Period×100；−Duty = −Width/Period×100。
- 本專案（`edge.py:75-82`）：
  - `rising=True`：+Width/Period。
  - `rising=False`：e0 下降、e1 上升、e2 下降，算 `e2.t_mid − e1.t_mid`，也就是**仍然是 +Width**，週期改成從下降緣起算。
- 實測（`sim.py`）：25% 脈波，本專案「上升緣」＝25%、「下降緣」＝25%；3000G 的 −Duty 應為 75%。
- 使用者若以為選「下降緣 ↓」就是 −Duty，會誤讀。
- 判定：**不同**（本專案沒有 −Duty）。

**Rise／Fall Time（p267）**
- 手冊：
  - 上升時間＝下閾值交越到上閾值交越的時間差；下降時間反之。
  - 建議把 time/div 調到最快，但整個邊緣仍要在螢幕上。
  - 手冊未載明：最少點數、內插方式、取哪個邊緣。
- 本專案：同一個公式，但要求 `b − a + 1 ≥ 4`（`edge.py:58`）。
- 見特別問題 a。

**Slew Rate（p274）**
- 手冊：ΔY/ΔX，上下閾值依閾值設定，量最靠近時基參考點的邊緣；FFT 來源不可用。
- 本專案：上升斜率／下降斜率 = (hi − lo)/(t_hi − t_lo)，所有邊緣都量，也受 ≥4 點限制。
- 判定：公式一致；邊緣選擇不同。

**Burst Width（p266）、Bit Rate（p267）、Time at Edge（p268）、Delay（p268–269）、Phase（p270）、X at Max／Min Y（p271）**
- 本專案皆沒有。
- 手冊要點：
  - Time at Edge：固定用 50% 加「少量遲滯」，量值未載明；中閾值設定不影響它；Edge # 從螢幕左邊數起。
  - Delay：負值代表來源 1 的邊緣比來源 2 晚。Source 1 選 Auto 時取最靠近時基參考點的邊緣；Source 2 自動取最靠近來源 1 的那個邊緣。可指定 Upper／Middle／Lower 閾值。
  - Phase：Phase = Delay/Period(來源 1)×360。負值代表來源 1 的上升緣比來源 2 晚。
  - X at Max／Min Y：從左邊數第一次出現極值的 X。

**Counter（p266）**
- 硬體計頻器：閘時間＝水平範圍，但限制在 0.1–10 s；最低頻率 2/閘時間；用觸發比較器，所以觸發準位必須設對；不受 Zoom 影響。
- 離線無法對應，不建議模擬。

### 2.3 計數類（p272–273）
- 手冊：
  - +/−Pulse Count 只寫「a pulse count」。
  - Rising／Falling Edge Count 只寫「an edge count」，且只限類比通道。
  - 用什麼閾值、是否需要遲滯，手冊未載明。推測與 Period 同樣用三閾值濾掉 runt，Infiniium 整理寫的是中閾值兩次交越。
- 本專案：沒有，但 `edge.edges()` 的長度就是邊緣數，成本很低。

### 2.4 混合類：Area（p273）、Slew Rate（p274）
- Area：接地以上減接地以下；Full Screen／N Cycles。積分方式手冊未載明，推測是矩形或梯形加總乘以 Δt。本專案沒有。

### 2.5 FFT 量測（p274–276）
- Channel Power：FFT span 內的功率。中心頻率取 FFT 函數的設定。
- Occupied Bandwidth：包含 99%（可調）功率的頻寬。
- ACPR：主頻帶寬與間距可調，旁帶 1H–5H/1L–5L；旁帶不完整時顯示 "Incomplete"。
- THD：各諧波頻帶的功率對基頻頻帶的比值，帶寬＝基頻的 1/2，游標畫在 ±f₀/4。可手動輸入基頻，或自動取最高峰當基頻。
  - 注意：p276 第一句寫 THD 是「ratio of power in the fundamental … to the power … in the rest」，與一般定義（諧波/基頻）**方向相反**；下一句又寫「compares [harmonics] to the fundamental」。手冊自相矛盾。推測實際上是諧波/基頻。
- 手冊未載明：視窗修正、功率加總方式、單位。
- 本專案：有 FFT 頻譜與 Track RF，沒有這四種量測。

### 2.6 Measurement Thresholds（p264、276–278）
- 手冊：
  - 預設 10/50/90% of Top–Base。
  - 可選 %（下限 0–98%、中 1–99%、上 2–100%），或 Absolute。Absolute 的預設是 800 mV／1.20 V／1.50 V。
  - 中閾值被上下閾值夾住，調整時會自動推移。
  - 每個類比通道與 math 各自一組。
  - Absolute 閾值限螢幕內的值，超出波形 min/max 時量測可能無效。
  - 改閾值會影響 Average、Delay、Duty、Fall、Freq、Overshoot、Period、Phase、Preshoot、Rise、±Width（p276）。
  - Top/Base 怎麼求：只有 p258–259 的眾數定義，**沒有可選的 Top/Base 模式**（Infiniium 有 Standard／Histogram／Min-Max／Custom）。
- 本專案：
  - 只有 `THRESHOLDS` 兩組（10/50/90、20/50/80），由 `analysis_api.measure` 套到所有量測。
  - 沒有 Absolute、自訂 %、逐通道設定。
  - 20/50/80 來自 Infiniium；3000G 雖沒有這組預設，但可用自訂 % 設出來。
- 數值差異：
  - 例：TTL 訊號 0–3.3 V，若真機設 Absolute 0.8/1.2/1.5 V，Top/Base 百分比法的中點是 1.65 V。對 2.6 ns 的邊緣，中點位置差約 (1.65−1.2)/(0.8·3.3)·2.6 ns ≈ 0.44 ns。
  - 這會直接影響 Delay 與 Width；Period 不受影響，因為同向邊緣的位移會互相抵消。
- 判定：部分一致。

### 2.7 Measurement Window（p278）
- 手冊：
  - Auto Select：有 Zoom 時先在 Zoom 量，量不到就回到 Main。
  - Main、Zoom 各自只量該視窗。
  - Gated by Cursors：X1–X2 之間；有 Zoom 時用 Zoom 視窗裡的游標。
- 本專案：
  - `rangeOf()` 只有兩種：游標區間，或 null。null 代表**整個檔案**，不是目前可見的畫面。
  - 游標區間的兩端都含（`_cut` 用 left/right searchsorted）。
- 數值差異：
  - 使用者在 GUI 放大到某一段時，若沒設游標，本專案仍量整個檔案（例如 100k 個邊緣），真機只量畫面上那一段。
  - Top/Base 也改由整檔決定：檔案前段若有暫態，Top/Base 與閾值會跟著偏。
- 判定：Gated by Cursors 一致；Main/Zoom（＝可見範圍）本專案沒有。

### 2.8 Measurement Statistics（p278–280）
- 手冊：
  - 欄位：名稱、目前、平均、最小、最大、σ、次數。
  - 「Statistics are based on the total number of captured waveforms (count)」，也就是**一筆擷取貢獻一個值**。
  - σ = √(Σ(xᵢ−x̄)²/N)（p263）。
  - Relative σ：σ 除以平均。
  - Max Count：只取最近 N 次。
  - 新增量測或按 Single 時統計歸零；Increment Statistics 可以在停止狀態下平移後手動加入一筆。
  - Analyze Segments：每個區段一筆。
- 本專案（`measure.py:133-136`）：
  - 「次數」＝這一筆記錄、這個範圍內的**事件數**，例如週期數或邊緣數。
  - 「目前」＝最左邊的事件。
  - 平均、最小、最大、`np.std`（ddof=0，與 /N 一致）都在事件之間計算。
  - 多一欄「範圍」（Infiniium 才有）。
  - 沒有 Relative σ、Max Count。
- 數值差異：
  - 例：10 MHz 方波整檔有 100k 個週期。本專案的週期 σ 是**一次擷取內的逐週期 jitter**（約數十 ps 等級）。3000G 若每次擷取只量一個週期，其 σ 是**跨擷取**的變動，量級可能相近但意義不同。
  - Vmax、Vtop 等單值量測，本專案次數永遠是 1、σ = 0；真機多次擷取後 σ ≠ 0。
  - 推測：InfiniiVision 實機的 Period 在單次擷取內可能已經對多個週期取平均，手冊沒寫，**需真機比對**。

---

## 三、特別問題

### a. 手冊對上升／下降時間是否要求最少取樣點？
- **3000G 手冊沒有任何最少取樣點的規定**（p267 只有定義與「time/div 盡量快」的建議）。
- 相關的只有 p250 的通則：解析度不足時顯示 "< value" 或 "> value" 等訊息，代表結果可能不可靠。
- 「至少 4 點（1 點高於上閾、1 點低於下閾、2 點在中間）」**只出現在 Infiniium 手冊**（Infiniium 整理 Rise_Time、A-1、A-2）。Infiniium 在解析度太粗時也不是空白，而是用 `≤` 標上界（Infiniium 整理「量測『?』與無效結果」）。
- 數值上為什麼要有門檻：用本專案 `edges()` 模擬 10–90% 為 2.6 ns 的高斯邊緣、2.5 ns 取樣、相位隨機 4000 次（`sim.py`）：
  - 96%（3837 個）的邊緣只有 3 點，線性內插平均得 **3.74 ns**（範圍 2.89–4.06），高估 44%。
  - 4% 的邊緣有 4 點，得 2.90 ns，仍高估 12%。
  - 改用 16 倍 sinc 內插（`sim2.py`，週期訊號）得 2.98 ± 0.31 ns，也只能部分改善。原因是這種邊緣的頻寬已經接近 200 MHz 的 Nyquist，資料本身就欠取樣。
  - 結論：在 2.5 ns 取樣下，任何方法都無法可靠量出 2.6 ns 的邊緣。目前顯示「—」**在數值上是保守而正確的**，問題在於呈現方式。
- 跟 3000G 對齊的做法：不要只顯示「—」。可以照 p250 的 "< value" 或 Infiniium 的 `≤`，輸出上界，例如「< t(b) − t(a)」（最後一個低於下閾的點到第一個高於上閾的點之間的時間）並標示為可疑。
- 推測：真機的 sin(x)/x 內插與更高的原生取樣率（.h5 檔的 2.5 ns 可能是抽點後的匯出），會讓面板仍顯示一個數字。**需真機比對**面板上的 Rise 讀值與該檔的取樣率。

### b. Top／Base 的求法 vs `levels()`
- 3000G（p258–259）只說「上半部的眾數；眾數不明確時用 Max／Min」。沒有「40%」，沒有「5%」，也沒有格數。「upper part」較接近「上半」，但未定義。
- `levels()` 用的是 Infiniium 的 40%／5% 規則，搭配 256 格切在 [vmin, vmax]。這裡的格寬是 **Vp-p/256**，不是 ADC 碼寬。
- 數值差異：0/1 V 方波加高斯噪聲（`sim3.py`）：

  | 噪聲 σ（相對振幅） | 本專案 Top | Base | 備註 |
  |---|---|---|---|
  | 0.5%～1.5% | ≈1.000 | ≈0.000 | 正常 |
  | **2.0%** | **1.093（＝Vmax）** | **−0.089（＝Vmin）** | 峰格次數低於 5%，退回極值 |
  | 3.0% | 1.119（＝Vmax） | −0.132 | 同上 |

  - σ = 2% 時，Vamp 從約 1.00 跳到 1.18（**+18%**）。所有閾值跟著外推約 9%，Overshoot 的分母變大、分子變成 0 或負值。這是**懸崖式**的跳變。
  - 原因：格寬太細（約 0.45% 振幅）。噪聲把一個平台攤到很多格，單一格的次數 ≈ 0.5 × 0.45/(2.5·2) ≈ 4.5%，低於 5%。
  - 用 8 位元量化（格寬固定）模擬，在 σ = 2% 時 Top 也會退回，Base 沒有（受量化格點影響）。所以此問題在真機上是否發生，取決於真機直方圖的格寬（手冊未載明）。
- 正弦：本專案頂格約佔 3.98%（解析：acos(1 − 2/256)/π），低於 5%，所以 Top = Vmax。與 3000G「眾數不明確時用 Max」的方向一致，但相當接近門檻。
- 三角波：每格均勻，Top = Vmax，一致。
- **需真機比對**：用一個有噪聲的方波，比較面板 Top 與本專案 Top，可判斷真機是否也有同樣的懸崖。

### c. Vrms、Vavg 是整個螢幕還是單週期？
- 3000G **兩者都有**，由使用者選擇：
  - Average：Full Screen／N Cycles（p261）。
  - DC RMS：Full Screen／N Cycles（p261–262），說明文字寫「over one or more full periods」。
  - AC RMS：N Cycles／Full Screen (Std Deviation)（p262）。
  - N Cycles 是「整數個週期」，少於 3 個邊緣顯示 "No edges"。
- 本專案：
  - Vrms(DC)、Vrms(AC) 只有整段，相當於 Full Screen，但範圍是整個檔案或游標區間，不是畫面。
  - Vavg 只有「一個週期」，而且沒有完整週期時退回整段平均。這**既不是** Full Screen，也不完全是 N Cycles（N 固定為 1）；退回整段而不報 "No edges"，也與手冊不同。
- 差多少：見 §2.1（Vavg 2.5 週期方波 0.5 vs 0.6；RMS 非整數週期 −1.8% 到 −2%）。

### d. Overshoot／Preshoot vs `edge.shoot`
- **公式**：
  - Overshoot（p259）：上升 = (局部極大 − Top)/Amp×100，下降 = (Base − 局部極小)/Amp×100。與 `shoot(pre=False)` 一致。
  - Preshoot（p260）：手冊**文字公式與 Overshoot 一字不差**（上升 = 局部極大 − Top），但 p261 的圖把上升緣前在 Base 的下凹標為 Preshoot（Base − 局部極小），下降緣前在 Top 的凸起標為 Preshoot（局部極大 − Top）。
    - 推測：文字公式是複製 Overshoot 造成的誤植，圖才是本意。圖與 Infiniium 一致，也與 `shoot(pre=True)` 一致（`high_side = rising != pre`）。
    - 若有人照 p260 文字實作，上升緣的 Preshoot 會變成量到平台上的凸起。上升緣前的平台區沒有凸起，所以會得到負值或 0。
- **區間**：3000G 只說「follows／precedes a major edge transition」，局部極值在哪個區間找，手冊未載明。本專案用 Infiniium 的定義：
  - 過衝：遠端閾值交越到下一緣之間的平台中點。
  - 前衝：前一緣之間的平台中點到近端閾值交越。
  - 而且缺鄰緣的邊緣會被跳過。
- **邊緣選擇**：
  - 3000G 只量「最靠近觸發參考點」的那一個邊緣（p259、p260）。
  - 本專案量所有同向邊緣，「目前」＝最左邊；最左邊緣通常沒有前鄰緣，所以被跳過，實際上是第二個。
  - 平均是所有邊緣的平均，最大值是全檔最壞值。
  - 這有實際差異：有振鈴且邊緣之間振鈴不同時，真機顯示一個邊緣的值，本專案的「目前」是另一個邊緣的值。
- **噪聲偏差**：兩者都會有。1% 噪聲的乾淨方波，本專案過衝約 3.3–3.6%（`sim3.py`，等於 max(噪聲) ≈ 3.3σ）。真機若量在顯示紀錄上，點數較少，偏差會略小（推測）。
- **負值**：手冊未說要截為 0；本專案保留原值。
- **離線沒有觸發參考點**：「最靠近觸發點」可以用 t = 0 替代（`analysis_api.marker_eval` 已有「資料含 0 秒就用 0」的慣例）。

### e. Frequency／Period／Duty／Width 的邊緣與中點判定
- 手冊：
  - 都以**中閾值交越**計時（p264–267）。
  - Period／Frequency 明確要求中閾值交越「must also travel through the lower and upper threshold levels」，以排除 runt（p264、p265）。
  - Width 與 Duty 沒有重述這條，推測相同。
  - 內插方式、多次交越（噪聲在中閾值附近抖動）時取哪一次、取哪個週期，手冊都未載明。
  - Time at Edge 另用「50% 加少量遲滯」，不受中閾值設定影響（p268）。這是唯一提到遲滯的地方。
- 本專案：
  - 三閾值遲滯狀態機，等同 runt 排除，一致。
  - 中點取邊緣區段內**第一次**越過中閾值，並與前一點線性內插（`_cross`）。若噪聲在中閾值附近來回，取第一次會讓上升緣偏早、下降緣也偏早。真機的取法未知。
  - Period 只用同方向邊緣，一致。
  - Width 一致；Duty 的 −Duty 不同（§2.2）。

---

## 四、建議（依影響大小排序；不改程式，只列方向）

**應改成與 3000G 一致**
1. **Duty Cycle 補上 −Duty**（影響中高、改動小）：
   - 把「下降緣」選項改成 −Width/Period×100（p267），或另外新增 −Duty 項目。
   - 至少要把 tooltip 改清楚，避免使用者誤以為選下降緣就是 −Duty。
2. **Vavg、DC/AC RMS 提供 Full Screen／N Cycles 兩種**（影響中高）：
   - N Cycles 取整數個週期（推測取能放下的最多個）。
   - 少於 3 個邊緣時回報 "No edges"，不要靜默退回整段平均。
   - Full Screen 就是目前的 RMS 做法。
   - 這也能讓 Vavg 與 RMS 的區間語意一致，目前 Vavg 是 1 個週期、RMS 是整段，彼此不一致。
3. **上升／下降時間在點數不足時輸出上界，而不是「—」**（影響高；計算本身正確，只改呈現）：
   - 仿照 p250 的 "< value" 或 Infiniium 的 `≤`，回報「< (t[b] − t[a])」並標示可疑。
   - **不建議拿掉 4 點門檻**：`sim.py` 顯示 3 點邊緣用線性內插會高估約 44%。
4. **「目前」改取最靠近 t = 0（觸發點）的事件**（影響中；Overshoot、Preshoot、Slew Rate 有手冊依據 p259、p260、p274）：
   - 資料不含 0 時，退回範圍中心。
   - Period、Width 是否也這樣做，手冊未載明，可以一併採用以求一致（推測）。
5. **量測視窗加「可見範圍」選項**（影響中）：
   - 對應 Main/Zoom（p278）。
   - 現在「全部」＝整檔，與真機「量畫面上的資料」（p250）相差很大，Top/Base、閾值與統計次數都會不同。

**保留現狀（與手冊不矛盾，或手冊沒寫）**
6. 遲滯三閾值的邊緣判定、中閾值線性內插、Period 只用同向邊緣、Width 定義：與 p264–266 一致。
7. Preshoot 依圖（p261）而非 p260 文字式：保留。建議在程式註解或文件註明「3000G 手冊 p260 文字式疑似誤植」。
8. 統計 σ 用 /N：與 p263 一致。
9. 「範圍」欄：多出來的欄位無害，保留。
10. 「事件內統計」的語意：離線只有一筆記錄，以事件為單位是合理的替代。但 UI 或匯出應註明「次數＝範圍內事件數（非擷取次數）」，避免與真機面板的 count 混淆。

**需真機比對（建議用 3000G 或同系列實機，對同一波形同時記錄面板值與匯出檔）**
11. **Top／Base 在噪聲約 2% 時的跳變**（影響中，`sim3.py`）：
    - 比對面板 Top 與本專案 Top。
    - 若真機不跳，考慮把直方圖格寬改為固定碼寬或滿刻度/256，或放寬 5% 門檻。目前規則只有 Infiniium 有，3000G 手冊無據。
12. **10 MHz 方波的 Rise Time**：比對面板讀值與 .h5 的取樣率，確認面板是否用更高取樣率或 sin(x)/x，以及是否顯示「<」。
13. **Period／Frequency 在單次擷取內是量一個週期還是取平均**（手冊未載明）：決定「目前」與「平均」應怎麼對齊面板。
14. **Absolute 閾值與逐通道閾值**（p277）：使用者若在真機上用 Absolute，離線結果的 Width／Delay 會差數百 ps（§2.6 的例子約 0.44 ns）。是否要支援，視實際使用情況決定。

**低優先（本專案沒有，需要時再加）**
15. X at Max／Min Y、Edge／Pulse Count、Burst Width、Bit Rate、Area：都能從現有 `levels()`／`edges()` 用幾行算出。
16. Delay／Phase／Ratio（需要雙來源）、FFT 四種量測（Channel Power、OBW、ACPR、THD）。其中 THD 的定義方向手冊自相矛盾（p276），實作前需確認。
17. Counter：離線做不到，不做。
