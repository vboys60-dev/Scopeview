# Web API 契約（L0 凍結版 v2）

權威來源：`docs/pywebview-GUI規劃建議書.html` 第 3～8 節；v2 依 Codex／Opus 審查最終裁決修訂。機器可讀版：`scope_tool/web/static/api_contract.json`（rules／methods／types／events／errors／endpoints／binary／envelope／intents／catalog）。
凍結後只有 lead 能改；其他 lane 需要新欄位或方法一律提需求，不自行加。

**機械驗證**
- Python：`owner ∈ {Api, Analysis}` 的公開方法集合 == `methods` 中同 owner 的集合（含參數名）；`wait_events`（owner=server）由 `server.py` 另計。
- JS：`createMock().methods` 與 `methods`（owner≠server 者）一致、參數名一致；`js/l0_check.mjs` 依 `types` 逐欄檢查 mock 輸出。

## 1. 傳輸

- 全走本機 HTTP，只綁 127.0.0.1。**只有 `static/js/bridge.js` 知道傳輸**；其他檔不得 `fetch`。
- 靜態檔（`/`、`/js`、`/css`、`/static`）不驗 token；只有 `/rpc`、`/wave`、`/fft`、`/screenshot` 驗 token（頁面 URL `?k=`）。
- `POST /rpc/<method>?k=TOKEN`，body 為 kwargs JSON。**body 必須帶齊 `params` 所有鍵，沒值填 `null`**；缺鍵或多鍵＝`BAD_REQUEST`。回應 HTTP 200：`{"ok":true,"result":…}` 或 `{"ok":false,"error":{"code","message","retryable"}}`。token 錯 403、方法不存在 404。
- `GET /wave?k&ch&t0&t1&px&gen`、`GET /fft?k&id&f0&f1&px&log=0|1`：二進位包絡（第 4 節）。`GET /screenshot/last?k&n`：原始位元組，直接進 `<img>`。
- 事件：`POST /rpc/wait_events`（body `{since, timeout}`，long-poll ≤25 s）回 `{seq, events[]}`；bridge 內部自動輪詢。
- JSON 內不得出現 NaN／Infinity，一律轉 `null`（二進位保留 NaN）。
- `?mock=1`：bridge 改用 `mock_backend.js`，無網路；同一套前端不改碼。
- 路徑：後端一律對收到的路徑 `expanduser`；`get_state().config` 內的路徑一律是絕對路徑，前端不自行展開 `~`。

### bridge.js 介面

| 成員 | 說明 |
|---|---|
| `call(method, params)` | 快速方法，回 Promise<result>；失敗丟 `BridgeError{code,message,retryable}` |
| `job(method, params, {requestId?})` | 工作型方法；先收 `{job:id}`，再等同 id 的 job 事件完成。同一 `requestId`（並行或事後）重送共用同一個 Promise；可重試的失敗（`retryable`）會從表中移除以便重送 |
| `on(type, fn)` | 訂閱 `"driver"`（儀器狀態）、`"desync"`（事件序號中斷，應提示重新整理）；回傳取消函式。單一 listener 丟例外不影響其他 |
| `fetchWave({ch,t0,t1,px,gen,signal?})` | → `{n, mode, x:Float64Array, lo:Float32Array, hi:Float32Array}`；t0／t1／x 皆來源時間 |
| `fetchSpectrum({id,f0,f1,px,log?,signal?})` | 同上，x 為 Hz |
| `screenshotUrl(n)` | → Promise<string>；n 為 `ShotResult.preview`（整數序號，只用來避開快取） |
| `MOCK` | boolean |

bridge 對**任何非 200**（含非 JSON 的 500）與非 JSON 的 RPC 回應一律轉 `BridgeError`：回應若有 JSON `{ok:false,error}` 以其 code 為準，否則 403→`FORBIDDEN`、404→`NOT_FOUND`、其餘→`UNEXPECTED`；fetch 失敗→`NETWORK`；二進位解碼失敗→`BAD_BINARY`（驗長度、`mode∈{0,1}`、保留欄位為 0）。`AbortError` 原樣丟出（正常流程，`main.js` 的 `unhandledrejection` 忽略它）。

`ui.pickPath(ctx, "folder"|"file", initial)`：`AppState.native_dialogs` 為 true 走 `pick_folder`／`pick_waveform_file`，否則改用 `ui.prompt`；取消回 `null`。

### request_id 冪等規則（`envelope`）

- body 頂層保留鍵 `request_id`（不屬於 `params`，不計入簽章）；**server 先 pop 掉才呼叫方法**。`bridge.job()` 預設自動產生；使用者再按一次按鈕要用新 id，想重試同一件事才沿用同 id。
- 去重表保留最近 **256** 筆。**BUSY 與參數錯誤（BAD_REQUEST）不登記**；同 ID 不同參數 → `BAD_REQUEST`。
- 進行中重送：回原 `{job:id}`。已完成的重送：回 `{job:id, done:{ok, result|error}}`，bridge 直接以 `done` 完成（完成結果保留供重送）。

### 工作、事件與 BUSY

- 工作型方法立即回 `{job:"j<N>"}`；結果以 `type:"job"` 事件回傳，事件可能**早於** RPC 回應抵達，bridge 負責暫存配對。早到暫存有上限，超限的最舊項記為「遺失」，其 `job()` 以 `NETWORK` 明確失敗，**不得靜默丟棄**。
- 儀器鎖：同時只允許一個儀器工作。**拿鎖的方法：`search／connect／disconnect／capture_info／screenshot／capture`**（契約 `lock:true`）。搶不到＝**RPC 同步回應 `ok:false, BUSY`**（不走 job 事件、不登記 request_id）。分析工作（`open_waveform／measure／math／fft／export_csv`）不拿儀器鎖，也不排在儀器工作後面。
- `connect`：先關舊連線再連；`driver` 事件**早於**該 connect 的 job 事件；成功時由後端回寫 `config.series_overrides[model]`（前端只需傳 `series_override`）。`disconnect` 為工作型、拿鎖，完成後發 `driver` 事件。
- 事件環形緩衝 **500**。`AppState.seq` 為目前序號，bridge 從該 seq 起收（不重播舊事件）；依 seq 排序、去重；序號出現**斷層**（超過容忍時間仍缺號）→ 所有等待中的工作以 `NETWORK`（retryable，訊息要求重新整理頁面）失敗並發 `desync`，**不得永遠等待**。`events.closing` 是 `app.py` 內部事件，不入契約。

## 2. 方法

`J`＝工作型、`L`＝拿儀器鎖。下表只列名稱；**完整參數（type／required／nullable）與回傳型別以 `api_contract.json` 為準**。

| 方法 | 參數 | 回傳 | 擁有 |
|---|---|---|---|
| get_state | — | AppState（含 native_dialogs、seq） | Api |
| save_config | patch | Config | Api |
| pick_folder / pick_waveform_file | initial(null) | 路徑或 null（null＝使用者取消，正常結果） | Api |
| search J L | — | FoundInstrument[] | Api |
| add_manual_ip | ip | FoundInstrument[] | Api |
| connect J L | resource, series_override(null) | ConnectResult | Api |
| connect_fake | — | ConnectResult（model＝`FAKE-SCOPE`） | Api |
| disconnect J L | — | null | Api |
| capture_info J L | — | CaptureInfo | Api |
| screenshot J L | directory, name, image_format, inverted, area | ShotResult{path, preview:int} | Api |
| capture J L | directory, name, channels, points, retrigger | CaptureResult{path, got_points, requested} | Api |
| open_waveform J | path | FileSummary | Analysis |
| cursor_readout | t1, t2, dx | CursorReadout | Analysis |
| marker_eval | mode, channel, x1, x2, y1, y2, screen_width, measurements | MarkerResult | Analysis |
| measure J | entries, range, dx, threshold | MeasureBatch{gen, revision, results} | Analysis |
| math J | op, a, b(null), param | ChannelInfo | Analysis |
| close_waveform | （無） | null | Analysis |
| remove_channel | name | null | Analysis |
| fft J | source, range, dx, window, unit, r_ohm, peak_count, peak_level, peak_sort, rbw, vbw | FFTResult | Analysis |
| fft_track_rf | spectrum_id, x, direction, level | RFResult | Analysis |
| export_csv J | range, max_points(null), directory(null) | PathResult | Analysis |
| export_measurements | rows, gen, revision, directory(null) | PathResult | Analysis |
| wait_events | since, timeout | EventsResult | server |

### 參數語義

- `math.param`：低通／高通＝fc（Hz）；平滑＝點數；其餘 0。`b` 僅二元運算（加減乘除）使用，其餘 `null`。
- `export_csv.max_points`：`null`＝不縮點。`directory`（`export_csv`／`export_measurements`）：`null`＝來源波形檔所在資料夾。`export_csv.range` 沿用現行行為：以游標時間切**原始（來源）時間軸**，不套 dx。
- `marker_eval.screen_width` 單位**秒**；`measurements`＝`[x,y,label][]`（來源座標），僅 Track Measurements 使用。
- `screenshot`／`capture` 的 `directory` 為絕對路徑字串（取自 `config`）。
- `export_measurements`：`rows`（MeasureResult[]）僅供核對；後端用 `revision` 對應的**快照**寫檔，過期 `gen`／`revision` → `STALE`。

### 範圍、dx 與空區間（measure／fft）

- `range`＝**顯示時間**，可反序（後端排序）；對每個通道先扣自己的 dx（`source = display − dx[ch]`），兩端含。`null`＝全部。
- `dx = {通道名: 秒}`，缺鍵＝0；「第一通道」＝`FileSummary.channels[0]`。
- 空區間（或區間內全為 NaN）→ **具名失敗結果**：measure 該列 `ok=false`＋`reason="所選範圍內沒有資料"`、`stats=null`；fft 回 `FFTResult{ok:false, reason, spectrum_id:null, peaks:[]，數值欄 null}`。**不得**回 `count=1` 的成功結果。
- `MeasureEntry.mode` 可省略但不可為 null，預設 `"full"`（整段樣本）。`"cycles"` 只對 Vavg、Vrms(DC)、Vrms(AC) 有意義；其他項目忽略。cycles 使用三閾值完整邊緣中，第一到最後一個 `rising` 指定方向的中閾交越，至少兩個同向邊緣（含中間反向緣，至少三緣）。樣本左閉右開，不足回 `No edges：範圍內不足一個完整週期`，不退回整段。Vavg 預設已改為整段算術平均，舊單週期／靜默退回取消。
- `MeasureResult.bound` 可省略／null，或 `"<"`（時間上界或下降斜率真值更負）、`">"`（上升斜率下界），方向皆表示真值相對顯示值。有 ≥4 點的同方向邊緣時只採可信值；全不足時使用括住樣本時間差及閾值差÷時間差。畫面與 CSV 統計欄加相同前綴（次數除外）。
- catalog 新增 `-工作週期`（時間、%、sloped），等於同組邊緣下 `100 - 工作週期`；工作週期為＋寬度／週期，週期由所選方向定義。cycles 結果標籤如 `Vavg(CH1 整數週期 ↑)`，full 不加註；CSV 同樣標示。
- JSON `optional_fields` 列出 types 中可省略的欄位；存在時仍須符合欄位型別與上述列舉值。
- `Stats.current`＝最靠近顯示時間 t=0 的事件；切片不含 0 時取最靠近切片時間中點者，同距取較早。事件時間為起始邊緣中閾交越（延遲／相位用來源 1）；單值取範圍結果，無事件時間時退回首事件。雙來源的參考點依來源 1 切片決定，其他統計欄不變。
- `MeasureResult.stats` 各欄 `float|null`，並帶 `gen`、`revision`（與 `MeasureBatch` 相同）。
- 雙來源 catalog：`延遲`（s）、`相位`（°）、`電壓比`（dB），分類「雙來源」、可選欄 `sources:2`（單來源省略或 1）。Qt 的 MEASUREMENTS 不含雙來源。
- `MeasureEntry.channel2:str`、`rising2:bool` 可省略，不可 null。雙來源缺少 channel2 → BAD_REQUEST；通道不存在／已刪除 → 該列失敗「來源通道已刪除」。rising2 預設同 rising；單來源忽略兩欄。`MeasureResult.channel2:str|null` 可省略／null；雙來源帶來源 2 名稱。
- 各通道獨立切顯示時間範圍（含各自 dx），獨立由 levels 與共用 threshold 決定三閾值。延遲／相位配對前，來源 1 邊緣先限於兩來源顯示時間交集，裁後無事件回「兩來源時間範圍沒有重疊」。延遲＝每個來源 1 指定邊緣的中閾交越，到來源 2 最近指定方向邊緣之 `t2−t1`（同距取較早），可負。相位＝該延遲／來源 1 到下一個同向邊緣的週期 ×360；最後事件略過，不包裹。
- 電壓比＝`20 log10(rms_ac(來源1)/rms_ac(來源2))`，各用自己的完整量測區間，事件數 1；任一 AC RMS 為 0 → 失敗並說明來源。任一來源沒有資料／指定邊緣／完整週期都回具名失敗列。
- 畫面與 CSV 量測欄一致包含來源 2：`延遲(CH1→CH2 ↑↓)`、`相位(CH1→CH2 ↑↑)`、`電壓比(CH1→CH2)`。量測面板來源 1 為目前選取通道，來源 2 可選所有通道，初始預設第一個其他通道；不足兩通道時雙來源按鈕停用並說明。

### FFT

- `r_ohm` 必填 float：前端把 Auto 依 `catalog.fft_impedances`（[標籤, Ω|null]，五選項：其他／未知 50、單端 50、差動 100、共模 25、手動＝使用者輸入）換成數值。`peak_level` 必填（前端預設 -40）。`catalog.fft_units` 不含 `"W"`（Qt UI 隱藏）。
- `FFTResult.unit`＝**輸出單位**：衍生通道來源為「`<u> rms`」；`Phase` 為「°」且 `peaks=[]`。`FFTResult` 與 math 的 `ChannelInfo` 帶 `gen`。
- 後端只保留最近一次頻譜；`/fft`、`fft_track_rf` 的 `spectrum_id` 不是目前頻譜（含開新檔後）→ `STALE`。

- `rbw`、`vbw` 必填且可為 null（Hz），version 維持 2。非 null 須為有限正數；非有限／≤0，或 `Phase` 帶非 null → `BAD_REQUEST`。
- `rbw=null` 直接沿用整段 FFT，`rbw=df×enbw_bins`、`segments=1`；手動 RBW 使用 Welch：L=round(enbw_bins·Fs/rbw)，夾到 [64,n]（n<64 時 L=n），50% 重疊、功率平均，尾端不足 hop 的資料捨棄。回實際 `rbw=enbw=enbw_bins·Fs/L`，`n` 仍是範圍內總點數。
- `vbw=null` 或 ≥實際 RBW 不平滑，回 `vbw=null`；否則於輸出單位域（含 dB）沿頻率做方框平均，寬 RBW²/VBW、點數取奇數並限於頻格數，兩端縮窗正規化；回套用的 VBW。這是本工具模擬做法，待真機比對，非頻譜儀等效公式。
- 峰值、基準線、Track RF 與 `/fft` 都用平滑後軌跡；平滑時峰值不內插，頻率取格心。失敗時 `segments`、`vbw` 為 null。

### Marker 與 Track RF

- `catalog.marker_modes` 僅五種（與 `analysis/marker.MODES` 一致）：Manual X only／Manual Y only／Manual X and Y／Track Waveforms／Track Measurements。`markerMode=null`＝傳統游標，**不呼叫** `marker_eval`；`marker_eval` 收到 Track RF 或未知模式 → `BAD_REQUEST`。
- RF 只走 `fft_track_rf(spectrum_id, x, direction, level)`：`direction ∈ {-1,0,1}`（其餘 `BAD_REQUEST`）。`0`＝最近**原始頻格**（同距取右）；`±1`＝依 `level` 門檻跳到下一個**原始峰格**（嚴格大於／小於目前 x）。無下一峰：**維持原位**（`x`＝最近頻格頻率）、`available=false`＋`reason`，`y` 仍回該頻格值。不可用時 `x`、`y` 一律仍回最近頻格值（`RFResult.y` 因此幾乎都有值）。

### 型別重點

`FileSummary.model／series／captured_at` 為 `str|null`，並有 `info:[label,value][]`（檔案資訊表）。`ChannelInfo.vmin／vmax` 全 NaN 時為 null。`CaptureResult.got_points`＝各通道最少點數、`requested`＝請求點數。`ShotResult.preview`＝整數序號。

## 3. 事件與錯誤

```
{"seq":12,"type":"job","id":"j7","kind":"capture","ok":true,"result":{"path":"/Users/me/Desktop/wave_20261022_120000.h5","got_points":10000,"requested":10000}}
{"seq":13,"type":"job","id":"j8","kind":"fft","ok":false,"error":{"code":"SCOPE_ERROR","message":"…","retryable":false}}
{"seq":14,"type":"driver","connected":true,"model":"DSO-X 3014G","series":"InfiniiVision"}
```

| code | 說明 | retryable |
|---|---|---|
| REMOTE_DESKTOP | RemoteDesktopError（SCPI 273），**優先於 SCOPE_ERROR 判斷**；「請關閉遠端桌面連線後重試」 | false |
| BUSY | 儀器鎖被佔用，RPC 同步回應 | true |
| SCOPE_ERROR | 其他 ScopeError，訊息原文 | false |
| UNSUPPORTED | UnsupportedError；前端據此走 `series_override` 流程（讓使用者手選系列後重送 connect） | false |
| STALE | `gen`／`revision`／`spectrum_id` 不符（含 /wave gen 不符） | false |
| BAD_REQUEST | 缺／多參數、分析層 ValueError、同 request_id 不同參數、Track RF 送進 marker_eval | false |
| UNEXPECTED | 其餘例外；message 以「未預期錯誤：」開頭 | false |
| FORBIDDEN／NOT_FOUND | 傳輸層（403／404），僅 bridge 產生 | false |
| NETWORK | fetch 失敗或事件序號斷層，僅 bridge 產生 | true |
| BAD_BINARY | 二進位長度／mode／保留欄位不符，僅 bridge 產生 | false |

UI 規則：錯誤一律用 `ui.showError`（`<dialog>`），不用 `window.alert`。

### examples

成功（工作型）：

```
POST /rpc/measure   {"entries":[{"channel":"CHAN1","name":"Vp-p","rising":true}],"range":[0.001,-0.001],"dx":{"CHAN2":0.0002},"threshold":"10/50/90 %","request_id":"r7-x1y2"}
→ 200 {"ok":true,"result":{"job":"j9"}}
事件 {"seq":21,"type":"job","id":"j9","kind":"measure","ok":true,"result":{"gen":3,"revision":12,"results":[
  {"channel":"CHAN1","name":"Vp-p","unit":"V","ok":true,"stats":{"current":2,"mean":2,"min":2,"max":2,"range":0,"std":0,"count":1},"reason":null,"gen":3,"revision":12}]}}
```

失敗（BUSY 同步、空區間具名失敗、過期）：

```
POST /rpc/capture_info  {}       → 200 {"ok":false,"error":{"code":"BUSY","message":"儀器忙碌中，請等目前操作完成","retryable":true}}
事件 measure 空區間   …"results":[{…,"ok":false,"stats":null,"reason":"所選範圍內沒有資料","gen":3,"revision":13}]
GET /wave?…&gen=2     → 409 {"ok":false,"error":{"code":"STALE","message":"開檔世代已變更","retryable":false}}
```

亂序事件（bridge 依 seq 重排；已送出的 seq 重送會被忽略）：

```
收到順序 seq=12(job j7) → seq=11(driver) → seq=11(driver，重複)
派送順序 seq=11 → seq=12（j7 的 Promise 完成），第二個 11 被丟棄
收到 seq=14 但 13 一直不來 → 超過容忍時間：先派送 14，其餘等待中的工作以 NETWORK 失敗並發 desync
```

## 4. 二進位格式（/wave、/fft 共用，little-endian）

```
uint32 n | uint32 mode(0=原始,1=包絡) | uint32 0 | uint32 0     ← 16 bytes
float64 x[n]    位移 16          （8 對齊，全精度）
float32 lo[n]   位移 16+8n       （只供顯示）
float32 hi[n]   位移 16+12n      （mode=0 時 hi==lo）
總長 16+16n
```

- **/wave**：`t0`／`t1` 與回傳 `x` 皆為**來源時間**（前端自行加 dx）；`gen` 不符 → 非 200＋`{ok:false,error:{code:"STALE"}}`。包絡模式 `x`＝每桶起點；`n ≤ 2·px+2`；`px` 上限 16384、單通道回傳上限 32768 點。
- **/fft**：`log=1` 時 `f0>0`；`log` 只改分桶（對數等距），`x` 仍為 Hz 且排除 0。
- **NaN 規則**：桶內含 NaN → 該桶 `lo`／`hi` **皆 NaN**（`np.minimum.reduceat` 語義，不得產生 ±Infinity）；二進位保留 NaN，轉 `null` 只在 JSON。
- **失敗**：非 200＋`{ok:false,error}` JSON；bridge 對任何非 200 一律轉 `BridgeError`。
- 降採樣為視覺預覽；游標讀值、量測、FFT、CSV 一律用全精度原始資料。

## 5. 座標定義

- `display_time = source_time + time_offset(dx)`；`display_y_div = source_value / scale_per_div + position_div`。
- **cursors（store）**：`x`＝顯示時間（秒）、`y`＝顯示格數（div）。送 `marker_eval` 前換成來源座標，**由 L5 `cursors.js` 負責**：`x_src = x − dx[channel]`、`y_src = (y − position) × scale`。
- 傳統游標 `cursor_readout` 用顯示時間吸附第一通道取樣點，各通道讀值先扣自己的 dx，落在該通道時間軸外回 `null`。
- 波形 CSV 匯出維持現行行為：原始資料不套顯示位移，以游標時間切原始時間軸。
- 縱軸 ±5 格（10 格）；V/格表與自動縮放見 `analysis/scales.js`（逐條移植 `ui/analysis_chanbar.py`）。
- µ 輸出一律 U+00B5；輸入（`parseSI`）U+00B5、U+03BC、`u` 都收。`fmt` 對齊 Qt：單位為 `""`、`%` 或以 `dB` 開頭不加前綴，其餘（含 V²、°）加 SI 前綴。

## 6. 前端 store 契約（`js/analysis/store.js`）

- 狀態：`file, channels, selected(通道名), view{t0,t1}, cursors{x1,x2,y1,y2}, rangeMode(all|cursors), markerMode, rfPos({x,y}|null，Hz 全精度), threshold, fftResult, measurements`。
- 通道記錄：`{name, unit, derived, color, visible, scale, position, vmin, vmax, time_offset}`。**`time_offset`（dx，秒）是唯一真值**，寫入者只有 chanbar／L5，經 `store.updateChannel`；送後端的 `dx` 由它組出（缺＝0）。
- `set(patch, origin)`：origin ∈ `user｜snap｜program`。`snap` 為游標吸附回寫，監聽者遇 `snap` 不得再觸發吸附。比較：`Object.is`，或兩邊都是 **plain object** 時一層淺比較（同值新物件不通知）；陣列依參照。**巢狀物件不可原地修改**，要改就建新物件。`on(fn)` 或 `on(keys[], fn)`，fn(state, 變動鍵, origin)。
- `setChannels(list)`：一次 `set({channels, selected})`、一次通知；選取依名稱保留，被刪則選原位置附近者。`updateChannel／removeChannel` 同理。
- `command(name, payload)`／`onCommand(name, fn)`：fire-and-forget 意圖。保留名稱：`tab.activated`（main 發；切分頁**及初始分頁掛載完成後**各發一次）。
- 三個 lane 不得同時擁有同一份游標真值：`cursors` 的唯一寫入者為 L5 `cursors.js`。

### 意圖（`intents`，全部凍結為**絕對值**，各有唯一處理者）

| 意圖 | payload | 唯一處理者 | 說明 |
|---|---|---|---|
| viewport.intent | `{t0, t1}` | L4 `tab_analysis.js` | 顯示時間範圍（秒）；寫 `store.view`（origin=user） |
| channel.shift_intent | `{name, time_offset}` | L5 `chanbar.js` | 該通道新的 time_offset（秒）；拖曳端自行記錄起點 |
| channel.scale_intent | `{name, scale?, position?}` | L5 `chanbar.js` | 新的 V/格 與／或位置（格）；未給的鍵不變 |
| cursor.intent | `{which:"x1"\|"x2"\|"y1"\|"y2", value}` | L5 `cursors.js` | x＝顯示時間（秒）、y＝顯示格數；`null`＝清除 |
| rf.intent | `{direction:-1\|0\|1, x}` | L5 `cursors.js` | x＝目前 RF 位置（Hz 全精度）；呼叫 `fft_track_rf`，寫 `store.rfPos` |

## 7. 頁面模組約定（main.js 掛載）

每個頁面模組 `export function mount(el, ctx)`；`ctx = {bridge, store, ui, fmt, scales, MOCK, appState, activeTab}`。對應：`connbar.js→#connbar`、`tab_screenshot.js→#tab-screenshot`、`tab_capture.js→#tab-capture`、`analysis/tab_analysis.js→#tab-analysis`。模組不存在時 main 顯示佔位，不中斷其他頁。`ctx.appState` 在 `driver` 事件時由 main 更新（connected／model／series）；`desync` 事件由 main 以 toast 提示重新整理。

## 8. 樣式 token 與 CSS class 名稱（L6 實作，其他 lane 只能引用）

淺色主題；圖區黑底（不做深色主題）。字型 `PingFang TC, Microsoft JhengHei, sans-serif`；不用 web font／CDN。窄版斷點約 900 px。

Token（`:root` CSS 變數）：

| 類別 | 名稱 |
|---|---|
| 色 | `--c-bg --c-surface --c-border --c-text --c-text-dim --c-accent --c-accent-text --c-danger --c-ok --c-warn --c-focus` |
| 圖區 | `--c-plot-bg(#000) --c-plot-grid --c-plot-axis --c-plot-text --c-ch1 --c-ch2 --c-ch3 --c-ch4 --c-ch5 --c-ch6 --c-cursor1 --c-cursor2` |
| 間距 | `--sp-1 --sp-2 --sp-3 --sp-4`（4／8／12／16 px） |
| 字 | `--font-ui --font-mono --fs-sm --fs-base --fs-lg` |
| 其他 | `--radius --shadow-dlg --h-control` |

通道色：`--c-ch1..6` 的值即 `catalog.channel_colors`（`#ffcc00 #00d0ff #ff5fbf #7be36b #ff8a3d #b79cff`）；通道依序取色，衍生通道接續取用。

Class（BEM 風格，`block__element--modifier`）：

| 區域 | class |
|---|---|
| 外框 | `app connbar tabs tab tab--active pages page legacy-warning` |
| 控制項 | `btn btn--primary btn--danger btn--small input select check field field__label field__hint row grow muted` |
| 狀態 | `is-disabled is-busy is-error is-selected`（任何元素可加） |
| 對話框／提示 | `dlg dlg__title dlg__body dlg__msg dlg__actions toast-host toast toast--info toast--ok toast--error` |
| 表格 | `table table--num table__empty` |
| 分析頁 | `analysis analysis__toolbar analysis__side analysis__plot analysis__results chanbar chip chip--selected chip__name chip__remove plot plot__canvas plot__overlay split split__handle` |

## 9. 不在契約內（刻意不做）

傳輸中途取消、掃網段搜尋、深色主題、多語系、Jitter／眼圖（保持未接線）。

## 附：lead 裁決（凍結時追加）
- FFT 空區間：回 `ok=false`＋`reason`，`spectrum_id`／數值欄為 null、`peaks=[]`（不走 SCOPE_ERROR）。
- 已完成工作重送：回 `{job, done:{ok,result|error}}`。
- STALE 涵蓋 `/wave`、`/fft` gen／spectrum_id 不符、`export_measurements` 過期 revision；二進位端點 STALE 用 HTTP 409。
- `export_csv.range` 為來源時間、不套 dx（與 measure／fft 的顯示時間不同，已知刻意差異）。
- 契約自 commit「P0 契約凍結」起只有 lead 能改。

## 附：P2 審查後 lead 裁決
- 新增 `close_waveform()`（Analysis，同步）：釋放後端全部波形資料，gen+1。前端關檔必須呼叫。
- `add_manual_ip` 回傳整份手動清單，前端以 label 找新增項。
- `spectrum_id` 程序內遞增，換檔不重用。
- `request_id` 去重鍵含方法名與參數；同 ID 不同方法／參數 → BAD_REQUEST。BAD_REQUEST 結果（含 job 內產生者）屬可重試，不留在去重表。
- Track Measurements：MeasureResult 無事件座標，列為已知限制（UI 標「尚未支援」）。
- CSV 游標區間：游標顯示時間直接切原始軸，不套 dx（與 Qt 一致）。
- 開檔序列化：開檔進行中，前端禁止再次 file.open／關檔。
