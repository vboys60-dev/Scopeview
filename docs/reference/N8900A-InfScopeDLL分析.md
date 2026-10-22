# InfScopeDLL.dll 原生反組譯與量測功能分析

分析日期：2026-10-22。已先閱讀 `docs/reference/ilspycmd-操作說明.md`。所有分析產物及重現腳本均置於本資料夾；原 DLL 僅以讀取方式開啟，未執行或修改。

## 結論與分析範圍

此檔為 **Windows x86-64 原生 PE32+ DLL**，不是可用 ilspycmd 還原成 C# 的 .NET 組件。已完成可執行區段的線性組合語言反組譯、一般／延遲匯入表、匯出表、ASCII／UTF-16LE 字串、C++ RTTI／虛擬函式表及重點呼叫分析。這些產物不是可重新編譯的完整 C++ 專案。

最具體的發現：

- 抖動：有 `cRjDjMeasOp`、`cRJDJCDFModel`、`cDualDiracCDFModel`、`cJitterSpectrumOp`、`cBerBathtubOp`、`cJitterTailFitBathtubOp` 等類別。已還原 Dual-Dirac 類別內一段使用兩次 `erfc` 的數值核心。
- 眼圖：有 `cRealTimeEyeMeasOp`，以及眼高、眼寬、交越、眼圖抖動、輪廓與週期的量測識別字。已確認呼叫外部 `EyeContour.dll!mlfEyeContour` 與 `PlotRTEye.dll!mlfPlotRTEye` 的位置。
- 時脈：有邊緣搜尋策略、時脈恢復相依處理、PLL 前後時脈資料，以及一／二／三／五階 PLL 和 explicit／equalized 模式的設定／報表字串。這些證據尚不足以還原各階 PLL 的差分方程及係數。
- `A_MeasJitterComponents` 字串所屬區段確實呼叫 `EZJitMeasure.dll!mlfEZJitMeasure`。完整抖動分解與擬合有外部模組邊界，不能把本 DLL 的包裝程式當成全部演算法。

## 檔案辨識與工具

| 項目 | 結果 |
|---|---|
| 來源 | `N8900A/1_Core/InfScopeDLL.dll` |
| 大小 | 74,521,216 bytes，約 71.07 MiB |
| SHA-256 | `1dc2357b092030a1967ddb12c99f53ae8d4808af7cd340f56d53a2c8a750a949` |
| `file` | `PE32+ executable (DLL) (GUI) x86-64, for MS Windows` |
| PE Machine | `0x8664`，AMD64 |
| CLR Runtime Header | RVA 與大小皆為 `0`，沒有 CLR 組件入口 |
| 偏好載入基址 | `0x180000000` |
| 匯出 | 333 筆 |
| 匯入 | 1,797 筆，含一般及延遲匯入 |
| `.pdata` | 176,208 筆 runtime-function 記錄；不等於原始碼函式數量 |
| RTTI | 掃描出 5,217 筆類別 TypeDescriptor 名稱候選 |

`file` 的原生 PE 判斷、MSVC C++ RTTI、MFC／VC Runtime 匯入及空的 CLR directory 相互一致。雖然環境已有 `ilspycmd` 與 `dotnet`，依操作說明的適用範圍，本次不使用 ilspycmd。

使用 `/usr/bin/objdump`（Apple LLVM 21.0.0）、`/usr/bin/strings`、Python 3 標準函式庫。PATH 未找到 `r2`／`radare2`／`rabin2`／Ghidra，`/Applications` 也未見 Ghidra、IDA、Hopper；未安裝額外套件。Python 環境亦沒有 pefile、capstone、lief，因此以本資料夾中的腳本解析 PE。

CodeView RSDS 記錄指向 `C:\kd\Inf\1180\source\Gui\Gui\bin\Release\InfScopeDll.pdb`，age 為 1；這只是二進位內的建置路徑，本次沒有載入該 PDB，不能由此宣稱已有私有函式符號。詳細欄位見 [pe-summary.json](../../N8900A/InfScopeDLL_decompiled/pe-summary.json)。

## 位址與證據讀法

本文件表格均以 **RVA** 為主；偏好 VA = `0x180000000 + RVA`。實際載入後須使用程序的實際基址處理 ASLR。檔案 offset 與 RVA 不同，請用 `strings-focus.tsv` 的對照欄位，不能把 `strings -t x` 的 offset 直接交給反組譯器當 VA。

證據分為：匯出符號（名稱確定）、RTTI／vftable（類別與槽位可定位，但方法名稱未知）、字串引用（證明該區段使用字串，功能名仍屬推定）、指令／匯入呼叫（可確認運算或模組邊界）。`focus-functions.asm` 中的 `sub_...` 是分析標籤，非原始名稱。

LLVM 會將未具名位址顯示成最近的匯出符號加 offset，例如 `<CallMethod+...>`；**這不表示整段程式真的屬於 CallMethod**。請以 RVA、`.pdata` 範圍及旁註證據定位。`.pdata` 記錄也可能是例外處理 funclet，不能直接當成完整原始函式。

## 抖動與 BER／bathtub

### 類別與重要區段

| 類別／識別字 | 相關 RVA | 可確認內容 |
|---|---|---|
| `cRjDjMeasOp` | vftable `0x378B688`；slot 3 → `0x19AA3A0` | RTTI 確認類別；槽位名稱未知，該槽不能直接命名為 RJ/DJ 數值計算 |
| `cRJDJCDFModel` | vftable `0x376FBD8` | CDF 模型類別；slot 1 指向 `0x2B68897`，未據此推定具體數值模型 |
| `cDualDiracCDFModel` | vftable `0x376FBF0`；slot 1 → `0x18E8EC0` | 152 bytes 的 `erfc` 數值核心，見下一節 |
| `cJitterSpectrumOp` | vftable `0x378B9D8` | RTTI 確認頻譜操作類別；未還原整段 FFT 處理流程 |
| `cBerBathtubOp` | vftable `0x378BAF8` | RTTI 確認 BER bathtub 操作類別 |
| `cJitterTailFitBathtubOp` | 見 `rtti-focus-vtables.tsv` | 尾端擬合 bathtub 操作類別 |
| `A_MeasJitterComponents` | `0x115C6A0..0x11613F4` | 多處字串引用；在 `0x115F6CD` 呼叫外部 EZJitMeasure |
| `A_MeasJitterComponentsClockData` | `0x11541D0..0x11543A6` | 時脈資料處理相關區段的字串證據 |
| `RJDJMeasResult` | `0x116D640..0x116DE76` | 結果資料處理相關區段 |
| `GetBathtubDataPlot` | `0x18E9A30..0x18EA0CD` | 資料曲線字串引用 |
| `GetBathtubModelPlot` | `0x18EA940..0x18EAD91` | 模型曲線字串引用 |
| `GetJitterTailfitBathtubDataPlot` | `0x18EBB90..0x18EC021` | 尾端擬合資料曲線字串引用 |
| `GetJitterTailfitBathtubModelPlot` | `0x18EC030..0x18EC4CC` | 尾端擬合模型曲線字串引用 |
| `cNoiseBerBathtubOp::GetNoiseBathtubModelPlot` | `0x19B0750..0x19B0D0C` | 含完整類別／方法名的診斷字串；仍非匯出符號 |

位址範圍的右端皆不包含在內。完整槽位與其目標見 [rtti-focus-vtables.tsv](../../N8900A/InfScopeDLL_decompiled/rtti-focus-vtables.tsv)；完整候選區段與理由見 [focus-functions.tsv](../../N8900A/InfScopeDLL_decompiled/focus-functions.tsv)。

設定字串包含 `algTailfitOnly`、`algSpectralTailfit`、`repTailfit`、`Pam4JitterJnu`、`Pam4JitterDualDirac`、`Pam4JitterPcie6dd`、`IEEE JnU Jitter Extrapolation`、`PCIe6 12E Jitter Extrapolation`。可確認存在這些模式／選項名稱，不能僅憑選項推定其數學實作。報表字串另含 BUJ、PJ、DJ、UDJ 的 Dual-Dirac 結果欄位。

### 已還原的 Dual-Dirac 數值核心

依 RTTI，`0x18E8EC0` 是 `cDualDiracCDFModel` 的 slot 1。指令在 `0x18E8F06` 與 `0x18E8F33` 經 IAT `0x32AD330` 呼叫 CRT `erfc`；不是僅以名稱猜測。常數已直接讀取二進位：

| 常數 RVA | 原始 bytes，little endian | 意義 |
|---|---|---|
| `0x3372670` | `0000000000000080` | 負零 bit pattern，供 XOR 翻轉 double 符號 |
| `0x33724B8` | `000000000000d03f` | `0.25` |
| `0x376FCB0` | `cd3b7f669ea0d63f` | `0.3535533905932738`，即 `1/(2√2)` |

以分析用參數名表示，其指令等價運算為：

```text
k = 0.3535533905932738
result = (double_at_this_plus_8 * 0.25) * (
    erfc(((-x - x) - a) * k / s_left)
  + erfc((b - (x + x)) * k / s_right)
)
```

Win64 呼叫慣例對照：RCX=this、XMM1=x、XMM2=s_left、XMM3=a；進入函式時的 `[RSP+0x28]` 為 s_right、`[RSP+0x30]` 為 b。`this+8` 欄位、a／b 的物理意義及單位尚未確認，s_left／s_right 名稱亦為分析命名。這段運算與雙尾 Gaussian／Dual-Dirac 模型相容，但不代表已還原 RJ、DJ 的估計器、擬合方式、BER 正規化或完整抖動分離流程。

原始指令見 [dual-dirac-kernel.asm](../../N8900A/InfScopeDLL_decompiled/dual-dirac-kernel.asm)，手動整理的等價 C++ 偽碼見 [dual_dirac_reconstructed.cpp](../../N8900A/InfScopeDLL_decompiled/dual_dirac_reconstructed.cpp)。偽碼不是自動反編譯成果，也未假定原本不存在的錯誤處理。

## 眼圖量測

`cRealTimeEyeMeasOp` 的 RTTI 對應 vftable RVA `0x378B448`；slot 2 指向 `0x19A73C0`。該槽只足以作為類別定位入口，不能直接當成眼圖統計演算法。

| 量測／處理識別字 | 證據 |
|---|---|
| `measEyeHeight` | 字串 RVA `0x33680D8`，引用區段 `0x29EC30..0x29EE0C` |
| `measEyeWidth` | 字串 RVA `0x3368358`，引用區段 `0x29F6F0..0x29F8D2` |
| `measEyeJitter`、`measEyeJit` | 字串 RVA `0x3368430`、`0x3368690` |
| `measEyeCross`、`measEyeEdge` | 字串 RVA `0x3368758`、`0x3368820` |
| `measEyeOneLevel`、`measEyeZeroLevel` | 字串 RVA `0x3368160`、`0x33681E0` |
| `measEyeTopBase`、`measEyeContour`、`measEyePeriod` | 字串 RVA `0x33688F0`、`0x3368930`、`0x3368F00` |
| `A_AnalyzeEyeContour` | 字串引用區段 `0x10EAAC0..0x10EB0EB` |
| `EyeContour.dll!mlfEyeContour` | 呼叫指令 RVA `0x1140C6D`，經 thunk `0x252654C` |
| `PlotRTEye.dll!mlfPlotRTEye` | 呼叫指令 RVA `0x1629CF8`，經 thunk `0x2527B92` |

前述 `meas...` 是註冊／分類識別字，**不是已恢復的 C++ 方法名**；低位址的引用區段多為初始化／註冊程式，不能當作眼高或眼寬計算本體。眼圖直方圖、閾值、插值、眼高／眼寬的精確公式尚未完成還原。`cMystFpgaSerdesCharacterizeEye` 等 SerDes 硬體掃描類別也存在，需與示波器的即時眼圖量測分開解讀。

## 時脈、邊緣與 PLL

| 類別／區段 | 相關 RVA | 判讀 |
|---|---|---|
| `cFindAllEdgesSwStrategy` | vftable `0x33742C0`，slot 1 → `0x10CC190` | 軟體邊緣搜尋策略，方法名未知 |
| `cFindAllEdgesPAMStrategy` | vftable `0x33742D8`，slot 1 → `0x10CD8E0`、slot 2 → `0x10CE010` | PAM 邊緣搜尋策略，方法名未知 |
| `cFindAllEdgesHwStrategy`、`cFindAllEdgesDFEStrategy`、`cFindAllEdgesCPHYStrategy` | 見 RTTI 表 | 硬體、DFE、C-PHY 的策略類別 |
| `A_MeasClockRecoveryDepend` | `0x10F4010..0x10F41E7` | 時脈恢復相依處理的字串引用 |
| `A_MeasClockRecoveryDependMultiSrc` | `0x10F4BD9..0x10F4DBF` | 多來源相依處理；可能是 funclet，不能只憑邊界認定完整函式 |
| `A_DoMeasClockRecoveryDependMultiSrc` | `0x10FB340..0x10FB585` | 同時有 DDR5／MIPI C-PHY 診斷字串 |
| `PrePLLClocks`／`PostPLLClocks` | `0x10FF4E0..0x1100659` | 同區段使用 PLL 前後資料名稱，可作為追蹤入口 |
| `*ClockRecoveryGenInterop` 名稱集合 | `0x12A7020..0x12A79B6` | 字串分派／註冊入口；不是各種 PLL 演算法本體 |
| `measPhaseJitter` | 引用區段 `0x2D0550..0x2D0709` | 相位抖動量測識別字的註冊線索 |
| `measPeriod` | 字串 RVA `0x336EBD8` | 週期量測識別字 |

`*ClockRecoveryGenInterop` 包含 Equalized、Explicit、ExplicitNoEq、FirstOrder、SecondOrder、ThirdOrder、FifthOrder、StandalonePll、FixedButNotAutomatic、FlexRay、MipiCphy、DDR5 等名稱。

設定／報表字串顯示一／二階有 Loop Bandwidth、二／三階有 Damping Factor、三階有 Omega Natural／Omega Pole、五階有 Omega 0／Omega 1／Omega LF，並有 PLL Settling。Explicit 模式另含 Clock Source、Clock Multiplier、Edges。上述是可讀到的參數介面證據；未從本次指令分析取得迴路濾波器係數、鎖定判定或各階離散化細節。另有 `Use Hw Clock Recovery`、`PllIdleClocks`、`PLL Phase Align` 的設定字串。

## 對外函式入口

以下名稱直接來自 PE 匯出表，可作為程式進入點；多數是 UI／控制包裝，不能視作數值核心。

| 匯出名稱 | ordinal | RVA |
|---|---:|---|
| `WuCopyClockRecoverySettings` | 31 | `0x198B4F0` |
| `WuExplicitClockRecovery` | 55 | `0x198B4D0` |
| `WuGetClockRecWizardInfo` | 71 | `0x1F14D40` |
| `WuGetEyeScanResults` | 81 | `0x126EC40` |
| `WuGetRjDjWizardString` | 153 | `0x1F14D60` |
| `WuSaveJitterData` | 268 | `0x1A4DE80` |

例如 `WuCopyClockRecoverySettings` 在 RVA `0x198B4F0` 以 `jmp` 跳到 `0x1663D70`。`WuReadClock` 也有匯出，但僅憑名稱不能認定它是波形時脈量測，故未納入核心清單。

## 外部演算法邊界

已從指令追到以下實際呼叫，而非僅看 DLL 檔名：

| 外部函式 | 呼叫點 RVA | 包含它的 `.pdata` 區段起點 |
|---|---|---|
| `EZJitMeasure.dll!mlfEZJitMeasure` | `0x115F6CD`、`0x1163C86` | `0x115C6A0`、`0x11616D0` |
| `EyeContour.dll!mlfEyeContour` | `0x1140C6D` | `0x1140A8E` |
| `PlotRTEye.dll!mlfPlotRTEye` | `0x1629CF8` | `0x1629BFA` |
| `DenoiseTJpp.dll!mlfDenoiseTJpp` | `0x19C0E54` | `0x19C09E0` |
| `DenoiseJNU.dll!mlfDenoiseJNU` | `0x19C19AC` | `0x19C1330` |
| `DenoisePOJ.dll!mlfDenoisePOJ` | `0x19C2AFC` | `0x19C2568` |

另外有 `mclmcrrt25_1.dll` 的 mxArray／mcl runtime 匯入，以及 `libfftw3-3.dll` 的 `fftw_plan_dft_1d`、`fftw_plan_dft_r2c_1d`、`fftw_plan_dft_c2r_1d`、`fftw_execute`。前者與 MATLAB Compiler 模組介面一致；後者證明本 DLL 使用 FFTW，但尚未逐條建立其與 jitter spectrum 的資料流關係。`dsp.dll` 另提供重取樣及複數／縮放運算。

完整外部呼叫證據見 [dependency-callers.tsv](../../N8900A/InfScopeDLL_decompiled/dependency-callers.tsv)、[dependency-callers.asm](../../N8900A/InfScopeDLL_decompiled/dependency-callers.asm)。本次未分析上述外部 DLL 的內容，因此未聲稱已恢復其中的數值實作。

## 輸出索引

| 產物 | 內容 |
|---|---|
| `native-full.asm.gz` | `.text`、`.textidx` 等可執行區段的完整線性 LLVM Intel 語法輸出；12,689,868 行，以 gzip 壓縮 |
| `focus-functions.asm`／`.tsv` | 重點區段的易讀指令與定位依據；範圍數見 `extraction-run.log` |
| `focus-direct-calls.tsv` | 重點區段內可直接解析的 call／jmp 目標；不含所有間接呼叫 |
| `dual-dirac-kernel.asm`／`dual_dirac_reconstructed.cpp` | 核心指令與手動整理的運算等價偽碼 |
| `exports.tsv`／`imports.tsv` | PE 匯出、一般及延遲匯入，附 RVA／VA |
| `rtti-types-all.tsv`／`rtti-focus-vtables.tsv` | 全部 RTTI 類別名稱候選與重點虛擬表槽位對應 |
| `strings-ascii.txt` | 系統 strings 的完整 ASCII 輸出，附十六進位檔案 offset |
| `strings-utf16le.tsv` | 標準函式庫抽取的 ASCII 可列印字元範圍 UTF-16LE 字串；非完整 Unicode 字串掃描 |
| `strings-focus-initial.txt`／`strings-focus.tsv` | 初步關鍵詞命中及較廣的分類字串，後者附 offset／RVA／VA |
| `string-xrefs.tsv` | 1,880 筆直接 RIP-relative 參照；僅匹配字串起點，含初始化程式搬移文字的指令 |
| `algorithm-import-xrefs.tsv` | CRT 數學、FFTW 與特定外部模組的 IAT 參照，含 thunk／位址取得，不全是呼叫 |
| `dependency-callers.tsv`／`.asm` | 追到特定延遲匯入 thunk 的直接呼叫與其所在區段 |
| `runtime-functions.tsv` | 全部 `.pdata` begin／end／unwind 記錄 |
| `pe-headers.txt`／`pe-summary.json` | LLVM PE 標頭、結構與 SHA-256 摘要 |
| `analysis-index.json` | 腳本間使用的機器可讀位址索引 |
| `*-run.log`、`*-summary.json`、`*.stderr.txt` | 執行結果、統計與工具診斷；空 stderr 表示該工具未寫入診斷 |
| `analyze_pe.py`、`disassemble.py`、`extract_focus.py`、`trace_dependency_calls.py`、`verify_outputs.py` | 可重現分析與校驗腳本，僅使用 Python 標準庫及 objdump |
| `verification.json`／`SHA256SUMS.txt` | 最終唯讀來源校驗、gzip／表格檢查與輸出雜湊清單 |

## 重現方式

在專案根目錄執行；所有重導向都留在本資料夾。以下會重新產生分析產物：

```sh
file N8900A/1_Core/InfScopeDLL.dll
strings -a -t x N8900A/1_Core/InfScopeDLL.dll > N8900A/InfScopeDLL_decompiled/strings-ascii.txt
objdump --file-headers --section-headers --private-headers N8900A/1_Core/InfScopeDLL.dll > N8900A/InfScopeDLL_decompiled/pe-headers.txt
python3 N8900A/InfScopeDLL_decompiled/analyze_pe.py
python3 N8900A/InfScopeDLL_decompiled/disassemble.py
python3 N8900A/InfScopeDLL_decompiled/extract_focus.py
python3 N8900A/InfScopeDLL_decompiled/trace_dependency_calls.py
python3 N8900A/InfScopeDLL_decompiled/verify_outputs.py
```

查看完整指令可用 `gzip -dc N8900A/InfScopeDLL_decompiled/native-full.asm.gz | less`。針對已知函式查詢時，objdump 的 start／stop 必須使用 **VA**，例如：

```sh
objdump -d --x86-asm-syntax=intel \
  --start-address=0x1818e8ec0 --stop-address=0x1818e8f58 \
  N8900A/1_Core/InfScopeDLL.dll
```

## 限制與後續追查入口

最終校驗通過：原 DLL 的 SHA-256 與初始分析一致，gzip 完整可讀，表格筆數與重點區段一致。共擷取 131 個重點區段、13 個特定外部模組直接呼叫點。完整線性輸出中仍有 **5,705 行 `<unknown>`**，表示 LLVM 未成功解碼，或掃到了非指令資料；不能宣稱所有指令均已正確解碼。校驗只檢查產物完整性與證據一致性，未在 Windows 上執行量測或驗證儀器的數值結果。

線性反組譯不會自動恢復控制流程、型別或原始方法名，可執行節內夾雜的資料也可能被誤解碼。字串參照只追到 objdump 顯示的直接 RIP-relative 目標，未全面處理間接指標、字串中段、虛擬呼叫及執行期分派；RTTI／vftable 由格式特徵辨識，連續函式指標的槽位清單屬候選，可能截斷或跨越相鄰資料，不能視作完整類別宣告。無 `.pdata` 目標只擷取 32／128-byte 視窗，不宣稱是完整函式。

若要繼續還原數值實作，優先在 Ghidra／IDA 載入本 DLL，以 `0x18E8EC0` 為 Dual-Dirac 核心入口，從 `0x115F6CD`／`0x1163C86` 的呼叫準備過程追抖動資料結構，並分別載入 `EZJitMeasure.dll`、`EyeContour.dll`。PLL 可從 `0x10FF4E0` 的前後時脈資料及 `0x12A7020` 的模式分派往下追；目前未取得各階 PLL 的完整係數或眼圖統計公式。
