# 自產的 HDF5 沿用 Keysight 原生結構

Infiniium 走存檔轉取，拿回來的是 Keysight 原生 `.h5`；InfiniiVision 只能直讀，檔案由 PC 端自己組。我們讓自產檔案沿用 Keysight 的 `/Waveforms/Channel N/Channel NData` 結構與 attrs 命名，另加一個自訂 group 存來源型號、系列、擷取時間與當時的 SCPI 設定。命名不漂亮，但分析頁因此只需要一套 loader 就能開兩條路線產出的檔；自訂一套乾淨結構會逼我們長期維護兩套解析程式。
