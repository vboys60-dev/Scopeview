# I3C 解碼計畫（離線分析：SCL／SDA 類比波形 → I3C Basic v1.2 SDR 事件）

2026-10-26 起草。分工：Claude 規劃／驗收，Codex 實作。本文件可直接照做；標「預設」的地方是開放問題的建議值，使用者沒回覆就照預設做。協定依據為 `docs/研究_數位解碼協定定義.md`（下稱「研究」）§2、§3、§9、§10；研究標「待確認」或本文件另作工程選擇處都明寫。經 Codex 兩輪審查修訂（§13）。

## 使用者決定（2026-10-26，已定）

1. **範圍**：I3C Basic v1.2、單 lane SDR 全套——Private write（T＝奇同位）、Private read（T＝繼續／結束交握）、address ACK／NACK、0x7E 廣播、Broadcast／Direct CCC（命令描述表驅動，未知碼保留 hex）、ENTDAA（PID／BCR／DCR、DA＋位址 parity、PID↔DA 位址表含有效時間）、IBI（MDB／payload 依 BCR）、Hot-Join（0x02）、HDR Exit 與 Target Reset pattern、I2C legacy transfer。HDR 只辨識進出：`ENTHDRn` 到 Exit 標「HDR-xxx 區段（未解碼）」與起訖時間。
2. **驗證資料**：無實測波形 → 程式合成 I3C 類比波形（雜訊、有限上升時間、parity 錯、DAA 兩 Target 競爭、IBI 有／無 payload、HJ 後 DAA、Reset 與 Exit 前綴重疊、擷取中途開始）。
3. **呈現**：(a) 主圖下方與時間軸對齊的標註列（縮小看 transaction、放大展開 byte／bit）；(b) B 區新增「解碼」分頁事件表，點列跳到波形；(c) 事件表匯出 CSV，並納入既有 HTML 報告（`report.js`）。
4. **預設**：使用者選 SCL／SDA 通道；門檻自動取平台中點＋遲滯、可手動覆寫；擷取中途開始時位址表標「未知」，不捏造。

---

## 0. 先決條件（Codex 開工前，lead 要先處理）

| # | 事項 | 原因 |
|---|---|---|
| A | **使用者同意契約追加**：4 個 Analysis 方法 `decode`（J）、`decode_frames`、`decode_bits`、`export_decode`；新型別 `DecodeSummary／DecodeCounts／DecodeFrames／DecodeFrame／DecodeField／AddrEntry／DecodeBits`；`version` 維持 2（同 FFT rbw／vbw 先例，只追加）。catalog 不變 | RULES：L0 契約凍結，只有 lead 能改 |
| B | RULES.md lane 表登記新檔（§6）；新 store 鍵 `decodeResult`、`decodeSel`、`plotRect` | 新檔沒登記不能改 |
| C | 授權跨 lane：L0（契約兩檔、`mock_backend.js`、`l0_sem.mjs`）、L1b（`analysis_api.py` 三行）、L4（`tab_analysis.js`、`mainplot.js`、`analysis.css` 檔尾）、L5（`bpanel.js`、`report.js`）、L8（`e2e_check.py`、`browser_check.py`、`selfcheck_node.js`、驗收清單） | 同 FFT／浮動面板前例，寫進 RULES.md 授權段 |

`analysis/*`、`storage/*`、`contracts.py` 仍凍結；只 **import** `analysis.measure.levels` 與 `storage.writer.timestamped`。

---

## 1. 現況摘要（實作者先讀）

| 項目 | 現況 | 對本案的影響 |
|---|---|---|
| 原始資料 | 只在後端 `Analysis._waves`（`Waveform(channel, time, voltage)`，float64，可達 100M 點／通道） | 解碼在後端做；前端 `/wave` 只有每像素 min/max 包絡，不能解碼 |
| 分析工作 | `server.rpc` 依契約 `job` 旗標 `jobs.submit`；分析執行緒 `ThreadPoolExecutor(1)`、不可取消；結果以 `type:"job"` 事件回傳，**事件環（500）與 request_id 去重表（256）都會保留 result** | job 只回小摘要；大的 frames 用同步 RPC 取（`bridge.call` 不帶 request_id，不進去重表、不進事件環） |
| 世代 | `_gen` 開／關檔 +1、`_alive(gen)` 丟 `StaleError`；`_spec` 只留最近一份、失敗時清空 | 解碼照抄：`_dec` 只留一份，失敗也清空，id 不符 → STALE |
| 參數驗證 | `server.rpc` 只驗頂層鍵集合；`validate_params` 尚未接 server，且具名物件型別不遞迴驗欄位 | `channels`／`options` 內容由 `DecodeMixin` 自行驗；巢狀錯誤在 job 內以 BAD_REQUEST 失敗（job 事件），頂層缺鍵則同步 BAD_REQUEST |
| 契約型別語法 | `l0_util.tc` 與 `_ok` 支援 `map<…>`、`[a,b]`、`X[]`、`|null`、具名型別；**欄位型別必須是字串**（不能內嵌物件） | `counts` 用具名型別 `DecodeCounts` |
| 300 行上限 | `analysis_api.py` 296、`browser_check.py` 300、`analysis_check.py` 286、`mock_backend.js` 260、`tab_analysis.js` 226 | 新功能開新檔；動到上列檔案要算行數（§6） |
| B 區頁籤 | `bpanel.js TABS`；`mountTabs` 對缺 panel 的 key 略過；`marker_check.mjs` 以 `TABS` 建 panels；`float_check.mjs` 以正規式抽 `resultTabs.update(...)` 原文在測試環境執行 | 加 `'decode'`；計數不得寫進 `resultTabs.update(...)` 那行（測試環境沒有該變數），改由 mountTabs 回傳的 `label()` 入口更新 |
| 版面預算 | `renderLayout`：`const chrome = chanbar 高 + 28` 傳入 `clampLayout`；`float_check` 綁 `effective = clampLayout(...)` 原文 | 標註列高度加在 `chrome` 那行，不改被綁的兩行 |
| 工具列 | 1400 寬已滿（匯出合併成下拉就是為了不換行） | **工具列不加控件**；解碼設定放「解碼」分頁內 |
| 樣式 | `analysis.css`／`vertical.css` 原有行不改（變異測試綁原文）；`glass.css` 只能用白名單屬性 | 新 class 寫在 `analysis.css` **檔尾新行**；表格沿用 `.table .table--num .results__table`；標註列屬圖區（`--c-plot-bg` 黑底）；**不改 glass.css** |
| 報告 | `report.js collectReport` 依畫面 DOM／canvas 組 section；`buildReport` 只看「有圖或非空表」 | 解碼 section 由有效 `decodeResult` 決定是否加入，不靠 DOM 有無 |

---

## 2. 架構分層與放置位置

```
類比 (t, v_scl, v_sda)                         後端 web/logic.py      ← 未來 I2C/SPI/UART/CAN 共用
  → 邏輯位準 {0,1,unknown}（雙門檻遲滯）           後端 web/logic.py
  → 邊沿（時間, 新值, 是否自 unknown 恢復）          後端 web/logic.py
  → I3C 狀態機（SDR/CCC/DAA/IBI/HJ/pattern/I2C）  後端 web/i3c_decode.py ＋ web/i3c_ccc.py
  → frames／fields／bits／位址表，存於 _dec          後端 web/analysis_decode.py（DecodeMixin）
  → UI：事件表／標註列／CSV／報告                    前端 decode*.js；CSV 由後端寫
```

**為何前四層全在後端**：原始點只在後端；GSa/s、千萬點傳到前端要 80 MB／通道，`/wave` 包絡會吃掉窄脈衝（研究 §10.1-6）；類比→邏輯→邊沿可 numpy 向量化（O(n)、分塊），狀態機只走邊沿（12.5 MHz、10 ms ≈ 50 萬邊沿），Python 迴圈可接受；既有 job／gen／STALE 直接沿用。

**為何傳輸分三段**：job `decode` 只回摘要（數 KB，事件環／去重表保留也無妨）；frames（可達數 MB）由同步 `decode_frames` 取一次；bit 時間只在放大到看得見 bit 時，以 `decode_bits` 取畫面範圍 ≤4096 個（實際 SCL 週期不固定，不能用 field 起訖平均切 9 格代替）。

**未來協定的接縫（只留這兩個）**：
1. `web/logic.py` 與協定無關（門檻、遲滯、邊沿）——SPI／UART／CAN 都從這層開始（研究 §10.1-2/3）。
2. RPC 名稱與參數形狀不綁 I3C：`decode(protocol, channels, thresholds, options)`，`channels`／`thresholds` 是「角色→值」map——加 I2C／SPI 不必新增方法（每次改契約都要 lead 同意）。
不做：decoder registry、catalog 角色表、基底類別。目前 `protocol` 只接受 `"i3c"`（直接 if），roles 寫死 `scl`、`sda`；第二個協定出現時再抽。

---

## 3. 後端設計

### 3.1 `web/logic.py`（類比→邏輯→邊沿，協定中立）

```python
HYST = 0.1                      # 遲滯半寬／(top−base)，待真機校準
LEVEL_SAMPLES = 4_000_000       # 平台估計最多用這麼多點（等距抽樣）
CHUNK = 1 << 22
MAX_EDGES = 10_000_000          # 每線上限，超過截斷
def auto_threshold(v: np.ndarray) -> tuple[float, float] | None
def to_edges(t: np.ndarray, v: np.ndarray, lo: float, hi: float) -> Edges
#  Edges = NamedTuple(time: float64[], value: int8[], resync: bool[], unknown: list[tuple[float,float]],
#                     min_run: int, single_sample: int, truncated: bool)
```
- **自動門檻**：n > `LEVEL_SAMPLES` 時以固定種子 `np.random.default_rng(0).choice(n, LEVEL_SAMPLES)` 隨機抽樣（**不用等距**，避免與週期訊號對齊只抽到高位），以 `np.isfinite` 過濾（NaN 與 ±Inf 都去掉）後 `vmin, vmax, top, base = measure.levels(...)`；`top−base ≤ 0` 或無有限值 → `None`。`mid=(top+base)/2`、`h=HYST·(top−base)` → `(mid−h, mid+h)`。抽樣只影響平台估計（直方圖），不影響邊沿。
- **遲滯**：`v≥hi → 1`、`v≤lo → 0`、中間區沿用前態（已定義樣本索引 `np.maximum.accumulate` forward-fill）；檔頭在中間區 → unknown 直到第一個定義樣本；**NaN／Inf → unknown 並打斷前態**（研究 §2）。由 unknown 恢復成 0／1 的第一個值記 `resync=True`，**不是真實邊沿**，狀態機不得把它當 START／STOP／bit。
- **分塊**：每塊 `CHUNK` 樣本，前態（含 unknown）跨塊帶入；不配置 n 長 int64。峰值記憶體≈ 一塊的暫存＋邊沿陣列。
- **邊沿時間**：翻轉樣本 i 以 `v[i−1]→v[i]` 線性內插所跨門檻（上升 hi、下降 lo）；內插後兩線同時刻 → 狀態機記 `ambiguous_edge`。
- **品質**：`min_run`＝最短穩定段（樣本數），SCL 最短高／低 <4 點 → `warnings`「取樣不足（最短 SCL 脈寬 N 點）」（研究 §2.1 經驗值）。不做 glitch 濾波（研究 §10.1-3），單樣本脈衝數記入 `single_sample`。
- 超過 `MAX_EDGES` → 截斷到該時間，`truncated=True`；任一線截斷時，DecodeMixin 把兩線都截在較早的截止時間再交給狀態機。上限常數可由呼叫端以參數覆寫（只供測試）。

### 3.2 `web/i3c_decode.py`＋`web/i3c_ccc.py`（狀態機）

輸入：兩線 `Edges`、`i2c_addrs: set[int]`；輸出：`frames`、`bits`（全部取樣 bit 的時間／值）、`addresses`、`warnings`。狀態機放 `i3c_decode.py`；CCC 表、payload 解讀、位址表更新放 `i3c_ccc.py`；各 ≤300 行。

#### 3.2.1 基本事件與優先順序
依時間走合併邊沿：
- **SCL 上升**：若在 pattern 計數中（見 3.2.7）先判 pattern；否則取當下 SDA 值為 1 bit（bit 時間＝上升緣時間）。
- **SCL＝1 時 SDA 下降**：START（frame 進行中則為 Sr）。**SCL＝1 時 SDA 上升**：STOP。在 read T 視窗內這兩者另有意義（3.2.3），先於一般 START／STOP 解讀。
- **SCL＝0 時 SDA 轉換**：一般資料變化；同一 SCL 低期間累計 SDA 下降次數 k 供 pattern 判定。
- **resync／unknown**：進行中 frame 以 `truncated` 結束，狀態回「未同步」。
- **未同步**：丟棄 bit，直到第一個 START 或 STOP；同步點前若有 SCL 活動，輸出 `kind="partial"`（「擷取開始於傳輸中途」，起訖＝第一個邊沿～同步點）。

#### 3.2.2 Header 與 frame 種類
Header＝9 bit：`A[6:0]`、`RnW`、ACK（0＝ACK）。`start` 欄記 `S` 或 `Sr`。

| 條件 | kind | 之後 |
|---|---|---|
| `0x7E/W`＋ACK，下一個事件是 9 bit | `ccc_broadcast`／`ccc_direct` | 第一個 byte＝CCC code＋T（奇同位），見 3.2.5 |
| `0x7E/W`＋ACK，下一個事件是 Sr | （不成 frame） | 7E header 併入後續 private／i2c frame 的第一個 field（label「7E 開場」）；**不產生缺 code 的 CCC** |
| `0x7E/R`，在 ENTDAA 內 | `daa` | 3.2.6 |
| `0x7E/R`，不在 ENTDAA 內 | `error` | reason `addr_7e_read` |
| `0x02/W`，在 START（非 Sr）後 | `hotjoin` | ACK／NACK 皆記；HJ 本身不建立位址表項 |
| 位址 ∈ `i2c_addrs` | `i2c` | 3.2.4 |
| START（非 Sr）＋位址／R（≠7E） | `ibi`，label「IBI（亦可能為 Controller 直接讀）」 | ACK → 讀取資料（3.2.3）；第一個 byte 只有在該 DA 的 BCR 已知且 BCR[2]=1 時標 `mdb`；BCR[2]=0 時之後的 byte 標 `data`＋reason `ibi_unexpected_payload`；BCR 未知時標 `data`、label「BCR 未知（若為 IBI 首 byte 為 MDB）」。NACK → `ack=false`，reason `nack`、label「IBI 被拒／延後」，`status=warn`（協定事件，非錯誤） |
| 其他 位址／W、Sr＋位址／R | `private_write`／`private_read` | 3.2.3 |
| 位址 NACK（上列以外） | 同上 kind，`ack=false` | reason `nack`、`status=warn`；等 Sr／P |

**位址類型**（取代初稿的啟發式）：「已確認 I3C DA」只來自本次擷取的 ENTDAA／SETDASA／SETNEWDA 指派且仍有效；`i2c_addrs` 由使用者在分頁輸入。兩者皆非的位址**依 I3C 解讀**（本工具是 I3C 解碼器），並加資訊性 reason `type_unknown`（不影響 status），label 提示「位址類型未確認；若為 I2C 裝置請加入 I2C 位址清單」。流量中看到的未確認位址以 `how="observed"` 記入位址表（`t_from=null`、`pid/bcr/dcr=null`），**observed 不算確認**，不參與任何判讀。

#### 3.2.3 資料 byte 與 T
- **寫入**（Private write、CCC code、Broadcast／Direct 寫資料）：8 bit MSB first＋T，`T = 1 ^ D7 ^ … ^ D0`（9 位 XOR＝1）；不符 → field `ok=false`、reason `parity`、frame `status=error`。
- **讀取**（Private read、IBI 資料、Direct GET 回傳）：第 9 bit 為 T 交握。**T 視窗**＝T 的 SCL 上升緣到下一個 SCL 下降緣：
  - T=1 且視窗內 SDA 下降 → **Controller 提前結束**（Target 已釋放 SDA，Controller 拉低＝Sr）；label 註記，之後當 Sr 處理（可能接 header 或 STOP）。
  - T=1 且視窗內無 SDA 變化 → 繼續下一 byte。
  - T=0 → Target 結束；視窗內 SDA 上升＝STOP；否則之後應為 Sr／P。T=0 後若又出現資料時脈（8 個以上 SCL 上升而無 Sr／P）→ reason `t_bit`、`status=error`。
  - T 上升緣與視窗內 SDA 轉換落在同一樣本（取樣不足）→ `ambiguous_edge`，不斷言由誰結束。
  - 讀取**不做 parity 檢查**。
- **I2C**：第 9 bit＝ACK(0)／NACK(1)；寫入 NACK → reason `nack`；讀取最後一 byte NACK 是正常結束。
- 擷取結束仍未見 STOP → reason `truncated`、`status=warn`。

#### 3.2.4 I2C legacy transfer
`S/Sr → 位址/RnW → ACK → (D[7:0]+ACK/NACK)* → P/Sr`，只用於 `i2c_addrs` 內的位址；10-bit 位址不做（研究 §3.10：I3C 位址為 7-bit）。

#### 3.2.5 CCC（`i3c_ccc.py` 表驅動）
表項：`code → (name, form: broadcast|direct, def: none|required|optional, defvals: set|None, payload: 描述|None, note: str|None)`；`payload=None`＝只保留 raw；`note` 放「非 Basic」「v1.1 起不得使用」等（後者同時給 reason `ccc_invalid`）。
- 收錄研究 §3.5 全部碼＋ENTHDR0–7（0x20–0x27）。**這是常用子集，不是完整 v1.2 表**；分三類：
  - 已知且解讀 payload（`parse=True`）：ENEC／DISEC（mask）、ENTAS0–3、RSTDAA（0x06）、ENTDAA、DEFTGTS（只列 raw）、SETMWL／SETMRL（u16；SETMRL 可多 1 byte IBI 長度）、GETMWL／GETMRL、SETDASA、SETNEWDA、GETPID（6 byte）、GETBCR、GETDCR、GETSTATUS（2 byte）、ENTHDR0–7、RSTACT（Defining Byte 0x00／0x01／0x02 有名稱）。
  - 已知但只保留 raw（`parse=False`）：GETMXDS、GETCAPS、ENDXFER 等格式依版本／能力不同者。
  - 不合法：Direct RSTDAA `0x86`（v1.1 起不得使用）→ reason `ccc_invalid`、`status=warn`；ENTHDR1／2 名稱照列但標「非 Basic」。
  - **未知碼**：`ccc_name=null`、label `CCC 0x5A`、byte 照列 raw，reason `ccc_unknown`（資訊性）。
- **Broadcast**（code < 0x80）：之後的寫入 byte 為 payload，到 Sr／P 為止（Sr 結束 broadcast 作用範圍）；長度不符表定義 → `ccc_format`。
- **Direct**（code ≥ 0x80）：code 後、第一個 Sr 前的 byte 依表 `def`：`none` 卻出現 byte → `ccc_format`；`required` 卻沒有 → `ccc_format`；`defvals` 不含該值 → `ccc_format`；未知碼的這些 byte 只列 raw（kind `data`，不稱 Defining Byte）。之後每個 `Sr＋位址／RnW＋ACK＋資料` 是同一 frame 的一個子段（fields 以子段 header 分隔，每段各自方向與 ACK），直到 STOP 或 `Sr＋0x7E/W`（開新 frame）。
- **位址表更新**（只在相關 header ACK、payload 格式與 T 全部正確時）：
  - **SETDASA**（0x87）：子段位址＝static address（W）；資料 1 byte，**DA 在 [7:1]、bit0 必須為 0**，再接該 byte 的 T 奇同位；bit0=1 → `ccc_format`、不更新。成功 → 新增 `{da, static, how:"SETDASA", t_from}`。
  - **SETNEWDA**（0x88）：子段位址＝舊 DA；同樣 [7:1]＋bit0=0。成功 → 舊項 `t_to`、新增新 DA 項（沿用 PID／BCR／DCR）。
  - **RSTDAA**（0x06）→ 全部有效項 `t_to`＝該時間、`note="RSTDAA"`。
  - **GETPID／GETBCR／GETDCR** 讀回值（T 交握正常結束）→ 填入該 DA 項的空欄；與已知值矛盾 → reason `addr_conflict`、不覆寫。
  - **Target Reset 確認**（3.2.7）→ 全部有效項 `t_to`＝最後 STOP、`note="Target Reset 後有效性未知"`；之後該位址回到「未確認」。

#### 3.2.6 ENTDAA
`S→7E/W→ACK→ENTDAA(0x07)+T`，之後每回合 `Sr→7E/R→ACK→PID[47:0],BCR[7:0],DCR[7:0]（64 bit，MSB first，無 T）→ DA[6:0]+PAR → ACK`。
- `PAR` 為 7 個位址 bit 的奇同位：`PAR = 1 ^ XOR(DA[6:0])`；不符 → reason `addr_parity`。
- 區分兩種 ACK：**7E/R header 的 ACK**（有 Target 參與）與**指派 DA 後的 ACK**（勝出者接受）。
- 回合 DA 被 ACK 且 PAR 正確 → 新增 `{da, pid, bcr, dcr, how:"ENTDAA", t_from=DA ACK 時間}`；DA NACK → 該回合 `status=error`、不入表。
- `7E/R` header NACK＝無剩餘參與者，**正常結束**（`status=ok`，label「DAA 結束」），不加 `nack` warn。
- 只看得到線上的 wired-AND 結果（勝出者），不列落敗者（研究 §3.6）。
- 一個 ENTDAA frame 的 fields：每回合 `addr(7E/R)`、`pid`、`bcr`、`dcr`、`da`。PID 48 bit < 2⁵³，JSON 整數安全。

#### 3.2.7 Pattern（SCL 持續低時的 SDA 轉換）
**計數窗**：在同一 SCL 低期間內，從「SDA 為高」的時刻開始計數——SCL 降低時 SDA 若為低（例如前一個 T=0／ACK），第一次上升是 Controller 的 setup，**不計入**。k＝計數窗內 SDA 下降次數、n＝計數窗內轉換次數，並記 SCL 再升高時的 SDA 值。**不在 k 達 4 時就判定，等該 SCL 低期間結束**（SCL 上升或擷取結束），避免 Reset 前 4 次下降先被 Exit 吃掉（研究 §3.9）。進入 pattern 尾段後，一般 header parser 不接手，直到 pattern 判定完。pattern 開始時若有進行中的 frame，該 frame 以 pattern 起點結束並加 `truncated`。
- **HDR Exit**：計數窗起始 SDA 高、k＝4、SCL 升高時 **SDA 為低**，之後 SCL 高時 SDA 上升（STOP）→ `kind="hdr_exit"`；在 HDR 區段內則結束該區段；不在 HDR 內也接受（錯誤復原），label 加「（未見 ENTHDR）」。缺 STOP → `pattern_incomplete`。
- **Target Reset**：計數窗起始 SDA 高、n＝14（k＝7）、SCL 升高時 SDA 為高，之後 Sr（SDA 降）、STOP（SDA 升）→ `kind="target_reset"`（Reset action 在最後 STOP 生效，`t1`＝STOP）。缺 Sr 或 STOP → `status=warn`、`pattern_incomplete`。
- 擷取在 SCL 低期間結束且 k ≥ 2 → `kind="pattern"`、`pattern_incomplete`（顯示 k）。
- 2 ≤ k、不符上兩者 → `kind="pattern"`、`pattern_unknown`。
- label 一律註「形狀辨識，未檢時序（tDIG_H 等待確認）」。

#### 3.2.8 HDR 區段
`ENTHDRn`（0x20–0x27）的 T 之後 → `kind="hdr"`、label `HDR-DDR／TSP／TSL／BT／HDR-n 區段（未解碼）`，`t0`＝CCC 結束、`t1`＝**Exit pattern 開始**（`hdr.t1 = hdr_exit.t0`，Exit 另成一筆 frame，兩者不重疊）；區段內只做 pattern 偵測，不解 bit、不產生其他 frame。擷取結束仍未見 Exit → `truncated`。

#### 3.2.9 不變量與上限
- frames 依 `t0` 排序且**互不重疊**（`t1[i] ≤ t0[i+1]`；HDR 區段內不產生 frame，所以成立）；`i3c_check` 斷言。
- 上限（具名常數）：`MAX_FRAMES=100_000`、`MAX_FIELDS=100_000`（bits 受 `MAX_EDGES` 約束）。超過 → 停止解碼、`truncated=true`、`warnings`「事件超過上限，只解到 t=…」。`# ponytail: 上限防 JSON／記憶體過大；需要時改分頁 RPC`。

### 3.3 `web/analysis_decode.py`（`DecodeMixin`）

```python
class DecodeMixin:
    def decode(self, protocol: str, channels: dict, thresholds: dict, options: dict) -> dict   # job
    def decode_frames(self, decode_id: str) -> dict
    def decode_bits(self, decode_id: str, t0: float, t1: float) -> dict
    def export_decode(self, decode_id: str, directory: str | None) -> dict
```
- `analysis_api.py`：加 import 一行、改 class 基底那行、`_reset` 加 `self._dec = None`（淨增約兩行，296→298）。行數以 `l0_check` 同樣的 `split("\n").length` 規則計，不只看 `wc -l`。
- **`decode` 驗參數**（方法內明確驗，不依賴 `_ok`）：`protocol=="i3c"`；`channels` 鍵恰為 `{scl, sda}`、值為字串、通道存在、兩者不同；`thresholds` 鍵恰為 `{scl, sda}`、值為 `null` 或兩個有限數且 `lo<hi`；`options` 鍵 ⊆ `{i2c_addrs}`，`i2c_addrs` 為 0–127 整數陣列；兩通道時間軸 `np.array_equal`（整條）且有限、嚴格遞增（只驗一次）。違反 → `BadRequest`（在 job 內 → job 事件 BAD_REQUEST；頂層缺鍵由 server 同步回）。
- **work**：**一開始在鎖內把 `_dec` 清成 None**（所以任何失敗——具名失敗、BAD_REQUEST、例外——之後舊 id 一律 STALE）。`to_edges`×2 → 任一線自動門檻 `None` 或邊沿數 0 → **具名失敗**（手動門檻超出訊號也走這條，統一語義），回完整 `DecodeSummary`：
  `{ok:false, reason:"SDA 無轉態（門檻 lo～hi）", gen, decode_id:null, protocol:"i3c", channels, thresholds:{scl:[lo,hi]|null, sda:…}, t0:null, t1:null, counts:{frames:0,fields:0,errors:0,warns:0}, truncated:false, warnings:[]}`。
  成功 → 狀態機 → **同一把鎖內** `self._alive(gen)` 後寫 `self._dec = {id, gen, frames, bits_t, bits_v, addresses, meta}`；寫入後不再修改（同步方法取參照即為不可變快照）。`meta` 在此固定（來源檔路徑、通道、門檻、options、解碼時間），匯出用它，不再讀當下 `_path`。
- **同步三方法**：先驗參數型別（`decode_id` 字串、`t0/t1` 有限數、`directory` 字串或 null，否則 BAD_REQUEST），再**在鎖內**檢查 `_dec` 存在、`id` 相符、`_dec.gen == self._gen`，取出參照後出鎖處理；不符 → STALE。
- `decode_id` 用模組層 `itertools.count`（`d1, d2…`，換檔不重用，同 `_SPEC_IDS`）。
- 時間一律 **SCL 通道來源時間**（不套 dx）；前端顯示時加 SCL 的 `time_offset`。
- **`decode_frames`**：回 `{decode_id, frames, addresses}`。
- **`decode_bits`**：`t0`、`t1` 有限（否則 BAD_REQUEST）、反序則交換、兩端含；`searchsorted` 二分取區間，依時間遞增，含所有被取樣的 bit（header、ACK、T、DAA 64 bit 皆含）；>4096 回前 4096＋`truncated:true`。
- **`export_decode`**：`timestamped(dir, f"{stem}_解碼", "csv")`，`utf-8-sig`，`dir=null`＝`meta` 的來源檔資料夾；寫入失敗 → `ScopeError`。內容：meta 列 → 空行 → 表頭 `frame#, 種類, 起(s), 迄(s), 位址, RnW, ACK, CCC, 狀態, 原因, 說明, field#, 欄位, 值(hex), 位元數, 第9位, 第9位意義, field狀態, field說明` → **每個 field 一列；沒有 field 的 frame（partial、hdr、hdr_exit、target_reset、pattern）也輸出一列**（field 欄空白）→ 空行 → 位址表（`DA, PID, BCR, DCR, static, 起, 迄, 來源, 備註`）。時間用 `repr(float)`（同量測 CSV）。

---

## 4. API 契約追加（`api_contract.json`＋`docs/web-api契約.md`，`version` 維持 2）

| 方法 | J | 參數（全部 required；nullable 註明） | 回傳 |
|---|---|---|---|
| `decode` | ✔ | `protocol: str`（目前只有 `"i3c"`）、`channels: map<str>`（I3C：`{scl, sda}`）、`thresholds: map<[float,float]|null>`（鍵同 channels；`null`＝自動）、`options: object`（I3C：`{i2c_addrs?: int[]}`） | `DecodeSummary` |
| `decode_frames` |  | `decode_id: str` | `DecodeFrames` |
| `decode_bits` |  | `decode_id: str`、`t0: float`、`t1: float`（SCL 來源時間，可反序） | `DecodeBits` |
| `export_decode` |  | `decode_id: str`、`directory: str`（nullable） | `PathResult` |

型別（`types`；欄位型別一律字串）：
```
DecodeSummary = {ok:"bool", reason:"str|null", gen:"int", decode_id:"str|null", protocol:"str",
                 channels:"map<str>", thresholds:"map<[float,float]|null>",
                 t0:"float|null", t1:"float|null", counts:"DecodeCounts", truncated:"bool", warnings:"str[]"}
DecodeCounts  = {frames:"int", fields:"int", errors:"int", warns:"int"}
DecodeFrames  = {decode_id:"str", frames:"DecodeFrame[]", addresses:"AddrEntry[]"}
DecodeFrame   = {i:"int", t0:"float", t1:"float", kind:"str", start:"str|null", addr:"int|null", rw:"int|null",
                 ack:"bool|null", ccc:"int|null", ccc_name:"str|null", label:"str",
                 status:"str", reasons:"str[]", fields:"DecodeField[]"}
DecodeField   = {t0:"float", t1:"float", kind:"str", addr:"int|null", value:"int|null", nbits:"int",
                 ninth:"int|null", ninth_kind:"str|null", ok:"bool", label:"str"}
AddrEntry     = {da:"int", pid:"int|null", bcr:"int|null", dcr:"int|null", static:"int|null",
                 t_from:"float|null", t_to:"float|null", how:"str", note:"str|null"}
DecodeBits    = {bits:"[float,int][]", truncated:"bool"}
```
（`DecodeField.addr`＝該 field 所屬 Direct 子段的目標位址，非子段 field 為 null。`thresholds` 回實際使用值（自動估出的或手動的）；某線自動估計失敗時該線為 null。是否自動由前端自己的設定得知，不另回 `auto`。失敗時完整樣本見 §3.3，`counts` 四欄必填為 0。）

列舉（寫進 `types_doc`）：
- `DecodeFrame.kind`：`private_write private_read ccc_broadcast ccc_direct daa ibi hotjoin i2c hdr hdr_exit target_reset pattern partial error`；`start`：`S Sr null`
- `DecodeField.kind`：`addr ccc def data mdb pid bcr dcr da`；`ninth_kind`：`ack parity tbit null`
- `status`：`ok warn error`
- `reasons`：`parity t_bit addr_parity addr_7e_read nack ccc_unknown ccc_invalid ccc_format type_unknown ibi_unexpected_payload addr_conflict pattern_incomplete pattern_unknown truncated ambiguous_edge`
- `AddrEntry.how`：`ENTDAA SETDASA SETNEWDA observed`；`t_from=null`＝擷取前即存在（未知）

錯誤：
- 頂層缺／多鍵 → 同步 `BAD_REQUEST`（server 既有）。內容錯（§3.3 清單）→ job 內 `BAD_REQUEST`。
- 自動門檻失敗、無轉態 → 具名失敗 `ok=false`（不是錯誤碼）。
- `decode_frames`／`decode_bits`／`export_decode` 的 `decode_id` 不是目前 `_dec`（含換檔、關檔、重新解碼、上次解碼失敗）→ `STALE`。
- job 完成時 `_alive(gen)` 失敗 → `STALE`（既有）。

mock（`mock_backend.js`，L0）：`KEYS` 加四方法；`decode` 驗頂層鍵與 `channels` 鍵；回固定小結果（摘要＋`decode_frames` 回 3 frames：一筆 CCC、一筆含 parity error 的 private write、一筆 IBI；`decode_bits` 回 9 bit；`export_decode` 回假路徑；id 不符回 STALE）。260 行追加後須 ≤300，超過就把固定資料放新檔 `mock_decode.js`（L0）。**`l0_sem.mjs` 以 `call()` 實際呼叫四方法**（成功、BAD_REQUEST、STALE），型別由 `tc` 驗。

---

## 5. 前端設計

### 5.1 狀態與執行（`static/js/analysis/decode.js`，L5，新）
- store 鍵：`decodeResult`（`{summary, frames, addresses, scl, stale}` 或 null；`scl`＝解碼時的 SCL 通道名；`stale`＝解碼後設定已變更，由 decode.js 寫，表格與報告共用此判據）、`decodeSel`（frame `i` 或 null）、`plotRect`（`{l, w}`，由主圖寫）。
- 設定（只存記憶體）：`{scl, sda, thr:{scl:null|[lo,hi], sda:…}, i2c:[…], band:true}`；預設 SCL／SDA＝前兩個原始通道。
- **觸發＝手動**（「解碼」按鈕，Q4）：`bridge.job("decode")` → `ok` 時 `bridge.call("decode_frames")` → 寫 `decodeResult`。token 在**按下解碼、設定變更、換／關檔時**都遞增；回來的結果 token 不符或 `summary.gen !== file.gen` 一律丟棄。設定變更後既有結果標「設定已變更，請重新解碼」（不自動重算：千萬點要數秒且單一分析執行緒會擋量測）。
- 換檔／關檔（`file.gen` 變）→ `decodeResult=null, decodeSel=null`（自己監聽 `file`，不改 `openPatch`／`closeFile`）。
- 原因碼→中文對照表放這裡（`parity`→「同位錯」…），涵蓋契約列舉全部值。

### 5.2 B 區「解碼」分頁（`decode_table.js`，L5，新）
- `bpanel.js`：`TABS` 加 `'decode'`、標籤「解碼」；`mountTabs` 回傳物件加 `label(key, text)`，由 `decode_table` 更新為 `解碼 (N)`（不動 `resultTabs.update(...)` 那行）。缺 decode panel 的舊測試宿主照舊略過。
- `tab_analysis.js`：lowerbody 加 `<div class="analysis__decode"></div>`，傳進 `mountTabs` panels，並 mount `decode_table`。
- 分頁內容（由上而下）：
  1. 設定列（一行，`overflow-x:auto` 不換行）：`SCL[CH▼] SDA[CH▼] 門檻[自動｜手動] SCL lo/hi SDA lo/hi I2C位址[  ] [解碼] [匯出 CSV] ☐標註列`。手動欄用 `fmt.parseSI`；結果回來後自動欄以灰字顯示實際門檻。I2C 位址輸入 hex，逗號分隔。
  2. 摘要：`N 筆｜錯誤 E｜警告 W｜門檻…｜warnings`；`truncated` 顯示上限提示；解碼中顯示「解碼中…（量測／FFT 會等候）」。
  3. 篩選：`全部｜只錯誤／警告`（預設全部）。
  4. 事件表（`.table .table--num .results__table`）：`# ｜ 時間 ｜ 類型 ｜ 位址 ｜ R/W ｜ 內容 ｜ 狀態`。內容＝CCC 名／bytes hex（錯誤 byte 前加 ⚠）／PID 等；狀態＝原因中文。**最多渲染 2000 列**，腳註「僅顯示前 2000 筆，匯出 CSV 含全部」。`# ponytail: 不做虛擬捲動`。
  5. `<details>` 位址表：`DA ｜ PID ｜ BCR ｜ DCR ｜ 起 ｜ 迄 ｜ 來源 ｜ 備註`；`t_from=null` 顯示「未知（擷取前）」、`pid=null` 顯示「—」、observed 標「觀察到（未確認）」。
- 點列（或 Enter）：`decodeSel=i`；發 `viewport.intent`（`jumpView`）：frame 長度 ≤ 目前 span 的 80% → 保持 span、以 frame 中心置中；否則 span＝長度×1.25；時間加 SCL `time_offset`。選中列 `tr.is-selected`。
- 匯出 CSV：`bridge.call("export_decode", {decode_id, directory:null})`；STALE → toast「解碼結果已過期，請重新解碼」。

### 5.3 標註列（`decode_band.js`，L4，新）
- 位置：`.analysis__main` 正下方新元素 `.analysis__decodeband`（`tab_analysis.js` 骨架一行），**CSS 固定高 40 px**（兩列各 18＋間隔），常數 `BAND_H=40` 與 CSS 一致（`decode_check` 比對）。顯示條件：`decodeResult?.summary.ok && band`，且窄版分頁切到 FFT 時隱藏。
- 版面：`renderLayout` 的 `const chrome = …+28` 改為 `…+28+(band 顯示 ? BAND_H : 0)`；`store.on(['decodeResult'])` 與 band 開關時呼叫 `schedule()`。`effective = clampLayout(...)`、`resultTabs.update(...)` 兩行原文不改。
- **X 對齊**：`mainplot.js draw()` 算出 rect 後，`store.set({ plotRect: { l: rect.l, w: rect.w } }, "program")`（淺比較，同值不通知）；標註列用 `linear(view.t0, view.t1, l, l+w)`。初始 `plotRect` 未設時用 `MARGIN.l`。
- 繪製（`createCanvas`；色取 `cssVar`：`--c-ok --c-warn --c-danger --c-accent --c-plot-text --c-plot-bg`）：
  - 上列 frame：依 status 上色的長條，寬 ≥40 px 寫 label（裁字），<2 px 的相鄰 frame 合併成一條。
  - 下列 field：寬 ≥24 px 寫 hex，第 9 bit 小標（`A`／`N`／`T1`／`T0`／`P✓`／`P✗`）。
  - 畫面內 bit 間距（field 寬÷nbits）≥10 px 時，`bridge.call("decode_bits")` 取畫面範圍（顯示時間扣 SCL dx 換成來源時間），debounce 150 ms，`makeLatest` 丟棄過期回應（RPC 本身無法中止）；結果以 `[t0,t1,decode_id]` 快取；下列改畫每個 bit 的 0／1 與取樣刻度。
  - 選中 frame 白框；點長條 → `decodeSel=i`，表格捲到該列。滾輪／拖曳不處理。
  - 只畫與 view 相交的 frame：frames 互不重疊且依 `t0` 排序，`t1` 也單調，可二分找第一個 `t1 ≥ v.t0`。
  - view、SCL `time_offset`、`plotRect`、`decodeResult`、`decodeSel` 變動皆重畫。

### 5.4 報告（`report.js`，L5）
`collectReport` 在 FFT section 之前加解碼 section，**條件**：`decodeResult?.summary.ok`、`summary.gen === file.gen`、`!decodeResult.stale`。內容：`{ title:'解碼（I3C）', img: snapshot(標註列 canvas, invert), caption: 通道＋門檻＋篩選＋「表格最多 2000 列」＋截斷說明, tables:[tableData(事件表), tableData(位址表)] }`。標註列隱藏時 img 為 null（只有表）。
- **await 競態**：`collectReport` 開頭記下 `decodeResult` 參照；`exportReport` 在 `buildReport` 之後、送 RPC 之前，再比一次 `file.gen` 與 `decodeResult` 參照（不同 → toast「解碼結果已變更，請重新匯出」）。
- **大小**：事件表「內容」欄超過 64 字元截斷加「…」（畫面同樣截斷，title 放全文）；位址表最多 256 列。`report_check` 以最壞資料（2000 列滿 64 字元＋256 列位址表＋1400×40 標註列 PNG）組完整 `export_report` 請求，`new TextEncoder().encode(JSON.stringify(body)).length < 8 MB`。

### 5.5 樣式
`analysis.css` 檔尾新增 `.analysis__decodeband{flex:0 0 auto;height:40px;background:var(--c-plot-bg)}`、`.decode__bar{display:flex;gap:var(--sp-2);overflow-x:auto;white-space:nowrap}`、`.decode__sum`。不改原有行、不改 glass.css；B 區頁籤沿用 `.analysis__resultTabs` 既有選中樣式；表格用既有 `.table` 樣式（深色＋選中列已處理）。

---

## 6. 檔案清單

| 檔案（lane） | 改什麼 |
|---|---|
| `web/logic.py`（L1b，**新**） | §3.1；`__main__` 自檢（遲滯、NaN 打斷、resync、分塊邊界、內插時間） |
| `web/i3c_ccc.py`（L1b，**新**） | CCC 表、payload label、位址表更新；`__main__` 自檢表格一致性 |
| `web/i3c_decode.py`（L1b，**新**） | §3.2 狀態機；`__main__` 跑手寫真值向量 H1–H3 |
| `web/i3c_synth.py`（L1b，**新**） | §7.1 產生器；`__main__` 自檢（仲裁、渲染） |
| `web/i3c_check.py`（L1b，**新**） | §7.2 全部向量、變異、效能；印 `web.i3c_check self-check OK` |
| `web/analysis_decode.py`（L1b，**新**） | `DecodeMixin`；`__main__` 自檢參數驗證、STALE、CSV |
| `web/analysis_api.py`（L1b） | 三行（import、基底、`_reset`），≤300 行 |
| `static/api_contract.json`、`docs/web-api契約.md`、`static/js/mock_backend.js`（可能加 `mock_decode.js`）、`static/js/l0_sem.mjs`（L0） | §4 |
| `web/e2e_check.py`（L8） | HTTP：decode→decode_frames→decode_bits→export_decode；頂層缺鍵同步 BAD_REQUEST、巢狀錯誤 job BAD_REQUEST；換檔後三方法 STALE；失敗解碼後舊 id STALE；以約 100k fields 的結果量 `decode_frames` HTTP 往返時間與回應位元組數（印出、寫進 HANDOFF） |
| `static/js/analysis/decode.js`（L5，**新**） | §5.1 |
| `static/js/analysis/decode_table.js`（L5，**新**） | §5.2 |
| `static/js/analysis/decode_band.js`（L4，**新**） | §5.3 |
| `static/js/analysis/bpanel.js`（L5） | `TABS`、按鈕定義、`label()` |
| `static/js/analysis/tab_analysis.js`（L4） | 骨架兩個元素、mount band／table、panels 加 decode、`chrome` 加 band 高、`decodeResult` 觸發 schedule、窄版 FFT 分頁隱藏 band |
| `static/js/analysis/mainplot.js`（L4） | `draw()` 寫 `plotRect`（一行） |
| `static/js/analysis/report.js`（L5） | 解碼 section |
| `static/css/analysis.css`（L4） | 檔尾新 class |
| `static/js/analysis/decode_check.mjs`（L8，**新**）＋`selfcheck_node.js` FILES | §9 |
| `web/browser_decode_checks.py`（L8，**新**）＋`browser_check.py` | §9；`browser_check.py` 已 300 行：把一段既有完整步驟（如 NaN CSV 三行）搬進 helper 再加一行 step，維持 ≤300 |
| `docs/離線分析功能規格.md` | 新增「I3C 解碼」節：門檻／遲滯、位元取樣、T 語意與視窗、位址類型規則、IBI 判讀、CCC 分類、pattern 規則、限制（RULES 第 11 條） |
| `RULES.md`、`HANDOFF.md`、`docs/web版驗收清單.md`、`docs/真機驗證清單.md` | lane 登記、授權段、現況、真人／實測待驗項（與示波器內建 I3C 解碼比對） |

---

## 7. 合成波形產生器與測試向量

### 7.1 `web/i3c_synth.py`
- **符號層**產生理想轉換序列 `[(t, line, level)]`＋真值 frames；**類比層**渲染成取樣。
- 符號層 API（串接成一段匯流排）：
  `idle(sec) / start() / rstart() / stop() / header(addr, rw, ack) / byte_w(v, t=None) / byte_r(v, t, abort=False) / ccc(code, defbyte=None, payload=(), targets=()) / entdaa(rounds) / ibi(da, payload, ack) / hotjoin(ack) / hdr(mode, n_toggles, seed) / hdr_exit(stop=True) / target_reset(sr=True, stop=True) / i2c(addr, rw, data, acks) / raw(transitions)`
  - `byte_w(v, t=None)`：t=None 用正確奇同位，可指定錯誤 T。
  - `byte_r(..., abort=True)`：T=1，並在 **T 的 SCL 高期間把 SDA 拉低**（真正的 Controller 提前結束），之後接 header 或 STOP。
  - 時序：`f_pp=12.5e6`、`f_od=2.5e6`（首個 7E header 與 DAA 用 OD 速率）、duty 50%、資料在 SCL 低期間中點變化。
  - **DAA 仲裁**：逐 bit 維護「仍參與」的 Target 集合；每 bit 線上值＝參與者送出值的 AND；送 1 讀到 0 的 Target 自該 bit 起退出（不再參與後面 bit）。勝出者得 DA，落敗者下一回合再競爭。真值記每回合勝出者。
- **類比層** `render(trans, fs, vdd=1.8, tr=2e-9, noise=0.02, seed, nan=())`：每樣本以「最後一次轉換」做一階 RC 趨近 `v=prev+(new−prev)(1−e^{−Δt/τ})`（τ=tr/2.2；用 `searchsorted` 向量化）；高斯雜訊 σ＝noise×vdd；可插 NaN 段；輸出 `(t, scl, sda)` 與可寫 CSV（`Time(s),CH1(V),CH2(V)`）的函式。
- **獨立性**：產生器只依本文件線上格式寫、不 import 解碼器；真值來自產生器輸入。另有 3 組 **手寫真值**（不經 synth 的 byte／DAA 輔助函式，直接逐 bit 寫轉換清單，依研究 §3.3／§3.6 的格式與 Microchip DAA／T-bit 流程圖）：H1＝`S 7E/W ACK Sr 08/W ACK A5+T P`；H2＝一回合 ENTDAA（PID=0x0123456789AB、BCR=0x06、DCR=0x44、DA=0x08）；H3＝private read 2 byte、第 2 byte T=1 後 Controller 拉低提前結束再 STOP。

### 7.2 測試向量（`i3c_check.py`）
每項斷言 frames 的 `kind／start／addr／rw／ack／ccc／fields(kind,value,nbits,ninth,ok)／status／reasons` 與真值完全一致，時間誤差 ≤2 個取樣週期；並斷言 frames 不重疊、依時間排序。

| # | 向量 | 預期 |
|---|---|---|
| H1–H3 | 手寫真值（§7.1） | 完全一致 |
| 1 | `S 7E/W(OD) Sr DA/W` 3 byte，同位正確 | 一筆 `private_write`，首 field「7E 開場」；ok |
| 2 | 同上，第 2 byte T 錯 | 該 field `parity`，frame `error`，其餘 ok |
| 3 | Private read 3 byte，T=1,1,0 後 P | ok |
| 4 | Private read，第 2 byte T=1 後 Controller 在 T 高期間拉低 | ok，label「Controller 提前結束」，後續 header 正確解出 |
| 5 | T=0 後 Controller 又送 8 個時脈 | `t_bit`、error |
| 6 | 位址 NACK（private write） | `ack=false`、warn、`nack` |
| 7 | Broadcast ENEC(0x00)+mask、RSTDAA(0x06)、SETMWL(0x09)+2 byte；SETMWL 只給 1 byte | 名稱與值正確；RSTDAA 使表項 `t_to`；1 byte 那筆 `ccc_format` |
| 8 | Direct GETPID(0x8D) 對兩個 DA（一個 ACK、一個 NACK）、GETBCR、GETDCR | 子段各自方向／ACK 正確；PID／BCR／DCR 填入表 |
| 9 | Direct RSTACT(0x9A) Defining Byte 0x01；RSTACT 無 Defining Byte；GETBCR 帶多餘 Defining Byte | 第一筆 def 名稱正確；後兩筆 `ccc_format` |
| 10 | SETDASA(0x87) 對 static 0x50 給 0x10（DA 0x08）；SETNEWDA(0x88) 0x08→0x09；SETDASA 給 0x11（bit0=1、T 正確） | 前兩筆更新表；第三筆 `ccc_format`、表不變 |
| 11 | Direct RSTDAA 0x86 | `ccc_invalid`、warn |
| 12 | 未知 CCC 0x5A＋2 byte | `ccc_name=null`、`ccc_unknown`、byte raw |
| 13 | ENTDAA 兩 Target，PID 從第一 bit 就不同（`0…` vs `1…`），另一組只在 BCR 最後 bit 不同 | 兩組都：第一回合勝出者 PID 正確（不是 AND 結果之外的值）、第二回合落敗者；最後 7E/R NACK 為正常結束（ok、無 `nack`） |
| 14 | ENTDAA DA parity 錯 → Target NACK | 該回合 `addr_parity`、error、不入表 |
| 15 | IBI，DA 的 BCR[2]=1（DAA 已見）MDB＋2 byte | `ibi`，fields `addr, mdb, data, data` |
| 16 | IBI，BCR[2]=0、BCR[1]=1 | `ibi` 無 payload |
| 17 | IBI，BCR=0x06 vs 0x02（只差 bit2）各一 | 分別有／無 MDB（驗不是看 bit1） |
| 18 | IBI 於 BCR 未知的 DA，帶 1 byte | `data`、label「BCR 未知」 |
| 19 | IBI NACK | `ack=false`、warn、`nack` |
| 20 | Hot-Join ACK → 稍後 ENTDAA 指派新 DA；Hot-Join NACK 後仍出現 ENTDAA；兩個 Target 同時 HJ（線上相同）後 DAA 兩回合 | `hotjoin` 獨立 frame、不建表項；DAA 正常建表 |
| 21 | ENTHDR0＋HDR 段（亂數翻轉）＋HDR Exit | 一筆 `hdr`（`t1`＝`hdr_exit.t0`）＋`hdr_exit`；區段內無其他 frame；不重疊 |
| 22 | Target Reset（14 轉換＋Sr＋P） | 一筆 `target_reset`，**沒有** `hdr_exit`（前綴重疊）；位址表項 `t_to`＝STOP、note |
| 22b | 前一 bit 為 T=0（SDA 低）後 SCL 低期間先 setup 上升再送 14 轉換 | 仍判 `target_reset`（setup 上升不計入，非 15 次） |
| 22c | Exit 4 次下降後 SDA 又升高才拉 SCL（尾段不符） | 不判 `hdr_exit`，`pattern_unknown` |
| 22d | Private write 進行中插入 Reset pattern | 該 write `truncated`，之後 `target_reset` |
| 23 | Reset pattern 缺 Sr／缺 P；擷取停在 SCL 低期間（k=5） | `pattern_incomplete`；最後者 `kind=pattern` |
| 24 | SDR 中出現 Exit（無 ENTHDR）；k=3 的 pattern | `hdr_exit`（label「未見 ENTHDR」）；`pattern_unknown` |
| 25 | I2C legacy write 2 byte、read 3 byte（ACK,ACK,NACK），位址在 `i2c_addrs` | `i2c`；讀最後 NACK 正常 |
| 26 | 同一 I2C 交易但 `i2c_addrs=[]` | 依 I3C 解讀、`type_unknown`；寫入 9th bit 不符同位時報 `parity`（使用者可加入清單） |
| 27 | 未知位址 private write `0x00,T=0`（I3C parity 錯，也像 I2C ACK） | `parity`＋`type_unknown`；之後同位址交易仍是 `type_unknown`（observed 不升格） |
| 28 | 擷取中途開始（切掉一筆 write 前 37%） | 第一筆 `partial`；之後正常；表中無捏造項；用到的 DA 為 `observed`、`t_from=null` |
| 29 | 雜訊 σ=5% vdd、tr=3 ns、1 GSa/s，20 seed | 與無雜訊完全相同 |
| 30 | 取樣不足（40 MSa/s 對 12.5 MHz） | `warnings` 含「取樣不足」；不崩潰 |
| 31 | 手動門檻高於訊號高位；SDA 全平；SDA 全 NaN／含 Inf | 三者皆 `ok=false`、reason 指出哪一線；`_dec` 為 None |
| 32 | 中間插 1 µs NaN | NaN 前 frame `truncated`；NaN 後重新同步；resync 不產生 START |
| 33 | 邊沿恰在 `CHUNK` 邊界（構造 4M±1 點處翻轉） | 與不分塊結果相同 |
| 34 | 兩線同一樣本翻轉（低 fs） | 不崩潰；`ambiguous_edge` |
| 35 | 兩通道時間軸中間某點不同；時間非遞增 | BAD_REQUEST |
| 36 | 長 idle（99% 時間為高）＋稀疏交易；以及週期恰為抽樣步距倍數的方波 | 自動門檻在 top／base 之間，解碼正確（後者驗隨機抽樣不 alias） |
| 37 | 上限：以參數把 `MAX_FIELDS`、`MAX_FRAMES` 各調小（如 500）再構造超量流量 | 各自觸發 `truncated=true`、數量 ≤ 上限、`warnings` 有截止時間；另以預設上限構造 100k fields 印 `json.dumps` 大小 |
| 38 | 效能：10M 點×2、約 2 萬 byte | 印耗時；斷言耗時 ≤15 s（目標 ≤5 s）；機器型號與數字寫進 HANDOFF |
| 39 | 高轉態密度：以參數把 `MAX_EDGES` 調小（如 1M）、SDA 每 2 點翻轉 | `MAX_EDGES` 生效、兩線截止於同一時間、不崩潰 |
| 40 | 記憶體：獨立子程序各跑一次 10M 檔解碼與 5 次連續解碼 | 印各自峰值 RSS（平台單位換算成 MB）；只記錄、不設比例硬斷言；數字寫進 HANDOFF |

**變異（後端）**：為了可替換，`i3c_decode.py` 把四個判定寫成模組層小函式：`parity_ok(v, t)`、`da_par(da)`、`classify_pattern(start_high, k, n, end_sda)`、`read_t_end(t, sda_fell, sda_rose)`。`i3c_check --mutations` 以 monkeypatch 把奇同位改偶同位、PAR 取反、pattern 改成「k≥4 即 Exit」、T 視窗忽略 SDA 下降，各自必須讓上表至少一項失敗。另有不靠 monkeypatch 的獨立反例：向量 13（仲裁）、22b（setup）、21（HDR 邊界）。

`analysis_decode` 自檢：`decode_bits` 在 1 byte 範圍回 9 bit 且值等於 field；端點含、反序交換、非有限 BAD_REQUEST、>4096 `truncated`；解碼失敗後舊 id STALE；換檔後 STALE；CSV 列數＝fields 數＋無 field 的 frame 數＋meta＋位址表；匯出用解碼當時的檔名（換檔後舊 id 已 STALE，不會寫錯檔名）。

---

## 8. 分階段（每階段可獨立驗收、獨立 commit）

共同驗證：
```
QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.<模組>
node scope_tool/web/static/js/selfcheck_node.js
QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.e2e_check      # Claude 在沙箱外跑
QT_QPA_PLATFORM=offscreen /opt/anaconda3/bin/python3 -B -m scope_tool.web.browser_check  # Claude 在沙箱外跑
```

### P1 解碼核心（純後端，無契約、無 UI）
做：`logic.py`、`i3c_ccc.py`、`i3c_decode.py`、`i3c_synth.py`、`i3c_check.py`；`docs/離線分析功能規格.md` I3C 節。
驗收：`web.logic`、`web.i3c_ccc`、`web.i3c_decode`、`web.i3c_synth`、`web.i3c_check`（含 `--mutations`）印 OK；§7.2 H1–H3、1–40 全過；效能數字印出。既有檔未動。

### P2 契約＋Analysis 接線（無 UI）
做：§4 契約兩檔＋mock＋`l0_sem.mjs`；`analysis_decode.py`；`analysis_api.py` 三行；`e2e_check.py`；RULES／HANDOFF 登記。
驗收：`web.analysis_api`（含 analysis_check）、`web.analysis_decode` OK；`selfcheck_node.js`（l0 契約／mock 鍵與 `call()` 型別）通過；`e2e_check` 全項通過；畫面無變化。

### P3 B 區「解碼」分頁＋CSV
做：`decode.js`、`decode_table.js`、`bpanel.js`、`tab_analysis.js`（panel）、`analysis.css` 檔尾；`decode_check.mjs`；`browser_decode_checks.py`（分頁部分）；`browser_check.py` 一行。
驗收：§9 P3 項全過。

### P4 標註列＋bit 展開＋報告
做：`decode_band.js`、`mainplot.js`、`tab_analysis.js`（band）、`report.js`；`decode_check.mjs`／`report_check.mjs`／`browser_decode_checks.py` 追加；HANDOFF／驗收清單／真機驗證清單。
驗收：§9 P4 項全過。

順序 P1 → P2 → P3 → P4；P1 後可先讓使用者看 `i3c_check` 輸出再決定是否繼續。

---

## 9. 驗收檢查（新增項目與可量化通過條件）

**`decode_check.mjs`（L8，加進 `selfcheck_node.js` FILES）**——產品純函式＋假 DOM：
- 原因碼對照覆蓋契約 `reasons` 列舉全部值（讀 `api_contract.json` 的 `types_doc` 比對，缺一即紅）。
- `jumpView`：短 frame 保持 span、中心誤差 <1e-9·span；長 frame span＝1.25×長度；加 SCL dx。
- `visibleFrames` 二分結果與暴力過濾相同（1000 筆隨機、含跨視窗左緣的長 frame）。
- `bandLayout`：<2 px 合併；label 只在 ≥40 px；bit 模式只在 bit 間距 ≥10 px；`BAND_H` 等於 `analysis.css` 的 `.analysis__decodeband` height。
- runner（假 bridge）：token 過期結果不寫 store；設定變更後回來的舊結果被丟棄；`file.gen` 改變清 `decodeResult`；設定變更只標 stale、不發 job（`bridge.calls` 計數不變）；`ok=false` 時不呼叫 `decode_frames`。
- 表格：2000 列上限與腳註；「只錯誤／警告」列數正確；點列發一次 `viewport.intent`；`label()` 更新頁籤文字。
- bpanel：缺 decode panel 時 mountTabs 不崩潰；持久化 `tab:'decode'` 可還原；浮動與右停靠下 decode 分頁可見。
- 報告：無結果、gen 不符、設定已變更三種情況下 `collectReport` 不含解碼 section；2000 列假資料的 HTML < 8 MB。
- 變異（`--mutations`）：`jumpView` 置中、`visibleFrames` 邊界、token 比對各改一處應失敗。

**`browser_decode_checks.py`（L8）**——以 `i3c_synth` 產生 2 通道 CSV（約 20 萬點，含向量 1、2、4、13、15、22、28）：
- P3：開檔 → 「解碼」分頁 → SCL=CH1、SDA=CH2 → 解碼 → 等 `decodeResult.summary.ok`；表格列數＝frames 數；parity 錯那列狀態欄含「同位錯」；點第 k 列後 view 中心與 frame 中心（加 dx）差 <1% span；匯出 CSV 路徑存在、列數符合；1400×900 下 `.analysis__toolbar` 高度＝本案前基線、B 區標題列高度＝基線（不換行）、`documentElement.scrollWidth ≤ clientWidth`；1000×800 下設定列可橫捲不撐寬頁面；console 無錯誤。
- P4：標註列 canvas 有墨（非背景像素 >100）；`|plotRect.l − 標註列實際繪製左緣| ≤1 px`；1400×900 主圖高度 ≥270 px；放大到單一 byte 時 `decode_bits` 被呼叫且下列畫出 9 個 bit；點標註列 frame → 表格該列 `is-selected`；匯出 HTML 報告含「解碼（I3C）」與事件表；5000 frames 下單次 `draw()` <30 ms（`performance.now()`，headless Chrome）；截圖 `decode_1400.png`、`decode_1000.png`。

**既有檢查不得退步**：`selfcheck_node.js`（含 `--mutations`，既知 p2b3 M2 例外除外）、`e2e_check`、`browser_check` 全綠；`float_check` 綁的兩行原文不變；`analysis_check` 結果不變。

---

## 10. 風險

| 風險 | 處置 |
|---|---|
| **只有合成波形**，產生器與解碼器可能同樣誤解規格 | 手寫真值 H1–H3 依官方流程圖；Codex 審協定；HANDOFF／真機驗證清單標「未經實測／原廠解碼比對」；取得實測後先比對示波器內建 I3C 解碼 |
| 研究的 CCC 表是常用子集、Basic v1.2 全文未逐條核對 | 分「解讀／raw／不合法／未知」四類；未知不擅自命名；規格文件註明版本來源 |
| S＋DA/R 無法分辨 IBI 與 Controller 直接讀 | 一律 kind `ibi` 但 label 註明；MDB 只在 BCR 已知時標 |
| CRR（Target 以 DA/W 請求）與 Private write 無法分辨 | 不做 CRR，列已知限制 |
| 擷取中途開始時位址類型未知，I2C 交易可能被報 parity | `type_unknown` 提示＋I2C 位址清單；不做會自我強化的猜測 |
| Exit／Reset 只驗形狀不驗時序 | label 註明；`tDIG_H` 待規範確認 |
| Python 狀態機在 100M 點忙碌匯流排上慢 | 邊沿向量化、分塊、`MAX_EDGES`；向量 38／39 量測；`# ponytail: 狀態機純 Python；邊沿 >5M 時考慮 numpy 化位元取樣` |
| 單一分析執行緒：解碼期間量測／FFT 排隊 | 手動觸發＋畫面提示；`jobs.py` 不動 |
| 結果保留在事件環／去重表 | job 只回摘要；frames 走同步 RPC；向量 40 驗重複解碼 RSS |
| 300 行上限 | 新檔分工；`analysis_api.py` 299、`browser_check.py` 搬 helper |
| `float_check`／`p2b*` 綁原文 | 不改 `effective = clampLayout(...)`、`resultTabs.update(...)` 兩行與 `layout.js` |
| 產品常數（`HYST`、上限、2000 列、4096 bit） | 具名常數；門檻可手動覆寫 |

---

## 11. 需要使用者決定的事項（附建議預設）

> 2026-10-26 使用者：全部照建議預設。

| # | 問題 | 建議預設 |
|---|---|---|
| Q1 | 契約追加 4 方法＋型別，`version` 維持 2，可以嗎？ | **可以**（同 rbw 先例） |
| Q2 | START 後直接 `DA/R` 一律標 IBI（註明可能是 Controller 直接讀），可以嗎？ | **可以**；MDB 只在 BCR 已知時標 |
| Q3 | 未在擷取中確認的位址一律依 I3C 解讀並標「類型未確認」，I2C 裝置由使用者在分頁填位址清單，可以嗎？ | **可以**（不做自動猜測：會把 I3C parity 錯誤誤認成 I2C） |
| Q4 | 自動或手動觸發解碼？ | **手動按鈕**；設定／檔案變更只標「請重新解碼」 |
| Q5 | 解碼範圍：整檔，或跟量測共用游標區間？ | **整檔**（位址表需要前文） |
| Q6 | SCL／SDA 的 dx（time_offset）要不要當 deskew 用於解碼？ | **不用**：解碼用來源時間，標註列跟 SCL 的 dx 走；deskew 需求出現再加 |
| Q7 | 遲滯寬度 | **±10%（top−base）**，可手動覆寫 lo／hi |
| Q8 | 事件表與報告列數上限 | 表格與報告 **2000 列**，CSV 全部 |
| Q9 | Target Reset 後位址表怎麼處理？ | **結束所有有效項並註「有效性未知」**，之後該位址視為未確認 |
| Q10 | 標註列預設顯示？ | 有結果就顯示，分頁內可關 |

---

## 12. 明確不做（本案）

HDR 內容解碼（DDR／BT／TSP／TSL）、HDR Restart 辨識、CRR、多 lane、10-bit 位址、時序合規檢查（tSU／tHD／tDIG_H）、glitch 濾波、deskew、自動偵測 SCL／SDA 通道、解碼範圍＝游標區間、表格虛擬捲動、「只畫面內」篩選、示波器內建解碼命令。

---

## 13. Codex 討論紀錄

以 `codex exec --sandbox read-only` 審查兩輪（提示與輸出在 session scratchpad）。

### 第一輪（初稿；結論「不宜直接照做」）

| 意見 | 處理 |
|---|---|
| 讀取 T 不能只取一次樣再看後續 Sr／P；要定義 T 期間 Controller 拉低提前結束與 START／STOP 優先序，合成器要產生真正的拉低 | **採納**：§3.2.3 T 視窗；synth `byte_r(abort=True)`；向量 4、5、H3 |
| DAA 合成「兩份 64 bit 全程 wired-AND」錯，落敗者送 1 讀 0 即退出 | **採納**：§7.1 逐 bit 參與者集合；向量 13 兩種分歧位置 |
| ENTDAA 最後 7E/R NACK 是正常結束，不應 warn；要區分 header ACK 與 DA ACK | **採納**：§3.2.6 |
| BCR[2]＝IBI payload、BCR[1]＝IBI 能力；BCR 未知不得當無 payload 或斷定 MDB | **採納**：§3.2.2；向量 16–18 |
| SETDASA／SETNEWDA 的 DA 在 [7:1]、bit0 必須為 0 | **採納**：§3.2.5；向量 10 |
| CCC 表是常用子集；Direct RSTDAA 0x86 不合法；Defining Byte 要依表判必須／可選／禁止 | **採納**：四類分法、`def/defvals`；向量 9、11 |
| `7E/W` 後直接 Sr 是 private 開場，不是缺 code 的 CCC | **採納**：§3.2.2 |
| S＋位址/R→IBI 的順序吞掉 I2C read；第九位啟發式會把 I3C parity 錯當 I2C 且 observed 自我強化 | **採納**：刪啟發式，改 `options.i2c_addrs`（I2C 優先）＋未確認位址依 I3C 解讀標 `type_unknown`；observed 不算確認；向量 26、27 |
| HJ 與後續 DAA 要獨立；Target Reset 後表項有效性未知 | **採納**：向量 20；Q9 改為結束有效項並註記 |
| `counts` 內嵌物件 `tc()` 會拋錯 | **採納**：`DecodeCounts` |
| `_ok` 不遞迴驗具名物件；server 只驗頂層鍵 | **採納**：方法內明確驗；區分同步與 job 內 BAD_REQUEST |
| 漏 `mock_catalog.js`；`l0_check` 不會自動呼叫新方法 | **採納**：改為不動 catalog（protocol／roles 寫死），`l0_sem.mjs` 以 `call()` 呼叫四方法 |
| 大結果會被事件環 500／去重表 256 保留 | **採納**：job 只回摘要，frames 走同步 `decode_frames`（`bridge.call` 不帶 request_id） |
| STALE 生命週期、失敗後舊 id、匯出用解碼當時的檔名 | **採納**：§3.3 |
| `view.plotRect` command 不保存，band 晚掛載拿不到初值 | **採納**：改 store 鍵 `plotRect` |
| band 只改 `chrome` 不夠（結果出現、開關、窄版 FFT 分頁、dx） | **採納**：§5.3 |
| `resultTabs.update(...)` 加變數會讓 float_check 失敗 | **採納**：bpanel 加 `label()` 入口 |
| 報告要由有效結果判斷、不靠 DOM | **採納**：§5.4 |
| 時間軸只比長度與首尾不夠；resync 不是邊沿；`v[isfinite]` 複製整條 | **採納**：整條 `array_equal`；`resync` 旗標；平台估計抽樣 |
| edges／frames 上限、`decode_bits` 語義、frames 不重疊、CSV 遺失無 field 事件 | **採納**：§3.1、§3.2.9、§3.3 |
| 更多反例＋依官方流程圖的手寫真值；JS 變異驗不到 Python 公式 | **採納**：H1–H3、向量擴充、後端 `--mutations` |
| protocol registry／catalog roles 是單實作抽象 | **部分採納**：刪 registry 與 catalog；保留 `decode(protocol, channels, thresholds, options)` 形狀（使用者要求未來接 I2C／SPI 等，避免每加一個協定就改方法清單） |
| 「只畫面內」篩選延後 | **採納** |
| 保留 `decode_bits`、2000 列、手動觸發 | 同意，保留 |

### 第二輪（修訂稿；結論「多數已處理，尚有幾項會錯判」）

| 意見 | 處理 |
|---|---|
| 契約型別 `options: object`、`[float,int][]`、`map<[float,float]|null>` 經實測 `tc()`／`_ok()` 皆可；失敗 Summary 可成立但要列完整樣本 | **採納**：§3.3 完整失敗樣本 |
| 同步回數 MB JSON 可行（8 MB 是請求上限），但要量實際 HTTP 往返 | **採納**：e2e 量 100k fields 往返與位元組 |
| `plotRect` 由 store 淺比較擋住，不會迴圈 | 確認，不改 |
| Reset 計數窗含 setup 上升會變 15 次；Exit 應要求 SCL 升高時 SDA 為低 | **採納**：§3.2.7 計數窗；向量 22b、22c |
| `hdr.t1`＝Exit 結束與另一筆 `hdr_exit` 重疊；Reset 插入進行中 frame 未定義 | **採納**：`hdr.t1 = hdr_exit.t0`；進行中 frame 以 `truncated` 結束；向量 22d |
| 失敗清空、同步方法快照的 STALE 規則不完整 | **採納**：work 開頭鎖內清 `_dec`；同步方法鎖內驗 id＋gen |
| 抽樣要濾 Inf、等距抽樣會 alias；`decodeResult` 缺 stale 判據；報告 await 競態；2000 列不保證 <8 MB | **採納**：`isfinite`＋固定種子隨機抽樣；`decodeResult.stale`；送出前再比參照；內容欄 64 字截斷、位址表 256 列、最壞資料驗完整請求位元組 |
| 行數算法、上限測不到（10M 點只有 5M 邊沿）、MAX_FIELDS 未測、`ru_maxrss` 比例斷言不可靠、monkeypatch 需要接點 | **採納**：上限常數可參數覆寫供測試；RSS 改子程序量測只記錄；判定寫成模組層小函式 |
| 可刪 `DecodeSummary.auto`、CCC 重複旗標 | **採納** |
| 可刪各小模組重複的 `__main__` | **不採納**：RULES 硬規則第 10 條要求每個模組留 `__main__` 自檢 |
