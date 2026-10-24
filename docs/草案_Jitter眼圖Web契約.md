# 草案：Jitter／眼圖 Web 契約

日期：2026-10-24。供 lead 審查，**尚未生效**；現行 v2 仍以 `docs/web-api契約.md`、`scope_tool/web/static/api_contract.json` 為準。本次僅修訂指定兩份草案，不修改程式或凍結契約。目標契約版本為 v3，待 lead 解凍後落地。

依據：上述兩份契約、`RULES.md`、`web/analysis_api.py`、`analysis/{clock,jitter,eye,status,slip,rate_seed}.py`、`ui/analysis_{jitter,eye}.py`（程式路徑皆以 `scope_tool/` 起算）。只分析已開檔案，不碰儀器；沿用 numpy，不增加套件／CDN。

## 1. RPC 與型別（提案）

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

## 2. 三態、原因碼與統計分欄

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

## 3. 圖形、容量與二進位端點

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

## 4. 舊結果回寫與錯誤

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

## 5. 匯出

`export_timing` 為 `job=false`，在 HTTP 執行緒同步寫檔並直接回 `PathResult`／錯誤包絡，不產生 job 事件；重算中仍可匯出前份存活快照。首版只匯出 CSV 摘要（UTF-8 BOM），不匯出原始趨勢／密度矩陣／圖片。directory=null 用來源檔目錄；expanduser，回絕對路徑。檔名 `{來源名}_Jitter或眼圖_YYYYMMDD_HHMMSS.csv`，永不覆蓋，同秒碰撞須另取未使用名稱。

- 中繼資料：來源絕對路徑、gen、revision、result_id、匯出時間、source／unit、顯示 range／來源 range、dx、threshold 與百分比、完整 ClockSpec／effective_edges、ui／rate／rate_unit、edge_count／n_ui、算法限制註記。
- 每列：name、unit、ok、current、mean、min、max、range、std、count、status、reasons、failure_code、reason、notes（含剔除數／比例）。
- 四項獨立欄：raw_sigma、measured_pp、trimmed_sigma、six_sigma_estimate；另 trimmed_count／fraction、signed_width、clock_status／reasons、diagnostics JSON、warnings。非適用留空，不填 0；含受限／無效結果須完整保留標記。
- 數值科學記號且可往返原精度；null 寫空白。匯出前短暫鎖內驗證並持有快照參照；鎖外先寫暫存，最後再鎖內驗世代、id 仍存活且快照自身 revision 等於請求（不比對已登記最新 revision），並以不覆蓋方式發布，失效即清暫存、回 STALE。

## 6. 後續改動位置與擁有權（僅列提案）

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
| `docs/web版驗收清單.md` | L8；新增驗收條件與未實機驗證註記，總長≤300 |

後續新檔共 10 個（含本草案與獨立 L1a jobs_check；4 個前端新檔暫緩），params／binary／export 仍按下表整併。新增檔案與**含自檢／註解的總行數預算**（名稱暫定；未建立任何下列實作檔）：

| 新檔 | 擁有／預算 | 職責 |
|---|---|---|
| `docs/草案_Jitter眼圖Web契約.md` | lead／≤250 | 本草案 |
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

## 7. Mock、驗證與採用預設

- Mock：`?mock=1` 全離線、同方法／參數／回傳型別／二進位格式；至少提供乾淨時脈、NRZ 自動 limited、缺邊、滑格疑慮、格號衝突 invalid、裁切 >1%、無正開口、空區間與非有限輸入。固定種子，不宣稱等同實際算法。
- 數值：用 clock.nrz 與既有 self-check 比對四分欄、UI／step／速率、N=1/20 與缺邊不跨、DCD 兩邊要求；驗裁切比例 0.99%／1%／1.01%、半格 1%／5% 邊界。密度朝向、2 UI、計數與 log1p 僅一次皆須驗。
- 契約：公開 Analysis 方法集合（含繼承）與 params 等於 JSON，mock 同步；巢狀欄位、nullable、有限值、未知鍵、巨大 names、bool-as-int、token、HTTP／事件錯誤皆有 assert。
- 競態：A 慢、B／C 依序入 FIFO；A 提交前已過期回 STALE，B 輪到 work() 開頭才判過期回 STALE、不進昂貴運算，C 正常執行；各分析 job 僅一個完成事件，同步 export_timing 無 job 事件且不受 FIFO 阻擋；FIFO 中眼圖擋住 measure／FFT、換檔／關檔、刪除來源、新參數防抖未送出、job 事件早到、舊 finally、同 id 重送／異參數、快照取代／換世代清除、下載中換檔、重算中前份快照仍可匯出、匯出暫存中快照被取代失效；舊結果不可回寫或產生已過期匯出檔。
- 容量：最大趨勢／密度、壞長度／尺寸／版本、NaN 斷線、64 KiB／64 MiB 邊界、超大來源的峰值記憶體／耗時；原有 wave／FFT／量測與儀器工作的數值／協定不得退化；另量測並揭露 FIFO 造成 measure／FFT 等待眼圖的延遲。
- 方式：依 RULES 用 `python3 -m scope_tool.web.jobs_check`、`python3 -m scope_tool.web.analysis_timing_check`、`python3 -m scope_tool.web.e2e_check`、Node／selfcheck.html，assert 且印 self-check OK；不新增 pytest／fixture／依賴。本次僅文件審核，以上皆為後續計畫，未執行功能測試。

採用預設：契約升 v3，待 lead 解凍；JSON 不受行數上限但歸 L0；每方法最新單份快照上限 64 MiB，換世代即清，沿用分析 FIFO；只考慮單一視窗；首版拒絕區間內任何非有限輸入，僅匯出摘要。新檔 lane 接手仍由 lead 排程，不把上述預設列為待選問題。數值風險：固定頻率不追 PLL／SSC、大 jitter 可能滑格且診斷會誤漏報、全自動 NRZ 速率有倍頻歧義；產品門檻尚待校準，與 EZJIT 的比較**待真機驗證**。
