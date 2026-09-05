# Keysight Infiniium 系列示波器 CSV 與 HDF5 資料匯出指南

本文件依據 Keysight Infiniium MXR/EXR 系列示波器編程手冊（Programmer's Guide），詳細彙整如何透過 SCPI 指令在遠端自動化程式中配置記憶體深度（記憶點數）、將波形匯出為 **HDF5 (.h5)** 或 **CSV (.csv)** 檔案，並透過匯流排安全取回控制端電腦的完整流程。

---

## 一、 H5 與 CSV 匯出資料格式說明

使用波形儲存指令時，可選擇 CSV、H5 或 H5INt 格式，兩者在資料結構、數值代表意義上有顯著不同：

### 1. CSV (Comma Separated Values)
* **副檔名**：`.csv`
* **資料結構**：純文字的 ASCII 格式，以逗號分隔。
* **檔頭設定（Header）**：
  * 可透過指令參數設定 `ON` 或 `OFF`。
  * 設為 `ON`（預設值）時，檔案開頭會包含數十行中繼標頭資訊，包含儀器型號、序號、韌體版本、取樣率、記憶體深度、時間與各通道垂直刻度等。
  * 標頭隨後為資料列，其行格式為：`Time (s), Channel 1 (V)`。如果同時顯示並儲存多通道（來源設為 `ALL`），資料列會自動橫向展開，例如：`Time (s), Channel 1 (V), Channel 2 (V)...`。
  * 設為 `OFF` 時，不產生任何設定說明標頭，直接輸出數據。

### 2. H5 (HDF5 浮點數格式)
* **副檔名**：`.h5`
* **資料特點**：波形數據以**單精度或雙精度浮點數（float32 / float64）**直接存放於資料集中。
* **數值意義**：陣列中的數值**直接就是真實物理電壓值（伏特，Volts）**，讀取時不需要再乘以 Y 增量或加上 Y 原點。
* **內部架構**（分層階層式結構）：
  * `/FileType`：包含檔案標識（Dataset `KeysightH5FileType` 值為 `'Keysight Waveform'`）。
  * `/Frame`：記錄儀器機型（Model）、序號（Serial）與擷取日期（Date）。
  * `/Waveforms/Channel <N>`：儲存通道的屬性（Attributes），如點數 `NumPoints`、時間增量 `XInc`、時間原點 `XOrg`、電壓增量 `YInc`、電壓原點 `YOrg` 與單位 `XUnits`/`YUnits`。
  * `/Waveforms/Channel <N>/Channel <N>Data`：實際波形數據的浮點數陣列。

### 3. H5INt (HDF5 整數格式)
* **副檔名**：`.h5`
* **資料特點**：波形數據以 **16-bit 有號整數（int16 ADC 量化代碼）** 方式存放。
* **優點**：檔案體積極小（約為 H5 浮點數格式的一半，CSV 的幾十分之一），是數百萬點以上超長波形的首選。
* **電壓還原公式**：
  $$\text{Voltage} = [(\text{RawValue} - \text{YReference}) \times \text{YInc}] + \text{YOrg}$$
  * `RawValue`：從 `/Waveforms/Channel <N>/Channel <N>Data` 資料集中讀取的整數值。
  * `YReference`（Y 軸參考代碼）、`YInc`（Y 軸垂直增量）、`YOrg`（Y 軸垂直原點）等中繼參數，需從 Channel <N> 組的屬性（Attributes）中讀取。

---

## 二、 記憶點數（Memory Depth）與取樣設定命令

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

## 三、 檔案儲存與取回命令

透過 `:DISK` 子系統（第 21 章），可以將擷取完成的記憶體波形，儲存為本機檔案並取回：

### 1. 儲存波形為本機檔案（`:DISK:SAVE:WAVeform`）
```scpi
:DISK:SAVE:WAVeform <source>,"<file_name>" [,<format>[,<header>]]
```
* **`<source>`**：欲儲存的波形來源（如 `CHANnel1` ~ `CHANnel8`、`ALL` 表示儲存所有顯示通道、`FUNCtion1` ~ `FUNCtion16`、`WMEMory1` ~ `WMEMory8` 等）。
* **`"<file_name>"`**：雙引號包覆的檔案名稱或絕對路徑。若未指定完整路徑，預設目錄為：`C:\Users\Public\Documents\Infiniium\`。
* **`<format>`**：指定檔案儲存格式（支援 `CSV`、`H5`、`H5INt`、`BINary`、`TSV`、`TXT`、`MATlab`、`INTernal` 等）。
* **`<header>`**：文字格式（如 CSV/TSV）專用，設定為 `ON`（或 `1`）以包含中繼標頭，或 `OFF`（或 `0`）以省略標頭。

### 2. 分段記憶體範圍設定（`:DISK:SEGMented`）
若啟用了分段擷取（Segmented Memory），此指令決定要儲存所有分段或僅儲存當前檢視之分段：
```scpi
:DISK:SEGMented {ALL | CURRent}
```

### 3. 下載二進位檔案數據（`:DISK:GETFILE?`）
將示波器本機磁碟上的檔案，轉換為 IEEE 488.2 定長二進位資料塊（Definite-Length Block）傳回控制端：
```scpi
:DISK:GETFILE? "<file_name>"
```
* **回傳格式**：`#<N><Length><Binary Raw Bytes Data><NewLine>`（PyVISA 函式會自動剝除標頭，取得純 bytearray）。

### 4. 刪除示波器暫存檔案（`:DISK:DELete`）
下載完畢後應主動刪除示波器硬碟上的暫存檔，防止磁碟容量被大型波形檔案佔滿：
```scpi
:DISK:DELete "<file_name>"
```

---

## 四、 遠端控制完整呼叫序列 (SCPI Command Sequence)

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

## 五、 Python (PyVISA) 自動化實作範例

### 1. 設定記憶點數並下載 H5/CSV 波形檔案
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

### 2. 使用 Python (h5py) 解析下載的 H5 檔案
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

## 六、 實務注意事項與除錯建議

1. **大點數（>100 kpts）強烈建議使用 H5/H5INt，嚴禁使用 CSV**：
   * CSV 是 ASCII 文字格式。10 Mpts（一千萬點）的 CSV 檔案通常高達 **300~500 MB**，示波器內部將二進位 ADC 點轉換為 ASCII 文字非常消耗 CPU 與硬碟 I/O，可能耗時長達數十秒。
   * 相同的 10 Mpts 波形若儲存為 `H5INt` 格式，大小僅約 **20 MB**，示波器通常在 1 秒內即可完成寫入。
2. **通訊逾時（Timeout）設定**：
   * 示波器在進行高深度記憶體存檔或傳輸檔案時，VISA 預設的 2 秒（2,000 ms）逾時極易觸發 `VI_ERROR_TMO` 錯誤。務必將 `scope.timeout` 配置於 **30,000 ~ 60,000 毫秒（30 至 60 秒）**。
3. **路徑反斜線轉義與跳脫**：
   * 在 Python 或 C 程式碼中，反斜線 `\` 常用作跳脫字元。在指定示波器硬碟路徑時，請使用 Raw 原始字串（如 `r"C:\Users\..."`）或雙反斜線（`"C:\\Users\\..."`）以避免語法錯誤。
4. **複合檔案備份**：
   * 如果除了波形，也想將當前儀器的面板設定（Setup）一併備份為單一專案專用檔，可使用 `:DISK:SAVE:COMPosite "<file_name>"` 命令，其將生成 `.osc` 複合檔案。該檔案可用於在電腦端的 **Keysight Infiniium Offline** 軟體中完全還原當時的測量現場。
