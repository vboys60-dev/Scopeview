# 示波器截圖與波形擷取工具

一個桌面工具，透過 VISA/SCPI 連上 Keysight 示波器，把螢幕截圖與波形原始資料存到電腦，並提供離線的波形檢視與游標量測。

## Language

### 儀器與連線

**儀器 (Instrument)**：
一台實體示波器。程式透過一個 VISA 資源字串與它通訊。
_Avoid_: 設備、機台、device

**系列 (Series)**：
決定 SCPI 命令寫法的機型分家。本工具只認兩家：InfiniiVision 與 Infiniium。新機型必須歸入其中一家，或另開新的一家。
_Avoid_: 型號、機種、model

**InfiniiVision**：
非 PC base 的機型（3000G / 3000X）。本機存檔只能寫到面板上的 USB 隨身碟，PC 端無法取回，因此波形一律走直讀。
_Avoid_: 3000系列、X系列

**Infiniium**：
PC base 的機型（EXR / MXR / S 系列）。跑 Windows，有硬碟，可以用 `:DISK:SAVE` 產檔再 `:DISK:GETFILE?` 取回。
_Avoid_: PC base 機、EXR系列

**搜尋 (Discovery)**：
在不知道位址的情況下把可連線的儀器找出來。包含列出 VISA 本地資源與掃描網路上的 LXI 廣播兩種來源。
_Avoid_: 掃描、scan、找機器

### 截圖

**截圖 (Screenshot)**：
示波器當下畫面的影像，由儀器產生後直傳回 PC，不落在儀器的儲存裝置上。
_Avoid_: 螢幕擷取、hardcopy、螢幕傾印

**截圖區域 (Capture Area)**：
截圖涵蓋的範圍，二選一：全螢幕（含選單與量測欄）或只有 10x8 的格線波形區。
_Avoid_: 範圍、region

**反轉色 (Inverted)**：
白底的省墨版本影像，與示波器原本的黑底相對。兩家系列用不同命令達成同一結果。
_Avoid_: 省墨模式、InkSaver、白底

### 波形

**波形擷取 (Waveform Capture)**：
把儀器記憶體裡的取樣點取回 PC 並存成檔案的動作。
_Avoid_: 抓資料、下載、擷取

**直讀 (Direct Read)**：
用 `:WAVeform:DATA?` 把取樣點直接讀回 PC，PC 端自己換算與寫檔。
_Avoid_: 讀取、直傳

**存檔轉取 (Save-and-Fetch)**：
讓儀器先把波形寫成檔案，再用 `:DISK:GETFILE?` 取回、取回後刪除。只有 Infiniium 支援。
_Avoid_: 落地、間接讀取

**PREamble**：
儀器回傳的十個換算參數，把原始碼值換成真實時間與電壓所必需。缺了它資料就只是一串沒有物理意義的數字。
_Avoid_: 標頭、header、metadata

**波形檔 (Waveform File)**：
存在電腦上的擷取結果，格式為 CSV 或 HDF5，內含取樣點與足以還原時間電壓軸的資訊。
_Avoid_: 資料檔、原始資料、HD5

**波形分析 (Waveform Analysis)**：
離線開啟本機波形檔，顯示、縮放、平移並用游標量測的功能。不需要連上儀器。
_Avoid_: 量測、檢視、看波形

**游標 (Cursor)**：
疊在波形上、可拖曳的量測參考線，成對使用以讀出時間差或電壓差。
_Avoid_: mark點、標記、標示點
