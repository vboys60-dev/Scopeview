# Keysight 示波器波形資料回傳與存檔 SCPI 命令指南

本文件適用於 Keysight (原 Agilent / HP) InfiniiVision 3000G / 3000X 等系列示波器，詳細說明如何透過遠端命令讀取波形採樣數據回傳至電腦端，以及命令示波器儲存波形檔案至隨身碟/本機硬碟。

---

## 一、架構一：遠端傳輸波形至 PC (:WAVeform 子系統)

這是自動化量測最主流的作法。控制端 PC 透過 SCPI 查詢命令獲取波形點陣二進位數據與刻度換算參數，直接於電腦端產生資料檔案（如 `.csv`、`.bin`、`.npy`）。

### 1. 核心傳輸命令列表

| SCPI 命令語法 | 查詢語法 (Query) | 參數 / 回傳值選項 | 說明 |
| :--- | :--- | :--- | :--- |
| **`:WAVeform:SOURce <source>`** | `:WAVeform:SOURce?` | `CHANnel<n>`、`FUNCtion<m>`、`MATH<m>`、`WMEMory<r>`、`SBUS{1\|2}` | 指定波形讀取來源通道（例如 `CHANnel1`）。查詢前該通道必須處於開啟狀態。 |
| **`:WAVeform:FORMat <format>`** | `:WAVeform:FORMat?` | `{WORD \| BYTE \| ASCii}` | 設定傳回資料格式：<br>• `BYTE`：8 位元整數（傳輸最快）。<br>• `WORD`：16 位元整數（高解析度模式推薦）。<br>• `ASCii`：浮點數文字串流（以逗號分隔，資料量大）。 |
| **`:WAVeform:POINts:MODE <mode>`** | `:WAVeform:POINts:MODE?` | `{NORMal \| RAW \| MAXimum}` | 設定取樣點擷取模式：<br>• `NORMal`：回傳螢幕顯示點數（通常 1,000 點）。<br>• `RAW`：回傳示波器底層完整採樣記憶體數據。 |
| **`:WAVeform:POINts <count>`** | `:WAVeform:POINts?` | 整數（如 `1000`、`10240`） | 設定欲擷取的波形點數上限。 |
| **`:WAVeform:BYTeorder <order>`** | `:WAVeform:BYTeorder?` | `{LSBFirst \| MSBFirst}` | 當格式設為 `WORD` 時，指定高低位元組順序（預設為 `MSBFirst`）。 |
| **`:WAVeform:UNSigned <setting>`** | `:WAVeform:UNSigned?` | `{{0 \| OFF} \| {1 \| ON}}` | 設定二進位數據傳回為無號整數 (`ON`) 或有號整數 (`OFF`)。 |
| **`n/a`** | **`:WAVeform:PREamble?`** | 10 個數值參數（逗號分隔字串） | **【關鍵命令】** 回傳將點陣二進位換算為真實時間 (s) 與電壓 (V) 的前導因數。 |
| **`n/a`** | **`:WAVeform:DATA?`** | IEEE-488.2 `#` 二進位區塊 | **【核心讀取】** 讀取波形二進位數據區塊。 |

---

### 2. 波形前導參數 (`:WAVeform:PREamble?`) 與真實物理量換算

`:WAVeform:PREamble?` 會傳回 10 個參數，定義如下：

| 索引 | 參數名稱 | 資料型態 | 意義說明 |
| :---: | :--- | :--- | :--- |
| **0** | `FORMAT` | int16 | 數據格式：`0 = BYTE`, `1 = WORD`, `4 = ASCII` |
| **1** | `TYPE` | int16 | 採樣類型：`0 = NORMal`, `1 = PEAK DETECT`, `2 = AVERage`, `3 = HRES` |
| **2** | `POINTS` | int32 | 本次實際傳回的數據點數 |
| **3** | `COUNT` | int32 | 平均次數（預設為 1） |
| **4** | `XINCREMENT` | float64 | X 軸點與點的時間間隔（單位：秒） |
| **5** | `XORIGIN` | float64 | 記憶體中第一個數據點的絕對時間起點（單位：秒） |
| **6** | `XREFERENCE` | int32 | X 軸原點對應的參考點索引（固定為 0） |
| **7** | `YINCREMENT` | float32 | Y 軸單位換算階梯電壓（單位：伏特/階） |
| **8** | `YORIGIN` | float32 | 螢幕垂直中心線對應的基準電壓值（單位：伏特） |
| **9** | `YREFERENCE` | int32 | Y 軸零點/原點對應的數字刻度階數 |

#### 數值轉換公式：
* **時間座標 $Time[i]$**：
  $$Time[i] = ((i - XREFERENCE) \times XINCREMENT) + XORIGIN$$
* **電壓值 $Voltage[i]$**：
  $$Voltage[i] = ((DataValue[i] - YREFERENCE) \times YINCREMENT) + YORIGIN$$

---

## 二、架構二：命令示波器本機 / USB 隨身碟存檔 (:SAVE 子系統)

若希望直接由示波器內部產生檔案存入插在前面板的 USB 隨身碟，則使用 `:SAVE` 相關命令：

| SCPI 命令語法 | 參數選項 | 說明 |
| :--- | :--- | :--- |
| **`:SAVE:WAVeform:FORMat <format>`** | `{CSV \| ASCiixy \| BINary}` | 設定儲存之波形檔案格式：<br>• `CSV`：將所有啟用的通道合併存於單一 `.csv` 檔。<br>• `ASCiixy`：每個通道個別存為獨立的 `.csv` 檔。<br>• `BINary`：示波器專屬高效二進位檔（`.bin`）。 |
| **`:SAVE:WAVeform:LENGth <length>`** | 整數（100 至示波器記憶體上限） | 指定欲寫入檔案的波形長度點數。 |
| **`:SAVE:WAVeform:LENGth:MAX <setting>`** | `{{0 \| OFF} \| {1 \| ON}}` | 是否直接儲存記憶體中的最大點數。 |
| **`:SAVE:WAVeform:SEGMented <opt>`** | `{ALL \| CURRent}` | 若使用分段記憶體 (Segmented Memory)，設定儲存所有段或當前段。 |
| **`:SAVE:WAVeform[:STARt] <file_name>`** | 字串（例如 `"\usb\data1.csv"`） | **觸發儲存**：開始將波形數據寫入指定路徑。 |
| **`:SAVE:MULTi[:STARt] <file_name>`** | 字串（副檔名必須為 `.h5`） | 儲存多通道波形為 HDF5 檔，可用於 Keysight N8900A Infiniium 離線分析軟體。 |

---

## 三、Python (PyVISA) 完整讀取波形並儲存為 CSV 範例

以下 Python 程式演示如何以二進位區塊高效讀取波形，並以向量化計算直接輸出為標準 `.csv` 檔案：

```python
import numpy as np
import pyvisa

# 1. 建立連線
rm = pyvisa.ResourceManager()
# 替換為實際儀器 VISA 資源字串 (如 TCPIP0::192.168.1.100::inst0::INSTR 或 USB0::...::INSTR)
scope = rm.open_resource("TCPIP0::192.168.1.100::inst0::INSTR")
scope.timeout = 20000  # 傳輸大量採樣點需設定較長超時

try:
    # 2. 停止示波器擷取以確保數據穩定
    scope.write(":STOP")

    # 3. 設置傳輸通道與格式 (以 CHANnel1, BYTE 模式為例)
    scope.write(":WAVeform:SOURce CHANnel1")
    scope.write(":WAVeform:FORMat BYTE")
    scope.write(":WAVeform:POINts:MODE RAW")  # 取得底層採樣數據
    scope.write(":WAVeform:POINts 100000")  # 要求 100,000 點
    scope.write(":WAVeform:UNSigned 1")  # 無號位元組 (0~255)

    # 4. 獲取前導資訊 (Preamble)
    preamble_str = scope.query(":WAVeform:PREamble?")
    preamble = [float(x) for x in preamble_str.split(",")]

    x_increment = preamble[4]
    x_origin = preamble[5]
    x_reference = preamble[6]
    y_increment = preamble[7]
    y_origin = preamble[8]
    y_reference = preamble[9]

    # 5. 讀取波形二進位數據塊 (query_binary_values 自動解析 IEEE-488.2 # 標頭)
    raw_bytes = scope.query_binary_values(
        ":WAVeform:DATA?", datatype="B", is_big_endian=True
    )
    raw_array = np.array(raw_bytes, dtype=np.float64)

    # 6. 利用公式向量化換算時間與電壓
    indices = np.arange(len(raw_array))
    time_data = ((indices - x_reference) * x_increment) + x_origin
    voltage_data = ((raw_array - y_reference) * y_increment) + y_origin

    # 7. 儲存為本地電腦 CSV 檔案
    output_filename = "waveform_ch1.csv"
    stacked_data = np.column_stack((time_data, voltage_data))
    np.savetxt(
        output_filename,
        stacked_data,
        delimiter=",",
        header="Time (s),Voltage (V)",
        comments="",
        fmt=["%.9e", "%.6e"],
    )

    print(f"成功擷取 {len(raw_array)} 點，已儲存至 {output_filename}")

finally:
    # 恢復示波器運作並關閉連線
    scope.write(":RUN")
    scope.close()
    rm.close()
```