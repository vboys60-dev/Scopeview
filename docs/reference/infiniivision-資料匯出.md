# Keysight InfiniiVision 3000G 示波器資料匯出與 VISA 編程實例指南

本指南詳細說明 Keysight InfiniiVision 3000G X-Series 示波器在進行資料匯出（CSV 與 HDF5 格式）時的**資料格式細節**，以及**記憶體點數（記憶點數）設定**與**關鍵 SCPI 控制命令**。

---

## 一、 資料格式說明

在 3000G 示波器中，匯出波形資料主要有兩種途徑：
1. **遠端主機讀取（PC Pull）**：透過 VISA 介面將資料傳輸至電腦，再由電腦程式寫入 CSV 等檔案。
2. **本機 USB 儲存（Scope Push）**：直接透過示波器面板或 SCPI 命令，將資料寫入插在示波器上的 USB 隨身碟。

### 1. CSV 格式 (Comma-Separated Values)

CSV 是最通用的文字資料格式，其內容為逗號分隔的數值。

#### A. 本機 USB 儲存格式
當使用儲存子系統（`:SAVE`）將波形儲存為 CSV 檔案時，支援以下兩種格式：
* **`ASCiixy` 格式**：為**每一個**目前顯示（開啟）的類比通道分別建立一個獨立的 `.csv` 檔案。檔案中包含時間與電壓的雙軸座標資料（X-Y 數據對）。
* **`CSV` 格式**：建立**單一**個 `.csv` 檔案，其中併排包含**所有**目前顯示（開啟）的類比通道資料，適合多通道同步分析。

#### B. 遠端傳輸資料轉換 (ASCII vs Binary)
當透過 VISA 使用 `:WAVeform` 子系統讀取資料時：
* **ASCII 格式 (`:WAV:FORM ASCii`)**：示波器會自動在內部將電壓編碼值轉換為實際的物理電壓值（浮點數），並以逗號分隔的字串傳回。在此格式下，若波形中有未取樣到的空洞（Holes），會以特殊值 `9.9e+37` 表示。
* **二進位格式 (`:WAV:FORM BYTE` 或 `WORD`)**：為了加快傳輸速度，通常會傳輸未經轉換的原始 8 位元（BYTE）或 16 位元（WORD）二進位整數塊。電腦端程式必須讀取**波形導言 (Preamble)**，並使用以下公式進行物理量轉換：
  $$\text{Time} = (\text{index} - X_{\text{reference}}) \times X_{\text{increment}} + X_{\text{origin}}$$
  $$\text{Voltage} = (\text{DataValue} - Y_{\text{reference}}) \times Y_{\text{increment}} + Y_{\text{origin}}$$
  * *註：在 3000G 中，$X_{\text{reference}}$ 通常為 0（代表顯示畫面的起點）。*

---

### 2. HDF5 格式 (.h5)

HDF5 是一種高效能的結構化二進位資料格式，適合保存大規模波形數據與完整的儀器元數據（Metadata）。在 3000G 中主要應用於：
* **多通道波形儲存（`:SAVE:MULTi`）**：將所有類比通道的完整波形與比例設定打包儲存為一個 `.h5` 檔案。此檔案可以直接匯入 **Keysight N8900A Infiniium Offline** 離線波形分析軟體中進行精密分析。
* **參考波形儲存（`:SAVE:WMEMory`）**：將指定的通道波形儲存至 USB 隨身碟，其預設且唯一的副檔名即為 `.h5`。之後可隨時透過 `:RECall:WMEMory` 將其載回示波器的參考波形位置（WMEM1~4）中顯示。

---

## 二、 記憶點數與取樣深度設定 (關鍵命令)

要完整匯出高品質的波形，必須正確配置**儀器硬體取樣深度（Acquisition Memory Depth）**與**資料傳輸/儲存點數（Waveform Transfer/Save Points）**。

### 1. 硬體記憶深度設定 (記憶點數)
這決定了示波器在單次擷取中，硬體實際採集並存在記憶體中的總點數。

* **命令：`:ACQuire:POINts[:ANALog] <points>`**
  * `<points>` 可設定為：
    * `AUTO`：自動模式，由示波器根據目前的時間掃描檔速（Timebase）自動選擇最佳的記憶深度。
    * `<points_value>`：手動設定整數點數（例如 `1000000`）。這會使示波器進入**數位化儀模式 (Digitizer Mode)**。
  * **查詢：`:ACQuire:POINts[:ANALog]?`**：查詢硬體實際擷取到的點數。
  * **自動切換：`:ACQuire:POINts[:ANALog]:AUTO <setting>`**：設定是否啟用自動決定深度（`ON` / `OFF`）。

---

### 2. 遠端傳輸點數控制 (PC 讀取時使用)
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

### 3. USB 儲存點數控制 (本機儲存時使用)
當直接控制示波器寫入 USB 隨身碟時，使用以下命令設定儲存長度：

* **`:SAVE:WAVeform:LENGth:MAX <setting>`**
  * `ON` (或 `1`)：強制儲存目前擷取到的**最大可用波形點數**（完整深度）。
  * `OFF` (或 `0`)：手動指定儲存長度。
* **`:SAVE:WAVeform:LENGth <length>`**
  * 當 `LENGth:MAX` 設為 `OFF` 時，指定要儲存的波形點數（100 至最大長度之間的整數）。

---

## 三、 完整匯出控制命令工作流

### 途徑 A：遠端 PC 透過 VISA 讀取並轉存為 CSV (推薦 Python 實例)

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

### 途徑 B：控制示波器直接將資料寫入本機 USB 隨身碟

此方法不需要透過 VISA 傳輸大量資料，適合現場測試。

#### 1. 匯出為一併包含所有通道的 CSV 檔案
```text
:SAVE:PWD "/usb/"                         # 設定目前儲存路徑為 USB 根目錄
:SAVE:WAVeform:FORMat CSV                 # 設定儲存格式為 CSV (單一檔案併排所有通道)
:SAVE:WAVeform:LENGth:MAX ON              # 設定儲存最大可用點數 (完整深度)
:SAVE:WAVeform:STARt "multi_channel_data" # 開始儲存，會產生 multi_channel_data.csv
```

#### 2. 匯出為多通道離線分析專用 HDF5 (.h5) 檔案
```text
:SAVE:PWD "/usb/"                         # 設定儲存路徑為 USB
:SAVE:MULTi:STARt "offline_analysis"      # 儲存多通道二進位 H5，會產生 offline_analysis.h5
                                          # 可直接使用 Keysight N8900A 軟體開啟。
```

#### 3. 將通道波形存為參考波形 HDF5 (.h5) 檔案
```text
:SAVE:PWD "/usb/"                         # 設定儲存路徑
:SAVE:WMEMory:SOURce CHANnel1             # 設定參考波形來源為通道 1
:SAVE:WMEMory:STARt "channel1_ref"        # 開始儲存，會產生 channel1_ref.h5
```

---
*本指南所列 SCPI 命令與格式標準，嚴格依據 Keysight InfiniiVision 3000G X-Series 示波器程式開發人員指南編撰。*
