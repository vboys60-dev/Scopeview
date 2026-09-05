# Keysight Infiniium 系列示波器遠端截圖與資料取回指南

本手冊彙整 Keysight Infiniium（包含 MXR、EXR 等系列）示波器透過 SCPI 遠端指令擷取螢幕畫面並傳回控制端電腦的兩種核心方法、二進位資料結構解析、完整參數規格以及 Python (PyVISA) 自動化程式範例。

---

## 目錄
1. [架構概述](#一-架構概述)
2. [方法一：直接截圖回傳影像資料（:DISPlay:DATA?）](#二-方法一直接截圖回傳影像資料displaydata)
3. [方法二：儲存至示波器硬碟後讀取取回（:DISK 命令群）](#三-方法二儲存至示波器硬碟後讀取取回disk-命令群)
4. [進階報告功能：量測報告匯出（:DISK:SAVE:MREPort）](#四-進階報告功能量測報告匯出disksavemreport)
5. [IEEE 488.2 定長二進位資料塊（Definite-Length Block）解析](#五-ieee-4882-定長二進位資料塊definite-length-block解析)
6. [Python (PyVISA) 自動化實作範例](#六-python-pyvisa-自動化實作範例)
7. [兩種擷取方式之比較與選擇建議](#七-兩種擷取方式之比較與選擇建議)
8. [實務注意事項與常見問題排除](#八-實務注意事項與常見問題排除)

---

## 一、 架構概述

在遠端自動化測試架構中，從 Keysight 示波器擷取畫面主要有兩種操作方式：

1. **直接串流讀取（Direct Query Transfer）**：
   - 透過查詢指令 `:DISPlay:DATA?`，示波器直接將當前畫面影像資料編碼為 IEEE 488.2 定長二進位資料塊（Binary Block）並透過匯流排（LAN / USB / GPIB）回傳至電腦。
   - **特點**：傳輸速度最快、示波器磁碟零讀寫耗損、不需處理暫存檔案管理。
2. **先儲存至示波器本機再讀取（Save to Disk & Fetch）**：
   - 先以 `:DISK:SAVE:IMAGe` 將畫面存成實體檔案至示波器本機硬碟，再以 `:DISK:GETFILE?` 命令將該檔案回傳，最後可視需求以 `:DISK:DELete` 刪除暫存檔。
   - **特點**：適合測試過程中需要在示波器本機留存 Log 記錄、或需要將量測設定嵌入圖檔（Setup Information）的場合。

---

## 二、 方法一：直接截圖回傳影像資料（:DISPlay:DATA?）

### 1. 命令語法
```scpi
:DISPlay:DATA? [<type>[,<screen_mode>[,<compression>[,<inversion>]]]]
```

### 2. 參數說明

| 參數 | 類型 / 可用選項 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `<type>` | `BMP` \| `JPG` \| `GIF` \| `TIF` \| `PNG` | `BMP` | 圖檔格式。實務上建議使用 `PNG` 或 `JPG`，壓縮比高且傳輸迅速。 |
| `<screen_mode>` | `SCReen` \| `GRATicule` | `SCReen` | **SCReen**：擷取整個螢幕畫面（含選單、視窗與量測結果欄）。<br>**GRATicule**：僅擷取 10×8 格線波形繪製區。 |
| `<compression>` | `ON` \| `OFF` | `ON` | 是否啟用影像壓縮。 |
| `<inversion>` | `NORMal` \| `INVert` | `NORMal` | **NORMal**：標準黑底畫面。<br>**INVert**：白底反轉色彩（適合列印與測試報告展示）。 |

### 3. SCPI 呼叫範例
- **擷取全螢幕 PNG 格式圖檔**：
  ```scpi
  :DISPlay:DATA? PNG,SCReen
  ```
- **擷取白底反轉之波形格線區圖片**：
  ```scpi
  :DISPlay:DATA? PNG,GRATicule,ON,INVert
  ```

---

## 三、 方法二：儲存至示波器硬碟後讀取取回（:DISK 命令群）

此方法依序分為儲存、下載與清理三個步驟：

### 步驟 1：儲存截圖至本機硬碟（:DISK:SAVE:IMAGe）
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

### 步驟 2：從示波器取回檔案（:DISK:GETFILE?）
以 IEEE 488.2 二進位區塊格式將示波器本機硬碟中的檔案讀取回傳。

* **命令語法**：
  ```scpi
  :DISK:GETFILE? "<file_name>"
  ```
* **SCPI 範例**：
  ```scpi
  :DISK:GETFILE? "C:\Users\Public\Documents\Infiniium\test.png"
  ```

### 步驟 3：清理示波器本機暫存檔（:DISK:DELete）
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

## 四、 進階報告功能：量測報告匯出（:DISK:SAVE:MREPort）

若測試需要完整記錄「儀器設定狀態」、「螢幕波形圖」以及「底部量測結果數據」，可使用複合報告命令：

* **命令語法**：
  ```scpi
  :DISK:SAVE:MREPort "<filename>"
  ```
* **說明**：
  - `<filename>` 必須包含 `.pdf` 或 `.mht`（MHTML 網頁封裝）副檔名。
  - 儲存完成後，同樣可透過 `:DISK:GETFILE?` 將 PDF 或 MHT 檔案下載回控制電腦。

---

## 五、 IEEE 488.2 定長二進位資料塊（Definite-Length Block）解析

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

## 六、 Python (PyVISA) 自動化實作範例

### 範例 1：直接截圖並儲存至本機（方法一，推薦）
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

### 範例 2：先存至示波器磁碟再讀取回傳（方法二）
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

## 七、 兩種擷取方式之比較與選擇建議

| 評估項目 | 方法一（`:DISPlay:DATA?`） | 方法二（`:DISK:SAVE:IMAGe` + `:DISK:GETFILE?`） |
| :--- | :--- | :--- |
| **指令複雜度** | 極簡（單一 Query 完成） | 較繁瑣（需 SAVE -> GETFILE -> DELete） |
| **傳輸耗時** | 最短（直接於記憶體壓縮串流輸出） | 較長（需等待示波器本機磁碟 I/O 寫入） |
| **硬碟磨損** | 零磁碟寫入 | 示波器 SSD 產生檔案寫入與刪除磨損 |
| **殘留管理** | 免維護，無殘留風險 | 程式端必須主動刪除以防佔滿示波器硬碟 |
| **附加功能** | 純影像輸出 | 可選擇將 Setup 參數資訊嵌入影像中 |
| **最佳適用場合** | **產線量產測試、連續波形截圖、即時監控** | 示波器需留存本機 Log 備查、或生成複合 PDF 報告 |

---

## 八、 實務注意事項與常見問題排除

1. **遠端桌面連線衝突（Error 273）**：
   - 當工程師透過 Windows 遠端桌面（Remote Desktop / RDP）連線控制示波器時，執行 `:DISPlay:DATA?` 或 `:DISK:SAVE:IMAGe` 可能觸發 `Error 273`。
   - **原因**：Windows RDP 會接管並虛擬化顯示子系統，干擾截圖引擎。
   - **解決方式**：執行自動化截圖測試前，請先結束示波器的 Windows 遠端桌面工作階段，或改用 Web 介面遠端監控。
2. **通訊逾時（Timeout）設定**：
   - 擷取高解析度畫面並進行 PNG/JPG 壓縮需要數百毫秒至 2 秒時間。PyVISA 預設逾時（約 2000 ms）容易因瞬時負載而 Timeout，強烈建議將連線物件的 `timeout` 設定於 `10000` ms（10 秒）以上。
3. **報告列印與白底色彩反轉（`INVert`）**：
   - 示波器螢幕預設為黑底以突顯各通道波形色彩，但在將圖檔放入 Word、PDF 報告或列印時，黑底非常耗費碳粉且不易書寫。建議將 `<inversion>` 參數指定為 `INVert`，可輸出清晰的白底波形圖。