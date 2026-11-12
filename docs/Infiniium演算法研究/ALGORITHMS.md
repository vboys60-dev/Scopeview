# Infiniium 量測演算法（官方說明檔 + MATLAB 編譯庫結構）

> 實作用規格見 `IMPLEMENTATION_SPEC.md`（含偽程式碼、邊界、N1–N13 裁決、驗證計畫）。本檔是研究依據，兩者衝突時以規格的裁決為準，並回頭核對本檔。

來源與可信度：
- 【官方】Keysight Infiniium Offline Analysis Help（`claude-cowork/示波器截圖/N8900A/Keysight Infiniium Offline Oscilloscope Analysis Software Help.tar.gz`，1,129 頁 htm）。這是廠商對演算法的敘述，不是我從程式碼還原的。
- 【結構】`claude-cowork/示波器截圖/N8900A/6_MATLAB_Compiled/*.ctf` 的檔名清單。`.m` 內容已加密（檔頭 `V2MCC`），**只能看到函式／類別分工，看不到公式**。
- 【推論】從檔名推測，未驗證。

## 1. 基本波形量測流程【官方】
1. **資料收集**：通道用擷取記錄，波形記憶體用儲存資料，函數先計算完才量測。
2. **直方圖**：把記錄的電壓分佈建成直方圖，以 8 bit 資料建立（平均模式下不是全解析度）。
3. **Vmin / Vmax**：由直方圖取絕對最小／最大，同時記錄是否削波。→ Vmin、Vmax、Vp-p、Tmin、Tmax、Tvolt。
4. **Top / Base**（`Calculating_Top_and_Base`）：
   - 只掃描直方圖**上 40%** 找 Top、**下 40%** 找 Base，**中間 20% 忽略**，避免把基線誤當 Top／Base。
   - 取該區間內**出現次數最多**的電壓。
   - 該次數 **< 總數 5%** 時，Top 退回絕對最大值、Base 退回絕對最小值（不規則或緩升波形）。
   - 好處：三角波不會讓 Top／Base 亂跳，低占空比訊號也找得到。
   - Vamp = Vtop − Vbase。
5. **閾值**（`Calculating_Thresholds`）：由 Top／Base 算出 upper／middle／lower，可為 IEEE 10/50/90 %，或自訂百分比／電壓。
6. **邊緣判定**（`Determining_Rising_and_Falling_Edges`）：
   - 上升沿必須依序通過 lower、middle、upper 三個閾值；下降沿相反。三個都完成才算邊緣，不完整的轉換與突波會被忽略。
   - **資料點不剛好在閾值上時，在兩點之間內插**，把穿越位置記入邊緣陣列。（這回答了先前 `dspi_edge` 反編譯看不到內插的疑問：內插存在於文件，但 `dspi_edge` 輸出的是否就是內插結果，仍未驗證。）
   - 邊緣的點範圍：從「越過 lower 前的最後一點」到「越過 upper 的第一點」，這樣量到最快的上升／下降時間。
   - 點數不足時，Rise time 不量測或標為可疑。`Rise_Time.htm` 明寫邊緣至少需要 4 個取樣點。
7. **時間定義**（`Timing_Definitions` 寫「第一個邊緣」；但 `Rise_Time.htm`／`Period.htm` 寫非 zoom 時量所有邊緣、起點為參考點最近的邊緣，並有 Measure All Edges 選項，兩頁說法不同）：
   - Rise = t(upper) − t(lower)；Fall = t(lower) − t(upper)
   - Period = 同方向相鄰兩邊緣在 **middle** 閾值的時間差；Frequency = 1/Period
   - +Width／−Width 用 middle 閾值；Duty = +Width/Period × 100
   - Δtime：可選閾值（lower/middle/upper）、邊緣極性、邊緣編號，量源 1 到源 2 的時間。
8. **電壓定義**（`Making_Voltage_Measurements`）：Vp-p = Vmax − Vmin；Vamp = Vtop − Vbase；Vavg 在 `Making_Voltage_Measurements` 寫「第一個週期」，但 `Average_Voltage.htm`／`RMS_Voltage.htm` 寫 Vavg、Vrms 都可選**單一週期或整個畫面**。Overshoot：上升緣 = 局部最大 − Top，下降緣 = Base − 局部最小。**Preshoot（以專頁 `Preshoot.htm` 為準）**：上升緣 = 100·(Base − 局部最小)/(Top − Base)，下降緣 = 100·(局部最大 − Top)/(Top − Base)。`Making_Voltage_Measurements` 以「第一個邊緣」分支（可解讀為量下一個邊緣之前的前衝），專頁以「被量的邊緣」分支，字面不同但未必矛盾；實作以專頁與公式圖 image105/107 為準（總覽頁缺 100/(Top−Base) 正規化）。Overshoot 亦同，見 image109/111。

## 2. 眼圖量測【官方】
- 資料來源是 **Color Grade 資料庫**（開啟 Real-Time Eye 時建立）。
- **Eye height**：在 Eye Window（預設 40%–60%，即中間 20%）內建垂直直方圖，找 Vtop、Vbase 與兩者標準差。
  - *Use Measured Data*：量窗內實測，回報**最小**眼高。
  - *Extrapolate Using Standard Deviation*：眼高 = (Vtop − 3σtop) − (Vbase + 3σbase)（公式圖 image210）。
  - 位置：*Find Eye Opening*（窗內）或 *At Recovered Clock Location*（可設 UI 百分比寬度，0 = 只取時脈點）。
- **Eye width**：在 Vtop／Vbase 之間建水平直方圖，取交叉點的平均時間與 σ。
  - 演算法同樣有 *Use Measured Data*（最小寬度）與 *Extrapolate*：眼寬 = (t₂ − 3σ₂) − (t₁ + 3σ₁)（image211；Eye_Width 頁文字誤寫成 eye height，是筆誤）。
  - 閾值：*Automatic*（交叉點最寬處）或 *Use Measurement Threshold*。單位 s 或 UI（無 clock recovery 時 UI 會報錯）。
- **眼圖 DCD**（`Eye_Duty_Cycle_Distortion.htm`）：中閾值上下降緣與上升緣**中位數**的時間差；百分比公式的分母用交叉點平均時間。與 §3 EZJIT Plus 的 DCD（兩直方圖**平均**之差）是不同的量測。
- **Eye jitter**：水平直方圖的交叉點標準差 σcrossing；RMS = 1σ，p-p = **6σ**（image212/213）。Q-factor = (Vtop−Vbase)/(σtop+σbase)；Crossing% = 100·(Vcross−Vbase)/(Vtop−Vbase)。
- **Eye Contour**（`Eye_Contour_generation`）：
  1. 找 Vcenter（累積眼圖最寬處）；量 Vmintop、Vmaxbot；量 Vcenter ±5 mV 的平均斜率。
  2. 在 Vcenter 量 Rj(rms-meas)，在 CK 交叉點量 Rn(rms-meas)，扣掉示波器自身的 Rj／Rn(rms-scope)。
  3. 用斜率把雜訊造成的 Rj 剝離，得到真 Rj。
  4. 對每個 BER：**Tj = Dj + ½·Qber·Rj(rms)**；Dj 在 Vpoint ±5 mV 區域用 dual-Dirac 量測。
  5. 邊緣電壓到 Vmintop／Vmaxbot 後改為垂直方向：**Tn = Dn + ½·Qber·Rn(rms)**，Dn 為 dual-Dirac 的確定性干擾。
  6. 連接各 BER 點成輪廓。

## 3. 抖動【官方】
- **TIE**：先做 clock recovery，每個資料間隔相對於還原時脈量測；非縮放模式量全部週期，縮放模式只量窗內。
- **Clock recovery（Constant Frequency）**：
  - Fully Automatic：找最窄脈衝並**假設它是孤立的 1 位元**，再據此估各脈衝的位元數（ISI 大時最窄脈衝會讓速率偏高）。
  - Semi-Automatic：使用者給名義速率當種子，只掃一遍。
  - Manual：直接用給定速率。
  - 自動／半自動時，實際速率與時脈相位使**平均 TIE = 0**。
- **TIE 濾波**：Highpass／Bandpass／Lowpass，邊緣形狀有 Rectangular（磚牆）、20/40/60 dB/decade、First／Second Order（可設阻尼，0.707 為 Butterworth）。
- **RJ/PJ 分離（EZJIT Plus）**：
  - **頻譜法**：抖動頻譜中窄頻尖峰 = PJ，剩下基線 = RJ。RJ Bandwidth：*Wide (white)* 假設基線平坦、寬頻凸起算 PJ；*Narrow (pink)*（預設）寬頻凸起算 RJ，使用**非線性判決閾值**跟隨非平坦基線。
  - **Tail Fit**：有串擾或 BUJ 時更準；「Spectral & Tail Fit」可選回報哪一個。
  - 可疑標記：完整資料圖樣少於 **128** 個時顯示 `?`；更少則顯示 "too few points"。
- **Dual-Dirac**：兩個 σ = RJrms 的高斯相距 DJδδ。**TJ(pp) = DJδδ + Q·RJrms**，Q 由 BER 決定。BER 等級 J2 / J4 / J5 / J9 對應 2.5e-3 / 2.5e-5 / 2.5e-6 / 2.5e-10。
- **DDJ**：有測試圖樣時，把 TIE 依圖樣長度切段平均得到圖樣長的 DDJ 向量；UTJ 是從 TIE 扣掉 DDJ 後再建直方圖。無圖樣時也能算，但「複雜得多」（官方未說明方法）。
- **DCD** = 上升緣位置直方圖平均與下降緣平均之差的絕對值。ISIpp = 上升緣或下降緣相關抖動的 p-p（取較大者）。DDPWS = T − min(所有脈衝寬度)。F/2 = 偶數位元與奇數位元邊緣位置差的絕對值。
- **JNU**：總抖動直方圖扣掉兩側各 10^-N/2 尾巴後的寬度；JHNU 是其中水平分量，用每個邊緣的 dual-Dirac 結果與斜率 1/|SR| 線性模型分離水平和垂直成分。
- **Noise**：同樣用頻譜法分離 RN 與 PI，預設 *wide (white)*。

## 4. PAM【官方】
- PAM 訊號的閾值對每個波形獨立設定；*Auto: 50% of levels* 取各 level 的 50% 位置；*Auto set* 以垂直直方圖決定閾值、遲滯與 level。Rise/Fall 用 10/90 或 20/80 **of levels**。
- **σn**：衡量各符號 level 的不相關 RMS 振幅雜訊（不含 ISI 與抖動）。PRBS13Q 方法：找 ≥6 個連續相同符號，在第 3 個 UI 中心取電壓，取各組變異數的標準差再平均。另有 PCIe、ASA、MPHY6、USB4 Gen4 等標準版本。

## 5. MATLAB 編譯庫結構【結構／推論】
共 40 多個庫，`.m` 加密。可見的分工：
| 庫 | 內容（檔名推得） |
|---|---|
| **EZJitMeasure**（279 個 .m） | `+decimation`（37，BufferedArray、頻譜 RJ 的白/粉紅降頻、FFT 大小選擇）、`+tailfit`（61，Histogram 平滑與尾端偵測、Classification 單/雙/三高斯擬合、Deconvolution 多尺度區塊比對估 DJpp、Tailfit 的 nlinfit + walkdown + robust sigma）、`+solver`（25，LinearSystem/Aggressor 矩陣，用於 ISI 濾波與串擾的 PI/RN）、`+data`（114）、`+control`（21）；頂層 `Periodic/`、`Random/`、`Tailfitting/`、`DFE/` 驅動。 |
| **EyeContour**（9） | `EyeContour`、`JitterFindContour`、`NoiseContour`、`ChiSqd`、`GetJitter` |
| **CalcPN**（17） | 相位雜訊：`FrequencyFinder`、`LeastSquaresFFT`、`SSCSpurs`（移除 SSC 雜散）、`CalcLogFreqScale`、`MeasureSkew` |
| **EffBits**（12） | 有效位元：`FFT_Real`、`FFT_Window`、`InterpT`、`IFFT_Real`（正弦擬合或 FFT 法未確認） |
| **Denoise\***（JNU 37、POJ 42、TJpp 37、Wfm 71） | 降低示波器自身雜訊／抖動的校正流程 |
| **CPhyThreshold**（4） | `findedge`、`filtercrossings` |
| **FindPhase、Find3dBPoint、DspUtils、TrainFFE、FilterTIEPCIE** | 各 1–3 個檔 |
| **PulseFitVector / PulseFitTapsDFE**（34/44）、**CrosstalkDriver**（189） | 均衡／DFE 脈衝擬合、串擾分析 |

## 6. 仍未得到
- 加密 `.m` 內的**實際公式與參數**（例如 Tail Fit 的起點判定、頻譜法的非線性閾值細節、EffBits 方法）。
- **OneSrcEval、TwoSrcEval**：不在 `6_MATLAB_Compiled/`，應是基本波形量測的主體，可能是非 MATLAB 的 C/C++。
- **InfiniiScan** 的官方說明：離線版 Help 沒有對應頁面（檔名搜尋 InfiniiScan／Zone／Non-monotonic 皆無，只有 `Runt_Trigger.htm`、`Serial_Trigger_Software-Based.htm`）。
- `dspi_edge` 是否就是文件所述的內插邊緣偵測（未驗證）。

## 7. Top/Base 直方圖範圍的敏感度實驗（2026-11-12）
官方 Help 只說「直方圖以 8 bit 資料建立」「量測直方圖取自顯示、資料量化到顯示解析度」，**沒有寫垂直範圍與格數**。因此用現行 `levels()` 邏輯在記憶體內比較三種假設（腳本 scratchpad `verify/hist_sens.py`）：現行（資料 min–max 分 256 格）、範圍放寬為 2 倍、先量化成 8 bit：
- **乾淨方波／PWM（01、07、08、10、12、15）**：三種假設的 Top/Base 幾乎相同，5% 回退不觸發。
- **含雜訊 PWM（06，σ≈100 mV、占空比 25.5%）**：Top 三種都回退（2.367 V）；**Base 在 min–max 回退為 −0.388 V，範圍 2 倍時找到 −0.012 V（真值 0）**。原因：格寬決定單格占比，5% 門檻是「單格次數」，格越寬越容易達標。
- **正弦（02、03）**：min–max 回退到極值（±5/−1），2 倍範圍則取到 4.984／−0.984（取峰值格）。
- **三角波（04）**：三種都回退，符合官方「三角波用 Min/Max」。
- 結論：**乾淨方波不受影響；有雜訊或無平台的波形，Top/Base 對直方圖範圍與格寬高度敏感，需實機（Infiniium）資料才能定案**。5% 門檻以「單格」或「峰區合計」計，官方也未明確（原文：occurrence count less than five percent of the total）。

## 8. 官方 Help 跨頁矛盾與缺漏（Codex 初掃 + Opus 複審，2026-11-12）
可信度原則：專頁 > 總覽頁；有公式圖 > 純文字（圖已實際打開確認）。涵蓋範圍：基本波形專頁約 30 頁、眼圖約 13 頁、抖動約 20 頁；**未核對**：Measurement_Analysis_EZJIT、JHrms_Derivation、PAM_Jitter_*、PAM_PRBS13Q、各 PLL 規格頁、DFE/FFE/CTLE、Mask 相關、Burst／Edge_Time／N-Period 等。「未發現」只代表已核對頁面中沒有。

### 高
- **N1 邊緣選取**：專頁（Rise/Fall/Period/Frequency/Width/Duty）寫「非 zoom 時量**所有**邊緣（含視窗外）」；`dlg_MeasurementSetup` 寫 Measure All Edges **關閉**時統計只算單一邊緣（時基/觸發參考最近者，或畫面左起第一個），其他邊緣忽略；開啟時才搜尋整筆擷取。以設定頁為準：實作兩種模式。
- **N2 Eye Contour 公式圖與文字相反**：文字說 Rj 在 Vcenter 應「加回」等於 Rj(rms-clean)；圖 eqn_onlyRj／eqn_Rj_rms 用 Rj 而非 Rn、符號為減號；斜率區間文字 ±5 mV、圖 ±10 mV；且「Rn/Rj(rms-scope) 設為 0」使扣除步驟無作用。建議採文字：onlyRj = √(Rjc² − (Rnc/SR)²)，各點 Rj = √(onlyRj² + (Rnc/SR(Vpoint))²)。

### 中
- **N3 ISI／DDJ 階層**：Jitter_Basics 寫「ISI 即 DDJ」；EZJIT Plus 頁為 DJ = DDJ(DCD+ISI) + BUJ(PJ+ABUJ)。採後者；DDJpp ≠ ISIpp。
- **N4 128 patterns**：同頁既當 `?` 門檻又當 "too few points" 門檻。`RJ___DJ_Record_Length_Requirements`：too few points < 約 30,800 UI；DDJ/DCD/ISI 至少 2 個 pattern；Periodic 的 RJ/PJ 需 2048 轉換（否則 "acquisition skipped"）；累計 154,000 轉換才出結果；Jitter_Graphs：需 1024 個完整 pattern 才用 periodic，否則 arbitrary。128 只用於 `?` 警示。
- **N5 Jitter ISI Filter**：Jitter_Graphs 說需 Periodic；Pattern_Length_Controls 說屬 Arbitrary 模式。以後者為準。
- **N6 BER**：三個對話框只列 J2/J4/J5/J9（2.5e-3/-5/-6/-10）；Noise_Tab 說可設數值 BER，預設 1E-12，範圍 1E-6–1E-18。**全套文字沒有 Q↔BER 數值表**。
- **N7 Q 係數**：RJ/DJ 頁 TJ = DJδδ + Q·RJ；Eye Contour 頁 Tj = Dj + ½Qber·Rj。兩頁都沒定義 Q 單側或雙側（若 Q₁(1e-12)≈7.03，則 TJ = DJδδ + 2Q₁·RJ）。
- **N8 Vavg 範圍**：總覽「第一週期」；專頁可選單週期或整個畫面。
- **N9 量測直方圖解析度**：Building_a_Histogram「8 bit」；Building_a_Measurement_Histogram「取自顯示、量化到顯示解析度」。直接影響 §7 的 Top/Base 敏感度，需實機資料。
- **PAM Eye Opening Probability**：同頁 VEC 段寫預設 10⁻⁵，控制項段寫 1E-02，原文沒說明情境（Opus 傾向視為實質衝突）。

### 低
- N10 Extinction Ratio：`?` 條件 > 2 °C，重做 dark cal 條件 ±1 °C。N11 color grade 計數器「53-bit」與最大計數 2,097,151（= 2²¹−1）不符。N12 Rise/Fall 分頁沒有 middle 閾值，但邊緣判定需通過三個閾值（推測用 General 分頁的 mid）。
- Histogram p-p「欄 vs 列」只是漏寫（水平用欄、垂直用列），非矛盾，依 Histogram_Results。
- Calculating_Top_and_Base 同頁「top 40 percent」vs「top half」：圖 fig05 與 4 個專頁都標 40%，**採 40%**。
- PAM 眼高眼寬前文只寫 zero hits，後文可選機率（At Probability 時不外插）：前文漏寫條件。
- Eye DCD 中間閾值文字寫 50%，公式圖變數也寫 50% point；使用者改 mid 時文字與公式不一致。

### 兩種 DCD（不同量測）
EZJIT Plus DCD：上升緣與下降緣位置直方圖**平均**之差；眼圖 DCD：中閾值上**中位數**之差（百分比公式分母用平均交叉時間）。

### 預設值（已核對）
眼窗 40%–60%；Start Measurement After = 1；一般閾值 10/50/90；Top/Base = Standard（資訊不足退 Min/Max）；RJ Bandwidth = narrow(pink)；**RN Bandwidth = wide(white)**；Clock recovery 一般 = Constant Frequency／Fully Automatic，分析精靈 typically 2nd Order PLL（Loop BW divisor 1667、damping 1.0）；PLL settling = 5 time constants；PAM：Receiver Sample Timing = Based on Center Eye、Eye Center Location = Maximum Eye Width、Time of Level = Eye Center、Eye Level Width = 10% symbol period；Jitter/Noise BER = 1E-12；TIE Filter：**官方未載預設**。
