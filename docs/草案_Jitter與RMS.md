# 草案：Jitter／眼圖 Web 契約與 RMS／相位追蹤

> 由下列檔案合併而成（原檔見 git 歷史）：草案_Jitter眼圖Web契約.md、草案_RMS縮放與相位追蹤定義.md


---

## 〔草案_Jitter眼圖Web契約〕

## 草案：Jitter／眼圖 Web 契約

日期：2026-10-24。供 lead 審查，**尚未生效**；現行 v2 仍以 `docs/web-api契約.md`、`scope_tool/web/static/api_contract.json` 為準。本次僅修訂指定兩份草案，不修改程式或凍結契約。目標契約版本為 v3，待 lead 解凍後落地。

依據：上述兩份契約、`RULES.md`、`web/analysis_api.py`、`analysis/{clock,jitter,eye,status,slip,rate_seed}.py`、`ui/analysis_{jitter,eye}.py`（程式路徑皆以 `scope_tool/` 起算）。只分析已開檔案，不碰儀器；沿用 numpy，不增加套件／CDN。

### 1. RPC 與型別（提案）

沿用 `/rpc/<method>`、job 事件、錯誤包絡與 256 筆 request_id 去重。以下方法皆 `owner=Analysis, lock=false`；`jitter_eval`／`eye_density` 為 `job=true`，`export_timing` 為 `job=false`，同現行 `export_measurements`，由 HTTP 執行緒同步寫檔、不入分析 FIFO；表列鍵必須全部傳入，僅註明 nullable 者可為 null，拒絕多鍵／缺鍵。`request_id:str` 是額外頂層保留鍵，由 server 移除，**不加入 Python 方法簽章**。

| 新方法 | 請求 kwargs | 完成結果 |
|---|---|---|
| `jitter_eval` | `gen:int, source:str, range:Range\|null, dx:Dx, threshold:str, clock:ClockSpec, names:str[]` | `JitterResult` |
| `eye_density` | `gen:int, source:str, range:Range\|null, dx:Dx, threshold:str, clock:ClockSpec, names:str[]` | `EyeResult`（含密度圖描述，無大型陣列） |
| `export_timing` | `gen:int, revision:int, result_id:str, directory:str\|null` | `PathResult`；匯出後端快照 |

- 沿用既有 `Range` 表示顯示時間（秒），可反序、兩端含；null＝全部；JSON 參數須寫 `type:"Range", nullable:true`，不可用 `type:"Range|null"`。先扣 `dx[source]` 得來源時間；`Dx=map<float>` 缺通道鍵＝0。運算只用原始取樣，不用預覽縮點。
- `threshold` 僅收現行 catalog.thresholds 的鍵（10/50/90 %、20/50/80 %）。`source` 可用原始／現存衍生通道；單位跟隨來源。
- 首版只考慮單一視窗。`gen` 為目前 FileSummary.gen；分析請求不帶 revision，沿用後端配號：採 `jobs.submit(..., on_accept=...)` 掛鉤，在去重未命中時才於 `_tbl_lock` 內呼叫；掛鉤取得 `Analysis._lock` 後配遞增正整數 revision（JS 安全整數），鎖序固定 `_tbl_lock→Analysis._lock`，不得反向取鎖。去重命中不呼叫掛鉤、不配號，沿用原工作及 revision。後端按方法記錄最新 revision；匯出請求只帶已接受結果的 revision，不另配號。公開方法簽章的參數名與順序須等於 JSON（`api.py:289–294`、`analysis_check.py:26–30`），`jitter_eval`／`eye_density` 不得加 revision 參數，也不得開公開 `accept_*`。私有 `Analysis._accept(name, kwargs)` 在接受時配號、擷取輸入快照並回傳捕捉兩者的 `work` 閉包；server 以 `submit(on_accept=lambda: analysis._accept(name, kwargs), ...)` 在去重未命中時執行接受掛鉤取得該閉包，之後才由 FIFO 執行 `work()`。
- `names` 保序去重後，Jitter 為 1–7 項且僅收 `jitter.NAMES`，眼圖為 1–9 項且僅收 `eye.NAMES`。新介面不公布「眼 Jitter RMS／p-p」舊別名。
- Jitter 名稱：TIE、N 週期、Period-Period、+寬度差、-寬度差、還原 UI、還原速率。資料型只支援 TIE／還原 UI／還原速率，其餘回具名失敗列，不新增 N-UI／UI-UI。
- 眼圖名稱：眼高、眼寬、Q 值、Crossing %、眼 Jitter 原始 σ、眼 Jitter 實測 p-p、眼 Jitter 裁切 σ、眼 Jitter 6σ 估計、DCD。

`ClockSpec`（巢狀鍵也須完整、精確驗型別；bool 不當作 int）：

| 欄位 | 型別／限制 | 預設與語義 |
|---|---|---|
| kind | str；catalog.clock_kinds | 時脈 |
| edges | str；catalog.clock_edges | 上升；資料型忽略但仍驗列舉，回傳 effective_edges=兩者 |
| mode | str；catalog.clock_modes | 全自動；半自動以 rate 起步再擬合，手動固定 UI 只估相位 |
| rate | finite float >0 | 1e6；時脈為 Hz，資料為 bit/s；全自動忽略但仍須合法 |
| n | int，1–20 | 1；只影響 N 週期／Period-Period |
| reference | str；catalog.clock_references | 固定；首版只允許「固定」 |

單邊時脈 UI＝週期；兩邊時脈 UI＝半週期、step=2；資料 UI＝位元週期、step=1。還原速率沿用 `clock.rate()`，不可直接一律取 1/UI。

結果型別須可直接寫入 JSON `types` 並交 `l0_util.tc()` 驗證：具名物件逐鍵 deepEqual，不使用繼承／欄位合併簡寫；所有列出的鍵必有。浮點型別只使用 `float`／`float|null`；非有限計算結果轉 null 並附原因，不轉 0。`Range`、`Dx`、`Stats`、`PathResult` 已存在於現行 JSON 契約，直接沿用，不重定義。`ClockSpec.reference` 首版即保留，避免日後增鍵破壞 `scope_tool/web/static/js/l0_util.mjs` 的逐鍵 deepEqual；現行分析核心尚無此欄位，由適配層驗證後轉換。

| 型別 | 完整欄位與型別 |
|---|---|
| `ClockSpec` | `kind:str, edges:str, mode:str, rate:float, n:int, reference:str` |
| `Assessment` | `status:str, reasons:str[], diagnostics:object` |
| `ClockInfo` | `ui:float\|null, rate:float\|null, rate_unit:str, t0:float\|null, step:int, effective_edges:str, edge_count:int, assessment:Assessment, warnings:str[]` |
| `TimingRow` | `name:str, unit:str, ok:bool, reason:str\|null, failure_code:str\|null, stats:Stats\|null, assessment:Assessment, notes:str[]` |
| `JitterResult` | `ok:bool, reason:str\|null, failure_code:str\|null, gen:int, revision:int, result_id:str\|null, source:str, unit:str, range:Range\|null, dx:Dx, threshold:str, clock:ClockSpec, clock_info:ClockInfo\|null, assessment:Assessment, rows:TimingRow[], trend:TrendRef\|null, histogram:Histogram\|null` |
| `TrendRef` | `id:str, points:int, x_unit:str, y_unit:str, gap_policy:str` |
| `Histogram` | `edges:float[], counts:int[]` |
| `EyeResult` | `ok:bool, reason:str\|null, failure_code:str\|null, gen:int, revision:int, result_id:str\|null, source:str, unit:str, range:Range\|null, dx:Dx, threshold:str, clock:ClockSpec, clock_info:ClockInfo\|null, assessment:Assessment, rows:TimingRow[], n_ui:float\|null, crossing:CrossingStats\|null, density:DensityRef\|null` |
| `CrossingStats` | `raw_sigma:float\|null, measured_pp:float\|null, trimmed_sigma:float\|null, six_sigma_estimate:float\|null, trimmed_count:int, trimmed_fraction:float\|null, signed_width:float\|null` |
| `DensityRef` | `id:str, nx:int, ny:int, x_range:[float,float], y_range:[float,float], x_unit:str, y_unit:str, layout:str, dtype:str, display_transform:str` |

列舉值獨立放 `catalog`，由 `l0_sem.mjs` 檢查值與 catalog 一致；型別字串只用 tc 支援的語法。catalog 列出 statuses＝valid／limited／invalid、clock_kinds＝時脈／NRZ 資料、clock_edges＝上升／下降／兩者、clock_modes＝全自動／半自動／手動、clock_references＝固定、rate_units＝Hz／bit/s、trend_units＝s、gap_policies＝break、density_x_units＝UI、density_layouts＝x-major、density_dtypes＝float64、density_transforms＝log1p，以及 jitter_names＝上述七項、eye_names＝上述九項、reason_text＝原因碼到繁中說明的 map、failure_codes＝第 4 節五項 failure_code、seed_methods＝first_local_histogram_peak／min_short_record。thresholds 沿用現有 catalog；來源單位為動態字串，不是列舉。ClockSpec 的型別表只描述 shape，上表限制與 catalog 在參數驗證及語義自檢中強制執行。Stats.std 為母體 σ（ddof=0）；Histogram.edges 長度＝counts+1，依完整 TIE 計數；Jitter 圖形固定展示 TIE。TimingRow.notes 永遠存在（無註記為 []），裁切相關列在此揭露剔除數／比例及可能偏樂觀的說明。

catalog 自檢須逐項相等：`clock_kinds`＝`list(clock.KINDS)`、`clock_edges`＝`list(clock.EDGES)`、`clock_modes`＝`list(clock.MODES)`；`jitter_names`＝`list(jitter.NAMES)`、`eye_names`＝`list(eye.NAMES)`，`reason_text` 等於 `status.REASON_TEXT`（含說明）；`failure_codes` 等於第 4 節清單。由 Python 自檢比對核心常數，前端語義自檢沿用 catalog。

量測名稱→單位如下；由 T7 分別在 `analysis/jitter.py`、`analysis/eye.py` 新增 `unit_of`，各管自身量測名稱，供適配層使用，不由前端猜測：

| 量測名稱 | 單位 |
|---|---|
| TIE、N 週期、Period-Period、+寬度差、-寬度差、還原 UI | s |
| 還原速率 | 時脈為 Hz；NRZ 資料為 bit/s（沿用 clock.rate 語義） |
| 眼高 | 來源單位（如 V） |
| 眼寬、眼 Jitter 原始 σ、眼 Jitter 實測 p-p、眼 Jitter 裁切 σ、眼 Jitter 6σ 估計、DCD | s |
| Q 值 | 空字串（無因次） |
| Crossing % | % |

`ok` 表示是否產生分析資料，與三態分開；可計算但 invalid 時仍可回參考圖與診斷。單列失敗不拖垮其他列；整體 assessment 取時脈及所選列的最差狀態、原因碼保序去重。密度圖另納入 `eye.assess("眼寬")`，符合 Qt 的眼寬狀態列；不得把眼寬失效回寫成時脈失效。

### 2. 三態、原因碼與統計分欄

valid＝有效；limited＝受限且顯示警告；invalid＝無效，不呈現為合格量測。原因碼直接沿用 `analysis/status.py`，繁中說明供顯示，程式不得解析說明字串。

| 原因碼 | 現行判定／狀態 |
|---|---|
| RATE_INFERRED | NRZ 全自動推估速率，limited |
| RATE_AMBIGUOUS | 正格距 gcd>1，速率可能有多解，limited |
| GRID_SLIP_SUSPECT | slip 聯合診斷命中，limited；僅疑慮，不修正 TIE |
| GRID_COLLISION | 相鄰格距≤0，數量未達門檻，limited |
| GRID_COLLISION_MANY | 衝突數≥max(3,ceil(0.001×相鄰間隔數))，invalid；沿用 `clock.py:25` 的待校準產品門檻（0.1%），取代記憶舊定案 1%，仍需校準 |
| HALF_UI_AMBIGUOUS | 還原間隔的半格半徑 0.1 內占比≥1%：limited；>5%：invalid；兩邊時脈用奇數格尺度 |
| LOW_EDGE_COUNT | 邊緣<1000，limited；<3 則還原失敗 |
| CROSSING_TRIMMED | 剔除比例嚴格 >1%，只降級裁切 σ／6σ 估計／眼寬至 limited |
| EYE_NO_POSITIVE_OPENING | 眼寬模型 signed_width≤0，invalid，眼寬值 null |

`assessment.diagnostics` 採 `object` 開放物件，不建立需精確鍵集合的 Diagnostics 具名型別；以下為可選公開鍵及語義型別，適用時才有值。l0_sem 驗證已知鍵的型別／列舉與有限性，未知診斷鍵不得影響三態：
- 時脈：`grid_collisions,collision_threshold,g,edge_count,low_edge_threshold:int`；`half_ui_fraction,half_ui_radius:float`。
- 種子（僅適用時）：`seed_method:str, seed_interval_count:int`（seed_method 值見 catalog.seed_methods）；`seed_peak_ui,seed_peak_fraction,seed_peak_threshold,seed_log_width:float`。不把全自動當成已知真實位元率。
- 滑格：`grid_slip_suspects,grid_slip_block_edges,grid_slip_window_blocks,grid_slip_pulse_max_gap:int`；`grid_slip_max_block_jump_ui,grid_slip_window_step_ui,grid_slip_local_step_ui,grid_slip_pulse_step_ui,grid_slip_pulse_sum_ui,grid_slip_quiet_step_ui,grid_slip_residual_boundary:float`。
- 交叉點：CrossingStats 各欄，另 `trimmed_limited_fraction,sigma_floor_ui:float`。產品門檻目前待校準，前端顯示後端結果，不重做判定。

四項統計必須分欄、皆為秒：原始 σ＝完整 TIE 的 std；實測 p-p＝完整 TIE 的 max−min；裁切 σ＝迭代 ±3σ 後的 σ；6σ 估計＝6×裁切 σ。不可把 6σ 當實測 p-p，或把裁切 σ 標成原始 RMS。剔除數／比例即使≤1% 也揭露；>1% 在裁切 σ、6σ 與眼寬旁提示「可能偏樂觀」，不連帶降級原始 σ／實測 p-p。

眼寬＝UI−6σ；眼高／Q 值用 UI 40–60% 原始樣本。非有限 Q 值回 null 並附說明，不假造有限值。畫面／匯出固定註明「固定頻率還原，未做 PLL／SSC 追蹤；眼圖為近似，與 Infiniium EZJIT／色階資料庫算法可能不同」。

### 3. 圖形、容量與二進位端點

以下是**新增上限提案**，不是現行已支援能力；只有 bridge 可 fetch。新增 GET 皆驗 token，回 `application/octet-stream`；失敗使用非 200 JSON 包絡（STALE=409、BAD_REQUEST=400），沿用 bridge 錯誤規則。

| 資料 | 傳輸與硬上限 |
|---|---|
| TIE 趨勢 | `GET /jitter?k&id&t0&t1&px&gen`；來源時間，沿用 16-byte v2 波形包絡；px 1–16384，n≤min(2×px+2,32768)，最多 524304 bytes |
| TIE 直方圖 | RPC JSON；bins=clip(floor(sqrt(edge_count)),10,200)，最多 201 edges＋200 counts |
| 眼圖密度 | `GET /eye?k&id&gen`；固定 400×256＝102400 格，不走 JSON／base64；x_range=[-0.5,1.5] UI，y_range 隨來源單位 |
| 小型結果 | 每份 RPC 完成結果 UTF-8 JSON ≤64 KiB；不得帶完整 times／tie／格號／原始波形，超限明確失敗，不靜默截斷 |

眼圖使用獨立格式，**不套一維 Envelope decoder**：little-endian header `uint32 version=1,nx=400,ny=256,reserved=0`（16 bytes），接 float64 原始 counts，索引 `ix*ny+iy`，總長 **819216 bytes**。需驗版本、保留欄、尺寸、長度，以及 counts 非負有限整數；座標取同 id 的 DensityRef。保留 float64 避免計數溢位／float32 失真；log1p 僅前端顯示一次。

TIE 斷線規則僅限時脈型：格距>step 處，在遞增的時間陣列插入缺口內時間、TIE 陣列插入 NaN，再直接呼叫 `decimate.wave()`。NRZ 長碼不是缺邊，不套此規則。原始模式每點一筆（含 NaN、視窗兩端補點），包絡模式**每桶一筆 x／lo／hi**；含 NaN 的桶 lo／hi 皆 NaN，保守留白。所有輸出均計入 n≤min(2×px+2,32768)，縮點後不追加斷點；二進位可含 NaN、不得含 Infinity。直方圖不含插入斷點，計數總和等於原始 TIE 數；量測／匯出仍用完整事件。

沿用 density 的 50,000,000 補點預算與約 2,000,000 分塊；超限降低補點倍率，不裁掉記錄。該常數不限制原始點數，原始記錄本身大於它時仍須另測記憶體；不能宣稱已有全程記憶體上限。

快取提案：每方法只留最新已完成快照，換世代（含換檔／關檔）即清；單份上限 64 MiB，含供趨勢／匯出持有的陣列，超額明確回 SCOPE_ERROR。新工作計算中可保留前份快照，成功提交才取代；id 程序內唯一、不因換檔重用。`jobs.py` 維持分析單執行緒 FIFO，不新增等待槽或取代邏輯；過期工作輪到 `work()` 時才丟 STALE，由既有 `_run` 包裝發一次完成事件。**耗時眼圖會擋住後續 measure／FFT**，不擴充 worker pool、不中斷已執行計算；同步 `export_timing` 不受 FIFO 阻擋，可匯出仍存活的前份快照。

### 4. 舊結果回寫與錯誤

1. 前端在換檔／關檔開始即清圖，增加本地 file epoch；來源、range、dx、threshold、ClockSpec、names 任一變動即增加本地操作序號，200 ms 防抖。此序號只供前端防舊回寫，不傳給後端。新操作給新 request_id，同件網路重試沿用原 id。
2. 後端在接受新 job、進 FIFO 前，以第 1 節 `on_accept` 掛鉤按固定鎖序核對 gen／來源、擷取輸入快照、配 revision 並登記該方法最新 revision；去重命中不再配號。`work()` 開頭先在鎖內比對 gen、來源存活與最新 revision，落後直接丟 STALE，不開始昂貴運算。計算完成再在**同一鎖內檢查並提交**，不吻合即 STALE，不能覆寫快取／匯出快照。L1a／L1b 協作接線；掛鉤失敗不登記去重、不入列，不能等輪到 work() 才配號。`Analysis._lock` 內不得有長運算；現行 `analysis_api.py:248–249` 建金字塔須移至鎖外、提交時再驗存活，或改用獨立配號小鎖並明定鎖序，避免接受掛鉤長時間佔住 `_tbl_lock`。
3. request_id 由 bridge 保存作 Promise 關聯；結果回傳後端 gen／revision。前端回寫前核對本地 epoch、目前 gen、本地操作序號及該次 request_id，再接受結果 revision；舊成功、舊錯誤、舊 finally 均不得改圖／提示／忙碌狀態。此檢查覆蓋「新參數尚未送達後端」的空窗。
4. 二進位下載開始與完成都核對同一 result_id／世代及本地操作序號；新請求可 AbortController 中止舊圖下載（不是取消儀器傳輸）。匯出由 HTTP 執行緒同步執行、不排 FIFO，只用目前已接受的 result_id；後端以 gen／id 查快照，再比對**該快照自身 revision 與請求 revision**；不比對該方法已登記的最新 revision，因此重算中前份快照仍可匯出。禁止接收前端數值作真值。

| 情況 | 回應／UI |
|---|---|
| 缺鍵、多鍵、巢狀 ClockSpec 錯型、未知名稱、非法範圍／速率 | BAD_REQUEST，retryable=false；登記去重前驗證，不保留錯誤 id |
| 空區間、全非有限、無振幅、邊緣不足、未收斂 | 正常完成 `ok=false, assessment.status=invalid`，圖 null；原因與 failure_code 必填 |
| 單列不適用／樣本不足 | 該列 ok=false、stats=null、invalid；其他列可成功 |
| 換檔／參數過期、快照被新結果取代／來源刪除 | STALE，retryable=false；過期操作靜默丟棄，當前操作提示重算 |
| 檔案寫入／資源上限失敗 | SCOPE_ERROR，retryable=false；保留目前可用圖，不假報匯出成功 |
| 網路／事件斷層、壞二進位、未預期例外 | 沿用 NETWORK／BAD_BINARY／UNEXPECTED；desync 提示重新整理，結束等待 |

提案 `failure_code`（與三態 reasons 分開）：`NO_DATA, NONFINITE_INPUT, CLOCK_RECOVERY_FAILED, MEASUREMENT_UNAVAILABLE, NONFINITE_RESULT`。成功為 null；既有分析層只有文字例外，適配層先以輸入檢查區分，其他還原失敗用 CLOCK_RECOVERY_FAILED，不解析中文例外來猜子類。單一 NaN 亦不可直接送進眼圖 min/max／histogram；首版拒絕該區間為 NONFINITE_INPUT，不跨缺樣補接。

### 5. 匯出

`export_timing` 為 `job=false`，在 HTTP 執行緒同步寫檔並直接回 `PathResult`／錯誤包絡，不產生 job 事件；重算中仍可匯出前份存活快照。首版只匯出 CSV 摘要（UTF-8 BOM），不匯出原始趨勢／密度矩陣／圖片。directory=null 用來源檔目錄；expanduser，回絕對路徑。檔名 `{來源名}_Jitter或眼圖_YYYYMMDD_HHMMSS.csv`，永不覆蓋，同秒碰撞須另取未使用名稱。

- 中繼資料：來源絕對路徑、gen、revision、result_id、匯出時間、source／unit、顯示 range／來源 range、dx、threshold 與百分比、完整 ClockSpec／effective_edges、ui／rate／rate_unit、edge_count／n_ui、算法限制註記。
- 每列：name、unit、ok、current、mean、min、max、range、std、count、status、reasons、failure_code、reason、notes（含剔除數／比例）。
- 四項獨立欄：raw_sigma、measured_pp、trimmed_sigma、six_sigma_estimate；另 trimmed_count／fraction、signed_width、clock_status／reasons、diagnostics JSON、warnings。非適用留空，不填 0；含受限／無效結果須完整保留標記。
- 數值科學記號且可往返原精度；null 寫空白。匯出前短暫鎖內驗證並持有快照參照；鎖外先寫暫存，最後再鎖內驗世代、id 仍存活且快照自身 revision 等於請求（不比對已登記最新 revision），並以不覆蓋方式發布，失效即清暫存、回 STALE。

### 6. 後續改動位置與擁有權（僅列提案）

須由 lead 解凍後逐檔落地；以下未實際修改。v3 變更屬 L0 Web 契約（`RULES.md:70`）：`docs/web-api契約.md`、`scope_tool/web/static/api_contract.json`、`scope_tool/web/static/js/{mock_catalog,mock_backend}.js`、`scope_tool/web/static/js/l0_*.mjs`；既有 Range／Stats／PathResult 沿用。`scope_tool/contracts.py` 是儀器契約，依 `RULES.md:11` 禁改，保持不變。只改 JSON 會使 `l0_check.mjs:14/24/28`、`selfcheck_node.js`、`api.py` 的 `contract_check`、`analysis_check.py:30` 失敗；合入 main 須同一筆包含 mock 同步與 Analysis 的 `jitter_eval`／`eye_density`／`export_timing` 三個同簽章 stub 方法。GUI P2 的 `view.undo`／`view.redo`／`layout.*` 屬前端 `store.command`，不在凍結契約內（`RULES.md` 已登記），與 v3 無共用改動、不需一併升版；順序為 GUI P2 先 commit，再一筆落地 v3（HANDOFF.md）。`analysis/*` 歸 T7 執行，Web lane 唯讀（`RULES.md:52、81`）；`ui/*` 同樣對 Web lane 唯讀。本輪明確不改 `web/static/js`、CSS 等前端實作；前端接線與自檢均為後續工作。

| 既有檔案 | 擁有者／擬改動點與行數控制 |
|---|---|
| `scope_tool/analysis/jitter.py`、`eye.py` | T7；各新增 unit_of 與自身名稱單位自檢，現 138／235 行，各≤300；Web lane 唯讀 |
| `docs/web-api契約.md` | L0；新增方法、三態、容量、端點、store、防護與匯出；修訂第 9 節排除項。現 253 行，目標≤290，詳細規格連至獨立文件 |
| `scope_tool/web/static/api_contract.json` | L0；version 升版，新增 methods／types／types_doc／catalog／endpoints／binary，擴充 STALE 與容量規則；目標 v3，待 lead 解凍；JSON 資料檔不受 300 行上限，但仍歸 L0 凍結管理 |
| `RULES.md` | lead；擁有權表逐一納入下表新檔：L0 mock／驗證、L1a 路由、L1b 分析／匯出、L4 面板與 CSS、L8 驗收；標明新 public mixin 方法歸 Analysis 機械驗證。保留凍結表與 300 行上限 |
| `scope_tool/web/analysis_api.py` | L1b；引入新 mixin、私有 _accept 配號交接、初始化／reset／remove_channel 失效掛鉤，短鎖提交；建金字塔移出鎖外或使用獨立配號小鎖；現 266 行，目標≤290 |
| `scope_tool/web/analysis_params.py` | L1b；將 `_ok` 的 MeasureEntry 特例改為通用具名物件精確鍵檢查：spec 必為 dict、set(v)==set(spec)，逐鍵遞迴；含 ClockSpec 缺鍵／多鍵／bool-as-int 拒絕，並由 catalog 檢查 kind／edges／mode、threshold／names 列舉與速率／n／長度限制；MeasureEntry 改精確鍵檢查須回歸既有合法輸入及缺／多鍵錯誤；不另開 params 新檔，目標≤160 |
| `scope_tool/web/jobs.py` | L1a；現 299 行，先搬自檢至新 jobs_check.py，保留薄入口；只加 on_accept 去重未命中掛鉤與固定鎖序，維持 FIFO，目標≤230 |
| `scope_tool/web/analysis_export.py` | L1b；現 63 行，合併 timing CSV 摘要匯出、快照驗證、暫存發布與碰撞處理，目標≤240 |
| `scope_tool/web/server.py` | L1a；**本次接線（待實作）**：現行 rpc 只查鍵集合，須只對 `owner=Analysis` 的方法在 jobs.request／submit 前呼叫 validate_params；既有 Analysis 方法的部分 BAD_REQUEST 將由 job 事件改為同步回應，須回歸錯誤時序。以 submit(on_accept=...) 接私有 _accept 回傳的 work，export_timing 走同步分支；掛新端點與 token／錯誤路由；現 299 行，必須先抽出二進位路由再接線，目標≤280，禁止直接追加超限 |
| `scope_tool/web/static/js/bridge.js` | L0；唯一 fetch 入口，新增 fetchJitter／fetchEye 與獨立密度解碼；現 185 行，目標≤280 |
| `scope_tool/web/static/js/mock_backend.js` | L0；登記同名、同參數 mock 方法；分析為 job，export_timing 同步回應；現 240 行，邏輯委派新模組，目標≤280 |
| `scope_tool/web/static/js/mock_catalog.js` | L0；同步 clock／量測名稱／原因碼／容量 catalog，目標≤100 |
| `scope_tool/web/static/js/analysis/store.js` | L0；clockSpec、各方法的後端 revision、本地操作序號／結果／忙碌狀態，巢狀值以新物件更新，目標≤120 |
| `scope_tool/web/static/js/analysis/tab_analysis.js` | L4；掛載兩面板、切頁與換檔失效，目標≤160 |
| `scope_tool/web/static/css/analysis.css` | L4；密度圖／雙圖排版與狀態提示，總長≤300，不超限追加 |
| `scope_tool/web/static/js/l0_check.mjs` | L0；呼叫既有 l0_sem 中擴充的契約語義自檢，維持公開方法／參數／catalog 一致，總長≤300 |
| `scope_tool/web/static/js/l0_sem.mjs` | L0；現 136 行，併入 timing 型別／catalog／重送／解碼自檢，目標≤290，不另開 l0_timing |
| `scope_tool/web/analysis_check.py` | L1b；呼叫新 timing 自檢，總長≤300 |
| `scope_tool/web/static/js/selfcheck_node.js` | L8；納入新前端自檢，總長≤300 |
| `scope_tool/web/static/selfcheck.html` | L8；離線畫圖／mock 自檢入口，總長≤300 |
| `scope_tool/web/e2e_check.py` | L8；現 218 行，新增 timing RPC／二進位／FIFO／同步匯出案例，並修改 `126–128` 的既有 BAD_REQUEST 驗收：由等待 job 事件改驗同步 RPC 錯誤且不入列；不承接 jobs 自檢，委派數值與情境 helper 至 analysis_timing_check，總長≤300 |
| `docs/驗證.md` | L8；新增驗收條件與未實機驗證註記，總長≤300 |

後續新檔共 10 個（含本草案與獨立 L1a jobs_check；4 個前端新檔暫緩），params／binary／export 仍按下表整併。新增檔案與**含自檢／註解的總行數預算**（名稱暫定；未建立任何下列實作檔）：

| 新檔 | 擁有／預算 | 職責 |
|---|---|---|
| `docs/草案_Jitter與RMS.md` | lead／≤250 | 本草案 |
| `scope_tool/web/analysis_timing.py` | L1b／≤240 | Analysis mixin、時脈／Jitter／眼圖適配與快照提交 |
| `scope_tool/web/analysis_timing_binary.py` | L1b／≤180 | 趨勢縮點、密度編碼、快取容量 |
| `scope_tool/web/analysis_timing_check.py` | L1b／≤240 | numpy 數值／狀態／FIFO 競態與跨層情境 helper 自檢 |
| `scope_tool/web/jobs_check.py` | L1a／≤220 | 搬入 jobs 既有自檢，補去重不配號、掛鉤一次性與鎖序檢查；不併入 e2e_check |
| `scope_tool/web/server_binary.py` | L1a／≤180 | 從 server 抽二進位路由並加入新端點 |
| `scope_tool/web/static/js/mock_timing.js` | L0／≤200 | 固定種子結果、容量／亂序／錯誤情境 |
| `scope_tool/web/static/js/analysis/timing_pane.js` | L4／≤240 | ClockSpec 設定、防抖、request 關聯、失效與共用狀態 |
| `scope_tool/web/static/js/analysis/jitterpane.js` | L4／≤180 | TIE 趨勢／直方圖／統計 |
| `scope_tool/web/static/js/analysis/eyepane.js` | L4／≤180 | 密度圖／四分欄／量測與匯出按鈕 |

任何既有模組將超過 300 行時先停下回報拆檔方案；不得靠壓縮程式或擅改他 lane 檔案過關。

### 7. Mock、驗證與採用預設

- Mock：`?mock=1` 全離線、同方法／參數／回傳型別／二進位格式；至少提供乾淨時脈、NRZ 自動 limited、缺邊、滑格疑慮、格號衝突 invalid、裁切 >1%、無正開口、空區間與非有限輸入。固定種子，不宣稱等同實際算法。
- 數值：用 clock.nrz 與既有 self-check 比對四分欄、UI／step／速率、N=1/20 與缺邊不跨、DCD 兩邊要求；驗裁切比例 0.99%／1%／1.01%、半格 1%／5% 邊界。密度朝向、2 UI、計數與 log1p 僅一次皆須驗。
- 契約：公開 Analysis 方法集合（含繼承）與 params 等於 JSON，mock 同步；巢狀欄位、nullable、有限值、未知鍵、巨大 names、bool-as-int、token、HTTP／事件錯誤皆有 assert。
- 競態：A 慢、B／C 依序入 FIFO；A 提交前已過期回 STALE，B 輪到 work() 開頭才判過期回 STALE、不進昂貴運算，C 正常執行；各分析 job 僅一個完成事件，同步 export_timing 無 job 事件且不受 FIFO 阻擋；FIFO 中眼圖擋住 measure／FFT、換檔／關檔、刪除來源、新參數防抖未送出、job 事件早到、舊 finally、同 id 重送／異參數、快照取代／換世代清除、下載中換檔、重算中前份快照仍可匯出、匯出暫存中快照被取代失效；舊結果不可回寫或產生已過期匯出檔。
- 容量：最大趨勢／密度、壞長度／尺寸／版本、NaN 斷線、64 KiB／64 MiB 邊界、超大來源的峰值記憶體／耗時；原有 wave／FFT／量測與儀器工作的數值／協定不得退化；另量測並揭露 FIFO 造成 measure／FFT 等待眼圖的延遲。
- 方式：依 RULES 用 `python3 -m scope_tool.web.jobs_check`、`python3 -m scope_tool.web.analysis_timing_check`、`python3 -m scope_tool.web.e2e_check`、Node／selfcheck.html，assert 且印 self-check OK；不新增 pytest／fixture／依賴。本次僅文件審核，以上皆為後續計畫，未執行功能測試。

採用預設：契約升 v3，待 lead 解凍；JSON 不受行數上限但歸 L0；每方法最新單份快照上限 64 MiB，換世代即清，沿用分析 FIFO；只考慮單一視窗；首版拒絕區間內任何非有限輸入，僅匯出摘要。新檔 lane 接手仍由 lead 排程，不把上述預設列為待選問題。數值風險：固定頻率不追 PLL／SSC、大 jitter 可能滑格且診斷會誤漏報、全自動 NRZ 速率有倍頻歧義；產品門檻尚待校準，與 EZJIT 的比較**待真機驗證**。


---

## 〔草案_RMS縮放與相位追蹤定義〕

## 草案：RMS 縮放與相位追蹤定義

2026-10-24。供決策與後續實作驗收，尚未定案；本次僅修訂指定兩份草案，未實作；下述 RMS 實測數字為 Opus 審查提供，本次未重跑；PLL 合成驗收與真機比對尚未執行。

### 依據與現況

- 依據本 repo 的 [離線分析功能規格](離線分析功能規格.md)、`scope_tool/analysis/{measure,clock,jitter,eye}.py` 與 Opus 審查結果；不依賴跨 repo 文件或暫存路徑。
- 擁有權：RMS、PLL 與其驗收均由 T7 執行；`analysis/*` 歸 T7，Web lane 唯讀（`RULES.md:52、81`）。
- 現況行數含空白／註解：measure 300、clock 300、jitter 138、eye 235。RMS 為整段樣本等權；AC 扣整段平均。clock 僅固定頻率；Jitter／眼圖 GUI 尚未接線。保留 NumPy-only 核心、既有三態與凍結契約。

### 案 A：RMS 一律採 2 冪次縮放（P3）

#### 對象、公式與邊界

DC、AC RMS 一律採 frexp／ldexp 的 2 冪次縮放；不設普通／極端資料的條件分支，不掃描最小非零值。不順帶修改 `stats.std`、TIE σ、Vavg 區間、時間加權或輸入 dtype 契約。有限 float64 為首版保證對象，整數仍依現況拒絕。

```text
a = max(abs(v))
若 a == 0：DC、AC 均回 +0
(m,e) = frexp(a)             # a=m*2**e，0.5 <= m < 1
y = ldexp(v,-e)              # 不建立可能溢位的 2**e
DC = ldexp(sqrt(mean(y*y)),e)
z = y-y.mean()              # 先縮放再平均／相減，避免 AC 前置運算溢位
AC = ldexp(sqrt(mean(z*z)),e)
```

零輸入處理是必要邊界；所有非零有限輸入共用同一路徑。2 冪縮放在可表示範圍內避免一般除法的額外捨入，極大動態範圍中的微小項仍可能下溢。不可表示的真實結果不強求有限值。

Opus 審查實測：一般資料 **1,000 組 DC／AC 逐位元差異 0**；極端尺度 **1e±200 相對誤差 2.2e−16**。這支持一律縮放的簡化方案；數字屬審查提供的實測紀錄，本次文件修訂未重跑，也不外推成所有平台／輸入皆逐位元相同。

目前 measure 會預先計算 top/base 及兩種 RMS，即使請求別種量測。極端案例須分別驗 helper 與公開 measure；若前置直方圖等先失敗，不得只憑 helper 通過宣稱端到端完成，亦不在此案擴張成全量測數值重寫。

#### 可驗收條件

| 案例 | 通過條件 |
|---|---|
| 一般 float64 回歸 | 同一 Python／NumPy／平台，以修改前版本為基準；seed=20261024，1,000 組 N=2…10000、尺度 1e−6…1e6 的常數、正弦、PWM、含 DC 雜訊，另含全零與負值。DC／AC 輸出以 uint64 位元比較，差異必為 0，不能用 allclose 代替；其他量測輸出與例外亦不變。 |
| 極端 DC | `[a,a]`、`[-a,a]`，a 分別為 1e200、1e−200，結果有限且非零，對 a 相對誤差 ≤5e−15；不得得到 inf 或 0。審查實測誤差為 2.2e−16。 |
| 混合尺度／點數 | `[1e200,1e−200]` 應為 1e200/√2，`[1e−200,0]` 為 1e−200/√2；一個大值加大量零，與獨立高精度參考相對誤差 ≤5e−15。 |
| 邊界 | frexp 指數切換附近各取 nextafter 兩側；含零、最小次正常值、接近 float64 最大有限值的常數。DC 及非常數 AC 的可表示答案誤差 ≤max(5e−15×參考值, 1 個最小次正常值)；常數 AC 改依下列 AC 條件 ≤5e−15·\|a\| 判定。 |
| AC | 常數 a=±1e±200 的 AC ≤5e−15·\|a\|（涵蓋 N=7、9999）；`[-a,a]` → a，誤差同上；大 DC 加可表示小擾動與高精度參考比較。已在輸入捨入消失的擾動不要求還原。 |

實作註記（2026-10-24）：「大 DC 加可表示小擾動」的 AC 只對平均可精確表示的對稱擾動達到相對參考值 ≤5e−15；不對稱擾動受平均值捨入限制，僅保證相對 |a| ≤5e−15（舊公式相同，非縮放造成）。

審查實測：N=7、9999、a=1e200 時，常數 AC 約 1.7e−16·|a|，舊公式亦同；平均值捨入可留非零殘差，不要求精確為零。

高精度參考用標準庫 Decimal，不能由同一縮放 helper 產生預期值。尤其 AC 必須先把**已存成 float 的輸入**逐項用 `Decimal.from_float(float(x))` 精確轉換，再於足夠精度下算平均、偏差平方平均及平方根；增加 Decimal 精度確認參考收斂。不得從原始十進位理想值或未捨入擾動建構參考。逐位元回歸限固定執行環境，不跨 NumPy 版本保證。

#### 拆檔、價值與優先度

後續實作預算（本次不改）：新增 `analysis/rms.py` ≤120 行（helper＋自檢）；將 measure 的 `_self_check` 主體原樣移至 `analysis/measure_check.py` ≤250 行，measure 保留薄包裝與原 `python3 -B -m scope_tool.analysis.measure` 入口。check 在執行時才匯入，避免循環；measure 目標 ≤190 行。若 check 逼近 300 行再按量測類別拆，不刪斷言湊行數。各新增模組保留可執行自檢；搬移前後既有自檢皆須通過。

**排入 P3，DC、AC 一起採一律 2 冪縮放。** 對衍生波形有價值，但一般示波器電壓少遇到 1e±200；先完成 PLL 核心原型。風險為一般資料位元回歸未涵蓋的捨入差、極端動態範圍小項下溢，以及公開入口先被其他量測計算阻斷。

### 案 B：相位追蹤（PLL／CDR）

#### 參考與量測意義

恢復時脈應獨立成資料流；不能照搬 scopehal 固定增益或把 PyBERT bang-bang 參數直接標成 Hz。以 [Keysight 二階 PLL](https://helpfiles.keysight.com/csg/d9300a/Help/Infiniium-UG/Content/Topics/Clock_Recovery/2nd_Order_PLL.htm) 的 type-II、JTF／OJTF 區分為參考；公式參見其 [JTF 定義](https://helpfiles.keysight.com/csg/d9300a/Help/Infiniium-UG/Content/Topics/Clock_Recovery/JTF_Equations_for_Second_Order_PLLs.htm)。不宣稱與 EZJIT 或特定協定符合。

首版限已知標稱速率的 NRZ，無法重現示波器「只用上升緣」的 Clock TIE；時脈型單／雙邊另案驗證後才開放。固定模式仍預設；「速率種子模式」（全／半自動、手動）與「參考模式」（固定、PLL）為不同設定。PLL 只接受 `ClockSpec.kind="NRZ 資料"、mode="手動"` 並提供標稱速率；其他組合回 BAD_REQUEST。「半自動」依賴全段擬合，與不偷看未來衝突；全自動亦有倍頻歧義。既有固定模式三種速率行為保持不變。

首版只做事件層 `pll.py` 原型與傳遞函數驗收，鎖定／捕獲／重鎖採下列新定義；GUI、眼圖與匯出接線暫緩，下述映射及接線條款為後續設計。

#### 模型與頻寬

提案採線性相位偵測器＋PI＋相位積分器的二階 type-II；令輸入／恢復相位為 d、q，頻率狀態 w 為絕對速率（UI/s，初值 R），d、q 為 UI 相位，時間用秒，連續目標模型：

```text
e = d-q；dq/dt = w + Kp*e；dw/dt = Ki*e
Kp = 2*ζ*ωn；Ki = ωn²；ζ = 1/√2
H(s) = (2*ζ*ωn*s + ωn²)/(s² + 2*ζ*ωn*s + ωn²)   # 恢復時脈 JTF
E(s) = 1-H(s) = s²/(s² + 2*ζ*ωn*s + ωn²)          # 殘餘 TIE OJTF
```

頻寬 B **明定為 JTF 高頻側 −3 dB 頻率（相對 DC 增益）**，不是自然頻率或 OJTF 頻寬。令 `c=sqrt(1+2ζ²+sqrt((1+2ζ²)²+1))`，則 `c≈2.058`、`ωn=2πB/c`。預設 `B=R/1667`（R 為 NRZ 位元率）；1 Gb/s 時約 599.88 kHz。此除數有 [Tektronix 硬體 FAQ](https://www.tek.com/en/support/faqs/what-loop-bandwidth-clock-recovery-hardware) 使用先例，但此處是產品預設提案，不代表所有協定或 Keysight 預設。自訂 B 暫限 `0 < B <= R/1000`。

離散核心採依實際轉態間隔 Δt 更新，狀態 `(t_prev,q,w)` 保存上一事件更新後的相位及絕對速率；`w` 初值為 R，並非零初值的頻率修正量：

```text
Δt = t_k-t_prev
q⁻(t_k) = q+w*Δt
n_k = round(q⁻(t_k))           # 最近整數 UI；恰半格視配對疑慮，不依語言 ties 規則接受
e_k = n_k-q⁻(t_k)
b⁻[n] = t_prev+(n-q)/w         # 本事件更新前狀態外插出的邊界
TIE_k = t_k-b⁻[n_k] = -e_k/w
q = q⁻(t_k)+Kp*Δt*e_k
w = w+Ki*Δt*e_k
t_prev = t_k
```

相位 `q` 的整數與小數部分分開存（整數格號＋有界 float64 小數），`q⁻` 推進先拆出整數進位；配對與 `n−q` 僅用局部差值，不形成巨大的 float64 絕對 UI。長記錄若只存 float64 絕對 UI，精度可能只剩約 1e−7 UI，無法滿足小殘差驗收。上式 q 僅為數學簡寫。

Δt 使用秒，不把長碼視為一個 UI；`n_k` 必須比前一轉態格號大，另存未 wrap 間隔／格號診斷。此式為連續模型的近似，須以掃頻驗證實際增益；不符下列容差就改離散化，不得僅以係數名稱宣稱達成頻寬。

輸出 TIE 必用**本邊緣更新前**的預測邊界 `b⁻[n]`，不得先以本邊緣校正再量測。更新後狀態只影響未來；無轉態 UI 用相同預更新狀態外插補邊界供眼圖映射，不補造 TIE 量測事件。已輸出的邊界不可回寫，跨更新的邊界也須嚴格遞增；邊界查詢須保存其生成狀態與有效段。TIE 不再保證均值為零，也不再額外去趨勢；σ 與 RMS 仍分開。

#### 鎖定、缺邊與重新鎖定（待校準的產品門檻）

- 初始用標稱 UI 及首有效交越相位，絕對頻率 w=R；捕獲範圍暫定標稱 ±1000 ppm；w 超界失鎖門檻另定較大值，例如相對 R 的 ±1500 ppm（待校準），不可直接拿捕獲界線當超界門檻。type-II、ζ=1/√2 對頻率階躍的 w 過衝約 4.3%，±1000 ppm 捕獲測試須容許此暫態。審查模擬：1000 ppm 的峰值 |TIE| 約 0.249 UI、可鎖；1400 ppm 已貼近 0.35 UI；2000 ppm 滑格，1% 始終鎖不住。這是待校準的產品門檻，不保證範圍外捕獲。不以全段擬合偷看未來追蹤結果。
- 重鎖以目前事件重設相位、前次時間及鎖定窗，`w` 保留目前有限且未超 w 門檻（例 ±1500 ppm）的估計，**不重設回 R**，避免頻偏下無限重鎖；非有限／超界 w 回無效並停止該次追蹤，待新請求重新初始化，不攜入重鎖。
- 每次啟動／重鎖先排除 `Tsettle=10/(ζ*ωn)`；其後連續 `W=max(1024 UI, 5/B 秒)` 的視窗內須有 ≥200 個有效轉態、預更新 |TIE| 的 95 分位 <0.1 UI、無滑格／衝突／w 超界才宣告鎖定。視窗內頻率估計首末各四分之一平均差須 <100 ppm。**取得鎖定後才開始計入後續事件**，不可回填鎖定判定窗。
- 單緣 |TIE|≥0.35 UI 視為配對疑慮，排除該緣且進入重新取得鎖定；非正邊界間隔、非有限狀態、w 超出獨立門檻（例 ±1500 ppm）立即失鎖；超過捕獲 ±1000 ppm 本身不構成失鎖。須另保留未 wrap 的間隔與格號診斷；單靠小殘差無法排除 cycle slip。
- NRZ 無轉態屬正常長碼，不補造量測邊緣。**間隔 ≤32 UI 都照常依實際 Δt 回授，不進 holdover、不重鎖，也不因此排除眼圖**，相位／格號及頻率異常仍按前項失鎖。PRBS7 最長連續碼為 7 UI、合法 8b10b 最長為 5 UI；若 >4 UI 就重鎖，這些碼型會反覆失鎖而無法正常取得鎖定。無轉態 UI 以外插邊界保留眼圖樣本；>32 UI 才失鎖、按前述保留 w 的規則重設相位與鎖定窗，重新取得鎖定。間隔 UI 數以預更新相位跨距判定，並驗格號差，邊界測試須涵蓋數值誤差。時脈型日後另分真正漏脈衝。
- 鎖定／失鎖區段、排除緣數、>32 UI 間隔與重鎖次數全保留；事件及眼圖不得跨失鎖邊界。短記錄若沒有鎖定後資料，回無效與原因，不回零 jitter。

預設 B=R/1667 時，`Tsettle≈7722 UI`、`W≈8335 UI`，僅取得鎖定就約需 16k UI，還須加上鎖定後量測資料。短於此長度不應預期有有效結果。

#### TIE、眼圖、狀態與 UI（後續接線設計）

- 回傳獨立追蹤結果（預測邊界、逐緣 TIE、valid mask、segment id、逐 UI 週期、設定及診斷）；既有 Clock 不塞入假固定 ui/t0。資料流應支援分塊，不為長連續碼無限展開全部空 UI。
- 眼圖相位用有效相鄰邊界：`φ(t)=n+(t−b[n])/(b[n+1]−b[n])`；所有 rails、density、Crossing % 及 DCD 共用此時基與遮罩，Crossing % 反向取樣也用邊界內插，不沿用 `t0+(n+c)*ui`。TIE 與眼圖使用同一組預更新邊界。
- 眼 Jitter 秒值依有效殘餘 TIE 統計；相位 σ 另按每緣局部 UI 正規化。原始 σ／實測 p-p、裁切 σ／6σ 的分列及 >1% 裁切提示保留。眼寬以 UI 為主，先只報 `1−6σ_phase` UI 的近似值；若需秒值，乘以有效區間局部 UI 中位數，明示「代表 UI 換算」，並揭露 UI 最小／最大值。不是 BER 開口。此 PLL 眼寬以 UI 為主，與 Jitter Web 草案眼寬以秒為單位不同，接線前須另提契約案。
- 還原 UI／速率改為有效局部週期中位數及其倒數，另列範圍；不能以標稱速率冒充追蹤結果。N 週期、Period-Period、寬度差仍由原始交越時間差計算，僅限同一有效段且不跨缺邊，不以殘餘 TIE 替代。
- 沿用 `valid / limited / invalid` 與還原／單筆兩層 worst 合併。擬增原因碼：無有效鎖定資料 `PLL_NOT_LOCKED` → invalid；保留子集且曾失鎖／重鎖 `PLL_RELOCKED`、排除暫態 `PLL_TRANSIENT_EXCLUDED` → limited；配對滑格 `PLL_CYCLE_SLIP` 對該段 invalid，整筆有其他有效段時 limited。純鎖定本身不自動降級；保留所有原有速率歧義與低樣本提示。
- diagnostics 至少帶參考模式、R、B 及其定義、ζ、ωn、離散模型版本、鎖定／有效比例、排除數、區段、局部 UI 範圍。既有固定格號 slip 診斷不直接套在 PLL 殘差；改對預測配對與邊界診斷，亦不得清掉先前已知歧義。
- 日後 GUI 接回時，在「時脈…」加參考模式開關，預設固定；PLL 開啟才顯示 B／除數、阻尼及有效資料比例。切換會重新計算所有 TIE／眼圖並更新匯出設定。常駐提示「PLL 會追蹤並吸收部分低頻抖動」。本案不把目前未接線畫面說成已可用；不靜默失敗退回固定模式。

#### 合成驗收（實作完成後才執行）

首版用精確交越事件；後續波形層才用 64 點/UI、線性邊緣；R=1 Gb/s、seed=20261024。每例經鎖定與排除後至少 2000 轉態；RJ 至少 20,000 個有效轉態，若只用 2000 轉態則容差放寬至 10%；SJ 另保留 ≥20 個最低測試頻率週期。振幅用已知頻率的 sin/cos 最小平方估計，不用 FFT 單格讀值。0.1B 的 20 週期本身約 333,400 UI（至少約 33 萬 UI），另加約 16k UI 捕獲；僅測試區段在 64 點/UI 就約 2100 萬點。因此 **0.1B 只在事件層測**，不要求波形層跑此例。

| 案例 | 通過條件 |
|---|---|
| 固定模式回歸 | 開關關閉時，四模組既有自檢通過；同環境舊／新結果逐位元、狀態與原因碼一致。 |
| 無 jitter、頻偏 ±1000 ppm | 正確格號、沒有 slip；有效事件殘餘 RMS <1e−6 UI；恢復速率誤差 <10 ppm。不可把取得鎖定前資料納入。 |
| 已知 SJ 掃頻 | 振幅 A=0.02 UI，f/B=0.1、1、10；恢復時脈振幅／A 符合 \|H(j2πf)\|、殘餘 TIE 符合 \|E(j2πf)\|，各相對誤差 ≤5%，相位誤差 ≤5°。 |
| SJ 被吸收的預期 | 對 ζ=1/√2、上述 JTF 定義，在 0.1B 時 `\|E(0.1B)\|≈0.0423`，殘餘約 0.0423A（約 96% 被追蹤吸收）；10B 殘餘約 A。固定手動參考仍量到約 A（誤差 ≤1%）。低頻 PLL TIE／折疊眼較窄是預期，不能解讀為原訊號 SJ 消失。 |
| 轉態密度 | 同一 SJ 分別套 alternating、PRBS7（最長 7 UI）、合法 8b10b（最長 5 UI，含跨碼字邊界）；明確驗碼長／格號、持續鎖定及有效樣本，掃頻皆符合上項容差，驗證 Δt／轉態密度不讓頻寬任意漂移。 |
| 捕獲邊界與重鎖狀態 | 驗 ±1000 ppm 可鎖，w 約 4.3% 過衝不誤判超界；1400／2000 ppm／1% 不納入捕獲保證，鎖定須符合完整判定窗。另測獨立 w 門檻（例 ±1500 ppm）內外；重鎖保留 w、重排相位及鎖定窗，不反覆重設 R；非有限／超 w 門檻回無效。 |
| 長碼與重鎖 | 插入 4、5、7、32、33 UI 無轉態，≤32 UI 保持鎖定並依 Δt 回授，無轉態 UI 外插邊界可用於眼圖但不增加 TIE 事件；33 UI 失鎖與重新取得鎖定，失鎖／重鎖窗不入統計，跨失鎖段連線／補點為零。 |
| 階躍與滑格 | 0.2 UI 相位階躍的線性暫態與獨立連續模型比對，波形最大差 ≤0.01 UI；0.6 UI 步階須排除並重鎖，不可只輸出一串正常的小 TIE。另驗整 UI 跳變可能不可辨識，不能承諾全檢出。 |
| RJ 與少量離群 | σ=0.01 UI 的獨立 RJ，測得殘餘變異數與實際離散模型對白雜訊的預測差 ≤5%（有效轉態 ≥20,000；若僅 2000 則 ≤10%）；加 1% 的 0.2 UI 延遲，原始有效 TIE 須保留尾端，裁切另計，不能當缺邊刪除。 |
| 眼圖與失敗狀態 | 已知邊界映射誤差 <1e−6 UI（事件層）；波形層 <0.01 UI。密度只用有效段，顯示補點不增加原始事件數；全未鎖、短記錄、頻率超界均無假零值，狀態／診斷／匯出設定相符。 |

#### 檔案預算、風險與採用預設

以下均由 T7 執行，尚未實作；含自檢每檔 ≤300，不動 `contracts.py`。原型先合併 `pll.py`、`pll_lock.py`、`clock_track.py` 職責於單一 `pll.py`，合併後超過 300 行再拆；後續接線檔案不列首版交付：

| 檔案 | 工作／目標上限 |
|---|---|
| `analysis/pll.py`（首版新增） | PI、整數／小數相位、事件更新、捕獲／鎖定／重鎖及邊界查詢原型，≤300 行；超限才拆 pll_lock.py／clock_track.py |
| `analysis/pll_check.py`（新增） | 首版事件層合成掃頻／頻偏／捕獲驗收，≤280 行；後續眼圖整合另放 `track_eye_check.py` ≤220 行 |
| `analysis/clock_check.py`（後續新增）、`clock.py` | 先搬既有自檢（≤200 行），clock 留薄入口及既有固定流程，整合後目標 ≤230 行 |
| `analysis/eye.py`、`eye_check.py`（後續新增） | 自檢先搬離；眼圖接共用相位／有效區段，eye ≤240、check ≤220 行 |
| `analysis/jitter.py`、`status.py`（後續） | 有效段篩選與統計標籤、集中原因碼；各 ≤250 行，近上限再拆診斷格式 |
| 未來 UI／服務／匯出 | 另立接線工作，各檔 ≤300 行；凍結 Web 契約若需擴充，先另提契約案，不在核心案暗改 |

**風險高，建議先做核心原型與傳遞函數驗收，再接 UI。** PLL 開工前須先完成 [驗證紀錄](DSOX6004A_Jitter驗證紀錄.md) L26 前置條件：用 `scope_trend_1M.json` 比對頻譜比值是否平坦，再確認參考時脈與門檻定義。風險包含轉態密度造成頻寬偏差、錯格後被迴路掩蓋、短記錄無有效區、篩除未鎖區導致偏樂觀、長碼外插與大 Δt 離散近似誤差、DCD／圖樣延遲被回授吸收，以及動態 UI 秒值比較失去共同參考。此線性模型也不代表真實接收器的 bang-bang CDR、SSC 全範圍或協定符合性。

採用預設：首版只做已知速率 NRZ；頻寬採 JTF −3 dB、B=R/1667、ζ=1/√2；≤32 UI 正常回授，>32 UI 才重鎖；眼寬以 UI 為主，秒值只作代表 UI 換算；先做核心原型及傳遞函數驗收，再排 GUI／匯出接線。開工仍以前述驗證紀錄 L26 的頻譜比值檢查及定義確認為前置條件。鎖定窗、±1000 ppm 捕獲範圍與獨立 w 超界門檻（例 ±1500 ppm）皆待校準，重鎖保留目前 w，沒有預先宣稱協定符合性。
