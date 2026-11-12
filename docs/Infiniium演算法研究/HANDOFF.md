# Infiniium.exe 分析交接

日期：2026-11-12

## 目標
分析 `Infiniium.exe`（Keysight Infiniium 示波器 GUI）的**通訊協定**與**量測項目／參數／量測方式**。

## 目標檔案
- `/Users/lianshi/Desktop/工作用區/Infiniium.exe`，467,875,968 B，PE32+ x64 .NET（WPF）。
- 體積 99% 是 managed resources（464 MB，全是 BMP/JPG/PNG 圖片）。程式碼與中繼資料僅約 2 MB。

## 已完成
1. **rea 與 Ghidra 連動已實測**：`open_binary` 需帶 `provider_id: "ghidra"`（預設是 Hopper）；通用 Mach-O 要先 `lipo -thin`（注意 `/bin/echo` 的架構是 arm64e）。Ghidra 12.1.4 位於 `~/Applications/ghidra_12.1.4_PUBLIC`。
2. **rea 打不開本檔**：`inspect_managed_artifact` 有固定 128 MB 的 snapshot 上限（不能調），本檔 446 MB 會 `resource_constraint`。
3. **改用 `ilspycmd`**（`~/.dotnet/tools/ilspycmd`，11.1.0.9782）：`ilspycmd -p -o <dir> Infiniium.exe`，約 7 秒完成。
4. 反編譯結果已複製到 `/Users/lianshi/Desktop/工作用區/Infiniium_decompiled/`（25 MB，1,934 個 .cs、805 個 .xaml，已排除圖片）。

## 通訊協定結論
本 exe 只是前端，**不含 SCPI 伺服器實作**，伺服器在原生 DLL：`Phoenix.dll`（30 個 P/Invoke）、`InstrumentConfigInterface.dll`（14 個）。這兩個 DLL 不在目前資料中，需從安裝目錄取得。

- 儀器對外介面（`CScpiServersStatusPanel.xaml.cs`）：VXI-11 `TCPIP0::<host>::inst<N>::INSTR`、Socket `...::<port>::SOCKET`、HiSLIP `...::hislip<N>,<port>::INSTR`、USB-TMC `USB0::10893::<model>::<serial>::0::INSTR`，另有 Telnet、GPIB。經 `CInfInput.WmGetRemoteInterfaces` 向原生層查詢。
- `SecureInstrComms` 可覆寫 VXI-11／Socket／Telnet 是否啟用（外部服務 `https://<host>:4201`）。
- 客戶端用途：VISA COM（`CInstrumentBrowserDlg`、`LOPowerCalibration`，送 `*RST;:OUTP ON;:FREQ`、`:POW`）；HTTP REST 明文 `PATCH http://<Url>/api/v3/chassis` 與 `.../ports/<n>/breakouts/1/deskew`（`CSSPRQSetupModel`）；Named Pipe `DcaXCommandPipe`（`CGui.cs`，單一實例轉送參數，結尾送 `/connect`）。

## 量測結論
GUI 只有量測**定義與設定介面**，演算法在原生層。已列出：
- 基本波形、眼圖、PAM-4、抖動／雜訊、功率、遮罩／極限測試、Clock Recovery、XTalk、Equalization、De-embedding 等類別。
- 關鍵檔案：`Infiniium.Gui.GuiUtils/CMeasurementMgr.cs`（2,863 行）、`Infiniium.Gui.SetupPanels/CMeasurementConfigSetupPanelModel.cs`（約 57 個 `MeasDef*`／`MeasSetup*` 控制項：閾值方法、百分比／電壓、Top/Base 演算法、Rise 與一般兩組）、`AgilentTechnologies.Oscilloscope.Widgets.CommonWidgets/CMeasurementIcons.xaml`（量測項目名稱）。
- 控制項選項值（列舉內容）尚未取得，可能在原生層。

## 未完成／下一步
- [ ] 取得 `Phoenix.dll`、`InstrumentConfigInterface.dll`，用 rea（Ghidra provider）分析 SCPI 解析與量測演算法。
- [ ] 找出 `MeasDef*` 控制項的列舉選項值（閾值方法、TopBaseAlg 等）。
- [ ] 依需求深入單一類別（抖動分離 RJ/PJ/DDJ、PAM-4 眼圖、功率分析）。

## 注意
- 只做靜態分析，未執行程式；通訊關鍵字只掃過 18 個檔案，自訂封裝的通訊可能漏掉。
- 若用 rea 開大檔，需先調 `ghidra.startup_timeout_ms`（預設 330 秒），MCP 用戶端逾時由 host 控制。
- scratchpad 內的 `out/`、`echo_thin` 為暫存，以工作區的 `Infiniium_decompiled/` 為準。

---

## 更新（續）：原生層分析

### 目標修正
- `Phoenix.dll`（133 KB，C++/CLI）**不是量測引擎**，是外部混頻器（Ext. Mixer）USB 驅動（WinUSB），匯出 30 個硬體控制函式（`openMixer`、`setPLLFrequencyMHz`、`setIFPath`、`readCalDataXML` 等）。先前「SCPI／量測演算法在 Phoenix.dll」的推測是錯的。
- 真正的控制層是 `Infiniium/InfScopeDLL.dll`（74.5 MB，x64 原生，匯出 333 個，320 個為 `Wu*`）。`InfThunker.dll`、`InfOsThunker.dll`、`Infiniium.exe` 匯入它。
- `InfScopeDLL.dll` 只是派發層：`WuMakeMeas` → `sub_1819c8080` → 主執行緒訊息佇列（`sub_1812da4d0`）。演算法在它匯入的外部庫，**這些庫不在 `Infiniium/` 資料夾內**：
  `OneSrcEval`、`TwoSrcEval`、`EZJitMeasure`、`EyeContour`、`EffBits`、`CalcPN`、`DenoiseJNU/POJ/TJpp/Wfm`、`DspUtils`、`FindPhase`、`Find3dBPoint`、`CPhyThreshold`、`PilotPhaseDetect`、`TrainFFE`、`mclmcrrt25_1`（MATLAB Compiler Runtime，推測部分庫由 MATLAB 編譯，未驗證）。

### rea 使用經驗
- Ghidra 開 74 MB 的 `InfScopeDLL.dll` 失敗：`OutOfMemoryError`（JVM 堆積 2G）。需在啟動 rea 的環境加 `GHIDRA_HEADLESS_MAXMEM`（或 `REA_GHIDRA_DISABLED_ANALYZERS`）並重啟，執行中無法改。
- 改用 Hopper（`provider_id: "hopper"`）成功，分析約 15–20 分鐘；已用 `update_analysis_settings` 把 `ghidra`/`hopper.startup_timeout_ms` 調為 1,800,000。
- 內部函式為 `sub_xxxx`，只有匯出有名字（`exp_Wu*`）。

### 量測參數選項值（靜態字串）
`strings -a -t x InfScopeDLL.dll` 可抽出 `.rdata` 控制項登錄表（約 0x3428a50–0x35d7c70），選項字串緊鄰控制項名稱。完整內容見 **`MEASUREMENT_PARAM_OPTIONS.md`**（閾值方法 12 種、Top/Base 演算法、訊號類型、眼圖演算法、RJ/RN 方法、TIE 濾波、InfiniiScan 模式等）。量測項目編號→名稱與分類見 **`MEASUREMENTS.md`**。

### dsp.dll 分析
- 476 KB，398 個匯出，通用 DSP 數學庫（雙精度 `dsp*`、單精度 `dspf*`，Intel MKL）。**不含量測邏輯**。
- 量測相關原語：`dspi_edge`（準位穿越）、`dsps_hist`、`dsps_peak/min/max/mean/median/rms/pop_stddev/skew/excess`、`dspi_hilbert/analytic/phase/unwrap`（TIE／相位）、`dspi_fft/rfft`、`dspi_window_*`、`dspd_rsmp`／`dsp_interp`／`dsp_cspline`、`dspi_differ/integ`、`dsps_lin_regres`。
- `dspi_edge`（0x6102df60）反編譯：輸入結構含取樣間隔、資料指標、點數；準位參數 + 旗標（bit0 上升穿越：前一點 ≤ 準位 < 目前點；bit1 下降穿越：前一點 ≥ 準位 > 目前點）；輸出「索引 × 取樣間隔」覆寫原陣列、取樣間隔重設為 1.0；結構第 6 欄非 0 時回傳 -1。**反編譯中看不到線性內插運算**（可能被 Hopper 省略，未確認）。
- `dsps_hist`（0x61046c60）只是外層，轉呼叫 `sub_61046d20`，未往下追。

### 待辦（更新）
- [ ] 取得上述演算法庫（特別是 `OneSrcEval.dll`、`TwoSrcEval.dll`、`EZJitMeasure.dll`、`EyeContour.dll`），可能在儀器上或其他安裝路徑。
- [ ] 若無法取得：追 `InfScopeDLL.dll` 的派發器 `sub_1812da4d0`，建立「控制項值 → 呼叫哪個外部庫函式」的對照（只能看到參數傳遞）。
- [ ] 驗證 `dspi_edge` 是否有內插；追 `sub_61046d20`（`dsps_hist` 本體）。
- [ ] 找出 Top/Base 選項（`histMinMax`/`histOnly`/`minMaxOnly`/`PamUserDef`）的 UI 顯示文字。

---

## 更新（續二）：演算法庫與官方說明（2026-11-12）

- **演算法庫找到了**：在 `~/Desktop/claude-cowork/示波器截圖/N8900A/6_MATLAB_Compiled/`（虛擬機路徑 `C:\Mac\Home\Desktop\claude-cowork\...`，即 Parallels 共用資料夾）。40 多個庫，每個 `.dll`（約 12 KB 薄殼）加 `.ctf`（zip）。**`.m` 已加密**（檔頭 `V2MCC`），只能看檔名結構，不能還原公式。
- **缺少** `OneSrcEval`、`TwoSrcEval`（應是基本波形量測主體，可能不是 MATLAB）。
- **官方 Help** 在 `claude-cowork/示波器截圖/N8900A/Keysight Infiniium Offline Oscilloscope Analysis Software Help.tar.gz`（1,129 頁）。Top/Base（上下 40% 直方圖、中間 20% 忽略、<5% 退回 Min/Max）、閾值、邊緣內插、時間／電壓定義、眼圖、RJ/PJ（頻譜法 + Tail Fit）、dual-Dirac、clock recovery 等演算法定義已整理在 **`ALGORITHMS.md`**。
- 解壓暫存在 scratchpad `help/`、`ctf/`，以 `ALGORITHMS.md` 為準。

### 待辦（更新）
- [x] 取得演算法庫（加密，只得結構）
- [x] 找 Top/Base 與其他量測的演算法定義（官方 Help）
- [ ] 找 `OneSrcEval`／`TwoSrcEval`；InfiniiScan 官方說明（離線 Help 沒有）
- [ ] 驗證 `dspi_edge` 是否為內插邊緣偵測；追 `sub_61046d20`
- [ ] 用 `claude-cowork` 內 DSO-X 實測資料驗證文件所述演算法（黑箱比對）

## 更新（續三）：實測驗證第一輪（Codex 審 + Opus 複審）
- 報告：scratchpad `verify/codex_report.md`；Opus 複審已推翻 4 項判定（Preshoot、DCD、Vavg、事件選取），根因是只拿 ALGORITHMS.md 當基準，而官方 Help 各量測有專頁且部分與總覽頁矛盾。
- 已修正 `ALGORITHMS.md`：Preshoot 以 `Preshoot.htm` 為準；Vavg/Vrms 可選單週期或整個畫面；4 點邊緣規則；眼圖 DCD（中位數）與 EZJIT Plus DCD（平均）區分。
- 可採用結論：Top/Base 40/20/40 與 5% 回退一致；眼高眼寬為 Extrapolate（±3σ／UI−6σ）、無 Measured Data 選項；TJ/RJ/DJ 與 BER→Q 未實作；閾值無絕對電壓入口；程式 σ 為迭代裁切、Vtop/Vbase 非垂直直方圖峰值。
- 未驗證：與 DSO-X／Infiniium 實際輸出一致性（本輪未重跑儀器）；01 案 8 µs 未被 Opus 重跑；Top/Base 直方圖範圍（資料 min–max vs ADC 滿刻度）影響 5% 回退。
- 產品程式碼未動，也未建議改動；要不要改由使用者決定。

## 更新（續四）：Top/Base 直方圖範圍（待辦第 2 點）
官方未載垂直範圍與格數。敏感度實驗見 `ALGORITHMS.md` §7：乾淨方波不受影響；雜訊 PWM 的 Base 回退與否取決於格寬；正弦的 Top/Base 取極值或峰值格也取決於範圍。需 Infiniium 實機資料定案。

## 更新（續五）：官方 Help 矛盾掃描（待辦第 3 點）
Codex 初掃 + Opus 複審，結果在 `ALGORITHMS.md` §8（含 13 項矛盾／缺漏與預設值表）。`ALGORITHMS.md` 已修正：眼高眼寬外插公式為 ±3σ（原誤寫為 ± σ）、Preshoot 描述改以專頁為準。未核對範圍列在 §8 開頭。

## 更新（續六）：實作規格
新增 `IMPLEMENTATION_SPEC.md`（約 1,030 行，由 Fable 撰寫偽程式碼與邊界，我只做索引）。內容：已確定／待驗證／未知總表；Top/Base、閾值、基本波形、眼圖、抖動雜訊各節的偽程式碼與邊界條件；N1–N13 裁決（N13 為規格自編，指 PAM Eye Opening Probability，`ALGORITHMS.md` §8 原未編號）；與 Python 實作差異與優先序 P0–P3；實機驗證計畫 V1–V20；27 項開放問題。
- 低信心項：N2、N7（Q 定雙側）、N9（改成可調參數）、N13、Top/Base 直方圖範圍、Eye Contour、BER→Q、RJ/PJ 頻譜、Tail Fit、Dual-Dirac 求法、TIE 濾波響應。
- 新發現：`dlg_MeasurementThreshold` 的 Top/Base 選項為 Standard（預設）／Histogram／Min, Max／Custom；與內部代號對應仍屬推測。
- 差異表只比對 measure/edge/eye/jitter/clock 五檔，不代表產品整體缺漏。
- 規格尚未經實機驗收；DSO-X 讀值僅旁證，主基準是 N8900A。產品程式碼未修改。
