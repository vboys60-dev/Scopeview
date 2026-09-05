# Keysight 示波器截圖與影像回傳 SCPI 命令指南

本文件適用於 Keysight InfiniiVision 系列示波器（包含 3000G / 3000X 等），整理透過遠端程式命令（VISA / SCPI）進行螢幕截圖並回傳影像資料至電腦端的完整命令清單。

---

## 一、核心截圖回傳命令 (Query Commands)

| SCPI 命令語法 | 支援參數 | 傳回資料格式 | 說明 |
| :--- | :--- | :--- | :--- |
| **`:DISPlay:DATA? [<format>][,<palette>]`** | `<format>`: `{BMP \| BMP8bit \| PNG}`<br>`<palette>`: `{COLor \| GRAYscale}` | IEEE-488.2 `#` 二進位區塊 | **官方推薦命令**。擷取當前螢幕畫面並直接回傳圖片二進位串流。若未指定參數，則採用目前面板預設格式。 |
| **`:HCOPY:SDUMp:DATA? [<format>]`** | `<format>`: `{PNG \| BMP \| BMP8bit}` | IEEE-488.2 `#` 二進位區塊 | **螢幕傾印回傳命令**。功能與 `:DISPlay:DATA?` 相似，回傳當前螢幕二進位資料。 |
| **`:PRINt? [<options>]`** | `<options>`: `{COLor \| GRAYscale \| BMP \| BMP8bit \| PNG}` | IEEE-488.2 `#` 二進位區塊 | **過時命令 (Obsolete)**。為相容早期舊型號示波器而保留，官方建議統一採用 `:DISPlay:DATA?`。 |

---

## 二、截圖前置設定命令

| SCPI 命令語法 | 查詢語法 | 參數設定 | 作用與注意事項 |
| :--- | :--- | :--- | :--- |
| **`:HARDcopy:INKSaver <setting>`** | `:HARDcopy:INKSaver?` | `{{0 \| OFF} \| {1 \| ON}}` | **色彩反轉（省墨模式）**。<br>• 示波器預設為 `ON`（列印模式：白底黑字）。<br>• **欲取得示波器原始黑底彩色畫面，截圖前必須先下達 `:HARDcopy:INKSaver OFF`**。 |
| **`:HCOPY:SDUMp:FORMat <format>`** | `:HCOPY:SDUMp:FORMat?` | `{BMP \| BMP8bit \| PNG}` | 設定傾印（SDUMp）之預設格式（預設為 `PNG`）。 |
| **`:HARDcopy:PALette <palette>`** | `:HARDcopy:PALette?` | `{COLor \| GRAYscale \| NONE}` | 設定截圖調色盤（彩色 / 灰階）。 |
| **`:HARDcopy:AREA <area>`** | `:HARDcopy:AREA?` | `{SCR \| GRAT}` | 設定截圖範圍：<br>• `SCR`：全螢幕 (Screen)<br>• `GRAT`：僅格線波形區 (Graticule) |

---

## 三、對比：本機與隨身碟存檔命令 (:SAVE 子系統)

若不是要回傳電腦，而是讓示波器將圖片存至其內部儲存區或前面板插上的 USB 隨身碟，則使用 `:SAVE:IMAGe` 相關命令：

* **`:SAVE:IMAGe[:STARt] [<file_name>]`**：將截圖存入指定檔案（如 `\usb\screen.png`）。
* **`:SAVE:IMAGe:FORMat <format>`**：設定格式（`BMP`, `BMP24bit`, `BMP8bit`, `PNG`）。
* **`:SAVE:IMAGe:INKSaver {{0 | OFF} | {1 | ON}}`**：設定存檔是否啟用省墨反白。
* **`:SAVE:IMAGe:PALette <palette>`**：設定存檔調色盤（`COLor` / `GRAYscale`）。
* **`:SAVE:IMAGe:FACTors {{0 | OFF} | {1 | ON}}`**：設定是否一併將示波器設置參數寫入同名 `.txt` 檔。

---

## 四、Python (PyVISA) 擷取範例

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