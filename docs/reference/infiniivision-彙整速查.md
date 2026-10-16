# Keysight 示波器截圖回傳、HDF5 與 CSV 匯出完整指令手冊

本手冊彙整 Keysight InfiniiVision 系列（含 HD3、HD5、3000G、4000G 等）示波器於 SCPI 遠端控制時，執行**螢幕截圖回傳**、**HDF5 (.h5) 檔案格式**、**CSV 格式解析**及**記憶體深度與波形點數配置**之完整命令與 Python 實作腳本。

---

## 1. 示波器截圖回傳命令

| 指令語法 | 參數選項 | 說明 | 回傳格式 |
| :--- | :--- | :--- | :--- |
| `:DISPlay:DATA? [<format>]` | `PNG`, `BMP` | 查詢並傳回螢幕畫面資料。 | IEEE-488.2 二進位區塊 (`#8...`) |
| `:HCOPy:SDUMp:DATA? [<format>]` | `PNG`, `BMP` | 截取螢幕數據（與 `:DISPlay:DATA?` 作用相同）。 | IEEE-488.2 二進位區塊 (`#8...`) |
| `:HCOPy:SDUMp[:DATA]:FORMat <format>` | `PNG`, `BMP` | 設定截圖預設影像格式。 | - |
| `:HCOPy:SDUMp[:DATA]:FORMat?` | - | 查詢目前設定的影像格式。 | `{PNG \| BMP}` |

---

## 2. HD5 / HDF5 (.h5) 資料格式說明

- **定義**：HDF5（Hierarchical Data Format v5，副檔名 `.h5`）是高容量階層式資料結構。
- **優勢**：
  - 支援將多個 Channel、Math 波形及分段記憶體（Segmented Memory）打包封裝。
  - 支援 GZIP 壓縮，較純文字 CSV 體積節省 70%~90%，傳輸與寫入速度大幅提升。
  - 內含 Metadata 屬性（X/Y 刻度、取樣率、Offset 等）。
  - 可直接被 Python (`h5py`)、MATLAB 及 Keysight Infiniium Offline (N8900A) 解析。

---

## 3. CSV 資料格式

### (A) 儀器本機直接儲存之 CSV
包含 Header（儀表型號、序號、取樣率、垂直/水平 Scale 與 Offset）及資料列：
```csv
x-axis, CHANnel1, CHANnel2
-5.000000e-04, 1.250000e+00, -3.125000e-01
-4.999999e-04, 1.252000e+00, -3.120000e-01
```

### (B) 透過 SCPI 讀取後重構之 CSV
利用 `:WAVeform:DATA?` 讀取數值，搭配 `:WAVeform:PREamble?` 參數換算：
- 時間：$$Time_i = X_{origin} + (i - X_{reference}) \times X_{increment}$$
- 電壓：$$Voltage_i = (RawValue_i - Y_{reference}) \times Y_{increment} + Y_{origin}$$

---

## 4. 記憶點數與波形匯出控制指令

### (A) 硬體擷取記憶深度 (:ACQuire)
- `:ACQuire:POINts[:ANALog] <points>`：設定目標記憶深度（例如 `100000`, `AUTO`）。
- `:ACQuire:POINts[:ANALog]:AUTO {{0|OFF} | {1|ON}}`：關閉/開啟記憶深度自動調整。
- `:ACQuire:POINts:MAX?`：查詢當前允許的最大擷取點數。
- `:DIGitize CHANnel1`：觸發單次採集並停止，確保波形記憶體被鎖定。

### (B) 波形傳輸子系統 (:WAVeform)
- `:WAVeform:SOURce CHANnel1`：指定讀取通道。
- `:WAVeform:POINts:MODE RAW`：**必設為 RAW 模式才能讀取完整的深記憶體數據**。
- `:WAVeform:POINts <points>`：指定傳輸點數。
- `:WAVeform:POINts?`：查詢實際可讀取點數。
- `:WAVeform:FORMat WORD`：設定 16-bit 傳輸（相容高解析 ADC）。
- `:WAVeform:BYTeorder LSBF`：設定為 Little-Endian 位元組順序。
- `:WAVeform:PREamble?`：查詢波形縮放計算係數。
- `:WAVeform:DATA?`：傳回二進位數據區塊。

### (C) 本機另存 CSV (:SAVE)
- `:SAVE:WAVeform:FORMat CSV`：指定存為 CSV。
- `:SAVE:WAVeform:LENGth:MAX ON`：以最大可用記憶點數儲存。
- `:SAVE:WAVeform[:STARt] "/usb/wave.csv"`：儲存檔案至 USB 儲存裝置。

---

## 5. Python (pyvisa) 自動化實作範例

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