# 自產的 HDF5 沿用 Keysight 原生結構

Infiniium 走存檔轉取，拿回來的是 Keysight 原生 `.h5`；InfiniiVision 只能直讀，檔案由 PC 端自己組。我們讓自產檔案沿用 Keysight 的 `/Waveforms/Channel N/Channel NData` 結構與 attrs 命名，另加一個自訂 group 存來源型號、系列、擷取時間與當時的 SCPI 設定。命名不漂亮，但分析頁因此只需要一套 loader 就能開兩條路線產出的檔；自訂一套乾淨結構會逼我們長期維護兩套解析程式。

**2026-10-16 補充：存原始整數。** 自產檔的 `Channel NData` 存 uint16 原始碼值，換算參數放 group attrs（`YInc`／`YOrg`／`YReference`），100M 點只要 200 MB，跟 Infiniium 的 H5INt 原生檔同一個思路；沒有 preamble 可還原時才存 float64 電壓。兩種整數檔的換算公式不同：自產檔是 `(raw − YReference) × YInc + YOrg`，Keysight 原生 H5INt 的 `YReference` 實測為 1，但**不能扣**，公式是 `raw × YInc + YOrg`（MXR254B 實測，扣了會差 1 LSB）。reader 用有沒有 `/ScopeTool` group 判斷是哪一種。
