# 示波器離線分析工具：SPI 解碼研究與實作規格

研究日期：2026-10-26。範圍：從已擷取的類比電壓－時間序列，被動離線解碼 SPI 事務（transaction）與字組（word）。本文件不實作程式，不定義示波器內建解碼命令。與 `docs/研究_數位解碼協定定義.md` 的關係：該文 §5 為 SPI 概要；§2.1 取樣率、§9 事件欄位、§10 架構本文僅引用不重抄。「解碼成功」只表示擷取資料符合所選參數，不代表元件相容性或規格通過。

## 0. SPI 沒有單一正式標準

SPI 是業界慣例（de facto）。Motorola 提出的 SPI、後續 Freescale／NXP 的 SPI 手冊、各 MCU 參考手冊與周邊 IC 資料表，用詞與細節並不完全一致。Wikipedia 明言 SPI 沒有 formal standard，因此符合性無法用單一規範驗證 [W1]。Linux 核心的 SPI 框架是軟體介面與傳輸模型，不是電氣或時序規範 [K1]。

**本文的判定原則**：
1. 四種 CPOL／CPHA 組合與 CS 低有效是最常見的預設，本文以此為主。
2. CS 極性、字長、位序、3-wire、Dual／Quad 屬於「器件 profile」，由使用者或器件資料表指定，解碼器不得猜成唯一答案。
3. 時序 ns、最高速率、電壓等數值只能引用器件資料表；本文不給通用數字。

## 1. 來源索引（本文使用的代號）

| 代號 | 來源 | 用途與查閱狀態 |
|---|---|---|
| W1 | Wikipedia，Serial Peripheral Interface（英文），查閱 2026-10-26 | 模式表（CPOL/CPHA、取樣與移位緣）、無正式標準、SS 低有效、3-wire、Dual／Quad 概述。百科，作彙整引用，不是規範 |
| K1 | Linux kernel 文件，SPI 驅動 API，docs.kernel.org/driver-api/spi.html，查閱 2026-10-26 | `mode` 定義資料時脈方式；SPI_CS_HIGH（預設 active low）；SPI_LSB_FIRST（預設 MSB）；`tx_nbits`／`rx_nbits` 的 1／2／4／8 線；`cs_change` 於訊息中途使 CS 暫時解除。頁面未逐一定義 CPOL／CPHA 邊緣，須以 W1 核對 |
| MC1 | Microchip 線上手冊 §1.4.1「Mode 0」說明，查閱 2026-10-26 | Mode 0 採樣／移位描述；文件識別待確認（審查者指出疑為 AVR151 應用筆記，尚未核對）。僅作單一器件實例 |
| M-BG | Motorola／Freescale，SPI Block Guide（2000 原版、2004 修訂）。NXP 社群附件 PDF 版本（`motorola_freescale_nxp_spi_manual_2000.pdf`）經 Codex 審查補查，指出其 §4.3–4.4 描述奇／偶緣與 CPHA 首位元；**本文作者未獨立核對全文，頁碼待人工確認** |
| S1 | Analog Devices，Introduction to SPI Interface，Analog Dialogue，2018，analog.com／articles／introduction-to-spi-interface | 與既有文件 §1 相同；模式表與本文一致（既有文件已引用） |
| S2 | Analog Devices，AN-1248 SPI Interface，analog.com／app-notes／an-1248 | 既有文件引用。本作者搜尋未找到原文，Codex 審查稱可由該頁取得並支持「資料可能於取樣緣後延遲更新」與「SPI 無正式標準」描述；**內容待人工核對，頁碼未定** |
| AN-877 | ADI，Interfacing to High Speed ADCs via SPI | 搜尋摘要所見，含 2-wire 與 3-wire 選項；未逐頁核對 |
| R-DS | Rigol DS4000 SPI 解碼選單描述，經銷商產品頁轉述（TEquipment） | 4 通道、CS 極性與通道、SCLK 取樣緣、MISO／MOSI 各自通道與極性、Data Bits 4–32、Endian 預設 MSB；CS 為 OFF 時於 SCLK 轉態取樣。**非原廠手冊，待確認** |
| O3 | Rohde & Schwarz RTM User Manual，§11.3.4、Table 11-1 | 既有文件 §9 已引用；Codex 審查確認其表格欄位為 Source、Length、Data、State。其中 State 是 frame 狀態，不是 CS 狀態 |
| KS | Keysight，I2C／SPI 觸發與解碼資料表 5990-3925（2014） | PDF 本體無法擷取文字，**SPI 欄位未核對，待確認** |
| F-SG／F-RG | 論壇討論：Siglent SDS800X 無 CS 解碼示範；Rigol DS1054Z 逾時分框 | 非一手，僅說明個別產品行為，不作通用規則 |
| L1 | Nordic sQSPI 功能頁（nrfconnectdocs.nordicsemi.com） | 3-wire half-duplex 的器件實例；Codex 審查指出未定位到具體版本與頁面，**僅作為例子，不作依據** |

## 2. 實體層與訊號定義

### 2.1 常見 4 線配置

| 訊號 | 方向（以主機端為準） | 作用 |
|---|---|---|
| SCLK | 主機輸出 | 位元時脈 |
| MOSI（SDI 於從機端） | 主→從 | 主機送出資料 |
| MISO（SDO 於從機端） | 從→主 | 從機送出資料 |
| CS／SS（nCS） | 主→從 | 選取從機並界定一次事務 |

SDI／SDO 是相對器件的命名，接線時須以「MOSI＝主機輸出」為準，避免把主機 SDI 誤接為 MOSI。單端 CMOS 居多，共同 GND。未被選取的從機 MISO 常為高阻態；未選取期間 MISO 的資料不予檢查（見 §4）。W1 指出 SS 低有效、高為未選取；K1 亦以 active low 為驅動層預設。〔W1, K1〕

### 2.2 CPOL／CPHA 與四種模式

W1 的模式表（CPOL 為高位元、CPHA 為低位元）與既有文件 §5.1 一致：

| 模式 | CPOL | CPHA | SCLK 閒置 | 取樣緣（sample） | 移位緣（shift） | 第一位元的要求 |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 低 | 上升（第一個邊緣） | 下降 | 第一位元須在第一個上升緣之前已穩定 |
| 1 | 0 | 1 | 低 | 下降（第二個邊緣） | 上升（第一個邊緣） | 第一個上升緣為移位緣；取樣在第二個邊緣（下降） |
| 2 | 1 | 0 | 高 | 下降（第一個邊緣） | 上升 | 第一位元須在第一個下降緣之前已穩定 |
| 3 | 1 | 1 | 高 | 上升（第二個邊緣） | 下降（第一個邊緣） | 第一個下降緣為移位緣；取樣在第二個邊緣（上升） |

說明：
- **取樣緣由 CPOL 與 CPHA 共同決定**，不能記成「CPHA=0 就是上升緣」。W1 的 Mode 2、3 即 CPOL=1 時取樣緣翻為下降。〔W1〕
- **CPHA=0**：第一個 SCLK 邊緣即取樣緣，第一位元在 CS 有效後、第一個取樣緣之前就必須穩定。W1 對 Mode 0 的描述為：CS 下降時即輸出 MSB。〔W1, MC1〕
- **CPHA=1**：第一個 SCLK 邊緣為移位緣，第二個為取樣緣。〔W1〕

文字時序示意（非比例，實際以量測為準）：

```
Mode 0 (CPOL=0, CPHA=0)
CS_n  ‾‾‾\_______________________________/‾‾‾
SCLK  ____|‾‾|__|‾‾|__|‾‾|__ ...     取樣=上升緣, 改變=下降緣
MOSI  ==== b7 ===|== b6 ==|== b5 ==|   首位元在第一上升緣前穩定

Mode 3 (CPOL=1, CPHA=1)
CS_n  ‾‾‾\_______________________________/‾‾‾
SCLK  ‾‾‾‾|__|‾‾|__|‾‾|__|‾‾ ...       移位=下降緣, 取樣=上升緣（第二邊緣）
```

### 2.3 位序、字長與多線

- **位序**：MSB first 為常見預設；K1 將 LSB first 列為覆寫預設的選項，表示兩者在實際軟體與器件中並存。〔K1〕
- **字長**：8 或 16 bit 是常見實例，但非通用規定；字長屬於器件命令層。R-DS 解碼器接受 4–32 bit（經銷商轉述）。〔R-DS〕
- **Dual／Quad SPI**：W1 指出 Dual 以 2 條資料線、Quad 以 4 條資料線，每 clock 傳 2 或 4 bit，通常為半雙工。K1 以 `tx_nbits`／`rx_nbits` 表示。〔W1, K1〕指令、位址與資料階段的線數可不同，屬器件規格（本文 §3.6 待確認）。
- **3-wire（半雙工）**：MOSI 與 MISO 合併為一條雙向線，方向由器件協議或回合（turnaround）切換。W1 指出多數控制器不支援，但可用軟體模擬。〔W1〕 Nordic sQSPI 功能頁描述 half-duplex 為三線、傳送後切為接收的配置，但本作者未能定位具體版本與頁面，僅作為待核對的器件例子。〔L1，待核對〕 Linux 社群一份 2013 年的 device tree 提案曾建議以 `spi-single` 取代 `spi-3wire`，屬歷史提案，不作實作依據。

## 3. 解碼狀態機

### 3.1 輸入假設

- 每個通道先經 §2 所述門檻判定，得到邏輯位準與 edge 列表（時間、方向、前後位準）。
- 解碼器消費 edge 與邏輯位準，不直接使用電壓。
- 使用者設定：SCLK、MOSI、MISO、CS 通道（MOSI 或 MISO 可缺一）；CS 極性；CPOL、CPHA；字長 W；位序；框界模式（CS-framed／CS-less）；3-wire 方向規則；去毛刺門檻 Dg（見 §4）。
- 解碼器可以從已擷取的第一個樣本開始，因此必須處理「初始狀態未知」的情況（見 3.3）。

### 3.2 取樣／移位邊緣表

```
mode  CPOL CPHA  sample_edge   shift_edge
 0     0    0    RISING        FALLING
 1     0    1    FALLING       RISING
 2     1    0    FALLING       RISING
 3     1    1    RISING        FALLING
```

對 CPHA=0：第一個 sample_edge 即第一位元的取樣點。對 CPHA=1：第一個 shift_edge 不取樣，第一個 sample_edge 即第一位元（亦即 SCLK 的第二個邊緣）。

### 3.3 CS-framed 狀態機（主要模式）

```
procedure OPEN_TXN(truncated, align):      // 兩種開框路徑共用
  open transaction T; record CS_start (或視窗起點)
  bit_count = 0; value_L = 0, known_L = 0 for L in {MOSI, MISO}   // 必須清空
  word_align = align                       // KNOWN 或 UNKNOWN
  truncated_start = truncated
  state = ACTIVE
  check the SCLK level and the first SCLK edge after opening:
      若與 CPOL 或預期方向不符，記 PHASE_UNCERTAIN（候選取樣保留，但不宣稱首位元可靠）

init:
  if CS 在視窗起點為有效:
      OPEN_TXN(truncated = TRUNCATED_START, align = UNKNOWN)
  else:
      state = IDLE

on CS edge to active (state == IDLE):
  OPEN_TXN(truncated = false, align = KNOWN)

on SCLK sample_edge while ACTIVE:
  // CPHA=1 時第一個 SCLK 邊緣是移位緣，不屬於 sample_edge，自然不被取樣
  sample MOSI and MISO into the current word:
      for each line L in {MOSI, MISO} that is configured:
          if level == 0 or 1: value_L[bit_count] = level; known_L[bit_count] = 1
          else:                value_L[bit_count] = 0;    known_L[bit_count] = 0  // X
  bit_count++
  if bit_count == W:
      emit WORD(value_MOSI, known_MOSI, value_MISO, known_MISO, order, t_start, t_end)
      reset word buffers and bit_count = 0

on SCLK edge (non-sample) while ACTIVE: ignore for bit logic (used only for timing checks)

on SCLK edge while IDLE: record CLK_OUTSIDE_CS (informational; see §4)

on CS edge to inactive while ACTIVE:
  if bit_count > 0: emit INCOMPLETE_WORD(bit_count, partial buffers)
  close transaction T (status derived from word events); state = IDLE

on end-of-window while ACTIVE:
  if bit_count > 0: emit INCOMPLETE_WORD(bit_count, partial buffers) with reason TRUNCATED_END
  close transaction T with reason TRUNCATED_END
```

**位序**：LSB first 時，`value[bit_count]` 的權重改為 `1 << bit_count`；MSB first 時改為 `1 << (W-1-bit_count)`。兩種情況都應以位元陣列保存，避免整數位移與 X 相互干擾。

**並行 MOSI／MISO**：在同一取樣緣讀兩線，同一 bit 索引配對。若只設定一條資料線，另一欄為 N/A，不補 0。

**CS 外的 SCLK**：記 `CLK_OUTSIDE_CS` 為資訊事件，不影響任何字組。共享匯流排上的 SCLK 可能服務其他器件，因此預設不是錯誤，只有在 profile 規定時才升級。

**CS 有效中時脈停頓**：是否允許，取決於器件。本研究未取得可引用的通用規定，待確認。預設記為 `CLK_GAP` 資訊事件，使用者可啟用「嚴格連續」規則。

### 3.4 CS-less 模式（無 CS 線）

沒有 CS 時，框界只能由 SCLK 的閒置時間決定。框的開始必須在「閒置後的第一個 SCLK 邊緣」判定，而不是在第一個取樣緣：

```
state = IDLE
last_edge_time = none

// 事件依時間順序處理：edge、timer、EOF。下一個 edge 到達前，若 timer 已到期，先處理 timer。
on timer expiry (now - last_edge_time > T_idle) while ACTIVE:
  if bit_count > 0: emit INCOMPLETE_WORD(bit_count, partial buffers)
  close transaction T; state = IDLE

on any SCLK edge:
  if state == IDLE:
      OPEN_TXN(truncated = false, align = UNVERIFIED)   // 清空 buffers、bit_count = 0
  if this edge is a sample_edge:
      sample MOSI/MISO as in 3.3
      bit_count++
      if bit_count == W:
          emit WORD(...)
          clear buffers; bit_count = 0                  // 必須重置，否則第二字組永遠不會輸出
  last_edge_time = t

on end-of-window while ACTIVE:
  process any timer expiry before the window end (依時間順序)
  if bit_count > 0: emit INCOMPLETE_WORD(TRUNCATED_END)
  close transaction T with reason TRUNCATED_END
```

**CPHA=1 注意**：閒置後第一個邊緣為移位緣，它會開框並重置計時器；取樣從下一個邊緣開始。此時若開框條件只看取樣緣，會漏掉該框。〔研究判斷，Codex 審查指出〕若框的開始邊緣與 CPOL 不符（例如非閒置位準的長停頓之後），標 `PHASE_UNCERTAIN`，與 §3.3 相同。

**T_idle 的可用條件**：

- 必須滿足 `最大框內無邊緣間隔 < T_idle < 最小框間無邊緣間隔`。若兩者無法分離，CS-less 分框不可靠，應標示 `FRAMING_UNRELIABLE` 並拒絕自動分框。
- 實作時 `T_idle` 由使用者指定，建議以擷取中量得的 gap 分佈直方圖協助選擇；不提供固定比例公式。
- CS-less 模式下 `word_align` 只能在框的起點確定，框內若有缺漏，後續字組全部錯位。因此 CS-less 結果一律標示 `ALIGN_UNVERIFIED`。

### 3.5 3-wire（半雙工）

- 單一資料線上方向必須由使用者的 profile 決定，不得由訊號推斷。
- profile 應逐階段定義：位元數、方向（write／read）、turnaround 週期（跳過的 SCLK 數）、dummy 週期、字長，以及方向切換時是否重置 word。
- 不定義時，直接套用 3.3 會把 turnaround 或 dummy 週期錯收為資料。此時應輸出無方向的原始位元流與 `DIRECTION_AMBIGUOUS`，不得輸出方向標籤。
- 方向切換點標 `TURNAROUND` 事件，記錄切換前後的 SCLK 數。

### 3.6 Dual／Quad（本版範圍）

- 本版只支援 SDR（每個取樣緣一個位元）的單線模式；Dual／Quad 只保留為規格待確認項目。
- 若將來支援，profile 須明列 IO0–IO3 的通道映射、每條線的 bit 權重、指令／位址／資料階段的線數與 dummy 週期，以及 W 不是 k（線數）整數倍時的處理。
- 在 profile 未定義前，解碼器只輸出各線原始 bit，不做組字。

## 4. 錯誤與異常

| 情況 | 偵測方式 | 標示與處置 |
|---|---|---|
| 不完整字組（CS 內 bit 數不是 W 的倍數） | CS 解除或窗口結束時 bit_count > 0 | `INCOMPLETE_WORD`，保留已取得的 bit 與時間範圍；不補零 |
| CS 內時脈數不符（如 W=8，CS 內取樣數 20） | 事務結束時取樣總數 mod W ≠ 0 | 同上；另加 `CLK_COUNT_MISMATCH` 於事務層 |
| 擷取從中途開始（初始 CS 已有效） | §3.3 init | 事務標 `TRUNCATED_START`；字組對齊 `ALIGN_UNKNOWN`；不計入完整事務統計 |
| 擷取在 CS 有效中結束 | §3.3 窗口結束 | `TRUNCATED_END`；已完整的字組保留，剩餘 bit 為 INCOMPLETE_WORD |
| 去毛刺（脈寬 < Dg 的 edge 對） | edge 配對後量脈寬 | `GLITCH`。移除成對 edge 後重建電平，並保留原始與過濾後事件。若過濾改變了 bit 值，該字組標 `limited` |
| CS 毛刺（CS 有效或解除的脈寬 < Dg） | 同上 | `CS_GLITCH`；預設不開啟新事務，使用者可選擇寬容模式 |
| 取樣時資料線為 X（落在中間區、缺值或擷取中斷） | 門檻判定 | 該 bit 的 `known` 為 0，WORD 標 `limited`，不可稱「正確解碼」 |
| 建立／保持不足 | 量測 data edge 與 sample edge 相對時間 | `SETUP_MARGIN_LOW` 警告，附量測值；需使用者提供器件規格才可判定違規 |
| CS 外的 SCLK | §3.3 IDLE 分支 | `CLK_OUTSIDE_CS` 資訊事件；不為錯誤 |
| 未選取期間 MISO 的資料 | — | 不檢查其有效性；不得由電壓判定高阻或浮動，因為上拉線也可能呈現有效 1 |
| 3-wire 方向不明 | §3.5 | `DIRECTION_AMBIGUOUS` |

**不宣稱的錯誤**：SPI 本身沒有 ACK、NACK、CRC、parity 或長度欄位。沒有器件 profile 時，不得標 `NACK`、`CRC error` 或 `parity error`。〔W1；既有文件 §5.2〕

**錯誤分類**（沿用既有 `valid / limited / invalid`）：
- `valid`：完整事務、完整字組、無 glitch、所有參數已由使用者確認。
- `limited`：有截斷、CS-less 對齊未驗證、3-wire 方向依規則推定、有 X、去毛刺改變了值，或參數為自動建議未經確認。
- `invalid`：僅用於 profile 明確定義的違規。本工具無 profile 時不輸出 `invalid`。

## 5. 參數與自動偵測

### 5.1 使用者必填或確認

| 參數 | 預設 | 說明 |
|---|---|---|
| SCLK、MOSI、MISO、CS 通道 | 無 | MOSI 或 MISO 可單獨缺一 |
| 各線門檻與遲滯 | 中點候選 | 沿用既有文件 §2；遲滯中間區保持前態，初始化或缺值時為 X |
| CS 極性 | active low | W1, K1 |
| CPOL、CPHA | 自動建議，使用者確認 | 見 5.2 |
| 字長 W | 8 | 8、16 為常見實例，須依器件設定 |
| 位序 | MSB | K1、R-DS 預設 MSB |
| 框界模式 | CS-framed | CS-less 需 T_idle |
| 3-wire、Dual／Quad | 關閉 | 需 profile |
| 最短關注脈寬 Ts | 由取樣率推算 | 解析度參數，見 5.3 |
| 去毛刺門檻 Dg | 與 Ts 相同 | 濾波參數，獨立於 Ts |

### 5.2 自動偵測建議（僅供確認，不覆寫使用者設定）

1. **CS 極性**：若擷取中 CS 有明確的切換，且在無傳輸期間閒置為高，建議 active low。若 CS 全程為單一位準，回報 `CS_CONSTANT` 並保留使用者設定，不自動視為 CS-less。
2. **CPOL**：在 CS 確定未選取且 SCLK 穩定的區間，量測閒置位準。閒置低建議 CPOL=0，閒置高建議 CPOL=1。使用的區間必須與目標 CS 邊界相關，列出觀測數與一致性；若無可靠閒置區間，保留 CPOL 歧義。共享 SCLK 可能服務其他器件，控制器也可能在切換器件時改變模式。
3. **CPHA**：對每個候選（CPHA=0／1），在每個候選取樣點分別量測兩個距離，分線統計：(a) 距前一次資料轉態的 setup（資料已穩定多久）；(b) 距後一次資料轉態的 hold（取樣後資料維持多久）。排除 X 位元與 CS 外的轉態。若某候選的 setup 與 hold 都明顯足夠，該候選取得支持。若資料在取樣緣附近轉態，不能單靠「貼近取樣緣」扣分，因為合法的短 hold 也會如此。S2 指出資料可能在取樣緣之後才更新，因此「資料改變應落在移位緣」不是硬規則。〔S2，本輪網頁核對支持此例外，待人工核對〕兩候選都合理、或缺少器件 setup／hold 限制時，標 `CPHA_AMBIGUOUS`。統計門檻（最少事件數、容差）未經驗證，列為待確認。
4. **字長 W**：以 CS-framed 完整事務的取樣數為輸入，輸出候選集合（例如 {8, 16, 32}）。整除性只能排除不可能的候選，不能決定唯一 W。計數應排除截斷與時脈不確定的事務。需要獨立的 word 邊界或已知命令才能確定。
5. **位序**：不可由訊號自動判定。預設 MSB；若使用者提供已知命令位元組，才可比對 MSB／LSB 候選。
6. **3-wire 方向**：不可自動判定。

所有自動結果都附依據欄位（例如「CS 未選取期間 SCLK 閒置低，觀測 N 次」），由使用者確認後才寫入設定。

### 5.3 取樣率與濾波參數

依既有文件 §2.1，SPI 每 SCLK 週期 ≥ 10 點，推薦 20–50 點。本文補充：

- **Ts（最短關注脈寬）** 是解析度參數：應由使用者指定，或取 SCLK 半週期與 CS 最短脈寬之較小者。Fs 須滿足 `Fs ≥ 4 / Ts`，使最短關注脈寬有約 4 點。這是工程可觀測性建議，不代表器件會拒絕更短脈衝。
- **Dg（去毛刺門檻）** 是處理參數，獨立於 Ts。Dg 過大會刪除合法脈衝，過小則放過毛刺。去毛刺不應被當成器件行為的證明。
- 若要驗證 setup／hold，取樣率與探棒頻寬須足以量測器件規格中的最小值。具體 ns 數值依器件資料表，本文不提供。
- 例：SCLK 10 MHz、每週期 20 點 → 200 MSa/s。此為工程估計，非來源規範值。

## 6. 事件表與標註列呈現

### 6.1 事件表欄位

共用欄位依既有文件 §9：`index、bus、t_start、t_end、duration、raw sample range、status、reason、profile 版本`。SPI 專用欄位：

| 欄位 | 說明 |
|---|---|
| Transaction ID | CS 有效區段（或 CS-less 框）的序號 |
| Level | `TXN`（事務）、`WORD`（字組）、`EVT`（錯誤或資訊事件） |
| Word index | 事務內字組序號，從 0 起 |
| Mode | CPOL／CPHA 組合，如 `M0`，並標示來源（使用者設定／自動建議） |
| Word bits (W) | 字長 |
| Order | MSB 或 LSB |
| MOSI／MISO | 字組值，含 `value`（數值）、`known_mask`（哪些 bit 已確定）、`observed` 與 `known` 的計數 |
| Display | hex、bin、dec 可選；含 X 的字組以遮罩表示（例如 `0x5?`），不得強行給整數 |
| Direction／line | `MOSI`、`MISO`、`WIRE`（3-wire）、`SDR`（本版） |
| Bits observed／known | 取樣次數與確定次數，區分「收滿但含 X」與「不完整」 |
| Status、reason | `valid`、`limited`、`invalid` 與原因代碼 |

事件表與標註列以同一 event ID 連結，點選可跳到對應 raw sample 範圍。事務狀態由其下屬的 WORD 與 EVT 彙整，事件依時間排序。〔既有文件 §9；O1、O3 的時間聯動〕

### 6.2 標註列（annotation）

- 時間軸上方或下方的 bus 列：CS 有效區段以括號標示；每個字組為一格，格內顯示 hex（MOSI 與 MISO 分列或雙值一格）。
- 縮小只顯示事務與字組；放大展開每個 bit，標示取樣點與資料有效範圍。
- 錯誤與警告以顏色與符號標示於發生的時間區段（例如不完整字組為灰色段），不只用一個紅色「fail」。
- 原始值（hex 與遮罩）必須保留，即使顯示 ASCII 或 dec。

既有文件 §9 已列 O3 的 SPI 欄位（Source、Data 等）。R-DS 的設定項可作參考，但本文不宣稱其事件表有 CS 狀態欄；CS 狀態是本工具的新增欄位。〔O3, R-DS；UI 結構為實作建議〕

## 7. 實作步驟

1. 讀入各線 edge 列表，依 Dg 處理毛刺並保留原始事件。
2. 依 CPOL、CPHA 決定 sample_edge 與 shift_edge（§3.2）。
3. 檢查視窗起點：若 CS 已有效，開啟 TRUNCATED_START 事務（§3.3 init）。
4. 依 CS 極性產生 CS 區段；區段外的 SCLK 記資訊事件。
5. 區段內依 sample_edge 取樣 MOSI／MISO，累積 `value`、`known_mask`，滿 W 輸出 WORD。
6. CS 解除或視窗結束時，輸出 INCOMPLETE_WORD 與事務摘要。
7. 無 CS 時改用 §3.4 的框界規則，並以 `ALIGN_UNVERIFIED` 標示。
8. 3-wire 或 Dual／Quad 依 profile 處理；無 profile 時輸出原始位元流。
9. 寫入事件表，附 raw sample range 與 status。
10. 自動偵測（§5.2）只在使用者要求「建議」時執行，不得覆寫使用者設定。

**單元驗證**：以 §8 測試案例逐一比對，並加入已知 TX 資料的隨機位元序列做交叉檢查。

## 8. 合成測試波形案例清單

除非另註，SCLK 為規則方波，CS 為 active low，時間與資料已知。預期為事件序列。

| # | 輸入描述 | 預期解碼事件 |
|---|---|---|
| T1 | Mode 0，W=8，MSB，CS 內 1 個字組，MOSI 線上序列 `10010110`，MISO 線上序列 `00101101` | TXN(1)；WORD(0) MOSI=0x96、MISO=0x2D，status valid |
| T2 | Mode 3，同上資料 | 同 T1（驗證 CPOL=1 取樣緣） |
| T3a | Mode 1，同上資料 | 同 T1（CPHA=1，CPOL=0，取樣在第二邊緣） |
| T3b | Mode 2，同上資料 | 同 T1（CPHA=0，CPOL=1，第一個下降緣即取樣） |
| T4 | 同 T1 的線上序列，但設定 LSB first | MOSI=0x69、MISO=0xB4（位序反轉） |
| T5 | W=16，CS 內 2 字組，中間 CS 不解除 | 2 個 WORD，word index 0、1 |
| T6 | 同 T5，但字組間 CS 解除再有效 | 2 個 TXN，各含 1 WORD |
| T7 | W=8，CS 內只有 12 個取樣 | WORD(0) 完整；INCOMPLETE_WORD(4 bits)；CLK_COUNT_MISMATCH |
| T8 | 初始視窗起點 CS 已有效，之後完整傳輸 1 字組 | TXN 標 TRUNCATED_START；第一個完整字組的 word_align 為 ALIGN_UNKNOWN，值正常輸出 |
| T9 | SCLK 中加入脈寬 < Dg 的單一 glitch | GLITCH；WORD 值不受影響 |
| T10a | CS 有效前出現脈寬 < Dg 的短脈衝 | CS_GLITCH；不開啟事務 |
| T10b-a | CS 有效期間的解除脈衝，Dg 去毛刺模式（移除脈寬 < Dg 的 CS 邊緣對） | CS_GLITCH；被移除的解除脈衝不結束事務，事務含後續傳輸 |
| T10b-b | 同上，但設定為「保留 CS 短脈衝並分框」模式 | 事務於解除處結束；後續傳輸為新事務，並標 CS_GLITCH |
| T11a | 初始 MISO 停在門檻中間區（缺值）開始 | 該 bit 的 known=0，WORD 標 limited |
| T11b | 已知前態下 MISO 進入中間區再回到前態，無邏輯轉態 | 保持前態，不產生 X，不產生事件；類比裕量警告不在本案範圍 |
| T12 | CS-less，框內最大無邊緣間隔小於 T_idle，框間間隔大於 T_idle | 兩個 TXN，WORD 正常，標 ALIGN_UNVERIFIED |
| T12b | CS-less，同一框內連續 16 個取樣，W=8 | 兩個 WORD（index 0、1），第二字組正確輸出，無誤報的 INCOMPLETE_WORD |
| T13a | CS-less，某框內在字組中途（已有 3 個殘留位元）停頓超過 T_idle | 該框截斷，INCOMPLETE_WORD(3 bits)；後續框重新開始 |
| T13b | CS-less，某框在整字邊界（殘留 0 位元）停頓超過 T_idle | 框結束，不輸出 INCOMPLETE_WORD |
| T14 | CS-less、CPHA=1，框起始為閒置後的移位緣，且起始位準符合 CPOL | 框於移位緣開啟；第一位元取自下一個取樣緣，無遺漏 |
| T14b | CS-less、CPHA=1，框起始邊緣與 CPOL 不符（例如非閒置位準） | 框標 PHASE_UNCERTAIN，字組值保留但不宣稱首位元可靠 |
| T15 | 3-wire，profile 指定 1 位元組 write、1 個 turnaround SCLK、1 位元組 read | WRITE WORD、TURNAROUND、READ WORD；方向依 profile |
| T16 | 3-wire，未提供 profile | DIRECTION_AMBIGUOUS；輸出原始位元流，無方向標籤 |
| T17 | 只接 MOSI，無 MISO | MISO 欄位 N/A；MOSI 正常輸出 |
| T18 | 自動偵測：CS 未選取期間 SCLK 閒置高，實際 Mode 2 | 建議 CPOL=1 並附觀測數；CPHA 依 §5.2(3) 統計建議 |
| T19 | 自動偵測：資料更新緊貼取樣緣，兩候選都無穩定窗 | CPHA_AMBIGUOUS，不提供確定值 |
| T20 | 自動偵測：CS 全程有效（CS_CONSTANT） | 不建議 CS 極性，不切換為 CS-less |
| T21 | W=12（非 8 倍數），CS 內 24 個取樣 | 2 個 WORD，每個 12 bit；字長無對齊錯誤 |
| T22 | 全 0 或全 1 的 MOSI，CPOL 無法由閒置推定 | CPOL 建議標不確定，不因資料全 0／1 而推論 |
| T23 | 擷取視窗在 CS 有效中結束，且恰好收滿 W 位 | WORD 完整輸出；事務標 TRUNCATED_END；無 INCOMPLETE_WORD |
| T24 | Dual／Quad 段（本版未支援） | 只輸出原始 bit，不組字，標 `UNSUPPORTED_MODE` |

**待補充的測試資料**：目前沒有經原廠解碼器驗證的黃金樣本。各案的「預期」是依規則推導，應以已知 TX 資料的實機或模擬輸出交叉比對後，才納入回歸測試。

## 9. 待確認項目

| 項目 | 目前狀態 | 需要的確認 |
|---|---|---|
| Motorola SPI Block Guide 的 CPOL／CPHA 原文 | 經 NXP 附件 PDF 的審查者摘要支持；本作者未核對頁碼 | 人工核對 §4.3–4.4 的文字與頁碼 |
| AN-1248 內容 | 既有文件引用；作者未核對 | 人工開啟 analog.com 頁面，確認資料更新時序與無正式標準的文字 |
| MC1 文件身分 | 疑為 AVR151，待核對 | 確認原文與 URL；核對其模式表與標題的矛盾 |
| Keysight 5990-3925 SPI 欄位 | PDF 無法擷取 | 人工開啟核對 |
| Rigol DS4000 原廠手冊 | 僅經銷商轉述 | 取得原廠 Decode 章節 |
| 無 CS 框界的通用規定 | 無通用來源，僅產品實例 | 以目標器件資料表為準 |
| CS 有效期間 SCLK 停頓是否允許 | 未取得通用規定 | 依器件資料表 |
| Dual／Quad 階段與組字規則 | 只有概述 | 指定器件後取其資料表 |
| 3-wire 方向與 turnaround 規則 | 只有協定概念與器件實例 | 依目標器件 profile |
| 器件建立／保持時間與 SCLK 最高速率 | 未查 | 依使用者器件資料表 |
| CPHA、CPOL、CS 極性自動偵測的統計門檻 | 研究啟發式，未驗證 | 以合成與實機資料交叉驗證後定案 |
| Microchip 模式 1 閒置位準的摘要 | 先前摘要有誤，本文不採用 | 以 W1 表與 MC1 原文核對 |

## 10. 結論

- 四模式由 CPOL（閒置位準）與 CPHA（取樣相位）決定，表格與 W1、既有文件一致，可直接實作。
- SPI 的正確性無法由波形本身證明。沒有 CRC 或命令 profile 時，不同模式可產生看似合理的位元組。因此本工具提供「建議」而非「確定」，並保留原始 bit 與 raw sample 範圍。
- 最優先的範圍：CS-framed、單線（MOSI 或 MISO）、Mode 0–3、位序與字長由使用者指定、支援截斷與 X 的標示。其次為 CS-less（需要驗證 T_idle 可分離）與並行 MOSI／MISO。3-wire 與 Dual／Quad 等有器件 profile 後再做。

---

## Codex 審查紀錄

**第 1 輪**（唯讀，`codex exec --sandbox read-only`）。主要意見與處理：

- 高：CPHA=1 文字歧義（「第二個 sample_edge」）→ 已改為「第二個 SCLK 邊緣即第一個 sample_edge」。
- 高：截斷（初始 CS 已有效、窗口結束）未進狀態機 → 已加入 init 與 end-of-window 分支，新增 TRUNCATED_START／END 測試（T8、T23）。
- 高：首邊緣假設未驗證 → 加入起始 SCLK 位準檢查與 PHASE_UNCERTAIN。
- 高：CS-less 開框條件漏掉 CPHA=1 → 改為在閒置後第一個 SCLK 邊緣開框（T14）。
- 高：CPHA 自動偵測條件寫反 → 改為資料更新緊貼取樣緣時扣分，兩者皆不穩定時 CPHA_AMBIGUOUS（T19）。
- 高：X 無法套用整數偽碼 → 改用 value＋known_mask＋observed／known 計數。
- 高：T4 測試值錯誤（0xA5 反轉仍為 0xA5）→ 改用不對稱序列 `10010110` → 0x96 與 0x69。
- 中：CS_UNUSED 不當 → 改為 CS_CONSTANT；CPOL 推定加入觀測數與歧義；字長整除改為候選集合；CS-less 逾時改為可分離條件（不提供固定比例公式）。
- 中：Wmin 混合解析度與濾波 → 拆為 Ts 與 Dg。
- 中：unknown 與遲滯衝突 → 區分 X 與中間區前態。
- 中：high-Z 不應由電壓判定 → 移除。
- 中：CS 外時脈不應一律警告 → 改資訊事件。
- 中：3-wire 缺階段規則 → 加入 turnaround、dummy、階段字長的 profile 要求。
- 中：Dual／Quad 組字規則不足 → 本版限 SDR，其餘列為待確認。
- 中：事件模型無法保存 X → 加入 observed／known 與遮罩顯示。
- 中：部分測試案例不完整 → 拆分 T3a／b、T10a／b、T11a／b，補 T21–T24。
- 中：MC1 來源身分 → 改為「疑為 AVR151，待確認」。
- 中：AN-1248、Block Guide 待確認狀態 → 補上審查者提供的連結，並標明本作者未核對全文。
- 中：Nordic、Linux 2013 patch 的歸因過強 → 降為器件實例與歷史提案，不作依據。
- 中：R-DS／O3 的 CS 狀態欄歸因錯誤 → 改為 O3 State 為 frame 狀態，CS 狀態為本工具新增欄位。
- 中：部分數值主張（8／16 最常見、LSB 亦常見）→ 改為「常見實例」。
- 低：來源代號可重現性、K1 措辭、交叉引用與 SDI／SDO 命名 → 已修正或註明。

**第 2 輪**（唯讀）。主要意見與處理：

- 高：初始 CS 已有效的截斷路徑未清空 buffers／bit_count → 新增共用 OPEN_TXN 程序，兩條開框路徑都清空；T8 改為「收滿 W 位的候選字組」，且維持 ALIGN_UNKNOWN，不因收滿 W 位而視為對齊恢復。
- 高：CS-less 輸出 WORD 後未重置 → 偽碼明列 emit 後清空並 bit_count=0；新增 T12b。
- 中：CPHA=1 首邊緣前提未涵蓋正常 CS 開框與 CS-less 中途開始 → 每次開框檢查邊緣位準與方向，不符標 PHASE_UNCERTAIN；新增 T14b。
- 中：timer 與 edge、EOF 的先後順序 → 明定依時間順序處理，timer 先於下一 edge 與 EOF；T13 拆為 T13a（字組中途停頓）與 T13b（整字邊界停頓）。
- 中：§5.2(3) 以對稱距離混合 setup 與 hold → 改為分別量測 setup 與 hold，分線統計，排除 X 與 CS 外轉態；兩候選皆合理時 CPHA_AMBIGUOUS。
- 中：T10b 的寬容設定與 Dg 過濾順序不清 → 拆為 T10b-a（移除解除毛刺）與 T10b-b（保留並分框）。
- 中：T11b 的「必有裕量警告」無規則支持 → 預期改為保持前態、不產生 X、不產生事件；類比裕量警告列為範圍外。
- 中：Nordic 正文語氣過強 → 改為「待核對的器件例子」。
- 低：來源處理紀錄與實際連結不完全相符 → 本輪未另補 M-BG 與 S2 的完整直接連結；M-BG 僅為檔名，AN-1248 的直接 URL 已列於 §1，但內容的人工核對仍待確認。**此項未完全處理，列為待確認**。

第 2 輪的兩項高嚴重度意見已全部修正；低嚴重度的來源連結項目未完全處理，已列入 §9 待確認。依規定上限兩輪，本文未進行第 3 輪審查。
