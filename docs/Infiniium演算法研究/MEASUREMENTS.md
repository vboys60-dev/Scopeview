# Infiniium 量測分析（基本波形 / 眼圖 / 抖動雜訊 / InfiniiScan / 量測參數）

來源：`Infiniium_decompiled/`（ilspycmd 反編譯）。靜態分析，未執行程式。
**限制**：GUI 只有定義與設定；演算法在原生 `Phoenix.dll`。編號 → 名稱由 `CMeasurementMgr.GetTypeAsString`（`switch(eType - 偏移)`）還原，`?` 表示該函式沒有對應名稱。部分項目受授權 option / frame class 控制（見 `CMeasurementCategories.cs`）。

## 1. 基本波形量測（Time / Voltage）
**Time**：28 Rise time、29 Fall time、49 + width、50 - width、43 Delta time、292/293 ± pulse count、30 Period、31 Frequency、53 Duty cycle、305 Burst period、306 Burst interval、36 T min、35 T max、41 T volt、42 T edge、308 Edge time、155 Edge-edge、594 Edge to all edges、893 High time、894 Low time、895 Time >,< level、662–665 Duty cycle adjustment I/Q/I'/Q'、667 SSPRQ100 deskew。
**Voltage**：34 V peak-peak、32 V min、33 V max、54 Average、46 RMS、39 Amplitude、38 Base、37 Top、51 Overshoot、52 Preshoot、300 V overshoot、301 V preshoot、286 Crossing、60/61/62 V upper/middle/lower、40 V time、302 Pulse top、303 Pulse base、304 Pulse amplitude、120 Area、139 Effective bits。
**Frequency（FFT）**：64–67 FFT frequency/magnitude/delta freq/delta magnitude、489 channel power、490 PSD、491 occupied bandwidth。
**Histogram**：72 p-p、166 min、167 max、74 mean、75 StdDev、73 Median、76/77/78 μ±1/2/3σ、595 μ-3σ、596 μ+3σ、79 Hits、80 Peak、307 Bin width。

## 2. 眼圖量測（Eye / Optical / PAM）
**Eye**：96 Eye height、99 Eye width、100 Eye jitter、97 Crossing %、98 Q factor、118 Duty cycle distortion、95 Extinction ratio、487 Eye one level、488 Eye zero level。
**Optical**：93 Optical average power、486 OMA（另有 Outer OMA / Outer ER）。
**PAM**：431 Level mean、432 Level RMS、447 Level skew、433 Level thickness、434 Eye skew、436 Eye level、439 PAM delta edge time、441 BER (Cumulative)、444 BER (Per Acq)；名稱表另有 SER、Level thickness、SNDR Level/Pmax、Effective Pmax、Pattern length、Peak-peak contrast（編號待對照）。

## 3. 抖動與雜訊
**時脈（Clock）**：142 Phase、153 Clock TIE、289 N-period、145 Period-period、151 +width-+width、152 -width--width、150 Duty cycle-duty cycle。
**資料（Data）**：158 Setup time、161 Hold time、154 TIE、147 Unit interval、146 Data rate、290 N-UI、291 UI-UI。（以上多數受 `HasJitterOption` 授權控制）
**圖形（SignalIntegrityGraph）**：TJ / RJ-PJ / DDJ / Composite TJ、DDJ 直方圖；TI / ISI / RN-PI 直方圖；BER Bathtub（含 Noise 版）；Jitter／Noise Spectrum；ISI vs Bit、DDJ vs Bit；ISI Filter／Noise ISI Filter；RJ,BUI Tail Fit Histogram；Noise Spectral vs Tail Fit；PI Threshold；Composite Interference；Pam4Jitter。
**控制項（Jit*）**：JitAnalysisMode、JitRjDjSrc、JitRjDjEdgeDir、JitRjDjUnits、JitRjPjAlgorithm、JitRjPjReporting、JitRnPiAlgorithm、JitRnPiReporting、JitDoRjDj／Hist／Spectrum／Noise／Smooth／MeasFn、JitMeas、JitMeasBer、JitBathtubScale、JitPatternLength、JitAutoPatternLength、JitRandomPatternLength、JitRecordLength、JitNUi、JitClockRef、JitForceClock、JitCalibrateSrc、JitLocationModel、JitRjDjPamThreshold、JitRjDjPamGraphEdgePos、JitNoiseUnits、JitNoiseGraphBit。
**控制項（Noise*）**：NoiseBwMode、NoiseCal／NoiseCalPath、NoiseRemoveRj／NoiseRemoveRn、Noise0Rn…Noise7Rn（各 PAM level）、NoiseOneRn／NoiseZeroRn、NoiseGraphLevel、BathtubScale。
**Clock Recovery**：ClockRecoveryType／Preset／Rate／Src／ClockSrc／EdgeDir／ApplyTo／State，SSC（SscEnabled／Amplitude／Frequency／Spread）、PLL specification。

## 4. InfiniiScan（= Software Trigger，`TrigSwState` 開關）
- 模式列舉 `eSwTrigMode`（控制項 `SwTrigMode`）：`SW_TRIG_OFF`、`SW_TRIG_ZONE`、`SW_TRIG_SERIAL`、`SW_TRIG_RUNT`、`SW_TRIG_NON_MONOTONIC`（Rise／Fall／Either）、`SW_TRIG_MEAS`（Measurement Limit）、`SW_TRIG_QUAL_FILTER_FOR_IVL`。
- Zone 參數：`SwTrigZoneSigId`、`SwTrigZoneMode`、`SwTrigZoneState`、`SwTrigZoneCenterTime`／`CenterVolts`／`Width`／`Height`、`SwTrigZoneLogic`（跨通道邏輯）、`SwTrigZoneSel`、`SwTrigZoneHideAll`、`SwTrigZoneDelete(All)`、`SwTrigZoneSummary`。
- Serial：`SwTrigSigId`、`SwTrigSerialDataRateStr`，需 Clock Recovery、Search String。
- 與其他功能互斥：啟用時 qualified counter 被禁用（`TrigQualifiedCounterDisallowedByInfiniiScan`）；`CSoftwareTriggerNotAllowedModel` 標示不支援的情況；選單在 RTSA 模式隱藏。
- 區域是在波形上畫框（Draw box mode）建立；另有頻域遮罩觸發區（`CGratFrequencyMaskTrigZoneCollectionModel`）。

## 5. 量測參數
**閾值**：MeasDef{Rise,Serial,"" }{ThreshMethod, ThreshSrc, ThreshApplyTo, ThreshHyst, TopPct/MidPct/BotPct, TopVolts/MidVolts/BotVolts, Top/Base, TopBaseAlg}、ThreshAutoSet、ThreshSnap。→ 上升沿、序列、一般三組獨立設定。
**眼圖／PAM**：EyeHeightAlg／EyeHeightLoc／EyeWidthAlg／EyeWidthThreshold／EyeBitWindow1,2／EyeBitWindowWidth／EyeJitFmt／ExtRatioFmt；PamLevel0–7；GenPam01…67Volts；LevelQual{Enable,Src1-3,On1-3,Criteria1-3}。
**一般**：SignalType／SignalTypeSrc、MeasAllEdges、WindowAllData、DbComp、EffBitsScale。
**MeasSetup**：Src1/Src2（EdgeDir/EdgeNum/EdgePos）、Delay Src1/Src2 Edge*、Window、Area、AcDc、AutoManual、NumEdges、RmsUnits、OmaUnits、RefImpedance(Auto)、Fft{CenterFreq,Fundamental(Mode),MeasBw,ObwPercent,Start/StopFreq}、JitUnits／PhaseJitterUnits／PhaseUnits／JitNoiseUnits／JitNoiseBit、Pam4Jitter{Algorithm,Defn,DefnFile,Units}、PamEyeProbability(State)、PamJitterCount、PamLevel、PamThreshold、SigmaN{File,Level,Std}、XCorrTime、Lfp{Delay,Length}、DfeTieLocation。
**未取得**：各控制項的**列舉選項值**（例如 ThreshMethod、TopBaseAlg 有哪幾種）不在本 exe，需從 `Phoenix.dll` 或實機取得。

## 關鍵檔案
`Infiniium.Gui/CMeasurementCategories.cs`、`Infiniium.Gui.GuiUtils/CMeasurementMgr.cs`、`Infiniium.Gui.SetupPanels/CMeasurementConfigSetupPanelModel.cs`、`CJitterSetupPanelModel.cs`、`CNoiseSetupPanelModel.cs`、`CSwTrigModeModel.cs`、`CTrigSw*Panel.xaml`、`CTrigGalleryModel.cs`。
