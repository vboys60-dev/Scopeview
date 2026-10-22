# Keysight Infiniium Offline 量測功能與算法（依 HTML 說明手冊整理）

- 來源：`N8900A/Keysight Infiniium Offline Oscilloscope Analysis Software Help/contents/`（檔名即主題）
- 欄位：名稱｜分類｜定義／公式｜前提或限制｜來源檔名（皆為 `.htm`，省略副檔名以外的路徑前綴）
- 公式來源：手冊中多數公式以 GIF／JPG／PNG 圖片呈現（位於 contents/images/），已逐一以影像讀取並轉寫；轉寫結果註明「（圖）」。
- 已複查（2026-10-22）：Phase、Vrms、Overshoot、Preshoot 等公式圖已逐張核對；錯誤與補充見文末「十、修訂紀錄」。
- 「手冊未載明」表示手冊文字與公式圖都沒有寫出，不做推測。
- 手冊為 Offline 版說明，部分選項（如 PAM、EZJIT、Optical）依授權而定。

---

## 一、時間量測（含混合時間／電壓）

| 名稱 | 分類 | 定義／公式 | 前提或限制 | 來源檔名 |
|---|---|---|---|---|
| Rise Time | 時間 | 上閾值時刻 − 下閾值時刻（作用於上升邊緣；參見算法細節 A-1、A-2） | 邊緣需通過下、中、上三閾值；至少 4 個取樣點（1 個高於上閾、1 個低於下閾、2 個介於其間）；可用 Measurement Thresholds 設定閾值 | Rise_Time |
| Fall Time | 時間 | 下閾值時刻 − 上閾值時刻（作用於下降邊緣） | 同 Rise Time；「手冊建議用較快掃速展開邊緣以提高精度」 | Fall_Time |
| Period | 時間（時脈） | 相同極性相鄰兩邊緣的「中閾值交越點」之間的時間差 | 至少要顯示一個完整週期且含兩個同極性邊緣；Measure All Edges 開啟時須選 Rising 或 Falling | Period |
| Frequency | 時間（時脈） | Frequency = 1 / Period（Period 定義同上） | 同 Period | Frequency |
| Positive Pulse Width (+ Width) | 時間 | 第一個上升邊緣中閾值 → 下一個下降邊緣中閾值（即 +width）；另見 A-5 的 Timing Definitions 分支式 | 須顯示完整脈波，兩邊緣都需穿越三個閾值 | Positive_Width；Timing_Definitions |
| Negative Pulse Width (− Width) | 時間 | 第一個下降邊緣中閾值 → 下一個上升邊緣中閾值（即 −width）；分支式見 A-5 | 同 +Width；另建議時基讓脈波佔螢幕約 80%，且基準（base/top）約佔 20% 螢幕 | Negative_Pulse_Width |
| Duty Cycle | 時間（時脈） | Duty Cycle = (+width / Period) × 100，即脈波高於中閾值的平均時間佔週期百分比 | 依賴 +width 與 Period；同樣需完整脈波；手冊建議時基最佳化 | Duty_Cycle |
| Duty Cycle Adjustment | 時間（DDR5） | DDR5 DQS 四段：I 相＝第一上升→第一下降；Q 相＝第一下降→第二上升；I′ 相＝第二上升→第二下降；Q′ 相＝第二下降→下一上升 | 以 Edge-Edge 修改版實作；設計於 Measure All Edges 單次擷取上累積統計 | Duty_Cycle_Adjustment |
| Delta Time (Δtime) | 時間 | 由「第一來源」指定邊緣到「第二來源」指定邊緣的時間差；邊緣由 編號(1–65534)、斜率（Rising／Falling／First on display）、閾值（Lower／Middle／Upper）定義 | 編號自視窗左側開始計數而非觸發點；指定邊緣未顯示時出現 "edge not found" | Delta_Time；Timing_Definitions |
| Edge-Edge | 時間 | 與 Delta Time 類似，但可用於量測趨勢（trend） | 需 Measure All Edges（自動開啟且不可關閉） | Edge-Edge |
| Edge Time | 時間 | 邊緣的時間位置 | Measure All Edges 開啟時需選 Rising／Falling／Both；關閉時量測時基參考點最近邊緣 | Edge_Time |
| Edge to All Edges | 時間 | 在每 N 個脈波為一組的所有組中，量測指定（Rising／Falling／Both）邊緣之間的時間；末端不足 N 的組也量測 | 需 Measure All Edges 與 Analyze All Data（自動開啟，不可關閉）；適合搭配直方圖 | Edge_to_All_Edges |
| High Time | 時間 | 訊號高於 V Upper 的時間 | 需 Measure All Edges（自動開啟）；「Current」結果與追蹤標記取自最接近螢幕水平中心的一次 | High_Time |
| Low Time | 時間 | 訊號低於 V Lower 的時間 | 同 High Time | Low_Time |
| Time >,< (Outside) Level | 時間 | 訊號高於 V Upper 或低於 V Lower 的時間（依閾值設定） | 需 Measure All Edges；所有發生處皆量測 | Time_Outside_Level |
| T Max | 時間 | 螢幕上最大電壓第一次出現的時間 | 位置無關，使用整個螢幕 | T_Max |
| T Min | 時間 | 螢幕上最小電壓第一次出現的時間 | 位置無關，使用整個螢幕 | T_Min |
| Pulse Count (+ and −) | 時間 | 正脈波數 / 負脈波數；脈波定義為訊號兩次穿越中閾值（正脈波：上升後下降；負脈波：下降後上升） | 需 Measure All Edges（自動開啟） | Pulse_Counting_Measurements |
| N-Period | 時間（時脈） | 連續 N 個週期的時間span；每次向右移動一個週期重新量測 | 需 Measure All Edges（自動開啟） | N-Period |
| Phase | 時間（時脈） | Phase（度）= 360° × Time Between Edges / Period of Source 1（圖） | 量測「第一組最左邊的兩個同向邊緣」的中閾值交越；至少兩個週期與兩個上升邊緣；需 Measure All Edges；亦可以時間（秒）表示 | Phase（公式圖 image89） |
| Burst Interval | 時間 | 兩次「穿越上或下閾值」的 burst 活動之間的閒置區（idle region）；idle time 指定被視為一個 interval 所需的最小閒置時間 | 手冊僅此一段文字，無公式與圖；與 Burst Width 搭配 | Burst_Interval |
| Burst Period | 時間 | 第一個 burst 起點至下一個 burst 起點之間的時間 | 可指定 idle time 以確保兩 burst 最小間距 | Burst_Period |
| Burst Width | 時間 | 第一個穿越下或上閾值的邊緣 → 最後一個穿越閾值的邊緣之間的時間 | burst 需前後各有至少 idle time 的「不超過上下閾值」區段才被判定 | Burst_Width |
| Hold Time | 時間（資料） | 時脈來源中閾值 → 資料來源中閾值的時間 | 同樣依 Measure All Edges（自動開啟） | Hold_Time |
| Setup Time | 時間（資料） | 資料來源中閾值 → 時脈來源中閾值的時間 | 同上 | Setup_Time |
| Slew Rate | 時間／電壓（混合） | Slew Rate = ΔV / ΔT；ΔV = 上閾值電壓 − 下閾值電壓；ΔT = 上閾值時刻 − 下閾值時刻（圖：ΔV 與 ΔT 定義） | 至少 4 個取樣點；Measure All Edges 開啟時選 Rising／Falling／Both | Slew_Rate（圖 image113） |
| Area | 時間／電壓（混合） | 波形（或選定的一個週期）與波形接地（waveform ground）之間的面積；公式與積分方式手冊未載明（已複查 Area.htm、Measurements_Mixed.htm，皆無公式圖） | 可選單一週期或整個螢幕；可用 Subtract 運算子先去除偏移；均勻次取樣 | Area |

---

## 二、電壓量測

| 名稱 | 分類 | 定義／公式 | 前提或限制 | 來源檔名 |
|---|---|---|---|---|
| Vmax (V max) | 電壓 | 螢幕上的絕對最大電壓（由量測直方圖／資料記錄決定） | 位置無關，使用整個螢幕；Color Grade 來源精度較低 | Maximum_Voltage；Calculating_Min_and_Max |
| Vmin (V min) | 電壓 | 螢幕上的絕對最小電壓 | 同 Vmax | Minimum_Voltage；Calculating_Min_and_Max |
| Vp-p (Peak-to-Peak Voltage) | 電壓 | Vp-p = Vmax − Vmin | 位置無關 | Peak-to-Peak_Voltage |
| Vtop (Top Voltage) | 電壓 | 量測直方圖上半部（最高 40%）的峰值；演算法依波形型態在「Vmax」與「直方圖峰值」間選擇 | 位置無關；方形波取直方圖峰、三角波取 Vmax（判斷準則細節見 A-3） | Top_Voltage |
| Vbase (Base Voltage) | 電壓 | 量測直方圖下半部（最低 40%）的峰值；同 Vtop 的選擇邏輯 | 位置無關 | Base_Voltage |
| Vamp (Amplitude, V amptd) | 電壓 | Vamp = Vtop − Vbase（手冊逐字載明；Vtop＝統計最高電平，Vbase＝統計最低電平） | 受閾值（Top/Base 定義）設定影響；Amplitude.htm 本身僅「波形顯示的振幅」＋圖（image95：Vamp 標於 Top 與 Base 之間） | Making_Voltage_Measurements；Calculating_Top_and_Base；Amplitude |
| Vavg (Average Voltage) | 電壓 | 波形資料的平均電壓；Making_Voltage_Measurements 寫「Vavg = average voltage of the first cycle of the signal」；數學式手冊未載明（無公式圖） | 可選單一週期（自最近邊緣或觸發參考點起算）或整個螢幕；採「均勻次取樣」以加速 | Average_Voltage；Making_Voltage_Measurements |
| V RMS | 電壓 | DC：DCVrms = √( Σᵢ₌₁ⁿ v(i)² / n )（圖）；AC：ACVrms = √( Σᵢ₌₁ⁿ [v(i) − Vavg]² / n )（圖）；已核對 image100、image101 無誤 | n＝螢幕上的取樣點數（非記憶體深度）；可選單一週期或整個螢幕；可選單位 Volts 或 dBm；均勻次取樣 | RMS_Voltage（公式圖 image100、image101） |
| Overshoot | 電壓（百分比） | 上升邊緣：Overshoot = 100 × (local maximum − top) / (top − base)（圖）；下降邊緣：Overshoot = 100 × (base − local minimum) / (top − base)（圖） | 公式圖 image109、image111 已核對無誤；Making_Voltage_Measurements 另有未乘 100／(top−base) 的簡式：首邊緣為上升 → overshoot = local max − top，否則 base − local min。過衝區間：上升邊緣左界＝上升邊緣穿越上閾值處、右界＝頂部中心點；下降邊緣左界＝穿越下閾值處、右界＝底部中心點；依 Measure All Edges 設定上升／下降 | Overshoot |
| Preshoot | 電壓（百分比） | 上升邊緣：Preshoot = 100 × (base − local minimum) / (top − base)（圖）；下降邊緣：Preshoot = 100 × (local maximum − top) / (top − base)（圖） | 公式圖 image105、image107 已核對無誤（Making_Voltage_Measurements 簡式：首邊緣下降 → base − local min，否則 local max − top）。區間：上升邊緣左界＝底部中心點、右界＝穿越下閾值處；下降邊緣左界＝頂部中心點、右界＝穿越上閾值處 | Preshoot |
| Undershoot | 電壓（百分比） | 正脈波：Undershoot(%) = (Top − localMinimum) / (Top − Base)，若 localMinimum < Top；否則 0。負脈波：Undershoot(%) = (localMaximum − Base) / (Top − Base)，若 localMaximum > Base；否則 0（圖 eqn_Undershoot_Positive_Pulse.jpg、eqn_Undershoot_Negative_Pulse.jpg；圖中式子無 ×100，單位標示為 %，是否已乘 100：待確認）。localMinimum 取於上升邊緣遠端（distal，上）與下降邊緣遠端（上）之間；localMaximum 取於下降邊緣近端（mesial，下）與上升邊緣近端（下）之間 | 只有在波形已達 ≥Top（正脈波）或 ≤Base（負脈波）後才量測；需至少兩個邊緣；多個時取最大幅度；以脈波極性而非單一邊緣量測 | Undershoot（圖 eqn_Undershoot_*.jpg） |
| Vovershoot | 電壓 | 同 Overshoot 的定義，但回傳 overshoot 的「局部電壓」而非百分比 | 同 Overshoot | Vovershoot |
| Vpreshoot | 電壓 | 同 Preshoot 的定義，但回傳 preshoot 的「局部電壓」而非百分比 | 同 Preshoot | Vpreshoot |
| Vundershoot | 電壓 | 同 Undershoot 的定義，但回傳 undershoot 的 localMinimum 或 localMaximum 電壓值 | 同 Undershoot | Vundershoot |
| Pulse Top | 電壓 | 正脈波在「脈波窗」內資料的平均值 | 脈波窗＝以中閾值量測的脈寬之中央 X%（如 50% 不含前後各 25%；100% 為整個脈波）；均勻次取樣 | Pulse_Top |
| Pulse Base | 電壓 | 負脈波在「脈波窗」內資料的平均值 | 同 Pulse Top | Pulse_Base |
| Pulse Amplitude | 電壓 | 脈波前後兩段脈波的電平差；脈波邊緣以中閾值判定；平均區間由 Pulse Width（%）決定 | 追蹤時 marker 圈出被比較的兩個脈波；均勻次取樣；具體正負號與符號慣例：手冊未載明 | Pulse_Amplitude |
| Crossing (Crossing Point) | 電壓 | 兩個波形交越（相交）時的電壓 | 取最接近螢幕中央的邊緣；公式：手冊未載明（已複查 Crossing_Point_Measurement.htm 與 meas_V_Crossing.png，後者僅為範例畫面截圖，結果 Crossing(2-4)） | Crossing_Point_Measurement |
| V Upper / V Middle / V Lower | 電壓（閾值） | 螢幕上上、中、下閾值的電壓值（依 Measurement Thresholds 設定） | 位置無關 | V_Upper；V_Middle；V_Lower |
| V Time (V time) | 電壓 | 指定時刻的電壓；時間以觸發事件為參考，且必須在螢幕上 | 若來源為 FFT，則改為量測指定頻率的振幅 | V_Time |
| Peak-Peak Contrast | 電壓（影像） | (Lmax − Lmin) / (Lmax + Lmin)（亦稱 Michelson contrast） | 以 Color Grade 資料庫量測；位置無關 | Peak-to-Peak_Contrast |

---

## 三、Marker／游標（dlg_MarkerSetup、GS_Markers、Markers、Marker_Results）

| 名稱 | 分類 | 定義／公式 | 前提或限制 | 來源檔名 |
|---|---|---|---|---|
| Manual (X only) | Marker 模式 | 一對可自由拖曳的水平 marker（X 方向） | 解析度＝顯示解析度；不追蹤內部取樣點 | dlg_MarkerSetup；GS_Markers |
| Manual (Y only) | Marker 模式 | 一對可自由拖曳的垂直 marker（Y 方向） | 數位訊號不可用 | dlg_MarkerSetup |
| Manual (X and Y) | Marker 模式 | X、Y 各一對 marker | 數位訊號不可用 | dlg_MarkerSetup |
| Track Waveforms | Marker 模式 | 一對可拖曳的水平 marker；每個水平 marker 同時標示波形在該時刻的垂直值（不可拖曳垂直方向） | 可偏移到螢幕外 ±1 秒或一個螢幕寬（取較大者）以量測長時延 | dlg_MarkerSetup |
| Track Measurements | Marker 模式 | 顯示自動量測實際使用的位置（不可移動） | 未選自動量測時不顯示 | dlg_MarkerSetup；GS_Markers |
| Track RF | Marker 模式 | 在 FFT 波形上顯示頻率與該點振幅；可設 Peak Level 作為左右跳到下一峰值的門檻 | 低於 Peak Level 的峰不計入 | dlg_MarkerSetup |
| ΔX | 結果欄位 | 水平 marker 與其配對 marker 的差 | 配對由 "Delta To" 欄指定 | Marker_Results |
| 1/ΔX | 結果欄位 | ΔX 的倒數（用於兩 marker 間的頻率）；Versus 波形不計算 | — | Marker_Results |
| ΔY | 結果欄位 | 垂直 marker 與其配對的差 | — | Marker_Results |
| ΔY/ΔX | 結果欄位 | 追蹤與 RF marker 的垂直差／水平差 | — | Marker_Results |
| Delta info on screen | 顯示選項 | 在螢幕上顯示 marker 對的差值；點選差值可整對拖曳 | — | dlg_MarkerSetup |

Marker 來源與單位：marker 需綁定來源波形，單位與刻度由來源決定（手冊 dlg_MarkerSetup）。

---

## 四、FFT（頻域）

| 名稱 | 分類 | 定義／公式 | 前提或限制 | 來源檔名 |
|---|---|---|---|---|
| FFT 計算點數 | FFT | 取「不小於波形視窗取樣點數的最小 2 的冪次」；例：1000 點 → 1024 點；不足時於前後補零 | 只計算視窗內點，除非 Measure All Edges／Analyze All Data | FFT_Theory；FFT_Magnitude；Measurements_FFT |
| FFT 頻率範圍 | FFT | 0 Hz 到 Fs/2（Fs＝取樣率）；N 個時域點產生 N/2 個頻域點（bin） | Nyquist＝Fs/2；高於 Nyquist 會混疊（aliasing） | FFT_Theory（圖 image115–117） |
| FFT Resolution（RBW） | FFT | Rectangular 窗：RBW ＝ 取樣率 / 記憶體深度（＝Fs/N）；其他窗需乘上 Normalized Equivalent Noise Bandwidth（ENBW）係數 | ENBW 數值：手冊未載明 | FFT_Magnitude；Measurements_FFT；FFT_Spectrum_Control |
| FFT Magnitude | FFT | 時域 → 頻域的振幅譜，單位可選 dBm、dBmV、dBµV、Vrms、Watt | 對數單位時零參考在頂部，線性單位時零參考在底部；可設 Reference Impedance（Auto：單端 50 Ω、差動 100 Ω、共模 25 Ω；手動 10–200 Ω） | FFT_Magnitude；FFT_Magnitude_Vertical_Units |
| FFT Phase | FFT | 頻域相位譜；相位參考為 Trigger（T=0）或螢幕水平零點（Entire Display），可設 Reference Time Delay | 相位公式：手冊未載明 | FFT_Phase |
| Power Spectral Density (PSD，數學函數) | FFT | 每 Hz 功率：FFT bin 功率 ÷ RBW；單位 dBm/Hz、Watt/Hz、或 V/√Hz（V/√Hz 為其平方根，稱 ASD） | 適合看雜訊底噪；FFT Magnitude 的雜訊功率與 bin 寬度有關 | Power_Spectral_Density；FFT_Power_Spectral_Density |
| FFT Power Spectral Density（量測） | FFT 量測 | 量測指定頻帶內的 FFT 功率並歸一化到 1 Hz；可同時用多個量測量不同頻帶 | 參數：Center Frequency、Measurement Bandwidth；與上列 PSD 數學函數是不同項目（原稿曾混為一談） | FFT_Power_Spectral_Density |
| FFT Freq | FFT 量測 | 量測 FFT 上某峰的頻率 | 峰定義：Peak Level（預設 −40 dBm）與 Peak 1（從左數第幾個峰）；只計高於 Peak Level 的峰 | FFT_Freq |
| FFT Δfreq | FFT 量測 | 兩個峰之間的頻率差（Peak 1、Peak 2） | 同上 | FFT_Delta_Freq |
| FFT Δmag | FFT 量測 | 兩個峰之間的振幅差 | 同上 | FFT_Delta_Mag |
| FFT Channel Power | FFT 量測 | dBm/dBmV/dBµV 單位：P_ch = 10·log₁₀( (B_s / RBW)·(1/N)·Σᵢ₌₁ᴺ 10^(P_i/10) )（圖）；Watt 單位：P_ch = (B_s / RBW)·(1/N)·Σᵢ₌₁ᴺ P_i（圖）；Vrms 先換算為 Watt | B_s＝頻帶寬度（Hz）；頻帶邊界不對齊 bin，首末點以線性內插 | FFT_Channel_Power（圖 eqn_power_in_the_channel*.jpg） |
| FFT Occupied Bandwidth | FFT 量測 | 量測包含螢幕上 FFT 指定百分比功率的頻率範圍 | 百分比由 Occupied Bandwidth Percent 設定；計算方法（累加方式、邊界內插）：手冊未載明 | FFT_Occupied_Bandwidth |
| Total Harmonic Distortion (THD) | FFT 量測 | THD = 100 × √(X₂² + X₃² + Xₙ² + …) / X₁（圖）；Xₙ＝第 n 次諧波電壓或電流，X₁＝基頻值 | 基頻可 Find Peak（依 Peak Level 與 Peak 1）或手動輸入；僅量測螢幕上可見的諧波 | Total_Harmonic_Distortion（圖 THD.png） |
| Spectrum Control | FFT 設定 | 以「data to analyze」方塊選取部分波形做 FFT；RBW 模式 Automatic 時以 Span:RBW 比值設定；調整 RBW 會自動改變記憶體深度 | 僅適用類比輸入通道（不適用 waveform memory 或 math 來源）；需 Analog Memory Depth 為 Automatic；Fast Plot 強制關閉 | FFT_Spectrum_Control |
| Gated FFT | FFT 設定 | 先建立水平 gating math 函數，再於其上加 FFT Magnitude（Gating 函數本身不顯示） | 操作：框選區域 → 右鍵 Gated FFT | Gated_FFT |
| 視窗：Rectangular (Uniform) | 視窗函數 | 不加窗（樣本不變）；RBW ＝ Fs/N；振幅精度佳，但易有洩漏（leakage） | 適合單次暫態或整數週期訊號；自窗（self-windowing）如脈衝、衰減正弦 | FFT_Theory；FFT_Spectrum_Control |
| 視窗：Hanning | 視窗函數 | 「平滑歸零」的升餘弦窗，首尾為 0、中央為 1；頻率解析度佳，振幅精度較差 | 手冊建議用於最佳頻率精度（需於 Math Functions 設定） | FFT_Theory；FFT_Magnitude |
| 視窗：Hamming | 視窗函數 | 「升餘弦（raised cosine）」函數，與 Hanning 同型但係數不同；頻率解析度佳，適合近距離正弦；振幅精度較差 | 係數數值：手冊未載明（FFT_Theory 僅一句話，無圖無式） | FFT_Theory；FFT_Magnitude；FFT_Phase |
| 視窗：Flattop | 視窗函數 | 頻域主瓣較寬且平坦；振幅精度佳，頻率解析度較差 | 手冊建議用於最佳振幅精度 | FFT_Theory；FFT_Magnitude |
| 視窗：Blackman-Harris | 視窗函數 | 主瓣不太寬（尚可辨頻）、旁瓣下降 90 dB；適合含遠處強干擾的訊號，可當通用窗 | 缺點：peak 寬；係數：手冊未載明 | FFT_Theory |
| FFT 單位換算（dBm↔V↔P） | 單位 | dBm = 10·log(P_in / 1 mW)（圖）；dBm（50 Ω）= 20·log(V_peak / 0.316228 V)（圖）；V_peak = V_rms/0.707107 = √(P·R)/0.707107（圖）；1 mW@50 Ω 之 V_peak＝0.316228 V（圖）；dBV = dBm 值 − 13.01 dB（圖） | 使用手冊指定之 Reference Impedance 取代 50 Ω；電壓量測不強制需要 Reference Impedance | FFT_Theory_Computation_of_dBm（image132–134）；FFT_Theory_Computation_of_dBV（image135） |
| 單位換算表 | 單位 | 見下方「FFT 單位換算表（完整）」（已回原 htm 與 eqn_*.png 逐格核對） | Z＝參考阻抗；忽略失配與插入損耗；dB 只表示功率比 | FFT_Magnitude_Vertical_Units |
| 阻抗換算 | 單位 | dBmV 在 Z₁ 轉換至 Z₂ 之修正量 ＝ 10·log(Z₂/Z₁)（圖）；例：42 dBmV（50 Ω）→ 75 Ω 為 +1.76 dB，得 43.76 dBmV（75 Ω） | 僅適用於同一系統內功率與電壓間的換算 | FFT_Magnitude_Vertical_Units（圖 eqn_dBmV_impedance_conversion.png） |

### FFT 單位換算表（完整，FFT_Magnitude_Vertical_Units；列＝From，欄＝To；Z＝參考阻抗）
基本式（圖 eqn_dB_P／eqn_dB_V／eqn_dBmV）：dB 為功率比的對數；亦可表為電壓比；V₁ 設為 1 mV 即 dBmV。V、P 以 Vrms、Watt 計（手冊未逐字寫「rms」但 dBmV／dBµV 定義為「RMS」）。

| From＼To | Volts, V | Watts, P | dBm | dBmV | dBµV |
|---|---|---|---|---|---|
| Volts, V | V | V²/Z（圖 eqn_V_to_P） | 10·log[V²/(10⁻³·Z)]（圖 eqn_V_to_dBm） | 20·log[V/10⁻³]（圖 eqn_V_to_dBmV） | 20·log[V/10⁻⁶]（圖 eqn_V_to_dBuV） |
| Watts, P | √(P·Z)（圖 eqn_P_to_V） | P | 10·log[P/10⁻³]（圖 eqn_P_to_dBm） | 20·log[√(Z·P)/10⁻³]（圖 eqn_P_to_dBmV） | 20·log[√(Z·P)/10⁻⁶]（圖 eqn_P_to_dBuV） |
| dBm | √( log⁻¹(dBm/10) · Z · 10⁻³ )（圖 eqn_dBm_to_V） | log⁻¹(dBm/10) · Z · 10⁻³（圖 eqn_dBm_to_P；式中 Z 照圖，手冊未解釋，與 P=10⁻³·10^(dBm/10) 不一致處待確認） | dBm | dBm + 30 + 10·log Z | dBm + 90 + 10·log Z |
| dBmV | log⁻¹[dBmV/20 − 3]（圖 eqn_dBmV_to_V） | (1/Z)·log⁻¹[dBmV/10 − 6]（圖 eqn_dBmV_to_P） | dBmV − 30 − 10·log Z | dBmV | dBmV + 60 |
| dBµV | log⁻¹[dBµV/20 − 6]（圖 eqn_dBuV_to_V） | (1/Z)·log⁻¹[dBµV/10 − 12]（圖 eqn_dBuV_to_P） | dBµV − 90 − 10·log Z | dBµV − 60 | dBµV |

- 備註：dBm 列之 P 欄（圖 eqn_dBm_to_P）圖中為「log⁻¹(dBm/10)·Z·10⁻³」，物理上應為 10⁻³·log⁻¹(dBm/10)（不含 Z）；此處照圖轉寫，疑似手冊筆誤，標「待確認」，未自行更正。
- 文字說明：3 dB 增減＝功率加倍／減半；dBm、dBµV 分別為高於 1 mW、1 µV 之 dB 數（FFT_Magnitude_Vertical_Units）。
- 預設垂直單位為 dBm。對數單位（dBm、dBmV、dBµV）零參考在格線頂端；線性單位（Vrms、Watt）在底端（FFT_Magnitude）。

### FFT 視窗與 ENBW 總結（手冊可得資訊）
- 手冊文字：Hanning＝「平滑歸零」；Flattop＝振幅精度；Rectangular＝無窗；Blackman-Harris＝旁瓣約 −90 dB；Hamming＝升餘弦、係數不同。
- 已複查 FFT_Theory.htm（含 image115–131）、FFT_Magnitude.htm、FFT_Phase.htm、FFT_Spectrum_Control.htm、Measurements_FFT.htm、Power_Spectral_Density.htm，並全檔搜尋 ENBW／equivalent noise／scalloping／coefficient：
  - 手冊**未載明**各視窗的係數或數學式、ENBW 數值、scalloping loss、最高旁瓣位準（僅 Blackman-Harris「旁瓣下降 90 dB」）；僅在 RBW 敘述中寫「其他視窗要套用 Normalized Equivalent Noise Bandwidth factor」（FFT_Magnitude、FFT_Spectrum_Control、Measurements_FFT、FFT_Phase、Power_Spectral_Density）。
  - FFT_Theory 的 image120–131 為時域／頻域示意圖，非公式（已讀 image115、117、122、127 確認：image115＝傅立葉積分式 V(f)=∫v(t)e^(−j2πft)dt；image117＝「0 Hz to Fs/2」）。
  - 選窗建議（FFT_Theory 表）：Hanning＝頻率解析度佳、適合正弦、振幅精度較差；Hamming＝頻率解析度佳、適合鄰近正弦、振幅精度較差；Flattop＝振幅精度佳、頻率解析度較差；Rectangular＝頻率解析度佳、自窗波形振幅精度佳、可能洩漏；Blackman-Harris＝適合遠處強干擾、通用、主峰寬。Hanning 或 Hamming 求最佳頻率精度、Flattop 求最佳振幅精度、Rectangular 用於單次暫態或整數週期訊號（FFT_Magnitude）。
  - FFT 頻率精度＝(1) bin 數限制：量測精度為 ±半個 bin（bin 間距＝時間記錄長度的倒數）＋(2) 取樣時脈振盪器精度（Measurements_FFT）。
  - 擷取建議：Real Time 取樣模式、關閉 sin(x)/x 內插、垂直靈敏度使訊號近滿幅但不截波（Measurements_FFT）。

---

## 五、量測閾值與 Top／Base 判定

| 名稱 | 分類 | 定義／公式 | 前提或限制 | 來源檔名 |
|---|---|---|---|---|
| IEEE 預設閾值 | 閾值 | 10% / 50% / 90%（下 / 中 / 上）以 Top、Base 為基準 | 手冊：為預設定義（IEEE） | dlg_MeasurementThreshold；Calculating_Thresholds |
| 20/50/80 | 閾值 | 20% / 50% / 80%；對振鈴或過衝大的波形較佳 | 同上 | dlg_MeasurementThreshold |
| Custom: % of top, base | 閾值 | 任意百分比（非 10/50/90 或 20/50/80） | — | dlg_MeasurementThreshold |
| Custom: thresholds (low, mid, up) | 閾值 | 以伏特定義固定閾值；下限不得高於中或上限，上限不得低於中或下限 | 不對稱閾值 | dlg_MeasurementThreshold |
| Custom: threshold ± hysteresis | 閾值 | Upper ＝ Mid + Hysteresis；Lower ＝ Mid − Hysteresis（伏特） | Rise/Fall 不可用；抖動量測建議 Mid 在來源 50%、Hysteresis 約為振幅 5% | dlg_MeasurementThreshold |
| Auto set thresholds | 閾值 | Mid ＝ (Vmax + Vmin) / 2；Hysteresis ＝ ±0.05 × (Vmax − Vmin) | 按鈕自動設定 | dlg_MeasurementThreshold |
| Snap to 0 | 閾值 | 閾值在 ±10 mV 內時移到 0 V | 差動訊號適用 | dlg_MeasurementThreshold |
| Top/Base：Standard（預設） | Top/Base | 直方圖最高 40% 找 Top、最低 40% 找 Base；中央 20% 不掃描；若某一端出現次數 < 總數 5% 則取絕對 Max／Min | 統計上資訊不足時自動改用 Min、Max | Calculating_Top_and_Base；dlg_MeasurementThreshold |
| Top/Base：Histogram | Top/Base | 依直方圖峰值（不考慮統計有效性） | 適用於雙峰直方圖；中央 20% 仍不掃描 | dlg_MeasurementThreshold |
| Top/Base：Min, Max | Top/Base | Top ＝ 最大值，Base ＝ 最小值 | 資訊不足時的預設 | dlg_MeasurementThreshold |
| Top/Base：Custom | Top/Base | 以伏特指定 Top／Base（不允許 Base 高於 Top） | — | dlg_MeasurementThreshold |
| Level Qualification | 條件量測 | 只在其他來源滿足條件時才量測時序（Above Middle／Below Middle／Between Upper, Lower／Not Between Thresholds） | 需 InfiniiScan Event Identification 授權；只檢查參與該量測的邊緣 | dlg_MeasurementLevelQualification |
| Measure All Edges | 量測範圍 | 開啟：量測整個 acquisition 的所有邊緣；關閉：僅量測螢幕上特定邊緣（以拖放或最接近時基參考者為準） | 改變設定會重新計數統計；Pulse Count、Edge-Edge、Hold／Setup、N-Period、Phase、EZJIT 會自動開啟 | dlg_MeasurementSetup |
| Analyze All Data | 量測範圍 | 開啟時對整個 acquisition 計算；關閉時只計算螢幕資料（深記憶體時會先做保形的資料縮減） | 與 Measure All Edges 聯動 | dlg_MeasurementSetup |

### 量測過程共通（Understanding_the_Measurement_Process）
1. 擷取資料記錄（Data Collection）。
2. 建立直方圖：以 8 位元資料建立（平均模式下非完整解析度）（Building_a_Histogram）。
3. 由直方圖與資料記錄求絕對 Max／Min（Calculating_Min_and_Max）。
4. 求 Top 與 Base（Calculating_Top_and_Base）。
5. 依 Top、Base 計算下 / 中 / 上閾值（Calculating_Thresholds）。
6. 以閾值找上升／下降邊緣與時序量測（Determining_Rising_and_Falling_Edges）。
7. 計算最終參數（Automatic_Parametric_Measurements）。

### 統計與結果欄位（Measurement_Results、Measurements_Histogram_Stats）
| 名稱 | 分類 | 定義 | 來源檔名 |
|---|---|---|---|
| Current | 統計 | 最近一次擷取的量測結果 | Measurement_Results |
| Mean | 統計 | 所有結果的平均 | Measurement_Results |
| Min / Max / Range | 統計 | 最小值／最大值／Max − Min | Measurement_Results |
| Std Dev | 統計 | 所有結果的標準差 | Measurement_Results |
| Count | 統計 | 納入統計的結果數 | Measurement_Results |
| Fail Min / Fail Max | 限值測試 | 低於下限／高於上限的失敗數（啟用 Limit Test 時出現） | Measurement_Results |
| Histogram (Measurement) | 直方圖 | 顯示量測值的直方圖；可設 Max Bins、量測範圍 min／max、Vertical Size（格數）；新擷取時更新 | Meas_Histogram |
| 直方圖統計：p-p | 直方圖統計 | 非零直方圖資料的寬度（第一與最後非零像素欄／列之差） | Measurements_Histogram_Stats |
| 直方圖統計：FWHM | 直方圖統計 | 半高寬 | 同上 |
| Mean / Std Dev / Median / Mode | 直方圖統計 | 平均、標準差、中位數（50% 位置）、眾數（最高柱） | 同上 |
| μ ± 1σ / 2σ / 3σ | 直方圖統計 | 落於平均 ±1σ（±2σ、±3σ）內的點數百分比 | 同上 |
| μ − 3σ / μ + 3σ | 直方圖統計 | 平均減／加三倍標準差 | 同上 |
| Hits / Peak / Bin Width | 直方圖統計 | 總樣本數、最高柱的次數、一柱代表的值範圍 | 同上 |

### 量測「?」與無效結果（Questionable_or_Missing_Measurement_Results）
- 空白：目前量測不在螢幕上。
- `?`：資料不足、波形截波（clipped）或取樣率不足以量測快速上升。
- `≤`：解析度太粗，手冊說明為量測邊界的上界。
- `------`：無效或量測取消。
- `Edge?`：找不到所需邊緣。
- `Closed eye`：眼圖不開，需套用等化。
- `Crossing?`：訊號不交越。

---

## 六、抖動（Jitter）與眼圖（Eye）— 僅列名稱與一句話

### EZJIT 時脈量測（Measurements_Clock、Jitter_Measurements_Clock_Measurements）
- Clock TIE：先做時脈復原，比較每個週期與理想時脈的誤差統計（Jitter_Meas_Clock_TIE）。
- Period-Period：連續 n 週期群組之差（Jitter_Meas_Clock_period-period）。
- +width − +width：正脈寬對正脈寬之差（Jitter_Meas_Clock_pos_width-pos_width）。
- −width − −width：負脈寬對負脈寬之差（Jitter_Meas_Clock_neg_width-neg_width）。
- Duty Cycle − Duty Cycle：逐週期占空比之差（Jitter_Meas_Clock_duty_cycle-duty_cycle）。

### EZJIT 資料量測（Measurements_Data、Jitter_Measurements_Serial_Data_Analysis_Measurements）
- Data TIE：以時脈位置為基準，比較資料邊緣交越與理想位置（Jitter_Meas_Data_TIE）。
- Noise：單 / 零位準的總雜訊（需 EZJIT Complete 授權）（Jitter_Meas_Data_noise）。
- UI、N-UI、UI-UI、Data Rate、Pattern Length、Clock Recovery Rate、Deemphasis（Jitter_Meas_Data_*）。
- N-UI：連續 N 個 UI 的時間；UI-UI：相鄰兩個 N-UI 量測之差（Jitter_Meas_Data_N-UI、Jitter_Meas_Data_UI-UI）。
- Hold Time／Setup Time 亦列於資料量測（見第一節）。

### EZJIT Plus 結果（Jitter_Measurements_RJ___DJ_Measurements）
- TJ(1E-XX)、RJrms、PJδδ、PJrms、BUJδδ、DJδδ、DDJpp、DCD、ISIpp、UTJ、UDJδδ、ScopeRJrms、ABUJrms、DDPWS、F/2（Even/Odd）、DJpp（需 EZJIT Plus 授權）。

### 眼圖（Measurements_Eye、Eye_*.htm）
均以 Color Grade 資料庫為基礎（需 Real-Time Eye 開啟）；手冊：「Eye measurements assume the eye is centered vertically on screen」（Measurements_Eye）。Start Measurement After 預設 1（最小最高命中數）。Vtop／Vbase＝垂直直方圖頂／底峰的平均電壓；σ_top／σ_base＝其標準差。

| 名稱 | 定義／公式 | 前提限制 | 來源檔名 |
|---|---|---|---|
| Eye Q-Factor | Q = (V_top − V_base) / (σ_top + σ_base)（圖 image214.gif）；噪聲越大 Q 越低 | Vtop／Vbase／σ 取自眼圖資料中間 20% 垂直切片（40%–60% 位置）的垂直直方圖；資料量不足時數值變動大 | Eye_Q-Factor |
| Eye Crossing % | Crossing % = 100 × (V_crossing − V_base) / (V_top − V_base)（圖 image207.gif）；理想為 50% | V_crossing＝交越點最常出現的垂直位置：先以整個畫面的水平直方圖定交越時間，再以窄垂直直方圖定 V_crossing；Vtop／Vbase 同樣取 40–60% 切片 | Eye_Crossing |
| Eye Height | 兩種演算法：Use Measured Data（在 Eye Window 內量測，回報最小眼高）；Extrapolate Using Standard Deviation：Eye Height = (V_top − 3σ_top) − (V_base + 3σ_base)（圖 image210.gif） | Eye Window Start／Stop 預設 40%／60%（中間 20%）；另有 Eye Height Location（含 Find Eye Opening 等；其他選項細節未讀） | Eye_Height |
| Eye Width | Use Measured Data（在交越點之間量測，回報最小眼寬）；Extrapolate：Eye Width = (t_crossing2 − 3σ_crossing2) − (t_crossing1 + 3σ_crossing1)（圖 image211.gif） | 水平直方圖取自 Vtop 與 Vbase 之間的資料；Eye Width Threshold：Automatic（交越處最寬）或 Use Measurement Threshold | Eye_Width |
| Eye Jitter | RMS：Jitter RMS = 1·σ_crossing（圖 image212.gif）；p-p：Jitter p-p = 6·σ_crossing（圖 image213.gif） | 以水平時間直方圖迭代縮窄視窗定交越點；單位可選秒或 UI（非 Real-Time Eye 不能用 UI） | Eye_Jitter |
| Eye Duty Cycle Distortion | 時間：DCD = \|t_rising50% − t_falling50%\|（圖 image208.gif）；百分比：DCD% = 100 × \|t_rising50% − t_falling50%\| / (t_crossing2 − t_crossing1)（圖 image209.gif） | t_rising50%／t_falling50%＝上升／下降邊緣達 Vtop 與 Vbase 之間 50% 的時間；中閾值預設 50%；以交越點與中閾值的直方圖分析 | Eye_Duty_Cycle_Distortion |

### 功率類（Power Measurements；automatic_power_measurements；需功率分析授權，手冊僅列名稱與簡述）
| 名稱 | 定義／公式 | 來源檔名 |
|---|---|---|
| Crest Factor | 電壓：Vpeak / VRMS；電流：Ipeak / IRMS（交流線路負載所需瞬時峰值與 RMS 之比）。手冊為文字式，無公式圖 | Crest_Factor_meas |
| Real Power | (1/N) Σₙ₌₀^(N−1) Vₙ·Iₙ（圖 eqn_Real_Power.jpg；N＝第 N 個取樣而非週期）；在代表功率的單一來源（通常為 V×I 乘法波形）上量測 | Real_Power_meas |
| Apparent Power | IRMS × VRMS（需電壓與電流兩個來源） | Apparent_Power_meas |
| Reactive Power | √(Apparent² − Real²)（圖 Reactive_Power.png；單位 VAR） | Reactive_Power_meas |
| Power Factor | Real Power / Apparent Power | Power_Factor_meas |
| Phase Angle（功率） | 功率三角形中視在功率與實功率之夾角（電流與電壓相位角） | Phase_Angle_meas |
| Input Power／Output Power | Input V × Input I／Output V × Output I（需 Auto Setup 指派四通道） | Input_Power_meas；Output_Power_meas |
| Efficiency | Output power / Input power | Efficiency_meas |
| Output Ripple | VMax − VMin（輸出電壓波形） | Output_Ripple_meas |
| Peak Current | 電流波形最大值與最小值中絕對值較大者（可正可負） | Peak_Current_meas |
| Transient | 暫態響應時間 = t2 − t1；t1＝電壓波形首次離開穩定帶、t2＝最後一次進入；穩定帶＝穩態輸出電壓 ± overshoot % | Transient_meas |
| Turn On Time | t2 − t1；t1＝AC 輸入達其最大振幅 10%、t2＝DC 輸出達其最大振幅 90% | Turn_On_Time_meas |
| Turn Off Time | t2 − t1；t1＝AC 輸入低於其正（或負）峰值 10%（先發生者）、t2＝DC 輸出降到穩態值 10% | Turn_Off_Time_meas |
| Power Loss | Pₙ = Vdsₙ × Idₙ（n 為每個取樣） | Power_Loss_meas |
| Power Loss/Cyc | Pₙ = (Vdsₙ·Idₙ) × (zoom 視窗時間範圍) × (開關訊號電壓之計數量測)；需 zoom 模式與計數器量測 | Power_Loss_Cyc_meas |
| Energy Loss | Σ(Vdsₙ × Idₙ) × 取樣間隔（sample size） | Energy_Loss_meas |
| Rds(on)、Vce(sat) | 開關元件特性，由 Rds(on) and Vce(sat) 功率分析量測；手冊無公式 | Rdson_meas；Vcesat_meas |

### 其他類別（僅名稱＋一句話＋來源檔；未深入）
| 類別／名稱 | 一句話 | 來源檔名 |
|---|---|---|
| Noise Reduction（降噪） | 授權功能；降低示波器自身對高速重複序列資料的雜訊貢獻，模式含 Cross-correlation（雙通道） | Noise_Reduction_Analysis |
| Jitter／Noise 結果（EZJIT Complete） | Noise 分頁：TJ／DJ／RN 等統計；Eye height = (one level − 0.5·TI_b) − (zero level + 0.5·TI_t)，TI 由雜訊直方圖與 dual-dirac 模型計算 | Noise_Tab_Measurements；Jitter_Meas_Data_noise |
| Phase Noise（相位雜訊） | 短期頻率穩定度；SSB 相位雜訊 ℒ(f)＝偏移頻率處功率密度與載波總功率之比（NIST 定義） | Phase_Noise_Analysis_Overview；Phase_Noise_Analysis |
| Crosstalk（串擾） | 不需關閉他路通道即可分離、量化多通道序列資料與電源的串擾與 SSN | Crosstalk_Overview；Crosstalk |
| Power Integrity（電源完整性） | 電源供應 Aggressor／Victim 相關雜訊與抖動分析 | Power_Integrity_Overview；PI_Overview_* |
| PAM（授權） | PAM Eye／Level／Rise-Fall／Noise／Jitter／BER-SER／SNDR／PAM-4 12 Edge Jitter 等結果 | PAM_Measurements；PAM_*_Meas_Results |
| Optical（需光學探棒） | Optical Average Power、OMA、Eye One／Zero Level、Extinction Ratio、Outer OMA、Outer ER、TDECQ（FlexRT） | Measurements_Optical；Optical_* |
| Three-Phase Power | 三相功率分析：Vrms／Irms／Vdc／Idc／Vcf／Icf／V-I Phase／P／S／Q／PF 等結果欄位 | Three_Phase_Power_Measurement_Results；Three-Phase_Power_Analysis |
| InfiniiSim | 量測／模擬電路模型（S 參數、傳遞函數、FIR）；僅列名稱 | InfiniiSim_What_Is；InfiniiSim_Transfer_Functions |

---

## 七、算法細節（需要較長說明者）

**A-1. 邊緣判定與內插**（Determining_Rising_and_Falling_Edges）
1. 掃描波形資料，記錄穿越下、中、上閾值的時點。
2. 若取樣點不剛好落在閾值上，系統在相鄰兩點之間內插（手冊未載明內插方式；僅寫「interpolates between the two points about the threshold」）。
3. 上升邊緣：定義為「最後一個低於下閾值的點」到「第一個高於上閾值的點」之間的過渡；下降邊緣反之。
4. 不完整穿越與毛刺（glitch）被忽略：邊緣必須完整穿越三個閾值。
5. 若取樣點不足，上升時間等量測「不被量測」或標示為可疑（questionable）。

**A-2. 上升／下降時間**（Rise_Time、Fall_Time、Determining_Rising_and_Falling_Edges）
1. 上升時間 ＝ 上閾值時刻 − 下閾值時刻（該上升邊緣）。
2. 下降時間 ＝ 下閾值時刻 − 上閾值時刻（該下降邊緣）。
3. 需至少 4 個取樣點（1 個高於上閾、1 個低於下閾、2 個介於其間）。
4. 非 zoom 模式：量測所有上升邊緣（含不在視窗內者）；zoom 模式：只量測 zoom 區域內者。

**A-3. Top／Base 與 Vtop／Vbase 判定**（Calculating_Top_and_Base、Top_Voltage、Base_Voltage）
1. 建立量測直方圖（8 位元資料）。
2. Top：直方圖最高 40% 區段中出現次數最多的電壓；Base：最低 40% 區段中出現次數最多的電壓；中央 20% 不掃描。
3. 若該端的出現次數 < 總次數的 5%，Top 取絕對 Max、Base 取絕對 Min。
4. Vtop／Vbase（Standard 定義）：在「直方圖峰值」與「Vmax／Vmin」之間依波形型態擇一（方形波取直方圖峰；三角波取 Vmax／Vmin），以防三角波時 Top 跳動；**具體判準：手冊未載明**。
5. 統計上資訊不足時，Standard 自動退回 Min、Max。

**A-4. 閾值計算**（Calculating_Thresholds、dlg_MeasurementThreshold）
1. Lower ＝ Base + p_low × (Top − Base)；Mid ＝ Base + p_mid × (Top − Base)；Upper ＝ Base + p_up × (Top − Base)。以 10/50/90 為例：p = 0.10 / 0.50 / 0.90（此式為手冊文字「10% of the amplitude between Top and Base」之直譯，手冊未以公式列出）。
2. Custom ± Hysteresis：Upper ＝ Mid + H；Lower ＝ Mid − H。
3. Auto set：Mid ＝ (Vmax + Vmin)/2；H ＝ 0.05 × (Vmax − Vmin)。
4. Snap to 0：|閾值| ≤ 10 mV 時設為 0。

**A-5. 時間量測定義**（Timing_Definitions）
1. 第一個邊緣為上升時：
   - Period ＝ 第二個上升邊緣中閾值 − 第一個上升邊緣中閾值；
   - +width ＝ 第一個下降邊緣中閾值 − 第一個上升邊緣中閾值；
   - −width ＝ 第二個上升邊緣中閾值 − 第一個下降邊緣中閾值。
2. 第一個邊緣為下降時：
   - Period ＝ 第二個下降邊緣中閾值 − 第一個下降邊緣中閾值；
   - +width ＝ 第二個下降邊緣中閾值 − 第一個上升邊緣中閾值；
   - −width ＝ 第一個上升邊緣中閾值 − 第一個下降邊緣中閾值。
3. Frequency ＝ 1 / Period。
4. Duty Cycle ＝ (+width / Period) × 100。

**A-6. Phase**（Phase.htm，圖 image89）
1. 取第一組最左側的兩個同向邊緣，於中閾值交越處計時。
2. Phase（deg）＝ 360° × (Time Between Edges) / (Period of Source 1)。
3. 需至少兩個週期與兩個上升邊緣；需 Measure All Edges。

**A-7. Overshoot／Preshoot**（Overshoot.htm、Preshoot.htm；圖 image109、111、104–107）
1. 判定邊緣極性（上升／下降，依 Measure All Edges 設定）。
2. Overshoot（上升）＝ 100 × (local max − Top) / (Top − Base)；（下降）＝ 100 × (Base − local min) / (Top − Base)。
3. Preshoot（上升）＝ 100 × (Base − local min) / (Top − Base)；（下降）＝ 100 × (local max − Top) / (Top − Base)。
4. 區間界定見表格。

**A-8. Vrms**（RMS_Voltage.htm，圖 image100、101）
1. 取螢幕上 n 個取樣點（非記憶體深度）。
2. DC Vrms ＝ √( Σ v(i)² / n )。
3. AC Vrms ＝ √( Σ (v(i) − Vavg)² / n )，Vavg 為同一區間的平均。
4. dBm 單位時以參考阻抗換算功率（Auto：單端 50 Ω、差動 100 Ω、共模 25 Ω；其他來源預設 50 Ω）。

**A-9. Pulse Top／Base／Amplitude**（Pulse_Top、Pulse_Base、Pulse_Amplitude）
1. 以中閾值界定脈波的起點與終點。
2. 取脈寬中央 X%（如 50%：去掉前後各 25%；100%：整段）之資料平均。
3. Pulse Amplitude ＝ 前後兩段電平之差（符號慣例：手冊未載明）。

**A-10. Delta Time**（Delta_Time、Timing_Definitions）
1. 邊緣指定：編號 1–65534、斜率（Rising／Falling／First on display）、閾值（Lower／Middle／Upper）。
2. 編號由視窗左側開始計數，非觸發點。
3. 指定邊緣不在視窗內時回報 "edge not found"。

**A-11. FFT 處理流程**（FFT_Theory、FFT_Magnitude、Measurements_FFT）
1. 取視窗內樣本（或 Analyze All Data／Measure All Edges 時取全部），補零至 2 的冪次。
2. 套用視窗函數（Rectangular、Hanning、Flattop、Blackman-Harris、Hamming）。
3. FFT 得 N/2 個頻域點（bin），頻率間隔 ＝ Fs/N（Rectangular）。
4. 依選定單位輸出（dBm、dBmV、dBµV、Vrms、Watt），dBm 之換算見第四節。
5. 峰值偵測：依 Peak Level（預設 −40 dBm）與 Peak 1、Peak 2 計數。
6. Detector：Off／Sample／Positive Peak／Negative Peak／Normal／Average（僅顯示用的分桶處理）。

**A-12. Channel Power**（FFT_Channel_Power）
1. dBm 系列：P_ch ＝ 10·log₁₀( (B_s/RBW) · (1/N) · Σ 10^(P_i/10) )。
2. Watt 系列：P_ch ＝ (B_s/RBW) · (1/N) · Σ P_i。
3. 頻帶邊界若不對齊 bin，首末點線性內插。

**A-13. PSD**（Power_Spectral_Density）
1. 每 bin 功率 ÷ RBW ＝ 每 Hz 功率（W/Hz 或 dBm/Hz）。
2. V/√Hz（ASD）＝ √(PSD)。

**A-14. THD**（Total_Harmonic_Distortion）
1. 基頻 X₁：Find Peak（依 Peak Level 與 Peak 1）或手動輸入。
2. THD ＝ 100 × √(X₂² + X₃² + … + Xₙ²) / X₁。

**A-15. Undershoot**（Undershoot.htm；圖 eqn_Undershoot_Positive_Pulse.jpg、eqn_Undershoot_Negative_Pulse.jpg）
1. 依脈波極性（非單一邊緣）量測；視窗內至少 2 個邊緣；多個畸變時取幅度最大者。
2. 須先達到 ≥ Top（正脈波）／≤ Base（負脈波）之後才量測。
3. 正脈波 ＝ (Top − localMinimum)/(Top − Base)，localMinimum < Top 時；否則 0。
4. 負脈波 ＝ (localMaximum − Base)/(Top − Base)，localMaximum > Base 時；否則 0。
5. 圖中標示 (%)，但式中無 ×100：是否乘 100 待確認。

**A-16. Eye Q-Factor／Crossing %／Height／Width／Jitter／DCD**（見第六節眼圖表）
1. 資料：Color Grade 資料庫；Vtop／Vbase／σ 由眼圖中間 20%（40%–60%）切片的垂直直方圖求得。
2. Q = (Vtop − Vbase)/(σtop + σbase)；Crossing % = 100·(Vcrossing − Vbase)/(Vtop − Vbase)。
3. Eye Height（外推）= (Vtop − 3σtop) − (Vbase + 3σbase)；Eye Width（外推）= (t_c2 − 3σ_c2) − (t_c1 + 3σ_c1)。
4. Eye Jitter：RMS = 1σ_crossing；p-p = 6σ_crossing。

**A-17. FFT 單位換算**（FFT_Magnitude_Vertical_Units；FFT_Theory_Computation_of_dBm／dBV）
1. dBm = 10·log(P_in / 1 mW)（image132）；50 Ω 時 dBm = 20·log(Vpeak / 0.316228 V)（image133）；Vpeak = Vrms/0.707107 = √(P·R)/0.707107，1 mW@50 Ω → 0.316228 V（image134）。
2. dBV = 20·log(Vpeak/0.316228) + 20·log(0.707107×0.316228) = dBm − 13.01 dB（image135）。
3. 手冊指定的 Reference Impedance 取代上式的 50 Ω；僅量測電壓時不需參考阻抗。
4. 其他單位對應見第四節「FFT 單位換算表（完整）」。

---

## 八、手冊未寫明、需真機驗證的項目

1. **Vtop／Vbase（Standard）在「直方圖峰」與「Vmax／Vmin」之間的選擇判準**：手冊只說明「decides whether …」，未給數值門檻（Top_Voltage、Calculating_Top_and_Base）。
2. **Vavg 的數學式與「first cycle」判定細節**：Making_Voltage_Measurements 僅寫「average voltage of the first cycle」；Average_Voltage 為整個螢幕或一個週期；無公式圖。（Vamp = Vtop − Vbase 已查明，移出本清單。）
3. **Vavg、Vrms、Area、Pulse Top／Base、Pulse Amplitude 的「均勻次取樣」**：手冊未說明比例，精度影響未量化。
4. **Undershoot 公式是否乘 100**：公式圖有、單位標 (%)，但式中無 ×100（待確認）。
5. **邊緣內插方式**：手冊僅寫 interpolates。
6. **Area 的積分方法與單位**：未載明（已複查 Area.htm、Measurements_Mixed.htm）。
7. **Crossing 的電壓計算公式**：未載明（Crossing_Point_Measurement.htm 僅文字與範例截圖）。
8. **Hold Time／Setup Time 的正式公式**：只有文字定義（中閾值到中閾值）。
9. **Pulse Amplitude 的符號慣例**：未載明。
10. **Phase 的「Period of Source 1」**：週期定義與平均方式未載明。
11. **FFT 各視窗係數、ENBW 數值、scalloping loss、旁瓣位準（除 Blackman-Harris 之 90 dB）**：手冊未載明（已全文搜尋，見第四節）。
12. **FFT Occupied Bandwidth 的計算方法**（累加方式、邊界內插）：未載明。
13. **FFT Phase 的解纏繞與相位定義細節**：未載明。
14. **Measure All Edges 與 Analyze All Data 在深記憶體資料縮減後的精度損失**：僅說「保形」。
15. **Reference Impedance Auto 判定與實際探棒對應**：手冊僅列單端 50 Ω／差動 100 Ω／共模 25 Ω 三種，實際探棒型號需真機確認。
16. **Track RF 與 FFT Peak Annotation 的峰值排序細節**：只列 Decreasing Magnitude 等選項。
17. **N-Period、Edge to All Edges 的末端不足 N 的群組之統計處理**：僅說「也量測」。
18. **Level Qualification 在邊緣上的判定時點**：取樣點層級未載明。
19. **直方圖 8 位元量化誤差**：未給數值。
20. **Burst Interval／Burst Width 的 idle time 預設值與判定演算法**：Burst_Interval 僅一段文字；預設值未載明。
21. **dBm→W 換算圖 eqn_dBm_to_P 的 Z 因子**：圖中含 Z，物理上不應有，疑手冊筆誤，需真機對照（待確認）。
22. **Eye Height Location 的其他選項**、**Eye 量測 Eye Window 外之細節**：未逐項讀。
23. **功率類（Crest Factor 等）的實際取樣範圍（整數週期？整螢幕？）**：Crest_Factor_meas 僅寫比值，未載明。

---

## 九、略過或未讀的主題

- **Optical、PAM、Three-Phase、InfiniiSim、Noise／Phase Noise／Crosstalk／Power Integrity**：僅列名稱與一句話（第六節「其他類別」），未深讀內文。
- **功率類**：已於第六節列出公式（文字式）；各量測的 UI 與 Auto Setup 細節未讀。
- **EZJIT 各量測的數學式**（如 TIE、Period-Period）：僅名稱與一句話。
- **Histogram 章節的 Waveform Histogram 操作細節**（Histograms、Histogram_Results）：僅讀摘要。
- **圖片檔**：僅讀取與公式有關者；FFT_Theory 內 image116、120、121、123–126、128–131 為示意圖，未逐一解讀。

---

## 十、修訂紀錄（2026-10-22 複查）

**抽查驗證**（對照原 .htm 與公式圖，共 33 項，其中錯誤／需補 3 類 4 項）

| 類別 | 已核對項目 | 結果 |
|---|---|---|
| 時間 | Rise_Time、Fall_Time、Period、Duty_Cycle、Negative_Pulse_Width、Delta_Time、Burst_Width、Hold_Time、Setup_Time、Slew_Rate、Phase（image88/89）、Pulse_Counting、N-Period、Edge_Time、T_Max、Timing_Definitions、Determining_Rising_and_Falling_Edges | 皆正確；Phase 公式圖 image89 核對無誤 |
| 電壓 | RMS_Voltage（image100/101）、Overshoot（image109/111）、Preshoot（image105/107）、Top_Voltage、Maximum_Voltage、Pulse_Top、Pulse_Amplitude、Calculating_Top_and_Base、Calculating_Thresholds | 皆正確；Vamp、Undershoot 原標「未載明」→ 實際手冊有（見下） |
| Marker | dlg_MarkerSetup、Marker_Results | 正確 |
| FFT | FFT_Theory、FFT_Magnitude、FFT_Spectrum_Control、FFT_Channel_Power（eqn_power_in_the_channel*.jpg）、Total_Harmonic_Distortion（THD.png）、FFT_Theory_Computation_of_dBm／dBV（image132–135）、FFT_Magnitude_Vertical_Units、FFT_Occupied_Bandwidth、FFT_Freq、Power_Spectral_Density | 兩處錯誤（見下），其餘正確 |

**修正與補充**
1. 錯誤修正：Auto 參考阻抗「共模 225 Ω」→ **25 Ω**（原誤將註腳上標「2」與 25 Ω 連讀成 225）。依據 FFT_Magnitude.htm、Power_Spectral_Density.htm、RMS_Voltage.htm（HTML 為 `<sup>2</sup>`＋`25 Ω`）。已改第四節、A-8、第八節。
2. 錯誤修正：FFT_Power_Spectral_Density（量測，頻帶功率歸一化到 1 Hz，參數 Center Frequency／Measurement Bandwidth）與 Power_Spectral_Density（數學函數）原混為一列，已拆開。
3. 「手冊未載明」改為已載明：Vamp = Vtop − Vbase（Making_Voltage_Measurements、Calculating_Top_and_Base）；Undershoot 公式（eqn_Undershoot_Positive_Pulse.jpg、eqn_Undershoot_Negative_Pulse.jpg，待確認是否 ×100）；Vavg 定義為「first cycle 的平均電壓」（Making_Voltage_Measurements；無數學式）。
4. FFT 單位換算表原標「逐格未可靠擷取」，現依 FFT_Magnitude_Vertical_Units.htm 表格結構與 17 張 eqn_*.png 補成完整 5×5 表（含一處疑似手冊筆誤，標待確認）。
5. 新增：Burst Interval（Burst_Interval）、Eye Q-Factor（image214）、Eye Crossing %（image207）、Eye Height／Width／Jitter／DCD 公式（image208–213）、功率類（含 Crest Factor＝Vpeak/VRMS、Ipeak/IRMS）、Noise／Phase Noise／Crosstalk／PAM／Optical／Three-Phase／InfiniiSim 名稱與一句話、FFT 頻率精度（±半 bin）說明、A-15～A-17。
6. 查明仍未載明：FFT 視窗係數／ENBW／scalloping loss（已搜尋 FFT_Theory 全部圖片與全檔關鍵字）、Area 公式、Crossing 公式（僅範例截圖 meas_V_Crossing.png）。

