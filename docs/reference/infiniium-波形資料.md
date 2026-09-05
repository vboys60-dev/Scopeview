# Keysight Infiniium 系列示波器波形資料回傳與檔案匯出指令指南

本文件依據 Keysight Infiniium MXR/EXR 系列示波器編程手冊（Programmer's Guide），詳細彙整如何透過 SCPI 指令在遠端自動化程式中匯出、回傳波形資料檔案（CSV、BIN、HDF5、MATLAB 等），以及直接串流讀取波形點數值資料的核心指令、參數定義、二進位資料結構與 Python (PyVISA) 實作範例。

---

## 目錄
1. [回傳波形資料之兩種核心架構比較](#一-回傳波形資料之兩種核心架構比較)
2. [方法一：波形資料檔案匯出與取回（:DISK 命令群）](#二-方法一波形資料檔案匯出與取回disk-命令群)
   - [1. 儲存波形為本機檔案（:DISK:SAVE:WAVeform）](#1-儲存波形為本機檔案disksavewaveform)
   - [2. 分段記憶體儲存範圍設定（:DISK:SEGMented）](#2-分段記憶體儲存範圍設定disksegmented)
   - [3. 讀取並下載檔案資料流（:DISK:GETFILE?）](#3-讀取並下載檔案資料流diskgetfile)
   - [4. 清除示波器端暫存檔案（:DISK:DELete）](#4-清除示波器端暫存檔案diskdelete)
   - [5. 專案複合檔案打包（:DISK:SAVE:COMPosite）](#5-專案複合檔案打包disksavecomposite)
3. [方法二：即時波形資料點串流讀取（:WAVeform 命令群）](#三-方法二即時波形資料點串流讀取waveform-命令群)
   - [1. 傳輸通道與資料格式配置（SOURce, FORMat, BYTeorder）](#1-傳輸通道與資料格式配置source-format-byteorder)
   - [2. 讀取波形前導轉換參數（:WAVeform:PREamble?）](#2-讀取波形前導轉換參數waveformpreamble)
   - [3. 電壓與時間軸座標換算數學公式](#3-電壓與時間軸座標換算數學公式)
   - [4. 讀取原始二進位波形點（:WAVeform:DATA?）](#4-讀取原始二進位波形點waveformdata)
4. [IEEE 488.2 定長二進位資料塊（Binary Block）解析](#四-ieee-4882-定長二進位資料塊binary-block解析)
5. [常見波形檔案格式特性與適用場景比較](#五-常見波形檔案格式特性與適用場景比較)
6. [Python (PyVISA) 自動化程式完整範例](#六-python-pyvisa-自動化程式完整範例)
   - [範例 1：透過 :DISK 命令下載完整波形檔案（CSV / H5 / BIN）](#範例-1透過-disk-命令下載完整波形檔案csv--h5--bin)
   - [範例 2：透過 :WAVeform 命令串流讀取波形點並繪圖儲存](#範例-2透過-waveform-命令串流讀取波形點並繪圖儲存)
7. [實務注意事項與常見除錯建議 (Troubleshooting)](#七-實務注意事項與常見除錯建議-troubleshooting)

---

## 一、 回傳波形資料之兩種核心架構比較

| 評估項目 | 方法一：波形資料檔案匯出後下載（:DISK 命令群） | 方法二：波形點數值直接串流讀取（:WAVeform 命令群） |
| :--- | :--- | :--- |
| **運作原理** | 示波器將波形轉換為標準實體檔案（如 CSV、BIN、HDF5），再以二進位資料流傳回電腦 | 示波器直接將記憶體中的波形 ADC 原始數位點透過匯流排串流傳回電腦 |
| **核心命令** | `:DISK:SAVE:WAVeform`<br>`:DISK:GETFILE?`<br>`:DISK:DELete` | `:WAVeform:SOURce`<br>`:WAVeform:FORMat`<br>`:WAVeform:PREamble?`<br>`:WAVeform:DATA?` |
| **支援檔案格式** | CSV, TSV, TXT, BIN, H5, H5INt, MATlab, INTernal/WFM, OSC | 純數值陣列（可由電腦端程式自行存為 NumPy、CSV 或資料庫） |
| **標頭與刻度資訊** | 示波器自動將時間、取樣率、刻度封裝於檔案中 | 需透過 `:WAVeform:PREamble?` 取得 10 個轉換係數並自行計算 |
| **多通道一次處理** | 支援 `ALL` 參數，可將所有已開啟的通道打包於單一檔案 | 需使用 `:WAVeform:SOURce` 逐一切換通道個別讀取 |
| **示波器磁碟負擔** | 需在示波器本機硬碟產生暫存檔，建議測試後刪除 | 零硬碟寫入，全記憶體運作 |
| **適用場景** | **需留存標準報表檔案（CSV/HDF5/MATLAB）、離線使用 Infiniium Offline 分析、批次多通道備份** | **高頻寬自動化產線、自訂演算法即時分析、連續快速擷取** |

---

## 二、 方法一：波形資料檔案匯出與取回（:DISK 命令群）

此方法透過示波器內部檔案引擎將波形封裝為指定格式之檔案，再透過通訊匯流排下載至控制電腦。

### 1. 儲存波形為本機檔案（:DISK:SAVE:WAVeform）

#### 語法
```scpi
:DISK:SAVE:WAVeform <source>,"<file_name>" [,<format>[,<header>]]