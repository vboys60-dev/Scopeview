# 量測參數的選項值（取自 InfScopeDLL.dll 字串登錄表）

來源：`Infiniium/InfScopeDLL.dll`（74.5 MB，x64 原生）`.rdata` 中的控制項登錄表，用 `strings -a -t x` 抽出，位址約 0x3428a50–0x35d7c70。
格式：**控制項** — UI 顯示文字 / SCPI 簡寫 / 內部代號。靜態字串，**尚未驗證實際演算法**（需反組譯，Hopper 分析進行中）。

## 閾值（Threshold）
**`MeasDefThreshMethod` / `MeasDefRiseThreshMethod` / `MeasDefSerialThreshMethod`**（一般 / 上升沿 / 序列三組）：
| 代號 | UI 文字 |
|---|---|
| thr1090 | 10%, 90% of top, base（UI 另有 10/50/90 的版本） |
| thr2080 | 20%, 80% of top, base（含 20/50/80 版本） |
| thrPam1090 | 10%, 90% of levels |
| thrPam2080 | 20%, 80% of levels |
| thrCustPct | Custom: % of top, base |
| thrCustV | Custom: thresholds (low, mid, up) |
| thrCustLvl | Custom: thresholds (low, up) |
| thrCustPam | Custom: thresholds ± hysteresis（PAM） |
| thrAutoPam | Auto: 50% of levels |
（另有 "Custom: threshold +/- hysteresis"、"Custom: thresholds +/- hysteresis" 兩個文字，與代號的對應未確認。）

- **`…ThreshSrc`**：`thrAllSrcs`（All Waveforms）／`thrIndivSrcs`（Individual Waveforms）。
- **`…ThreshApplyTo`**、**`…ThreshHyst`**（Hysteresis）、**`MeasDefThreshSnap`**、**`MeasDefThreshAutoSet`**。
- **`ThreshAutoSetMode`**：`AutoSetMemory`／`AutoSetUi`／`AutoSetUiForce`（UI Force Wait）／`AutoSetFast`。
- 百分比與電壓值：`MeasDef{,Rise,Serial}{Top,Mid,Bot}{Pct,Volts}`；PAM 閾值 `GenPam01…67Volts`（01/12/23/34/45/56/67 Threshold）。

## Top / Base
- **`MeasDef{,Rise,Serial}TopBaseAlg`** 的選項代號：`histMinMax`、`histOnly`、`minMaxOnly`、`PamUserDef`。（UI 文字未擷取到）
- **`…TopBaseSens`**（靈敏度）、`MeasDef{,Rise,Serial}Top`／`Base`（手動值）。
- PAM：`PamLevel0…7`（PAM Level 0…7，Auto Setup Gen 1…7），模式 `PAM Auto Levels`／`PAM Custom Levels`。

## 訊號類型 `MeasDefSignalType`
Unspecified、NRZ、PAM-3、PAM-4、PAM-6、PAM-8、MIPI C-PHY、DDR5、mmW (Ext. Mixer)、Frequency Extension、Spectrum Analysis (DDC)、RTSA、OMA。
內部代號：signalUnspecified／Nrz／Pam3／Pam4／Pam6／Pam8／Cphy（+Peer1/2）／Ddr5Dq／Ddr5Dqs／Ddr5Ca4／MmWave(BwExt)／Sa／Rtsa／Oma。SCPI 簡寫：UNSP、NRZ、PAM3…CPHY、DDR5、MMW、FEXT、SPEC、RTSA、OMA。

## 眼圖
| 控制項 | 選項 |
|---|---|
| `MeasDefEyeHeightAlg` | Use Measured Data（eyeMinMax）／Extrapolate Using Standard Deviation（eyeExtrap） |
| `MeasDefEyeHeightLoc` | At Recovered Clock Location（CLOCk, eyeLocRecClock）／Find Eye Opening（FIND, eyeLocFindEye） |
| `MeasDefEyeWidthAlg` / `EyeWidthThreshold` | Automatic（eyeThreshAuto）／Use Measurement Threshold（SPECified, eyeThreshSpec） |
| `MeasDefEyeBitWindow1/2/Width` | Eye Window Start／Stop／Width |
| 眼寬基準 | Based on Center Eye（CEYE, basedOnCenterEye）／Per Eye Level（PELevel, perEyeLevel） |
| `Slicer Sample Timing` | `SlicerSampleTiming`（PAM 眼圖取樣時機） |
另有 `MeasDefEyeAlg`、`MeasDefEyeType`、`MeasDefEyeJitFmt(Event)`、`MeasDefExtRatioFmt`、`MeasDefEffBitsScale`（ADC／Display）。

## 電位限定（Level Qualification）
`MeasDefLevelQualEnable`、`Src1-3`、`On1-3`、`Criteria1-3`：Above Middle Threshold（aboveThr）／Below Middle Threshold（belowThr）／Between Upper, Lower Thresholds（betThr）／Not Between Thresholds（notBetThr）。

## 閘控與視窗
`MeasDefGatingEnable/Start/Stop`（GUI 反編譯沒有的新發現）、`MeasDefWindowAllData`、`MeasDefMeasAllEdges`、`MeasDefAnyFunctions`。

## 抖動／雜訊
- **`JitRjPjAlgorithm`（RJ Method）／`JitRnPiAlgorithm`（RN Method）**：Spectral Only（SPECtral, algSpectralOnly）／Tail Fit Only（TAILfit, algTailfitOnly）／Spectral & Tail Fit（BOTH, algSpectralTailfit）。
- **`JitRjPjReporting`／`JitRnPiReporting`**：Report Spectral（repSpectral）／Report Tail Fit（repTailfit）。
- **`JitRjDjEdgeDir`**：edgeRis／edgeFall／edgeRisFall。
- **使用者指定**：`JitterScopeRj`（Scope RJrms）、`SpecifyUserRj`／`JitterUserRj`、`SpecifyUserRn`、`Noise0Rn…Noise7Rn`。
- **PAM 邊緣**：`JitRjDjPamGraphEdgePos` 的選項 0/1、1/2 … 6/7（相鄰 level 間的邊緣）。
- **TIE 濾波器** `TieFilterType`：Highpass／Bandpass／Lowpass；`TieFilterTieShape`：Rectangular／20dB／40dB／60dB Decade／First Order／Second Order；`TieFilterStartFreq`／`StopFreq`／`DampingFactor`。
- **Clock Recovery 模式**：Fully Automatic（clkFullAuto）／Semi-Automatic（clkAuto）／Manual（clkFix）。

## InfiniiScan `SwTrigMode`
swTrigOff、swTrigMeas（Measurement，`SwTrigMeasSetup`）、swTrigZone（Zone Qualify）、swTrigSerial（Generic Serial，`SwTrigSerialDataRateStr`、Search String）、swTrigNonMono（Non-monotonic Edge：`NonMonotonicHyst`、`NonMonotonicEdgeDir` rising/falling/either）、swTrigRunt（`RuntUpperLevel`、`RuntLowerLevel`）、swTrigQualFilterForIVL。另有 "Extended Bandwidth (EBW)" 與 `HwToSwTrigDelay`（相對硬體觸發的延遲）。

## 尚未得到
- **演算法本體**：怎麼從波形算出 Rise time、怎麼找 Top/Base、RJ/PJ 如何分離——需要反組譯函式（Hopper 分析完成後用 `xrefs` 追 `thr1090`、`histMinMax`、`algTailfitOnly` 等代號）。
- Top/Base 選項的 UI 顯示文字。
