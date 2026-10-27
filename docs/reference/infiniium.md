# Infiniium 參考

> 由下列檔案合併而成（原檔見 git 歷史）：infiniium-截圖.md、infiniium-波形資料.md、infiniium-資料匯出.md


---

## 〔infiniium-截圖〕

## Keysight Infiniium 系列示波器遠端截圖與資料取回指南

本手冊彙整 Keysight Infiniium（包含 MXR、EXR 等系列）示波器透過 SCPI 遠端指令擷取螢幕畫面並傳回控制端電腦的兩種核心方法、二進位資料結構解析、完整參數規格以及 Python (PyVISA) 自動化程式範例。

---

### 目錄
1. [架構概述](#一-架構概述)
2. [方法一：直接截圖回傳影像資料（:DISPlay:DATA?）](#二-方法一直接截圖回傳影像資料displaydata)
3. [方法二：儲存至示波器硬碟後讀取取回（:DISK 命令群）](#三-方法二儲存至示波器硬碟後讀取取回disk-命令群)
4. [進階報告功能：量測報告匯出（:DISK:SAVE:MREPort）](#四-進階報告功能量測報告匯出disksavemreport)
5. [IEEE 488.2 定長二進位資料塊（Definite-Length Block）解析](#五-ieee-4882-定長二進位資料塊definite-length-block解析)
6. [Python (PyVISA) 自動化實作範例](#六-python-pyvisa-自動化實作範例)
7. [兩種擷取方式之比較與選擇建議](#七-兩種擷取方式之比較與選擇建議)
8. [實務注意事項與常見問題排除](#八-實務注意事項與常見問題排除)

---

### 一、 架構概述

在遠端自動化測試架構中，從 Keysight 示波器擷取畫面主要有兩種操作方式：

1. **直接串流讀取（Direct Query Transfer）**：
   - 透過查詢指令 `:DISPlay:DATA?`，示波器直接將當前畫面影像資料編碼為 IEEE 488.2 定長二進位資料塊（Binary Block）並透過匯流排（LAN / USB / GPIB）回傳至電腦。
   - **特點**：傳輸速度最快、示波器磁碟零讀寫耗損、不需處理暫存檔案管理。
2. **先儲存至示波器本機再讀取（Save to Disk & Fetch）**：
   - 先以 `:DISK:SAVE:IMAGe` 將畫面存成實體檔案至示波器本機硬碟，再以 `:DISK:GETFILE?` 命令將該檔案回傳，最後可視需求以 `:DISK:DELete` 刪除暫存檔。
   - **特點**：適合測試過程中需要在示波器本機留存 Log 記錄、或需要將量測設定嵌入圖檔（Setup Information）的場合。

---

### 二、 方法一：直接截圖回傳影像資料（:DISPlay:DATA?）

#### 1. 命令語法
```scpi
:DISPlay:DATA? [<type>[,<screen_mode>[,<compression>[,<inversion>]]]]
```

#### 2. 參數說明

| 參數 | 類型 / 可用選項 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `<type>` | `BMP` \| `JPG` \| `GIF` \| `TIF` \| `PNG` | `BMP` | 圖檔格式。實務上建議使用 `PNG` 或 `JPG`，壓縮比高且傳輸迅速。 |
| `<screen_mode>` | `SCReen` \| `GRATicule` | `SCReen` | **SCReen**：擷取整個螢幕畫面（含選單、視窗與量測結果欄）。<br>**GRATicule**：僅擷取 10×8 格線波形繪製區。 |
| `<compression>` | `ON` \| `OFF` | `ON` | 是否啟用影像壓縮。 |
| `<inversion>` | `NORMal` \| `INVert` | `NORMal` | **NORMal**：標準黑底畫面。<br>**INVert**：白底反轉色彩（適合列印與測試報告展示）。 |

#### 3. SCPI 呼叫範例
- **擷取全螢幕 PNG 格式圖檔**：
  ```scpi
  :DISPlay:DATA? PNG,SCReen
  ```
- **擷取白底反轉之波形格線區圖片**：
  ```scpi
  :DISPlay:DATA? PNG,GRATicule,ON,INVert
  ```

---

### 三、 方法二：儲存至示波器硬碟後讀取取回（:DISK 命令群）

此方法依序分為儲存、下載與清理三個步驟：

#### 步驟 1：儲存截圖至本機硬碟（:DISK:SAVE:IMAGe）
將螢幕截圖儲存至示波器磁碟指定路徑。若未指定絕對路徑，預設存放於 `C:\Users\Public\Documents\Infiniium`。

* **命令語法**：
  ```scpi
  :DISK:SAVE:IMAGe "<file_name>" [,<format> [,{SCReen | GRATicule} [,{ON | 1} | {OFF | 0} [,{NORMal | INVert} [,{ON | 1} | {OFF | 0}]]]]]
  ```
* **參數說明**：
  - `"<file_name>"`：檔案名稱或完整檔案路徑（如 `"C:\Scope\capture.png"` 或 `"shot1"`）。
  - `<format>`：支援 `BMP`、`GIF`、`TIF`、`JPEG`、`PNG`。
  - `{SCReen | GRATicule}`：全螢幕或僅格線區域。
  - 第 1 個 `{ON | OFF}`：調色盤色彩壓縮設定。
  - `{NORMal | INVert}`：正常色彩或色彩反轉（白底）。
  - 第 2 個 `{ON | OFF}`：**是否在影像檔案中嵌入設定資訊（Setup Information）**。
* **SCPI 範例**：
  ```scpi
  :DISK:SAVE:IMAGe "C:\Users\Public\Documents\Infiniium\test.png",PNG,SCReen,ON,NORMal
  ```

#### 步驟 2：從示波器取回檔案（:DISK:GETFILE?）
以 IEEE 488.2 二進位區塊格式將示波器本機硬碟中的檔案讀取回傳。

* **命令語法**：
  ```scpi
  :DISK:GETFILE? "<file_name>"
  ```
* **SCPI 範例**：
  ```scpi
  :DISK:GETFILE? "C:\Users\Public\Documents\Infiniium\test.png"
  ```

#### 步驟 3：清理示波器本機暫存檔（:DISK:DELete）
在取得圖檔後刪除示波器端暫存檔，避免累積佔滿硬碟空間。

* **命令語法**：
  ```scpi
  :DISK:DELete "<file_name>"
  ```
* **SCPI 範例**：
  ```scpi
  :DISK:DELete "C:\Users\Public\Documents\Infiniium\test.png"
  ```

---

### 四、 進階報告功能：量測報告匯出（:DISK:SAVE:MREPort）

若測試需要完整記錄「儀器設定狀態」、「螢幕波形圖」以及「底部量測結果數據」，可使用複合報告命令：

* **命令語法**：
  ```scpi
  :DISK:SAVE:MREPort "<filename>"
  ```
* **說明**：
  - `<filename>` 必須包含 `.pdf` 或 `.mht`（MHTML 網頁封裝）副檔名。
  - 儲存完成後，同樣可透過 `:DISK:GETFILE?` 將 PDF 或 MHT 檔案下載回控制電腦。

---

### 五、 IEEE 488.2 定長二進位資料塊（Definite-Length Block）解析

查詢指令（`:DISPlay:DATA?` 或 `:DISK:GETFILE?`）回傳的影像資料均符合 IEEE 488.2 定長二進位區塊格式：

```text
#<N><Length><Binary Bytes Data><NewLine>
```

- **`#`**：起始識別字元。
- **`<N>`**：單一 ASCII 數字（1~9），代表後續 `<Length>` 數字本身佔用的字元數。
- **`<Length>`**：長度為 `N` 個字元的十進位數字，表示後續二進位原始資料的位元組長度（Bytes）。
- **`<Binary Data Bytes>`**：原始二進位資料流（即 PNG、JPG 或 BMP 的完整檔案內容）。
- **`<NewLine>`**：結尾換行字元（`\n`，ASCII 0x0A）。

> **實務提示**：若使用 Python PyVISA 程式庫，可調用 `query_binary_values()` 函式，程式庫會自動剖析並去除 `#<N><Length>` 標頭，直接輸出整包原始二進位資料（bytearray）。

---

### 六、 Python (PyVISA) 自動化實作範例

#### 範例 1：直接截圖並儲存至本機（方法一，推薦）
```python
import pyvisa

# 示波器連線字串 (可透過 Keysight Connection Expert 取得)
VISA_ADDRESS = "TCPIP0::192.168.1.100::inst0::INSTR"

rm = pyvisa.ResourceManager()
scope = rm.open_resource(VISA_ADDRESS)

# 影像渲染與傳輸需要時間，建議設定 timeout 為 10 秒以上
scope.timeout = 10000

print("正在擷取螢幕畫面...")
# 發送截圖查詢指令並取得二進位資料 (datatype='B' 代表無號 8-bit 整數)
image_bytes = scope.query_binary_values(
    ":DISPlay:DATA? PNG,SCReen,ON,NORMal",
    datatype="B",
    container=bytearray
)

# 寫入控制電腦本地檔案
output_file = "scope_screenshot.png"
with open(output_file, "wb") as f:
    f.write(image_bytes)

print(f"截圖成功！檔案已儲存為 {output_file}，大小：{len(image_bytes)} bytes")
scope.close()
```

#### 範例 2：先存至示波器磁碟再讀取回傳（方法二）
```python
import pyvisa

VISA_ADDRESS = "TCPIP0::192.168.1.100::inst0::INSTR"
REMOTE_FILE = r"C:\Users\Public\Documents\Infiniium\temp_shot.png"
LOCAL_FILE = "downloaded_shot.png"

rm = pyvisa.ResourceManager()
scope = rm.open_resource(VISA_ADDRESS)
scope.timeout = 15000

# 1. 存檔至示波器磁碟
print("命令示波器儲存截圖至本機硬碟...")
scope.write(f':DISK:SAVE:IMAGe "{REMOTE_FILE}",PNG,SCReen,ON,NORMal')

# 同步等待操作完成
scope.query("*OPC?")

# 2. 透過二進位串流取回檔案
print("從示波器下載圖檔...")
file_bytes = scope.query_binary_values(
    f':DISK:GETFILE? "{REMOTE_FILE}"',
    datatype="B",
    container=bytearray
)

with open(LOCAL_FILE, "wb") as f:
    f.write(file_bytes)
print(f"檔案下載完成，儲存為 {LOCAL_FILE}")

# 3. 清理示波器端暫存檔
scope.write(f':DISK:DELete "{REMOTE_FILE}"')
print("示波器暫存檔案已清除。")

scope.close()
```

---

### 七、 兩種擷取方式之比較與選擇建議

| 評估項目 | 方法一（`:DISPlay:DATA?`） | 方法二（`:DISK:SAVE:IMAGe` + `:DISK:GETFILE?`） |
| :--- | :--- | :--- |
| **指令複雜度** | 極簡（單一 Query 完成） | 較繁瑣（需 SAVE -> GETFILE -> DELete） |
| **傳輸耗時** | 最短（直接於記憶體壓縮串流輸出） | 較長（需等待示波器本機磁碟 I/O 寫入） |
| **硬碟磨損** | 零磁碟寫入 | 示波器 SSD 產生檔案寫入與刪除磨損 |
| **殘留管理** | 免維護，無殘留風險 | 程式端必須主動刪除以防佔滿示波器硬碟 |
| **附加功能** | 純影像輸出 | 可選擇將 Setup 參數資訊嵌入影像中 |
| **最佳適用場合** | **產線量產測試、連續波形截圖、即時監控** | 示波器需留存本機 Log 備查、或生成複合 PDF 報告 |

---

### 八、 實務注意事項與常見問題排除

1. **遠端桌面連線衝突（Error 273）**：
   - 當工程師透過 Windows 遠端桌面（Remote Desktop / RDP）連線控制示波器時，執行 `:DISPlay:DATA?` 或 `:DISK:SAVE:IMAGe` 可能觸發 `Error 273`。
   - **原因**：Windows RDP 會接管並虛擬化顯示子系統，干擾截圖引擎。
   - **解決方式**：執行自動化截圖測試前，請先結束示波器的 Windows 遠端桌面工作階段，或改用 Web 介面遠端監控。
2. **通訊逾時（Timeout）設定**：
   - 擷取高解析度畫面並進行 PNG/JPG 壓縮需要數百毫秒至 2 秒時間。PyVISA 預設逾時（約 2000 ms）容易因瞬時負載而 Timeout，強烈建議將連線物件的 `timeout` 設定於 `10000` ms（10 秒）以上。
3. **報告列印與白底色彩反轉（`INVert`）**：
   - 示波器螢幕預設為黑底以突顯各通道波形色彩，但在將圖檔放入 Word、PDF 報告或列印時，黑底非常耗費碳粉且不易書寫。建議將 `<inversion>` 參數指定為 `INVert`，可輸出清晰的白底波形圖。

---

## 〔infiniium-波形資料〕

## Keysight Infiniium 系列示波器波形資料回傳與檔案匯出指令指南

本文件依據 Keysight Infiniium MXR/EXR 系列示波器編程手冊（Programmer's Guide），詳細彙整如何透過 SCPI 指令在遠端自動化程式中匯出、回傳波形資料檔案（CSV、BIN、HDF5、MATLAB 等），以及直接串流讀取波形點數值資料的核心指令、參數定義、二進位資料結構與 Python (PyVISA) 實作範例。

---

### 目錄
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

### 一、 回傳波形資料之兩種核心架構比較

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

### 二、 方法一：波形資料檔案匯出與取回（:DISK 命令群）

此方法透過示波器內部檔案引擎將波形封裝為指定格式之檔案，再透過通訊匯流排下載至控制電腦。

#### 1. 儲存波形為本機檔案（:DISK:SAVE:WAVeform）

##### 語法
```scpi
:DISK:SAVE:WAVeform <source>,"<file_name>" [,<format>[,<header>]]

---

## 〔infiniium-資料匯出〕

## Keysight Infiniium 系列示波器 CSV 與 HDF5 資料匯出指南

本文件依據 Keysight Infiniium MXR/EXR 系列示波器編程手冊（Programmer's Guide），詳細彙整如何透過 SCPI 指令在遠端自動化程式中配置記憶體深度（記憶點數）、將波形匯出為 **HDF5 (.h5)** 或 **CSV (.csv)** 檔案，並透過匯流排安全取回控制端電腦的完整流程。

---

### 一、 H5 與 CSV 匯出資料格式說明

使用波形儲存指令時，可選擇 CSV、H5 或 H5INt 格式，兩者在資料結構、數值代表意義上有顯著不同：

#### 1. CSV (Comma Separated Values)
* **副檔名**：`.csv`
* **資料結構**：純文字的 ASCII 格式，以逗號分隔。
* **檔頭設定（Header）**：
  * 可透過指令參數設定 `ON` 或 `OFF`。
  * 設為 `ON`（預設值）時，檔案開頭會包含數十行中繼標頭資訊，包含儀器型號、序號、韌體版本、取樣率、記憶體深度、時間與各通道垂直刻度等。
  * 標頭隨後為資料列，其行格式為：`Time (s), Channel 1 (V)`。如果同時顯示並儲存多通道（來源設為 `ALL`），資料列會自動橫向展開，例如：`Time (s), Channel 1 (V), Channel 2 (V)...`。
  * 設為 `OFF` 時，不產生任何設定說明標頭，直接輸出數據。

#### 2. H5 (HDF5 浮點數格式)
* **副檔名**：`.h5`
* **資料特點**：波形數據以**單精度或雙精度浮點數（float32 / float64）**直接存放於資料集中。
* **數值意義**：陣列中的數值**直接就是真實物理電壓值（伏特，Volts）**，讀取時不需要再乘以 Y 增量或加上 Y 原點。
* **內部架構**（分層階層式結構）：
  * `/FileType`：包含檔案標識（Dataset `KeysightH5FileType` 值為 `'Keysight Waveform'`）。
  * `/Frame`：記錄儀器機型（Model）、序號（Serial）與擷取日期（Date）。
  * `/Waveforms/Channel <N>`：儲存通道的屬性（Attributes），如點數 `NumPoints`、時間增量 `XInc`、時間原點 `XOrg`、電壓增量 `YInc`、電壓原點 `YOrg` 與單位 `XUnits`/`YUnits`。
  * `/Waveforms/Channel <N>/Channel <N>Data`：實際波形數據的浮點數陣列。

#### 3. H5INt (HDF5 整數格式)
* **副檔名**：`.h5`
* **資料特點**：波形數據以 **16-bit 有號整數（int16 ADC 量化代碼）** 方式存放。
* **優點**：檔案體積極小（約為 H5 浮點數格式的一半，CSV 的幾十分之一），是數百萬點以上超長波形的首選。
* **電壓還原公式**：
  $$\text{Voltage} = [(\text{RawValue} - \text{YReference}) \times \text{YInc}] + \text{YOrg}$$
  * `RawValue`：從 `/Waveforms/Channel <N>/Channel <N>Data` 資料集中讀取的整數值。
  * `YReference`（Y 軸參考代碼）、`YInc`（Y 軸垂直增量）、`YOrg`（Y 軸垂直原點）等中繼參數，需從 Channel <N> 組的屬性（Attributes）中讀取。

---

### 二、 記憶點數（Memory Depth）與取樣設定命令

要確保匯出的檔案包含預期的點數，必須在擷取階段完成記憶體深度配置（隸屬於手冊第 14 章 :ACQuire 命令子系統）：

| SCPI 命令 / 查詢 | 參數範圍 / 類型 | 說明 |
| :--- | :--- | :--- |
| **`:ACQuire:POINts:AUTO <state>`** | `{{ON \| 1} \| {OFF \| 0}}` | 開啟或關閉自動記憶體深度控制。**手動指定點數前必須先設為 `OFF`（或 `0`）**。 |
| **`:ACQuire:POINts[:ANALog] <value>`** | `<points_value> \| AUTO \| MAX` | **設定類比通道擷取點數（記憶體深度）**。<br>• `<points_value>`：手動指定的整數（如 `1000000` 表示 1 Mpts）。<br>• `MAX`：設定為硬體最大允許深度。<br>• `AUTO`：自動選擇。 |
| **`:ACQuire:POINts[:ANALog]?`** | *(無)* | 查詢目前設定的記憶體深度（點數）。 |
| **`:ACQuire:POINts:MAXimum?`** | *(無)* | 查詢當前時基與通道配置下，硬體允許的記憶點數最大限制。 |
| **`:WAVeform:POINts?`** | *(無)* | 查詢目前波形記憶體緩衝區內實際擷取完成的點數（傳輸前確認用）。 |

> **記憶體與取樣率連動提示**：
> 在 Infiniium 示波器中，若手動指定點數（POINts），點數設定優先，取樣率（SRATe）會依水平時基與點數自動調整限制；若手動指定取樣率，則取樣率優先，記憶體深度會被限制。

---

### 三、 檔案儲存與取回命令

透過 `:DISK` 子系統（第 21 章），可以將擷取完成的記憶體波形，儲存為本機檔案並取回：

#### 1. 儲存波形為本機檔案（`:DISK:SAVE:WAVeform`）
```scpi
:DISK:SAVE:WAVeform <source>,"<file_name>" [,<format>[,<header>]]
```
* **`<source>`**：欲儲存的波形來源（如 `CHANnel1` ~ `CHANnel8`、`ALL` 表示儲存所有顯示通道、`FUNCtion1` ~ `FUNCtion16`、`WMEMory1` ~ `WMEMory8` 等）。
* **`"<file_name>"`**：雙引號包覆的檔案名稱或絕對路徑。若未指定完整路徑，預設目錄為：`C:\Users\Public\Documents\Infiniium\`。
* **`<format>`**：指定檔案儲存格式（支援 `CSV`、`H5`、`H5INt`、`BINary`、`TSV`、`TXT`、`MATlab`、`INTernal` 等）。
* **`<header>`**：文字格式（如 CSV/TSV）專用，設定為 `ON`（或 `1`）以包含中繼標頭，或 `OFF`（或 `0`）以省略標頭。

#### 2. 分段記憶體範圍設定（`:DISK:SEGMented`）
若啟用了分段擷取（Segmented Memory），此指令決定要儲存所有分段或僅儲存當前檢視之分段：
```scpi
:DISK:SEGMented {ALL | CURRent}
```

#### 3. 下載二進位檔案數據（`:DISK:GETFILE?`）
將示波器本機磁碟上的檔案，轉換為 IEEE 488.2 定長二進位資料塊（Definite-Length Block）傳回控制端：
```scpi
:DISK:GETFILE? "<file_name>"
```
* **回傳格式**：`#<N><Length><Binary Raw Bytes Data><NewLine>`（PyVISA 函式會自動剝除標頭，取得純 bytearray）。

#### 4. 刪除示波器暫存檔案（`:DISK:DELete`）
下載完畢後應主動刪除示波器硬碟上的暫存檔，防止磁碟容量被大型波形檔案佔滿：
```scpi
:DISK:DELete "<file_name>"
```

---

### 四、 遠端控制完整呼叫序列 (SCPI Command Sequence)

以下為自動化測試程式進行設定、擷取、匯出與下載的標準執行順序：

```scpi
; 1. 配置記憶體點數與取樣率
:ACQuire:POINts:AUTO OFF                   ; 關閉自動點數控制
:ACQuire:POINts:ANALog 1000000             ; 設定記憶體深度為 1,000,000 點 (1 Mpts)
:ACQuire:POINts:ANALog?                    ; 查詢確認實際點數

; 2. 執行單次波形擷取並等待完成
:STOP                                      ; 先停止擷取
:SINGle                                    ; 觸發單次擷取
*OPC?                                      ; 等待波形擷取與量測分析完成（回傳 1）

; 3. 將 Channel 1 儲存為浮點數 HDF5 檔案
:DISK:SAVE:WAVeform CHANnel1,"C:\Users\Public\Documents\Infiniium\export.h5",H5
*OPC?                                      ; 重要！必須等待示波器實體硬碟寫入完畢並回傳 1

; 4. 透過二進位串流將 H5 檔案下載至控制端電腦
:DISK:GETFILE? "C:\Users\Public\Documents\Infiniium\export.h5"

; 5. 下載成功後，清除示波器硬碟上的暫存檔
:DISK:DELete "C:\Users\Public\Documents\Infiniium\export.h5"
```

---

### 五、 Python (PyVISA) 自動化實作範例

#### 1. 設定記憶點數並下載 H5/CSV 波形檔案
```python
import pyvisa
import time

# 示波器連線設定 (支援 TCP/IP, HiSLIP 或 USB)
VISA_ADDRESS = "TCPIP0::192.168.1.100::hislip0::INSTR"
REMOTE_FILE = r"C:\Users\Public\Documents\Infiniium\temp_waveform.h5"
LOCAL_FILE = "downloaded_waveform.h5"
TARGET_POINTS = 1_000_000  # 目標記憶體深度 1 Mpts

rm = pyvisa.ResourceManager()
scope = rm.open_resource(VISA_ADDRESS)

# 涉及磁碟寫入與大型二進位傳輸，建議將 timeout 延長至 30 秒以上
scope.timeout = 30000

try:
    print("1. 配置手動記憶體深度...")
    scope.write(":ACQuire:POINts:AUTO OFF")
    scope.write(f":ACQuire:POINts:ANALog {TARGET_POINTS}")
    actual_pts = scope.query(":ACQuire:POINts:ANALog?").strip()
    print(f"   實際配置點數: {int(float(actual_pts)):,} 點")

    print("2. 執行單次擷取...")
    scope.write(":STOP")
    scope.write(":SINGle")
    scope.query("*OPC?")  # 等待擷取與分析完成

    print("3. 要求示波器本機儲存為 HDF5 檔案...")
    scope.write(f':DISK:SAVE:WAVeform CHANnel1,"{REMOTE_FILE}",H5')
    scope.query("*OPC?")  # 重要！等待示波器寫檔完畢
    print("   示波器本機檔案寫入完成。")

    print("4. 下載 H5 檔案至控制端電腦...")
    # query_binary_values 會自動剥除 IEEE 488.2 標頭
    file_bytes = scope.query_binary_values(
        f':DISK:GETFILE? "{REMOTE_FILE}"',
        datatype="B",
        container=bytearray
    )

    with open(LOCAL_FILE, "wb") as f:
        f.write(file_bytes)
    print(f"   下載成功！大小: {len(file_bytes):,} Bytes，已儲存至 {LOCAL_FILE}")

    print("5. 清理示波器端暫存檔...")
    scope.write(f':DISK:DELete "{REMOTE_FILE}"')
    print("   暫存檔已刪除。")

finally:
    scope.write(":RUN")
    scope.close()
```

#### 2. 使用 Python (h5py) 解析下載的 H5 檔案
```python
import h5py
import numpy as np

H5_FILENAME = "downloaded_waveform.h5"

with h5py.File(H5_FILENAME, "r") as h5:
    # 取得 Channel 1 資訊群組
    ch1_group = h5["Waveforms/Channel 1"]
    
    # 讀取中繼資料屬性
    num_pts = ch1_group.attrs["NumPoints"]
    x_org = ch1_group.attrs["XOrg"]      # X 軸時間起點 (秒)
    x_inc = ch1_group.attrs["XInc"]      # 取樣時間間距 (秒)
    y_org = ch1_group.attrs["YOrg"]      # Y 軸垂直偏移中心值 (伏特)
    y_inc = ch1_group.attrs["YInc"]      # Y 軸垂直增量
    y_ref = ch1_group.attrs["YReference"]# Y 軸垂直參考基準
    
    # 讀取資料集
    raw_data = np.array(ch1_group["Channel 1Data"])
    
    # 建立時間軸
    time_axis = x_org + (np.arange(len(raw_data)) * x_inc)
    
    # 判斷是否需要進行電壓還原 (H5 浮點數格式直接為真實電壓，H5INt 需要換算)
    if np.issubdtype(raw_data.dtype, np.floating):
        voltage_axis = raw_data
    else:
        voltage_axis = ((raw_data - y_ref) * y_inc) + y_org

    print(f"讀取完成！總數據點數: {len(voltage_axis):,} 點")
    print(f"取樣率: {1/x_inc/1e9:.2f} GSa/s")
    print("前 3 點物理量座標：")
    for i in range(3):
        print(f"  [{i}] 時間: {time_axis[i]*1e9:8.3f} ns | 電壓: {voltage_axis[i]:8.4f} V")
```

---

### 六、 實務注意事項與除錯建議

1. **大點數（>100 kpts）強烈建議使用 H5/H5INt，嚴禁使用 CSV**：
   * CSV 是 ASCII 文字格式。10 Mpts（一千萬點）的 CSV 檔案通常高達 **300~500 MB**，示波器內部將二進位 ADC 點轉換為 ASCII 文字非常消耗 CPU 與硬碟 I/O，可能耗時長達數十秒。
   * 相同的 10 Mpts 波形若儲存為 `H5INt` 格式，大小僅約 **20 MB**，示波器通常在 1 秒內即可完成寫入。
2. **通訊逾時（Timeout）設定**：
   * 示波器在進行高深度記憶體存檔或傳輸檔案時，VISA 預設的 2 秒（2,000 ms）逾時極易觸發 `VI_ERROR_TMO` 錯誤。務必將 `scope.timeout` 配置於 **30,000 ~ 60,000 毫秒（30 至 60 秒）**。
3. **路徑反斜線轉義與跳脫**：
   * 在 Python 或 C 程式碼中，反斜線 `\` 常用作跳脫字元。在指定示波器硬碟路徑時，請使用 Raw 原始字串（如 `r"C:\Users\..."`）或雙反斜線（`"C:\\Users\\..."`）以避免語法錯誤。
4. **複合檔案備份**：
   * 如果除了波形，也想將當前儀器的面板設定（Setup）一併備份為單一專案專用檔，可使用 `:DISK:SAVE:COMPosite "<file_name>"` 命令，其將生成 `.osc` 複合檔案。該檔案可用於在電腦端的 **Keysight Infiniium Offline** 軟體中完全還原當時的測量現場。
