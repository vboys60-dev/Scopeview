# 示波器離線分析工具：UART、RS-232 與 RS-485 解碼實作規格研究

研究日期：2026-10-26。範圍：從類比電壓－時間序列被動解碼 UART 字元框，涵蓋 RS-232 與 RS-485 實體層（承載 UART）、半雙工換向、9-bit／multidrop 位址模式，以及 Modbus RTU 的 3.5 字元靜默分框。本文不實作程式、不定義示波器內建命令。

與既有研究的關係：`docs/研究_數位解碼協定定義.md` 的 §2（門檻與取樣）、§2.1（取樣率估計）、§6（RS-232／UART）、§7（RS-485）、§9（呈現欄位）、§10（實作建議）已有概要。本文不重抄，只補可直接實作的部分：狀態機、鮑率容差數式、異常碼、自動偵測、事件表欄位、測試向量。

章節引用慣例：未加「本文」前綴的 §x 指 `研究_數位解碼協定定義.md`；本文自身段落以「本文 §x」標示。「待確認」表示目前取得的來源不足以核對，不能當作硬編碼常數。

## 1. 來源索引（本文新增）

既有來源代號（U1、U2、R1、R2、O3、O4 等）沿用 `研究_數位解碼協定定義.md` §1 的定義。本文新增：

| 代號 | 來源 | 取得狀態與本文用途 |
|---|---|---|
| MB1 | Modbus Organization，*Modbus over Serial Line Specification and Implementation Guide* V1.02，2006-12-20 | 已取得 PDF 全文（大學鏡像 `cars.uchicago.edu`；官方入口 `modbus.org/modbus-specifications`）。引用：§2.5.1（11-bit 字元、LSB first、預設 even parity、無 parity 須 2 stop）、§2.5.1.1（3.5／1.5 字元規則、固定計時建議）、§3.4.6（線路極化電阻）、附錄 B（CRC-16）。終端段落的完整節號待確認。 |
| R3 | TI，*The RS-485 Design Guide*（SLLA272D）§7 Failsafe | 已由 TI 文件檢視器讀取 §7 摘要。RB 公式為圖片，未取得；文中 528 Ω 與 523 Ω 的對應待確認。 |
| T2 | TI，MC1489A／SN75189 RS-232 receiver 資料表 | 僅取得搜尋摘要：資料表所列接收器輸入電阻範圍 3 kΩ～7 kΩ，可外接電阻移位門檻。表格數值待確認。 |
| DS83 | Dallas Semiconductor，Application Note 83，*Fundamentals of RS-232*，1998 | 僅取得摘要，圖示 receiver 門檻約 +3 V／−3 V 區間，引用 EIA/TIA-232-E 版本。TIA-232-F 原文待確認。 |
| A1 | Analog Devices（原 Maxim），*Determining Clock Accuracy Requirements for UART Communications*，2003 | 本次讀取全文逾時，僅有標題與摘要。公式與數字待確認。 |
| K1 | Keysight，N5457A 與 Infiniium 90000 RS-232／UART 資料表（搜尋摘要） | 摘要：5～8 bits、none／odd／even parity、手動設定 baud、parity error 觸發與色彩標示。 |
| TK1 | Tektronix，Serial Triggering and Analysis 資料表（第三方站轉載 PDF） | 摘要：Polarity 有 Normal（RS-232）與 Inverted（UART、RS-422、RS-485）；Parity none／odd／even；鮑率 300～921,600 b/s 與自訂。轉載來源，待確認原廠版本。 |

取得限制：TIA-232-F 與 TIA/EIA-485-A 原文為付費標準，本次未取得，相關數值以 U1、R1、R3、DS83 等間接來源標示。網路搜尋多為摘要，未讀到 Keysight、R&S、Tektronix 應用筆記的 PDF 本體。非原廠部落格內容未採為依據。

## 2. 實體層

### 2.1 TTL／CMOS UART

- 閒置為高，start bit 為低，LSB first；定義見 §6.2、MB1 §2.5.1。
- 門檻依 I/O 電壓 VDD：預設判位中點 0.5×VDD，遲滯採 V↓ = 0.4×VDD、V↑ = 0.6×VDD。這是實作預設，不是器件規範；1.8 V 與 3.3 V 兩種 VDD 各自可由使用者覆寫。〔來源：§2；實作建議〕
- 單端點對點，不需終端電阻。〔來源：§6.1〕

### 2.2 RS-232

- 電壓：mark（邏輯 1）為負，space（邏輯 0）為正，閒置為 mark。典型發送電壓 ±5 V 至 ±15 V。〔來源：U1、§6.1〕
- 接收判位：DS83 摘要示意 −3 V 以下為 mark、+3 V 以上為 space，中間不保證有效。TIA-232-F 的精確門檻與取樣規定待確認。接收器輸入電阻為 T2 資料表所列 3 kΩ～7 kΩ 範圍。〔來源：DS83、T2；待確認〕
- 解碼器預設：V↓ = −3 V、V↑ = +3 V，中間區依 §2 規則維持前態，並累計「中間區持續時間」，超過半個位元時標 `LEVEL_UNKNOWN`。這是設計預設，使用者可覆寫；若訊號振幅小於 ±3 V，須降低門檻。〔來源：§2；實作建議〕
- 本研究不做器件合規判定，只做訊號解碼。〔來源：§6.1〕

### 2.3 RS-485 承載 UART

- 差動電壓定義為 `Vdiff = V(X) − V(Y)`，X、Y 由使用者選擇（A／B 或 D0／D1 的命名在廠商間可能相反，見 §7.1）。接收器判位約 ±200 mV，中間區不能假定有效。〔來源：R1、R2、§7.1〕
- 失效保護：有終端的匯流排若無驅動，差動接近 0 V。傳統接收器的輸出在此狀態未定義，但具內建 failsafe 的器件會強制輸出定義狀態。外部 failsafe 的設計目標為 `VAB = 200 mV + VNoise`；R3 提到內建 failsafe 的最差雜訊餘裕只有約 10 mV。兩者都是器件或設計條件，不是所有 RS-485 接收器的通用保證。〔來源：R3 §7；適用條件待確認〕
- 偏置：MB1 §3.4.6 規定，只有在有裝置需要線路極化時，才設一組偏置電阻，阻值 450 Ω～650 Ω，D1 上拉到 5 V、D0 下拉到共同端，且整條匯流排只設在一個位置。D1／D0 與 A／B 的對應依廠商文件，待確認。〔來源：MB1 §3.4.6〕
- 終端：兩端各 120 Ω 為常見作法〔R1、R3〕；MB1 另提 150 Ω（0.5 W）或 1 nF 串 120 Ω 的選項，節號待確認。不應每個節點都裝終端。〔見其他文件 §7.1〕
- 解碼規則：`|Vdiff| < 200 mV` 的取樣視窗若多數為 X，該位元為 X；字元中任一資料或 parity 位元為 X，字元值為 null（見 §5.1）。正常邊沿會短暫經過中間區，單一邊沿不應使整段無效，因此只以視窗多數決判定。這與其他文件 §7.1「近零電壓不應強行當有效字元」一致。

### 2.4 極性與邏輯映射

所有協定共用同一映射表，使用者只設定映射，不另寫分支：

| 設定 | 邏輯 1 的判定 | 閒置狀態 | 備註 |
|---|---|---|---|
| TTL normal | V ≥ V↑ | 高 | 預設 |
| TTL inverted | V ≤ V↓ | 低 | 對應 TK1 的 Inverted |
| RS-232 | V ≤ V↓（負電壓） | 負 | 本研究對 RS-232 的預設 |
| RS-485 normal | Vdiff ≥ +200 mV（Vdiff 定義為 X−Y） | 依偏置 | 使用者選擇 |
| RS-485 inverted | Vdiff ≤ −200 mV | 依偏置 | TK1 把 RS-485 列為 Inverted 類 |

來源：TK1 極性選項、R1／R2 判位、U1；本映射為實作建議。

## 3. 解碼狀態機

### 3.1 參數

每個解碼設定為一個 profile：

- `Rb`：鮑率，`T = 1/Rb`（秒）。
- `D`：資料位元數，5～8（9-bit 見 §3.5）。
- `P`：parity，`N`（無）、`E`、`O`、`M`（mark）、`S`（space）。
- `S`：stop 位元數，本版僅支援 1 或 2。S = 2 為嚴格模式（所有 stop 中心皆須為 1）；寬鬆模式（只檢查第一個 stop）與 1.5 stop 本版停用，見 §12。
- `order`：固定 LSB first。
- `inv`：極性，見 §2.4。
- `g_min`：脈寬下限，預設 0.3×T（工程預設，待以合成測試校正）。
- `Tb`：break 門檻，預設 `(1 + D + P_bits + S)×T`，即一個完整字元長。器件或上層協定的 break 長度不同時須覆寫（待確認）。
- `P_bits`：1（有 parity）或 0（無 parity）。

parity 位元 p 的計算：even 時 `p = popcount(data) mod 2`（使資料與 p 合計為偶數）；odd 時 `p = 1 − (popcount(data) mod 2)`；mark 固定 p = 1，space 固定 p = 0，二者都不檢查資料內容。〔來源：MB1 §2.5.1 預設 even；§6.2〕

位元位置（單位 T，以 start 邊沿為 0）：start 佔 [0,1)，資料第 k 位佔 [k, k+1)，parity 佔 [D+1, D+2)（若有），stop 自 `n_pre = 1 + D + P_bits` 起佔 S 個位元。

### 3.2 三值取樣

- 取樣結果為 `0`、`1` 或 `X`（未知）。
- 取樣視窗 `[t−w, t+w]`，`w = 0.1T`，內含原始樣本。若多數樣本落在未知區（§2.2、§2.3 的中間區），結果為 `X`；否則為多數決的 0 或 1。
- `X` 不得當作 0 或 1 使用：不能用於通過 start 檢查、不能更新 mark 證據，也不能被寫成資料位元。含 X 的字元值為 null，逐位元保留 X 遮罩。
- 視窗多數決需要足夠樣本：視窗寬 0.2T，至少 3 點，因此每位元至少 16 點（見 §6.3）。低於此值時退回單點取樣，並標示 `LIMITED_SAMPLING`。

### 3.3 狀態與游標

狀態：

- `HUNT`：尚未同步（擷取開頭，或前一字元 stop 無效之後）。接受 start 的條件：最近一次上升緣到 start 下降緣的 mark 長度 ≥ T，且 start 中點取樣為明確的 0。
- `SYNCED`：已同步。前一字元 stop 有效，下一個 start 可在前一字元最後一個 stop 中心之後的任何下降緣出現，不要求 mark ≥ T（以容許 stop 因時脈誤差縮短，見 U20）。
- `BREAK_WAIT`：break 結束後，等待上升緣。
- `last_rise` 於每個上升緣更新（不論是否在字元區間內），擷取起點若為 1，則以擷取起點作為初值。

游標與消耗：每個 start 候選（接受與否）都會消耗其字元區間 `[t0, frame_end]`，`frame_end` 為最後一個 stop 中心。區間內的轉換不作 start 判斷。

```
state = HUNT
last_rise = capture_start if level(capture_start) == 1 else None
if level(capture_start) == 0: emit(UNSYNCED, capture_start, first_rise)   # 擷取起點為低：到第一個上升緣為止標 UNSYNCED
frame_end = -inf
for each transition (t, L) in order:                  # 已套用 g_min；L 為新電平
    if L == 1: last_rise = t
    if t < frame_end:                                  # 位於上一個字元的區間內
        if L == 0 and stop_start < t < stop_center_first: emit(SHORT_STOP, t)
        continue
    if state == BREAK_WAIT:
        if L == 1: state = HUNT
        continue
    if L == 0 and (state == SYNCED or (last_rise is not None and t - last_rise >= T)):
        t0 = t
        if sample(t0 + 0.5T) != 0:                     # false start：中點不是明確 0
            emit(GLITCH, t0, "false start"); last_rise = None; continue
        bits, parity_bits, stop_samples = decode(t0)   # 取樣規則見 3.4
        stop_start        = t0 + n_pre*T
        stop_center_first = t0 + (n_pre + 0.5)T
        frame_end         = t0 + (n_pre + S - 0.5)T
        stop_ok = all(v == 1 for v in stop_samples)    # 含 X 時為 False
        low = low_run(t0)                              # 向後找到下一個上升緣的時間差
        if all(b == 0 for b in bits) and stop_samples[0] == 0 and low >= Tb:
            emit(BREAK, t0, t0 + low); frame_end = t0 + low; state = BREAK_WAIT; last_rise = None
        elif state == HUNT and not stop_ok:
            emit(UNSYNCED, t0, frame_end); last_rise = None           # 候選無效：消耗區間，留在 HUNT
        else:
            emit(BYTE, t0, frame_end, bits, parity_ok, stop_ok)      # HUNT 中首個有效字元標 sync_acquired
            state = SYNCED if stop_ok else HUNT
            if not stop_ok: last_rise = None
# 擷取結束
if frame_end > capture_end: emit(TRUNCATED)            # 最後一個字元未完成
if state == BREAK_WAIT: emit(BREAK_OPEN if capture_end - break_start >= Tb else TRUNCATED)
```

要點：

1. **mark 量測**：HUNT 要求的 mark ≥ T 以上升緣量測；SYNCED 不要求 mark，只要求 start 在前一字元最後 stop 中心之後。
2. **字元區間內的轉換不作 start 判斷**：資料位元的邊沿在區間內被忽略，因此不會被誤當 start。區間內的 stop 起點之後、stop 中心之前的下降緣記為 `SHORT_STOP`。
3. **X 不更新 mark 證據**：X 區間不能當作已證實的連續 mark。
4. **無效候選消耗區間**：HUNT 中 stop 無效的候選字元只輸出 `UNSYNCED` 並消耗區間，之後必須重新出現上升緣與 ≥ T 的 mark 才能再接受 start，因此不會從該字元內部的資料邊沿重新開始。
5. **BREAK 之後**：break 結束的上升緣進入 HUNT，之後的 start 需要 ≥ T 的 mark（見 U28）。
6. **假同步**：HUNT 中，資料位元內的單位元 mark 可能被當成 start 候選。候選必須 stop 有效才輸出 BYTE，否則輸出 UNSYNCED，因此多數假同步不會產生假的 BYTE；但若資料恰好形成有效的 stop，仍可能誤判，故擷取中途的首個字元應視為低可信。
7. **S = 2 僅支援嚴格模式**：`stop_ok` 要求所有 stop 中心皆為 1，區間延伸至最後一個 stop 中心，因此第二個 stop 的下降緣不會被當成新 start。

### 3.4 資料、parity、stop 取樣

- 資料位元 k（LSB first）取樣於 `t0 + (k + 0.5)T`，k = 1…D。
- parity 取樣於 `t0 + (D + 1.5)T`（若有）。
- stop 第一個中心取樣於 `t0 + (n_pre + 0.5)T`；S = 2 時，第二個 stop 中心取樣於 `t0 + (n_pre + 1.5)T`。
- 所有取樣都使用 3.2 的三值規則。

### 3.5 資料位元 5～9 與 9-bit 模式

- `D = 5`：取 bit0～bit4，無高位。
- `D = 8`：標準，MB1 RTU 同樣使用 8 bits。〔MB1 §2.5.1〕
- `D = 9`：9 個資料位元，parity 計算範圍為 D 個資料位元。第 9 位的語意（例如 multidrop 的 address flag）由上層協定定義。本文不假定固定語意，profile 需明確指定；若未指定，事件只保留原始第 9 位值。（待確認某目標協定）
- 9-bit 與 parity 合用時，需在 profile 中明示是否計算 parity；本版預設 D = 9 時 P = N。

## 4. 鮑率容差與時脈漂移

### 4.1 取樣誤差公式

設 `P_last` 為最後一個有檢查意義的 stop 中心，相對 start 邊沿的位元位置（單位 T）：

```
P_last = n_pre + S − 0.5          # n_pre = 1 + D + P_bits
```

此式假設 S = 1 或 S = 2，且最後一個 stop 中心即為最晚的取樣點。

設收發相對誤差 `ε = Rtx / Rrx − 1`（正值表示送端較快）。接收端在位元位置 P 的取樣點與送端位元中心的偏移約為 `P × ε` 位元（以 Rrx 的位元時間為單位，ε 小時近似成立）。要求最晚取樣點的偏移小於半個位元，並保留 `δ` 給 start 同步與量化誤差：

```
|ε| × P_last + δ < 0.5    （δ：start 同步與取樣量化誤差，單位位元）
```

### 4.2 各格式容許值

| 格式 | P_last | 理論上限 ε（δ = 0） | 保守上限 ε（δ = 0.1） |
|---|---:|---:|---:|
| 8N1 | 9.5 | 5.26% | 4.21% |
| 8E1／8O1 | 10.5 | 4.76% | 3.81% |
| 8N2 | 10.5 | 4.76% | 3.81% |
| 9N1 | 10.5 | 4.76% | 3.81% |
| 7E1 | 9.5 | 5.26% | 4.21% |
| 5N1 | 6.5 | 7.69% | 6.15% |

計算為本研究依 4.1 推導，屬於理想模型下的充分條件，並非任何硬體 UART 的保證容差。

誤差合併：兩端相對標稱誤差分別為 a、b，單端絕對值不超過 A 時，收發相對誤差為 `ε = (a − b)/(1 + b)`，這是 `Rtx/Rrx − 1` 的精確展開。其最壞情況為 `2A/(1 − A)`（a = A、b = −A）；例如 A = 2% 時為約 4.08%，高於 4%。表中的上限是對收發合併誤差 ε 的界限；若要換算為單端 A，取 `2A/(1 − A) ≤ 上限`，例如 8N1（δ = 0）的 5.26% 對應 A ≈ 2.56%。〔來源：推導；A1 的數字待確認〕

### 4.3 時脈漂移的累積與「不可跨 frame 累積」

- **單一字元內**：偏移隨位元位置線性增加，見本文 §4.1。
- **跨字元**：若每個字元都以自身 start 重新同步，誤差不跨字元累積。
- **若用一個全域格點**（例如以第一個字元估得的 T，對整段擷取一直使用）：第 N 個位元的格點誤差為 `N × ε`。以 ε = 0.5% 為例，經過 1000 個位元後格點誤差為 5 個位元，解碼必錯。因此解碼器**必須每個 start 重新對齊**，不得使用全域格點。

### 4.4 數值例

| 鮑率 | T | 8N1、ε = 2% 時在 P_last 的偏移 | 時間偏移 |
|---|---:|---:|---:|
| 9600 | 104.17 µs | 0.19 位元 | 約 19.8 µs |
| 115200 | 8.68 µs | 0.19 位元 | 約 1.65 µs |
| 1 Mbaud | 1.00 µs | 0.19 位元 | 約 0.19 µs |

ε = 5% 時，8N1 的偏移為 0.475 位元，接近上限 0.5。以上數字為理想時脈計算，未含示波器時基誤差與類比邊沿抖動。示波器時基誤差的量級待確認，應查該機型規格。

## 5. 錯誤與異常標示

### 5.1 代碼表

| 代碼 | 觸發條件 | 事件 status | 處置 |
|---|---|---|---|
| `FRAMING` | stop 中心取樣不為 1（非 BREAK） | error | 仍輸出字元值（含 X 遮罩），標紅 |
| `PARITY` | parity 計算與接收值不符（P 為 E／O） | error | 仍輸出字元值，記錄 expected／received |
| `BREAK` | 全 0、stop 為 0、低電平 ≥ Tb | info（可設定） | 不作為一般字元，改為獨立事件；可選 keep_as_zero |
| `BREAK_OPEN` | break 持續到擷取結束 | info | 只記錄開始時間 |
| `GLITCH` | 脈寬 < g_min 被移除；或 start 中點非 0（false start） | warn | 不產生字元 |
| `UNSYNCED` | 擷取中途開始，首個字元 stop 無效 | info | 標示為未解碼區 |
| `TRUNCATED` | 字元在擷取結束前未完成 | warn | 不輸出字元值，保留已取得的位元與 X 遮罩 |
| `SHORT_STOP` | stop 中心前出現下降緣 | warn | 可能鮑率或時脈不符，併入 BAUD_SUSPECT 統計 |
| `TIMING_MARGIN` | 字元內有至少 2 個資料邊沿，且其最大偏差 > 0.25 位元 | warn | 提示鮑率或 δ 可能不足；單一 start 邊沿的字元無法評估 |
| `LIMITED_SAMPLING` | 每位元取樣點不足 16 點，無法多數決 | warn | 退回單點取樣 |
| `LEVEL_UNKNOWN` | 中間區持續超過 T/2 | warn | 該段位元為 X |
| `BAUD_SUSPECT` | framing 或 SHORT_STOP 比例超過閾值（預設 10%） | warn | 建議檢查鮑率與格式 |
| `BAUD_AMBIGUOUS` | 自動鮑率有多個同等可信候選 | warn | 列出候選，不唯一選定 |
| `AMBIGUOUS_FORMAT` | 多個 parity 或 stop 候選在整段擷取中都無錯誤 | warn | 列出候選，不唯一選定 |
| `POLARITY_SUSPECT` | 多數字元 framing，且閒置為低 | warn | 建議切換 inv |
| `RS485_DIFF_UNCERTAIN` | 字元中任一資料位元或 parity 位元取樣為 X | warn | 該字元值為 null，保留 X 遮罩 |
| `RS485_CONTENTION` | 同一差動對上，兩個已知 driver 的有效 DE 重疊（需 DE 通道） | warn | 同時標示兩個來源 |
| `GLITCH_IN_FRAME` | 字元內部有被移除的脈衝 | info | 該位元仍以 3.2 多數決取值 |
| `MB_CRC_ERR`、`MB_GAP_INVALID`、`MB_FRAME_OPEN`、`MB_FRAME_LONG`、`NONSTANDARD_FORMAT` | Modbus 模式（本文 §8） | 依 §8 | 依 §8 |

來源：§5 的 framing、parity 原則〔其他文件 §6.3〕；break、glitch、TIMING_MARGIN 等命名為本研究實作建議。

### 5.2 不應判為錯誤的情況

- 閒置期間的低電平不視為 break，除非持續 ≥ Tb 且符合 BREAK 的其他條件。
- Modbus 的 3.5 字元靜默是合法的框界，不是錯誤（見本文 §8）。
- 字元之間的空閒不是 framing 錯誤。
- `UNSYNCED` 與 `TRUNCATED` 是擷取限制，不是傳送錯誤。

### 5.3 同一字元多錯誤

- framing 與 parity 可同時發生，兩者都保留。
- BREAK 同時含 framing 的語意，但以 BREAK 為主事件，不重複輸出 framing。
- GLITCH 若位於資料位元中間，仍以多數決取該位元，並附加 `GLITCH_IN_FRAME`。

### 5.4 可觀測性限制

- 離線無法得知硬體 overrun、buffer overflow 或接收器實際取到的值；僅憑 TXD／RXD 波形不能證明。〔其他文件 §6.3〕
- 在已知字元邊界、D 與 parity 位置、且無 X 的前提下，單一字元已足以判定其是否符合 E 或 O；不能唯一判定的是格式本身（D、P、S 的組合），需由多個字元或 frame 的一致性判定（見本文 §6.4）。
- 擷取中途開始時，假同步不可完全排除（見本文 §3.3 第 3 點）。

## 6. 使用者參數與自動偵測

### 6.1 參數與預設

| 參數 | 預設 | 能否自動偵測 | 說明 |
|---|---|---|---|
| 通道（TX、RX、差動 X−Y） | 無 | 否 | 使用者指定 |
| 電氣 profile（TTL、RS-232、RS-485） | 依通道 | 只能建議 | 依振幅建議：0～3.3 V → TTL；±5～±15 V → RS-232；差動對 → RS-485。須使用者確認 |
| 極性 inv | 依 profile | 可建議 | 依 POLARITY_SUSPECT 統計建議，不自動套用 |
| 門檻與遲滯 | §2 預設 | 否 | 使用者可覆寫 |
| 鮑率 Rb | 自動或指定 | 可（見本文 §6.2） | 自動結果需使用者確認 |
| D、P、S | 8、N、1 | 部分（見本文 §6.4） | 只能排名候選，不能唯一確定 |
| g_min | 0.3×T | 否 | 校正前的工程預設 |
| Tb | `(1+D+P_bits+S)×T` | 否 | 器件不同時覆寫，待確認 |
| Modbus 框架模式 | 關閉 | 否 | 使用者啟用，見本文 §8 |

來源：其他文件 §6.3 的參數建議、TK1 的 polarity 與 parity 選項；預設值為實作建議。

### 6.2 鮑率與格式自動偵測（研究提出的啟發式演算法）

目標：從擷取中的邊沿同時估計鮑率與格式，避免只靠單一最短間隔或單一字元。本演算法為本研究提出的啟發式，尚未以實際資料驗證。

1. **第一階段過濾（與鮑率無關）**：以 `g0 = 2/Fs` 為脈寬下限，去除明顯取樣雜訊。`g0` 不依賴 T，避免循環相依。
2. **候選產生**：
   - 鮑率：對每個間隔 `d_i` 取 `T = d_i/k`（k = 1…12），相近者（相對差 < 2%）合併；另加入標準鮑率列表（見下）。
   - 格式：若使用者已指定，只用該格式；否則列舉 D = 8、P ∈ {N, E, O}、S ∈ {1, 2} 共 6 種，與鮑率候選聯合評估。
3. **逐候選 dry run**：對每個 (T, 格式) 候選，以 §3.3 的狀態機對整段轉換序列試解碼（每個候選使用自己的 `g_min = 0.3T` 重新過濾），記錄有效字元數 N_ok（stop 有效且 parity 符合）、錯誤字元數 N_err，以及未被任何字元區間涵蓋的轉換比例 U。
4. **可接受條件**：N_ok ≥ 2（證據下限）；N_err / (N_ok + N_err) ≤ 5%；非閒置間隔中 `|d_i/T − round(d_i/T)| ≤ 0.1` 的比例 ≥ 95%。不滿足者排除。
5. **判定**：
   - 通過者中，若最佳候選的 U 比次佳候選小至少 1 個百分點，且 N_ok 不少於次佳，則唯一。
   - 否則若鮑率不同而格式相同：`BAUD_AMBIGUOUS`，列出所有通過候選。
   - 若格式不同：`AMBIGUOUS_FORMAT`，列出所有通過候選。
   - 若所有候選的 N_ok 都小於 2：`INSUFFICIENT_EVIDENCE`，不做唯一判定。
6. **2 倍誤判**：若 T 能擬合全部邊沿，T/2 也能（每個邊沿都落在 T/2 的整數倍上）。T/2 候選會在 stop 取樣與 parity 上產生錯誤，由步驟 4 的 N_err 排除；若資料量太少而兩者 N_err 都為 0，由步驟 5 標示歧義。〔研究推論；未以實際資料驗證〕

標準鮑率列表：1200、2400、4800、9600、19200、38400、57600、115200、230400、460800、921600、1000000。TK1 列出 300～921,600 b/s 與自訂值；1 Mbaud 等高速率的存在依器件，待確認。〔來源：TK1、U1、§6.2〕

- 演算法中的 0.1、95%、5%、N_ok ≥ 2、1 百分點、2%、1.5% 皆為工程預設，待以本文 §10 的合成測試校正。
- 「0xAA／0x55 常作為鮑率測試樣式」的說法來自第三方教學，非權威來源，本文只將其作為測試建議。

### 6.3 最低取樣率

本研究沿用 §6.2 的建議（每位元 16～32 點），並補充：

- 自動偵測需要最短間隔內至少 4 個樣本，即 `Fs ≥ 4 / T_min`；`g0 = 2/Fs` 的設計需要 `Fs ≥ 8 / T_min` 才有足夠裕度。
- 位元中心的多數決（本文 §3.2）至少需要每位元 16 點，否則退回單點取樣（`LIMITED_SAMPLING`）。
- 115200 baud：`Fs ≥ 1.84 MSa/s`（16 點/位元），建議 3.7 MSa/s 以上（32 點）。
- 1 Mbaud：`Fs ≥ 16 MSa/s`，建議 32 MSa/s 以上。

以上是本研究的工程估計，不是 UART 規範的解碼下限；與 §2.1 一致。〔來源：§2.1、§6.2；工程估計〕


### 6.4 parity 與 stop 格式判定

- 格式與鮑率聯合判定（見本文 §6.2 步驟 2–5），不先固定 8N1 再排名；8N1 與 8O1 對 parity 位元的解讀不同，若先固定格式會使真實鮑率的評分失真。
- 排除規則的依據：偶數個 1 的資料字元，E 下 parity 位元應為 0、O 下應為 1。若擷取中該位置為 1，則 E 被排除；0x55、0xAA（偶數個 1）即屬此例（見 U18）。
- 增加 stop 數不會修復第一個 stop 中心為 0 的字元；S 候選依同一排名規則比較，不固定建議增加 stop。
- 使用者已指定格式時直接使用該格式，只做鮑率估計。

## 7. RS-485 專項補充

### 7.1 換向、DE 與衝突

- 半雙工時，DE 與 RE 若可觀測，可判斷哪個 driver 在驅動。沒有 DE 時，只能從差動電壓推斷，且不能分辨「誰在驅動」。〔來源：§7.1、§2〕
- DE 在字元前後的時序（提前或延後）為 turnaround 證據，應記為 `direction evidence`，不強制解讀。
- **衝突判定**：只有在需要 DE 通道、且兩個已知 driver 的有效 DE 區間重疊時，才標示 `RS485_CONTENTION`。正常的單一發送（DE 有效且資料活動）不是衝突。差動近零本身只代表 `RS485_DIFF_UNCERTAIN`，不能推論為衝突。〔來源：§7.1、§2 對可觀測性的限制；研究判斷〕
- **半雙工回音**：若 TX 與 RX 在同一對線上，RX 會看到自己發送的字元。解碼器應將與 TX 事件時間窗重合且內容相同的 RX 字元標為 `echo` 並預設隱藏，此規則需使用者開啟。

### 7.2 Vdiff 與字元

- 字元解碼與 RS-232 共用同一狀態機，只差在輸入為 `Vdiff` 而非單端電壓。
- `Vdiff` 的判位以 §2.4 的映射為準，inv 與 X−Y 方向由使用者設定。
- TK1 把 RS-485 列為 Inverted 類，這是 Tektronix 的 UI 分類，不是 RS-485 規範。〔來源：TK1；待確認原廠含義〕

## 8. Modbus RTU 框架規則（profile）

本節只描述 MB1 的 RTU 框架規則。功能碼、位址與資料內容屬上層協定，不在本研究範圍（見本文 §12）。

### 8.1 字元格式

- 每個位元組為 11 bits：1 start、8 data（LSB first）、1 parity、1 stop。〔MB1 §2.5.1〕
- 預設 even parity。若無 parity，須使用 2 stop bits，即 11 bits 字元。〔MB1 §2.5.1〕
- 解碼器啟用 Modbus 模式時，格式必須為 8E1（預設）、8O1 或 8N2（MB1 允許 even、odd、no parity 三種選項，且 no parity 須 2 stop bits）；其他格式標示 `NONSTANDARD_FORMAT`，並提示 MB1 的計時規則是否適用待確認。〔MB1 §2.5.1〕

### 8.2 靜默時間

設 `t_char = 11 / Rb`（秒）：

- `Rb ≤ 19200`：`t1.5 = 1.5 × t_char`，`t3.5 = 3.5 × t_char`，必須遵守。〔MB1 §2.5.1.1〕
- `Rb > 19200`：建議固定值 `t1.5 = 750 µs`、`t3.5 = 1.750 ms`。〔MB1 §2.5.1.1〕

| Rb | t1.5 | t3.5 | 來源 |
|---|---:|---:|---|
| 1200 | 13.75 ms | 32.08 ms | 計算 |
| 4800 | 3.44 ms | 8.02 ms | 計算 |
| 9600 | 1.719 ms | 4.010 ms | 計算 |
| 19200 | 0.859 ms | 2.005 ms | 計算 |
| 38400 | 750 µs（建議） | 1.750 ms（建議） | MB1 固定值 |
| 115200 | 750 µs（建議） | 1.750 ms（建議） | MB1 固定值 |

### 8.3 靜默與框界

靜默時間定義為前一字元 stop 結束到下一字元 start 的時間差，以時間而非位元計數量測：

| 靜默區間 | 判定 | 事件 |
|---|---|---|
| `≤ t1.5` | 同一框內的連續字元 | 併入目前框 |
| `(t1.5, t3.5)` | 框內中斷，框不完整，也不能當作合法框界 | 目前框標 `MB_GAP_INVALID`；之後的字元暫不納入框，直到靜默 ≥ t3.5 |
| `≥ t3.5` | 框界（等於 t3.5 即為框界） | 結束目前框，開始新框 |

- 框內靜默超過 t1.5 時，MB1 規定該框應丟棄；本工具保留原始事件並標示無效，不直接刪除。〔MB1 §2.5.1.1〕
- 擷取開頭的第一個框：若擷取開始前的靜默長度未知，該框標示 `MB_FRAME_OPEN`，不做完整性判定。
- 框長度超過 256 bytes（MB1 最大值）時標示 `MB_FRAME_LONG`。〔MB1 §2.5.1.1〕

### 8.4 CRC-16

- 初值 0xFFFF；多項式 0xA001（反射式）。每個位元組 XOR 進暫存器低位元組後，做 8 次：檢查 LSB，為 1 時右移並 XOR 0xA001，否則只右移。
- 計算範圍：框中所有位元組，不含 start、parity、stop，也不含框末兩個 CRC 位元組。〔MB1 附錄 B〕
- CRC 低位元組先送，高位元組後送。〔MB1 §2.5.1.1、附錄 B〕
- 已知答案（本研究以 Python 驗算）：`01 03 00 00 00 0A` 的 CRC-16 為 0xCDC5，線上順序為 `C5 CD`。此為常見 Modbus 範例，與 MB1 附錄 B 的演算法一致，範例值待以 MB1 原文核對。
- 事件欄位：`crc_received`、`crc_calc`、`crc_ok`。計算失敗或框無效時，`crc_ok` 為 null，不得以 CRC 錯誤代替框錯誤。

### 8.5 解碼器的處理

- Modbus 框架模式只在使用者啟用時套用；未啟用時，RTU 位元組仍作為通用 UART 字元輸出。
- 框事件（`modbus_frame`）以字元事件為子項目，欄位含框起點、框終點、框內字元數、CRC 結果。
- CRC 錯誤與框架錯誤分開標示；CRC 錯誤只在 Modbus 模式下出現（見 §5.1）。

## 9. 事件表與標註呈現

### 9.1 呈現原則（參考 O3、O4、K1、TK1）

- **標註列**：每個字元一個方塊，顯示十六進位；放大後展開 start、資料位元、parity、stop。〔來源：§9、O3〕
- **錯誤顏色**：framing、parity 用紅色，BREAK 與 GLITCH 以不同形狀區分（例如 BREAK 用灰色長條，GLITCH 用虛線小標）。K1 的 parity error 以顏色標示，可沿用此思路。〔來源：K1〕
- **表格與跳轉**：事件表依 `t_start` 排序，點選列可跳到波形對應位置，與 §9 的 Tektronix 描述一致。〔來源：§9、O1〕
- **profile 標示**：標註列旁顯示目前 profile（鮑率、格式、極性、門檻），避免使用者看不懂結果。
- **X 與未知**：含 X 的位元以灰色斜線顯示，不以 0 或 1 著色。

### 9.2 事件欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| `event_id` | string | 與標註列連結 |
| `bus` | TX／RX／BUS／null | BUS 用於 RS-485 合併 lane；未知時為 null |
| `kind` | byte／break／break_open／glitch／unsynced／truncated／marker／modbus_frame | 事件類型 |
| `t_start`、`t_end` | float（秒） | 時間範圍；break_open 的 `t_end` 為 null |
| `sample_index_start`、`sample_index_end` | int | 原始樣本範圍，對應其他文件 §10.1 的索引要求 |
| `bits` | array of {time, value: 0／1／X, quality} | 逐位元取樣結果與品質；X 的位元 value 為 X，不以 0 或 1 代替 |
| `value_u`、`value_hex`、`value_ascii` | int、string、string（皆可為 null） | 字元值；含 X 時為 null；ASCII 僅供顯示 |
| `data_bits`、`parity_expected`、`parity_received` | int、0／1 或 null、0／1 或 null | 格式與 parity 資訊；未啟用 parity 時為 null |
| `stop_ok` | true／false／null | stop 取樣結果；null 表示未完成或含 X |
| `status` | ok／info／warn／error | 顯示等級 |
| `reasons` | string[] | 代碼列表，見 §5.1 |
| `profile` | object | 鮑率、D、P、S、inv、門檻、profile 版本 |

所有事件另存 `index`、`bus`、時間來源與 profile 版本，對應 `研究_數位解碼協定定義.md` §9 的共同欄位，本文不重列。〔來源：§9〕

Modbus 框事件另含 `frame_start`、`frame_end`、`byte_count`、`crc_received`、`crc_calc`、`crc_ok`（可為 null），以及 `child_event_ids`。

### 9.3 TX／RX 雙通道

- 每個通道使用各自的 profile 獨立解碼，不共用狀態機。
- 事件依 `t_start` 合併到同一張表，以 `bus` 欄位區分。
- 重疊時間的事件不合併，標註列以半透明重疊顯示。
- RS-485 半雙工時，若 TX 與 RX 無 DE 證據，只能顯示為同一 lane 的兩個來源，並標示 `direction unknown`。
- 回音規則見本文 §7.1。

## 10. 合成測試波形案例

### 10.1 產生器規格

- 產生理想方波，取樣率 Fs，位元時間 T，上升與下降時間可設為 0。
- 電壓：TTL（0／3.3 V）、RS-232（+12 V／−12 V）、RS-485 差動（±1.2 V）。
- 閒置狀態需明示：TTL 閒置為高，RS-232 閒置為 −12 V，RS-485 閒置差動為 −1.2 V 或 +1.2 V（與 inv 配對，見 §2.4）。
- 字元前後的 mark 長度與尾端 idle 需明示，避免擷取邊界影響結果。
- 可加入：固定 ε（鮑率誤差）、固定 gap、glitch、差動近零段、白雜訊。
- 每個案例同時輸出預期事件表與 ground-truth 字元序列，供單元測試比對。
- 所有案例的取樣相位固定為每個邊沿落在取樣點之間（不落在取樣點上），避免浮點取整造成的隨機結果。

### 10.2 測試案例

| ID | 輸入描述 | 預期解碼事件（判定條件） |
|---|---|---|
| U01 | 9600 8N1，閒置高，單一字元 0x55（bit0 先送：1,0,1,0,1,0,1,0），之後 idle | BYTE 0x55，stop 為 1，status ok |
| U02 | 9600 8E1，單一字元 0x41（popcount = 2，parity 位元 = 0） | BYTE 0x41，parity 符合，status ok |
| U03 | 同 U02，但設定 8O1 | BYTE 0x41，PARITY error |
| U04 | 9600 8N1，字元 0x41，stop 位元改為低電平（持續 1 位元，之後回 idle） | BYTE 0x41，FRAMING error |
| U05 | 9600 8N1，連續低電平 1.2 ms（≥ Tb = 10T ≈ 1.04 ms）後回到高，回到高後保持 idle 2T，再送字元 0x41 | BREAK（不輸出 0x00）；隨後 BYTE 0x41，status ok |
| U06 | 9600，idle 高，中間插入 20 µs 低脈衝（約 0.19T，小於 g_min） | GLITCH，無 BYTE |
| U07a | 9600 8N1，擷取起點恰為前一字元 stop 位元的起點（線路為高），之後接一個完整字元 0x41（前方 mark 為 1T） | 只輸出 BYTE 0x41，無 UNSYNCED 區段 |
| U07b | 9600 8N1，擷取起點位於 0x00 字元的資料中段（線路為低）；0x00 結束後回 mark，之後送字元 0x41（前方 mark ≥ T） | 擷取起點到第一個上升緣之間標 UNSYNCED（不輸出字元）；之後 BYTE 0x41 正常解出 |
| U08 | 9600 8N1，最後字元在第 4 個資料位元中途被擷取結束 | TRUNCATED，不輸出字元值，保留已取得位元與 X 遮罩 |
| U09 | 9600 8N1，字元 0x41，其 stop 高電平只持續 0.3T 後線路轉低（下一 start 早到） | FRAMING 與 SHORT_STOP 同時出現；不要求後續字元解出 |
| U10 | 8N2（S = 2，嚴格模式），字元 0x41，第二個 stop 位元為低（持續 1T，之後回 mark） | FRAMING，字元值 0x41；之後直到 mark ≥ T 才接受新 start。寬鬆模式本版停用 |
| U11 | 5N1，字元 0x1F（5 個 1，LSB first） | BYTE 0x1F，data_bits = 5 |
| U12 | 9N1，字元 0x1A5（LSB first：1,0,1,0,0,1,0,1,1） | BYTE 0x1A5，data_bits = 9，parity 為 null |
| U13 | RS-232：閒置 −12 V，start +12 V，字元 0x41，profile = RS-232 | BYTE 0x41，ok |
| U14 | 同 U13，但 profile 的 inv 設為 true | 所有字元 FRAMING，並觸發 POLARITY_SUSPECT |
| U15 | RS-485：閒置 Vdiff = −1.2 V（X−Y），字元 0x41，profile 為 RS-485 inverted | BYTE 0x41，ok（閒置 mark 為 Vdiff ≤ −200 mV） |
| U16 | RS-485：資料區的 2 個位元期間 Vdiff 約 +100 mV（|Vdiff| < 200 mV） | RS485_DIFF_UNCERTAIN，對應位元為 X，不輸出確定的字元值 |
| U17 | TX 送 0x41、RX 送 0x42，兩者在時間上部分重疊（各自獨立的 lane） | 兩個 BYTE，bus 分別為 TX、RX，值各自正確，無串擾 |
| U18 | 19200 8N1，交替送 0x55、0xAA，字元間 idle 2T，共 8 個字元 | 鮑率 19200 通過；parity 候選 E 因 parity 位元不符被排除（0x55、0xAA 皆為偶數個 1，E 預期 parity 為 0，實際為 stop 的 1）；N 與 O 皆無錯誤。結果：AMBIGUOUS_FORMAT，候選 {N, O}，不得唯一選定 parity |
| U19 | 9600 8N1，只有一個字元 0x00，後接 idle | 有效字元數 N_ok = 1 < 2；結果 INSUFFICIENT_EVIDENCE，不得唯一判定鮑率或格式（E 因 parity 不符被排除；N 與 O 皆可解釋此字元） |
| U20 | 9600 8N1，ε = +4%（Rtx = 1.04·Rrx），背靠背送 8 個字元 0x55；解碼器以 Rrx 取樣，取樣時刻為 (k+0.5)·Trx | 8 個字元全部為 0x55，無 FRAMING。依公式：stop 取樣時刻 9.88 Ttx 落在第 9 位（stop，讀為 1）；下一個 start 於 9.62 Trx 到達，晚於前一字元 stop 中心（9.5 Trx），由 SYNCED 接受 |
| U21 | 同 U20，ε = +6% | 第 1 個字元值為 0xD5（第 7 個資料位元取樣時刻 9.01 Trx 落在 stop 位元，讀為 1，與 0x55 的第 8 位元 0 不符），並產生 FRAMING；下一個 start 於 9.43 Trx 早於 stop 中心，產生 SHORT_STOP。本案例只判定第 1 個字元，之後的同步由 U07 規則決定，不列為預期 |
| U22 | 同 U20，ε = −6% | 第 1 個字元值為 0xD5（第 7 個資料位元取樣時刻 7.99 Trx 落在第 7 位元，讀為 1），stop 取樣時刻 8.93 Trx 落在資料位元 7（讀為 0），產生 FRAMING。本案例只判定第 1 個字元 |
| U23 | Modbus 模式，8E1，9600，框內 gap = 1.6 ms（小於 t1.5 = 1.719 ms） | 框內連續，不中斷；CRC 依框內容判定 |
| U24 | Modbus 模式，8E1，9600，框內 gap = 1.8 ms（介於 t1.5 與 t3.5 之間） | 目前框標 MB_GAP_INVALID，框不完整，之後字元暫不納入框 |
| U25 | Modbus 模式，8E1，9600，框 `01 03 00 00 00 0A C5 CD`，前後 idle ≥ 4.01 ms | 一個框，crc_received = 0xCDC5，crc_calc = 0xCDC5，crc_ok = true |
| U26 | 同 U25，但第 3 個位元組改為 0x01 | 同一框，crc_ok = false，不以 framing 代替 |
| U27 | 9600 8N1，0x00 字元，其低電平持續 9.8T（短於 Tb = 10T），之後回 mark | FRAMING，不是 BREAK，值為 0x00 |
| U28 | 9600 8N1，連續低電平 1.2 ms 後回 mark，mark 持續恰好 1T，之後送字元 0x41 | BREAK，隨後 BYTE 0x41（驗證 HUNT 接受 mark ≥ T 的條件） |
| U29 | 擷取在 break 低電平中途結束 | 低電平已持續 ≥ Tb：BREAK_OPEN，無 BYTE；未達 Tb：TRUNCATED |
| U30 | RS-485 兩個 driver 的 DE 區間重疊（需 DE 通道） | RS485_CONTENTION |
| U31 | RS-485 只有 Vdiff 近零段（無 DE 通道） | RS485_DIFF_UNCERTAIN，不得標為 RS485_CONTENTION |
| U32 | 9600 8N1，設定 S = 1.5 | profile 驗證拒絕，回報不支援的格式；不解碼 |

（U01～U32 為規劃用，未寫成測試檔。±12 V 與 ±1.2 V 為示意值，實際振幅依器件，見 §2.2、§2.3。）

## 11. 實作建議

- **模組切分**：門檻與遲滯 → 轉換序列（含 g_min 過濾）→ UART framer（吃 profile）→ 事件。framer 為純函式，輸入轉換序列與 profile，輸出事件列表，便於單元測試。
- **取樣查詢**：以 `bisect` 查原始樣本索引，每位元 O(log n)。長擷取分塊處理時，狀態（HUNT／SYNCED／BREAK_WAIT）、last_rise、frame_end 必須跨 chunk 保留。
- **效能**：與其他文件 §10.1 一致，先把樣本壓縮為邊沿與事件，再做解碼；繪圖降採樣不得影響解碼輸入。〔來源：其他文件 §10.1〕
- **測試**：以本文 §10.2 的案例作為 table-driven test，每個案例一個預期事件列表與 ground-truth 字元序列。
- **不做**：不實作 RS-485 的 DE 自動推斷、不實作多節點仲裁、不實作 Modbus 功能碼解析，這些另案。

## 12. 待確認清單

| 項目 | 目前狀態 | 需要的來源或動作 |
|---|---|---|
| TIA-232-F 精確接收門檻 | 只有 DS83 摘要與 U1 | 取得 TIA-232-F 原文或 TI／ADI 應用筆記 |
| 1.5 stop 的取樣規定 | 本版停用（U32） | 取得器件 datasheet 或 TIA 原文後再開放 |
| 寬鬆 stop 模式（只檢查第一 stop） | 本版停用 | 若需模擬只檢查第一 stop 的接收器，另案定義其後下降緣的處理，並查目標器件行為 |
| TIA/EIA-485-A 門檻與 failsafe 文字 | 只有 R1、R3 摘要 | 取得 TIA/EIA-485-A 原文 |
| R3 的 RB 公式與 523 Ω、528 Ω 的對應 | 圖片公式未取得 | 取得 SLLA272D 圖 7-1 與 Equation 2 |
| UART 時脈容差公式與數字 | 只有 A1 標題與摘要（本次全文讀取逾時） | 重新讀取 A1 全文或其 PDF，核對本文 §4.2 的表 |
| MB1 終端與偏置段落的正確節號 | 偏置為 §3.4.6；終端節號待確認 | 核對 MB1 §3.4 完整內容 |
| D1／D0 與 A／B 的對應 | MB1 用 D0／D1，R1 用 A／B | 查 MB1 接腳表與廠商文件 |
| Modbus CRC 已知答案 | 本研究以 Python 驗算為 0xCDC5 | 以 MB1 附錄 B 的範例核對 |
| Break 長度定義（各器件） | 預設 `(1+D+P_bits+S)×T` | 查各器件或上層協定規格 |
| 自動鮑率參數（0.1、95%、1 百分點、1.5%、2%、g_min 0.3T） | 工程預設 | 以本文 §10.2 合成測試校正 |
| 示波器時基誤差量級 | 未取得 | 查示波器規格 |
| Keysight、R&S、Tektronix 解碼畫面與欄位 | 只有摘要與 TK1 轉載 | 讀取應用筆記或使用手冊 PDF 本體 |
| 1 Mbaud 等高速鮑率 | 依器件 | 查器件 datasheet |
| 9-bit 模式第 9 位的語意 | 未定義 | 依目標上層協定確認 |
| Modbus 上層（功能碼、位址、資料） | 本文不涵蓋 | 另案研究 |
| 半雙工回音規則的實際行為 | 本文提出規則 | 以實際 TX／RX 擷取驗證 |

## Codex 審查紀錄

審查方式：以唯讀 sandbox 執行 `codex exec`，審查要求見 `/private/tmp/claude-501/-Users-lianshi-Desktop-claude-cowork-------html/8b49dc01-328c-40db-82f4-b6978b04c0d5/scratchpad/codex_uart_review.md`，原始輸出見 `/private/tmp/claude-501/-Users-lianshi-Desktop-claude-cowork-------html/8b49dc01-328c-40db-82f4-b6978b04c0d5/scratchpad/codex_uart_out.txt`。

**第一輪**（共約 20 點，高 7、中 10、低 3）。Codex 確認 U01 的 0x55 位元序、U02 的 0x41 even parity、U12 的 0x1A5 位元序，以及 §4.2、§8.2 的算術正確。主要意見與處理：

| 意見 | 嚴重度 | 處理 |
|---|---|---|
| mark 長度在上升緣量測時機錯誤 | 高 | 改為上升緣記錄 mark_start，下降緣檢查（本文 §3.3） |
| 字元結束後仍處理字元內轉換，資料邊沿可能被誤當 start | 高 | 改為 FRAME 狀態，stop 中心前的轉換不參與 start 判斷（§3.3） |
| BREAK 後無恢復路徑（缺 WAIT_MARK） | 高 | 加入 BREAK_WAIT 與 BREAK_OPEN（§3.3、§5.1） |
| unknown 未貫穿狀態機，RS-485 的 ±200 mV 規則過度寬泛 | 高 | 改為三值取樣 0／1／X（§3.2、§2.3） |
| 自動鮑率有循環相依，候選不完整 | 高 | 第一階段改為與鮑率無關的過濾，再從間隔群產生候選（§6.2） |
| 「最大可擬合 T」不能消除歧義，且 T/2 論證在有誤差時不成立 | 高 | 改為啟發式，加入 frame 有效率排名與 BAUD_AMBIGUOUS（§6.2） |
| 衝突判定把正常發送誤報為 contention | 高 | 只在有 DE 證據且兩個 driver 重疊時標示（§7.1） |
| U25 的輸入與預期矛盾（9600 的 0x00 低 0.5 ms 不可能同時解出 0x00 與 stop 為 0） | 高 | 改為連續低 9.8T 的 U27，預期 FRAMING（§10.2） |
| 誤差合併的「相加」只是小誤差近似 | 中 | 補上精確式 `(a−b)/(1+b)` 與近似條件（§4.2） |
| 1.5-stop 中心定義不一致，且 1.5 stop 不是通用規則 | 中 | 1.5 stop 本版停用（§3.1、U32） |
| 8 點／位元無法保證視窗三點 | 中 | 多數決需每位元 ≥16 點，否則 LIMITED_SAMPLING（§3.2、§6.3） |
| TIMING_MARGIN 無可計算定義，孤立 0xFF 無法評估 | 中 | 定義為字元內至少 2 個資料邊沿才評估（§5.1） |
| U20、U21 的預期取決於後續波形 | 中 | 改以 ground truth 比對判定，並加入負 ε（§10.2 U20～U22） |
| SHORT_STOP 只檢查早於第一 stop 中心，無法驗證 stop 長度 | 中 | stop 起點後、中心前的下降緣記為 SHORT_STOP（§3.3、U09） |
| 「stop 錯就建議 S=2」沒有普遍理由 | 中 | 改為候選排名，不固定建議（§6.4） |
| CRC 缺少完整迴圈與已知答案 | 中 | 補上完整迴圈與已知答案 `C5 CD`（§8.4） |
| Modbus 分框缺狀態與事件模型 | 中 | 加入靜默區間表與框事件欄位（§8.3、§9.2） |
| Modbus 模式與預設 8N1 衝突 | 中 | 啟用時驗證格式，非標準標示 NONSTANDARD_FORMAT（§8.1） |
| 9-bit 與 parity 覆蓋範圍 profile 未定義 | 中 | 明定 parity 覆蓋 D 個資料位元，第 9 位由 profile 指定（§3.5） |
| 事件 schema 無法表達 unknown、缺失遮罩 | 中 | stop_ok 改為三值，bits 逐位元含品質（§9.2） |
| 部分測試案例輸入不唯一（U06、U07、U08、U14、U15） | 中 | 逐一改寫為確定的波形與判定（§10.2） |
| 測試案例缺 false start、BREAK 恢復、CRC 錯誤、t1.5／t3.5 邊界等 | 中 | 補入 U23～U32，並加入固定取樣相位規則（§10.1） |
| RS-485 來源條件被省略（偏置前提、failsafe 適用條件） | 中 | 補入來源的適用條件（§2.3） |
| 來源索引缺 URL、版號與頁碼 | 低 | 本輪未補 URL 與頁碼；已標明哪些是待確認（§1 取得限制） |
| 「典型 3 kΩ～7 kΩ」用語 | 低 | 改為資料表所列範圍（§2.2） |
| 交叉引用與符號不一致（§x 前綴、P 與長度計算） | 低 | 統一「本文 §x」與「其他文件 §x」，改用 `P_bits` |

**第二輪**（唯讀審查，約 15 點，高 4、中 8、低 2 以上）。第二輪指出的狀態機與演算法問題，主要處理如下：

| 意見 | 嚴重度 | 處理 |
|---|---|---|
| FRAME 結束後 mark 狀態未落實，背靠背字元可能漏解 | 高 | 改寫 3.3 虛擬碼：`last_rise` 於每個上升緣更新；字元區間內不判 start；不再用推算的 stop_start 代替實際 mark |
| 每個 start 都要求 mark ≥ T，拒絕合法時脈誤差（U20） | 高 | 區分 HUNT（需 mark ≥ T）與 SYNCED（start 只需在前一字元最後 stop 中心之後） |
| UNSYNCED_WAIT 候選無效時 continue，沒有消耗區間 | 高 | 無效候選消耗 `[t0, frame_end]`，之後需重新出現上升緣與 ≥ T 的 mark |
| 鮑率評分只計已產生的字元，零字元與覆蓋率未定義；錯誤鮑率可能以單一假字元勝出 | 高 | 改為 dry run：定義 N_ok、N_err、未解釋轉換比例 U，並設 N_ok ≥ 2 的證據下限與 INSUFFICIENT_EVIDENCE（6.2） |
| 鮑率階段固定 8N1，會誤判 8E1／8O1 的 parity 位元 | 中 | 鮑率與格式聯合評估（6.2、6.4） |
| S = 2 嚴格模式的 stop 取樣與游標不完整 | 中 | 停用寬鬆模式（3.1、12）；區間延伸至最後 stop 中心（3.3 第 7 點） |
| 初始低電平區段、capture-end、BREAK_OPEN 的處理未在虛擬碼中 | 中 | 加入擷取起點 UNSYNCED 區段與擷取結束處理（3.3） |
| U07a 的 stop 起點條件不足 | 中 | 明定擷取起點恰為 stop 起點、前方 mark 為 1T（U07a） |
| U18、U19 的預期無法唯一推得 | 中 | 改為以 popcount 與 parity 位元排除 E，列出候選 {N, O}；U19 改為 INSUFFICIENT_EVIDENCE（U18、U19） |
| U20～U22 未明定 Rrx、Rtx、取樣時刻 | 中 | 明定 Rtx = Rrx(1+ε)、取樣時刻 (k+0.5)Trx，並依公式推得 U20～U22 的預期（U21、U22 只判定第 1 個字元） |
| U28 與「無 idle」的描述矛盾 | 中 | 改為 mark 恰為 1T 的 U28，與 U05（保持 idle 2T）分開 |
| U29 無法唯一判為 break | 中 | 明定低電平已達 Tb 才為 BREAK_OPEN，否則 TRUNCATED（U29） |
| RS-485 X 規則（多數決 vs 任一位元） 不一致 | 中 | 字元中任一資料或 parity 位元為 X，字元值為 null（2.3、5.1） |
| 8O1 被標為非標準，與 MB1 不符（MB1 允許 odd） | 中 | 8E1、8O1、8N2 皆為合法格式（8.1） |
| t1.5 邊界的 `≥`／`>` 不一致 | 中 | 框內條件改為 `≤ t1.5`，無效區間為 `(t1.5, t3.5)`（8.3） |
| 「單一字元無法區分 E 與 O」過度絕對 | 低 | 補上邊界與 parity 位置已知的前提（5.4） |
| `|a|+|b|` 不是保守界限 | 低 | 改用精確展開與最壞情況 `2A/(1−A)`（4.2） |

本輪第二輪高嚴重度意見已依虛擬碼與演算法修正。仍需注意：狀態機與自動偵測的正確性仍只是書面推演，需以實作後的合成測試（本文 §10.2）驗證；本研究未執行第三輪審查，原因是兩輪上限已用盡。

仍未完全消除的風險：自動鮑率演算法與 BREAK 之後的假同步規則都是本研究提出的啟發式，尚未以實際波形驗證；U21、U22 以 ground truth 比對判定，需實作後才能確定預期值。
