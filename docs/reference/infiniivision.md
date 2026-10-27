# InfiniiVision 參考

> 由下列檔案合併而成（原檔見 git 歷史）：infiniivision-彙整速查.md、infiniivision-截圖.md、infiniivision-波形資料.md、infiniivision-資料匯出.md


---

## 〔infiniivision-彙整速查〕

## Keysight 示波器截圖回傳、HDF5 與 CSV 匯出完整指令手冊

本手冊彙整 Keysight InfiniiVision 系列（含 HD3、HD5、3000G、4000G 等）示波器於 SCPI 遠端控制時，執行**螢幕截圖回傳**、**HDF5 (.h5) 檔案格式**、**CSV 格式解析**及**記憶體深度與波形點數配置**之完整命令與 Python 實作腳本。

---

### 1. 示波器截圖回傳命令

| 指令語法 | 參數選項 | 說明 | 回傳格式 |
| :--- | :--- | :--- | :--- |
| `:DISPlay:DATA? [<format>]` | `PNG`, `BMP` | 查詢並傳回螢幕畫面資料。 | IEEE-488.2 二進位區塊 (`#8...`) |
| `:HCOPy:SDUMp:DATA? [<format>]` | `PNG`, `BMP` | 截取螢幕數據（與 `:DISPlay:DATA?` 作用相同）。 | IEEE-488.2 二進位區塊 (`#8...`) |
| `:HCOPy:SDUMp[:DATA]:FORMat <format>` | `PNG`, `BMP` | 設定截圖預設影像格式。 | - |
| `:HCOPy:SDUMp[:DATA]:FORMat?` | - | 查詢目前設定的影像格式。 | `{PNG \| BMP}` |

---

### 2. HD5 / HDF5 (.h5) 資料格式說明

- **定義**：HDF5（Hierarchical Data Format v5，副檔名 `.h5`）是高容量階層式資料結構。
- **優勢**：
  - 支援將多個 Channel、Math 波形及分段記憶體（Segmented Memory）打包封裝。
  - 支援 GZIP 壓縮，較純文字 CSV 體積節省 70%~90%，傳輸與寫入速度大幅提升。
  - 內含 Metadata 屬性（X/Y 刻度、取樣率、Offset 等）。
  - 可直接被 Python (`h5py`)、MATLAB 及 Keysight Infiniium Offline (N8900A) 解析。

---

### 3. CSV 資料格式

#### (A) 儀器本機直接儲存之 CSV
包含 Header（儀表型號、序號、取樣率、垂直/水平 Scale 與 Offset）及資料列：
```csv
x-axis, CHANnel1, CHANnel2
-5.000000e-04, 1.250000e+00, -3.125000e-01
-4.999999e-04, 1.252000e+00, -3.120000e-01
```

#### (B) 透過 SCPI 讀取後重構之 CSV
利用 `:WAVeform:DATA?` 讀取數值，搭配 `:WAVeform:PREamble?` 參數換算：
- 時間：$$Time_i = X_{origin} + (i - X_{reference}) \times X_{increment}$$
- 電壓：$$Voltage_i = (RawValue_i - Y_{reference}) \times Y_{increment} + Y_{origin}$$

---

### 4. 記憶點數與波形匯出控制指令

#### (A) 硬體擷取記憶深度 (:ACQuire)
- `:ACQuire:POINts[:ANALog] <points>`：設定目標記憶深度（例如 `100000`, `AUTO`）。
- `:ACQuire:POINts[:ANALog]:AUTO {{0|OFF} | {1|ON}}`：關閉/開啟記憶深度自動調整。
- `:ACQuire:POINts:MAX?`：查詢當前允許的最大擷取點數。
- `:DIGitize CHANnel1`：觸發單次採集並停止，確保波形記憶體被鎖定。

#### (B) 波形傳輸子系統 (:WAVeform)
- `:WAVeform:SOURce CHANnel1`：指定讀取通道。
- `:WAVeform:POINts:MODE RAW`：**必設為 RAW 模式才能讀取完整的深記憶體數據**。
- `:WAVeform:POINts <points>`：指定傳輸點數。
- `:WAVeform:POINts?`：查詢實際可讀取點數。
- `:WAVeform:FORMat WORD`：設定 16-bit 傳輸（相容高解析 ADC）。
- `:WAVeform:BYTeorder LSBF`：設定為 Little-Endian 位元組順序。
- `:WAVeform:PREamble?`：查詢波形縮放計算係數。
- `:WAVeform:DATA?`：傳回二進位數據區塊。

#### (C) 本機另存 CSV (:SAVE)
- `:SAVE:WAVeform:FORMat CSV`：指定存為 CSV。
- `:SAVE:WAVeform:LENGth:MAX ON`：以最大可用記憶點數儲存。
- `:SAVE:WAVeform[:STARt] "/usb/wave.csv"`：儲存檔案至 USB 儲存裝置。

---

### 5. Python (pyvisa) 自動化實作範例

```python
import pyvisa
import numpy as np

# 1. 連線至示波器
rm = pyvisa.ResourceManager()
scope = rm.open_resource('TCPIP0::192.168.1.100::inst0::INSTR')
scope.timeout = 30000  # 30 秒

# 2. 螢幕截圖並回傳儲存為 PNG
scope.write(":DISPlay:DATA? PNG")
raw_img = scope.read_raw()
header_len = 2 + int(chr(raw_img[1]))
img_bytes = raw_img[header_len:-1]  # 剝除 IEEE-488.2 標頭與結尾換行
with open("screenshot.png", "wb") as f:
    f.write(img_bytes)
print("截圖已儲存為 screenshot.png")

# 3. 配置硬體記憶體深度
scope.write(":ACQuire:POINts:AUTO OFF")
scope.write(":ACQuire:POINts 100000")  # 100k 點
scope.write(":DIGitize CHANnel1")

# 4. 配置波形讀取參數（RAW 深度記憶體模式）
scope.write(":WAVeform:SOURce CHANnel1")
scope.write(":WAVeform:POINts:MODE RAW")
scope.write(":WAVeform:POINts 100000")
scope.write(":WAVeform:FORMat WORD")
scope.write(":WAVeform:BYTeorder LSBF")

# 5. 讀取 Preamble 取得換算參數
preamble = scope.query(":WAVeform:PREamble?").split(",")
x_inc = float(preamble[4])
x_org = float(preamble[5])
x_ref = float(preamble[6])
y_inc = float(preamble[7])
y_org = float(preamble[8])
y_ref = float(preamble[9])

# 6. 讀取數據並重構為 CSV
scope.write(":WAVeform:DATA?")
raw_vals = np.array(scope.read_binary_values(datatype='H', is_big_endian=False))

time_axis = x_org + (np.arange(len(raw_vals)) - x_ref) * x_inc
volt_axis = (raw_vals - y_ref) * y_inc + y_org

with open("waveform_data.csv", "w", encoding="utf-8") as f:
    f.write("Time (s),Voltage (V)\n")
    for t, v in zip(time_axis, volt_axis):
        f.write(f"{t:E},{v:.6f}\n")

print(f"成功匯出 {len(raw_vals)} 筆資料至 waveform_data.csv")
scope.close()
```

---

## 〔infiniivision-截圖〕

## Keysight 示波器截圖與影像回傳 SCPI 命令指南

本文件適用於 Keysight InfiniiVision 系列示波器（包含 3000G / 3000X 等），整理透過遠端程式命令（VISA / SCPI）進行螢幕截圖並回傳影像資料至電腦端的完整命令清單。

---

### 一、核心截圖回傳命令 (Query Commands)

| SCPI 命令語法 | 支援參數 | 傳回資料格式 | 說明 |
| :--- | :--- | :--- | :--- |
| **`:DISPlay:DATA? [<format>][,<palette>]`** | `<format>`: `{BMP \| BMP8bit \| PNG}`<br>`<palette>`: `{COLor \| GRAYscale}` | IEEE-488.2 `#` 二進位區塊 | **官方推薦命令**。擷取當前螢幕畫面並直接回傳圖片二進位串流。若未指定參數，則採用目前面板預設格式。 |
| **`:HCOPY:SDUMp:DATA? [<format>]`** | `<format>`: `{PNG \| BMP \| BMP8bit}` | IEEE-488.2 `#` 二進位區塊 | **螢幕傾印回傳命令**。功能與 `:DISPlay:DATA?` 相似，回傳當前螢幕二進位資料。 |
| **`:PRINt? [<options>]`** | `<options>`: `{COLor \| GRAYscale \| BMP \| BMP8bit \| PNG}` | IEEE-488.2 `#` 二進位區塊 | **過時命令 (Obsolete)**。為相容早期舊型號示波器而保留，官方建議統一採用 `:DISPlay:DATA?`。 |

---

### 二、截圖前置設定命令

| SCPI 命令語法 | 查詢語法 | 參數設定 | 作用與注意事項 |
| :--- | :--- | :--- | :--- |
| **`:HARDcopy:INKSaver <setting>`** | `:HARDcopy:INKSaver?` | `{{0 \| OFF} \| {1 \| ON}}` | **色彩反轉（省墨模式）**。<br>• 示波器預設為 `ON`（列印模式：白底黑字）。<br>• **欲取得示波器原始黑底彩色畫面，截圖前必須先下達 `:HARDcopy:INKSaver OFF`**。 |
| **`:HCOPY:SDUMp:FORMat <format>`** | `:HCOPY:SDUMp:FORMat?` | `{BMP \| BMP8bit \| PNG}` | 設定傾印（SDUMp）之預設格式（預設為 `PNG`）。 |
| **`:HARDcopy:PALette <palette>`** | `:HARDcopy:PALette?` | `{COLor \| GRAYscale \| NONE}` | 設定截圖調色盤（彩色 / 灰階）。 |
| **`:HARDcopy:AREA <area>`** | `:HARDcopy:AREA?` | `{SCR \| GRAT}` | 設定截圖範圍：<br>• `SCR`：全螢幕 (Screen)<br>• `GRAT`：僅格線波形區 (Graticule) |

---

### 三、對比：本機與隨身碟存檔命令 (:SAVE 子系統)

若不是要回傳電腦，而是讓示波器將圖片存至其內部儲存區或前面板插上的 USB 隨身碟，則使用 `:SAVE:IMAGe` 相關命令：

* **`:SAVE:IMAGe[:STARt] [<file_name>]`**：將截圖存入指定檔案（如 `\usb\screen.png`）。
* **`:SAVE:IMAGe:FORMat <format>`**：設定格式（`BMP`, `BMP24bit`, `BMP8bit`, `PNG`）。
* **`:SAVE:IMAGe:INKSaver {{0 | OFF} | {1 | ON}}`**：設定存檔是否啟用省墨反白。
* **`:SAVE:IMAGe:PALette <palette>`**：設定存檔調色盤（`COLor` / `GRAYscale`）。
* **`:SAVE:IMAGe:FACTors {{0 | OFF} | {1 | ON}}`**：設定是否一併將示波器設置參數寫入同名 `.txt` 檔。

---

### 四、Python (PyVISA) 擷取範例

```python
import pyvisa

# 建立 VISA 資源連線
rm = pyvisa.ResourceManager()
# 替換為實際連線字串 (USB / LAN)
scope = rm.open_resource("TCPIP0::192.168.1.100::inst0::INSTR")
scope.timeout = 15000  # 傳輸圖片耗時較長，建議設定 15 秒以上

# 步驟 1: 關閉省墨模式 (獲取真實螢幕黑底效果)
scope.write(":HARDcopy:INKSaver OFF")

# 步驟 2: 查詢並回傳截圖二進位數據 (以 PNG 彩色為例)
# query_binary_values 會自動解析 IEEE-488.2 # 標頭並提取圖片 bytes
image_data = scope.query_binary_values(
    ":DISPlay:DATA? PNG, COLor", datatype="B", is_big_endian=True
)

# 步驟 3: 儲存至本機檔案
with open("scope_screenshot.png", "wb") as f:
    f.write(bytearray(image_data))

print("截圖已成功儲存至 scope_screenshot.png")

scope.close()
rm.close()
```

---

## 〔infiniivision-波形資料〕

## Keysight 示波器波形資料回傳與存檔 SCPI 命令指南

本文件適用於 Keysight (原 Agilent / HP) InfiniiVision 3000G / 3000X 等系列示波器，詳細說明如何透過遠端命令讀取波形採樣數據回傳至電腦端，以及命令示波器儲存波形檔案至隨身碟/本機硬碟。

---

### 一、架構一：遠端傳輸波形至 PC (:WAVeform 子系統)

這是自動化量測最主流的作法。控制端 PC 透過 SCPI 查詢命令獲取波形點陣二進位數據與刻度換算參數，直接於電腦端產生資料檔案（如 `.csv`、`.bin`、`.npy`）。

#### 1. 核心傳輸命令列表

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

#### 2. 波形前導參數 (`:WAVeform:PREamble?`) 與真實物理量換算

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

##### 數值轉換公式：
* **時間座標 $Time[i]$**：
  $$Time[i] = ((i - XREFERENCE) \times XINCREMENT) + XORIGIN$$
* **電壓值 $Voltage[i]$**：
  $$Voltage[i] = ((DataValue[i] - YREFERENCE) \times YINCREMENT) + YORIGIN$$

---

### 二、架構二：命令示波器本機 / USB 隨身碟存檔 (:SAVE 子系統)

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

### 三、Python (PyVISA) 完整讀取波形並儲存為 CSV 範例

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

---

## 〔infiniivision-資料匯出〕

## Keysight InfiniiVision 3000G 示波器資料匯出與 VISA 編程實例指南

本指南詳細說明 Keysight InfiniiVision 3000G X-Series 示波器在進行資料匯出（CSV 與 HDF5 格式）時的**資料格式細節**，以及**記憶體點數（記憶點數）設定**與**關鍵 SCPI 控制命令**。

---

### 一、 資料格式說明

在 3000G 示波器中，匯出波形資料主要有兩種途徑：
1. **遠端主機讀取（PC Pull）**：透過 VISA 介面將資料傳輸至電腦，再由電腦程式寫入 CSV 等檔案。
2. **本機 USB 儲存（Scope Push）**：直接透過示波器面板或 SCPI 命令，將資料寫入插在示波器上的 USB 隨身碟。

#### 1. CSV 格式 (Comma-Separated Values)

CSV 是最通用的文字資料格式，其內容為逗號分隔的數值。

##### A. 本機 USB 儲存格式
當使用儲存子系統（`:SAVE`）將波形儲存為 CSV 檔案時，支援以下兩種格式：
* **`ASCiixy` 格式**：為**每一個**目前顯示（開啟）的類比通道分別建立一個獨立的 `.csv` 檔案。檔案中包含時間與電壓的雙軸座標資料（X-Y 數據對）。
* **`CSV` 格式**：建立**單一**個 `.csv` 檔案，其中併排包含**所有**目前顯示（開啟）的類比通道資料，適合多通道同步分析。

##### B. 遠端傳輸資料轉換 (ASCII vs Binary)
當透過 VISA 使用 `:WAVeform` 子系統讀取資料時：
* **ASCII 格式 (`:WAV:FORM ASCii`)**：示波器會自動在內部將電壓編碼值轉換為實際的物理電壓值（浮點數），並以逗號分隔的字串傳回。在此格式下，若波形中有未取樣到的空洞（Holes），會以特殊值 `9.9e+37` 表示。
* **二進位格式 (`:WAV:FORM BYTE` 或 `WORD`)**：為了加快傳輸速度，通常會傳輸未經轉換的原始 8 位元（BYTE）或 16 位元（WORD）二進位整數塊。電腦端程式必須讀取**波形導言 (Preamble)**，並使用以下公式進行物理量轉換：
  $$\text{Time} = (\text{index} - X_{\text{reference}}) \times X_{\text{increment}} + X_{\text{origin}}$$
  $$\text{Voltage} = (\text{DataValue} - Y_{\text{reference}}) \times Y_{\text{increment}} + Y_{\text{origin}}$$
  * *註：在 3000G 中，$X_{\text{reference}}$ 通常為 0（代表顯示畫面的起點）。*

---

#### 2. HDF5 格式 (.h5)

HDF5 是一種高效能的結構化二進位資料格式，適合保存大規模波形數據與完整的儀器元數據（Metadata）。在 3000G 中主要應用於：
* **多通道波形儲存（`:SAVE:MULTi`）**：將所有類比通道的完整波形與比例設定打包儲存為一個 `.h5` 檔案。此檔案可以直接匯入 **Keysight N8900A Infiniium Offline** 離線波形分析軟體中進行精密分析。
* **參考波形儲存（`:SAVE:WMEMory`）**：將指定的通道波形儲存至 USB 隨身碟，其預設且唯一的副檔名即為 `.h5`。之後可隨時透過 `:RECall:WMEMory` 將其載回示波器的參考波形位置（WMEM1~4）中顯示。

---

### 二、 記憶點數與取樣深度設定 (關鍵命令)

要完整匯出高品質的波形，必須正確配置**儀器硬體取樣深度（Acquisition Memory Depth）**與**資料傳輸/儲存點數（Waveform Transfer/Save Points）**。

#### 1. 硬體記憶深度設定 (記憶點數)
這決定了示波器在單次擷取中，硬體實際採集並存在記憶體中的總點數。

* **命令：`:ACQuire:POINts[:ANALog] <points>`**
  * `<points>` 可設定為：
    * `AUTO`：自動模式，由示波器根據目前的時間掃描檔速（Timebase）自動選擇最佳的記憶深度。
    * `<points_value>`：手動設定整數點數（例如 `1000000`）。這會使示波器進入**數位化儀模式 (Digitizer Mode)**。
  * **查詢：`:ACQuire:POINts[:ANALog]?`**：查詢硬體實際擷取到的點數。
  * **自動切換：`:ACQuire:POINts[:ANALog]:AUTO <setting>`**：設定是否啟用自動決定深度（`ON` / `OFF`）。

---

#### 2. 遠端傳輸點數控制 (PC 讀取時使用)
擷取完成後，您可以指定要從記憶體中下載多少點到電腦。這可以與硬體深度不同，用於進行資料抽取（Decimation）。

* **第一步：設定點數模式**
  * **`:WAVeform:POINts:MODE <points_mode>`**
    * `RAW`：從原始取樣記錄中讀取。若要下載超過 62,500 點以上的**完整記憶深度原始數據**，**必須**設定為 `RAW`，且示波器必須處於 **STOP** 狀態。
    * `NORMal`：下載「測量記錄（Measurement Record）」，為原始資料的 62,500 點（最大值）重建表示。
    * `MAXimum`：下載目前設定下的最大可用點數（最高支援 4,000,000 點，數位通道可達 8,000,000 點）。

* **第二步：指定下載點數**
  * **`:WAVeform:POINts <wfm_points>`**
    * 設定 `:WAVeform:DATA?` 查詢時要傳回的具體點數。
    * 參數可為 `100` 到 `10000000` 之間的整數（必須是 1,000 的偶數因數，例如 100, 250, 500, 1000，或直接設定為 `MAXimum`）。

---

#### 3. USB 儲存點數控制 (本機儲存時使用)
當直接控制示波器寫入 USB 隨身碟時，使用以下命令設定儲存長度：

* **`:SAVE:WAVeform:LENGth:MAX <setting>`**
  * `ON` (或 `1`)：強制儲存目前擷取到的**最大可用波形點數**（完整深度）。
  * `OFF` (或 `0`)：手動指定儲存長度。
* **`:SAVE:WAVeform:LENGth <length>`**
  * 當 `LENGth:MAX` 設為 `OFF` 時，指定要儲存的波形點數（100 至最大長度之間的整數）。

---

### 三、 完整匯出控制命令工作流

#### 途徑 A：遠端 PC 透過 VISA 讀取並轉存為 CSV (推薦 Python 實例)

此工作流會先透過 `:DIGitize` 進行強制單次同步擷取，再以二進位 BYTE 格式高速讀取 RAW 數據，最後於 PC 端計算並輸出為 CSV。

```python
import sys
import struct
import pyvisa

# 1. 初始化 VISA 連接
rm = pyvisa.ResourceManager()
# 請替換為您示波器的實際 VISA 資源名稱 (USB, TCPIP, GPIB)
visa_address = 'TCPIP0::192.168.1.100::inst0::INSTR'
try:
    scope = rm.open_resource(visa_address)
    scope.timeout = 15000  # 設定超時 (毫秒)
    scope.chunk_size = 1024000
except Exception as e:
    print(f"無法連接示波器: {e}")
    sys.exit()

# 2. 設定硬體記憶深度並擷取波形
scope.write(":ACQuire:POINts 1000000")  # 要求硬體採樣 1M 點 (記憶點數)
scope.write(":ACQuire:TYPE NORMal")      # 正常取樣模式
scope.write(":DIGitize CHANnel1")        # 強制進行單次同步擷取，擷取完成後會自動 STOP

# 3. 配置波形匯出參數 (RAW 模式)
scope.write(":WAVeform:SOURce CHANnel1")      # 設定資料來源為通道 1
scope.write(":WAVeform:POINts:MODE RAW")      # 啟用 RAW 原始點數模式 (必須在 STOP 下)
scope.write(":WAVeform:POINts 1000000")       # 設定要求傳輸 1M 點
scope.write(":WAVeform:FORMat BYTE")          # 使用 BYTE (8-bit) 高速二進位格式
scope.write(":WAVeform:UNSigned ON")          # 設定傳回無符號整數 (0-255)

# 4. 讀取波形導言 (Preamble) 用於後續物理量轉換
preamble_str = scope.query(":WAVeform:PREamble?")
preamble = [float(x) for x in preamble_str.split(',')]

wav_format    = int(preamble[0])  # 0=BYTE, 1=WORD, 4=ASCII
acq_type      = int(preamble[1])  # 0=NORMAL, 1=PEAK, 2=AVERAGE, 3=HRES
points        = int(preamble[2])  # 實際傳輸點數
count         = int(preamble[3])  # 平均次數 (通常為 1)
x_increment   = preamble[4]       # 時間步進 (X軸解析度)
x_origin      = preamble[5]       # 起始時間
x_reference   = int(preamble[6])  # 時間參考點 (通常為 0)
y_increment   = preamble[7]       # 電壓步進
y_origin      = preamble[8]       # 螢幕中心電壓
y_reference   = int(preamble[9])  # 電壓參考點 (通常為 125/128)

print(f"實際傳輸點數: {points}")
print(f"時間解析度 (X_inc): {x_increment} sec/point")
print(f"電壓解析度 (Y_inc): {y_increment} V/step")

# 5. 高速讀取二進位資料塊
scope.write(":WAVeform:DATA?")
raw_data = scope.read_bytes_block() # 自動解析 IEEE 488.2 數據頭 (例如 #8000100000)

# 6. 電腦端計算並寫入 CSV 檔案
output_file = "waveform_data.csv"
with open(output_file, "w") as f:
    f.write("Time (s),Voltage (V)\n")
    for i in range(points):
        # 計算時間與實際電壓值
        time_val = x_origin + (i * x_increment)
        voltage_val = (raw_data[i] - y_reference) * y_increment + y_origin
        f.write(f"{time_val:.9E},{voltage_val:.6f}\n")

print(f"成功將 {points} 點波形資料寫入 {output_file}")
scope.close()
```

---

#### 途徑 B：控制示波器直接將資料寫入本機 USB 隨身碟

此方法不需要透過 VISA 傳輸大量資料，適合現場測試。

##### 1. 匯出為一併包含所有通道的 CSV 檔案
```text
:SAVE:PWD "/usb/"                         # 設定目前儲存路徑為 USB 根目錄
:SAVE:WAVeform:FORMat CSV                 # 設定儲存格式為 CSV (單一檔案併排所有通道)
:SAVE:WAVeform:LENGth:MAX ON              # 設定儲存最大可用點數 (完整深度)
:SAVE:WAVeform:STARt "multi_channel_data" # 開始儲存，會產生 multi_channel_data.csv
```

##### 2. 匯出為多通道離線分析專用 HDF5 (.h5) 檔案
```text
:SAVE:PWD "/usb/"                         # 設定儲存路徑為 USB
:SAVE:MULTi:STARt "offline_analysis"      # 儲存多通道二進位 H5，會產生 offline_analysis.h5
                                          # 可直接使用 Keysight N8900A 軟體開啟。
```

##### 3. 將通道波形存為參考波形 HDF5 (.h5) 檔案
```text
:SAVE:PWD "/usb/"                         # 設定儲存路徑
:SAVE:WMEMory:SOURce CHANnel1             # 設定參考波形來源為通道 1
:SAVE:WMEMory:STARt "channel1_ref"        # 開始儲存，會產生 channel1_ref.h5
```

---
*本指南所列 SCPI 命令與格式標準，嚴格依據 Keysight InfiniiVision 3000G X-Series 示波器程式開發人員指南編撰。*
