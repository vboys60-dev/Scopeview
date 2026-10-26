# 示波器離線分析工具：I2C 解碼研究

研究日期：2026-10-26。範圍：`scope_tool/` 未來從類比電壓－時間序列被動離線解碼 I2C，涵蓋 Standard／Fast／Fast-mode Plus／Hs／UFm 的時序與訊框、7-bit 與 10-bit 位址、General Call、Device ID、clock stretching、Hs 切換，並說明 SMBus 的差異與 PEC。本文件不定義示波器內建解碼命令，不實作程式。

本文「解碼成功」只表示擷取資料符合所選解析規則，不代表電氣或協定相容性認證。數值均由 UM10204 與 SMBus 3.1 原文表格核對；未能核對者標「待確認」。

與「總研究」（`docs/研究_數位解碼協定定義.md`）的關係：總研究 §4（I2C）、§9（呈現欄位）、§10（實作建議）已給概要。本文補充可直接實作的完整時序表、訊框與位址流程、狀態機、異常表與測試案例；與總研究重複處僅為必要的重述，原始定義以總研究為準。

## 0. 來源與口徑

沿用總研究來源代號：

| 代號 | 來源 | 本文使用方式 |
|---|---|---|
| I1 | NXP UM10204，I²C-bus specification and user manual，Rev. 7.0，2021-10-01 | 主規範。以 `pypdf` 抽出 PDF 文字層（62 頁）後逐表核對 |
| O2 | Keysight N8843A I3C 解碼資料表（總研究） | 呈現欄位參考 |
| O3 | R&S RTM User Manual（總研究） | I2C 解碼欄位（R/W、ID）參考 |
| O4 | R&S UART/RS232 軟體頁（總研究） | 列表與標註參考 |

本次新增來源：

| 代號 | 來源 | 取得狀態 |
|---|---|---|
| X1 | SMBus Specification Version 3.1，System Management Interface Forum，2018（[smbus.org](https://smbus.org/specs/SMBus_3_1_20180319.pdf)） | 已下載並抽文字（85 頁）；timeout、延展、Table 2 AC 規格、邏輯位準、10-bit、PEC、ARA、Host Notify 取自此版 |
| X2 | Tektronix，How to Troubleshoot System Problems Using Oscilloscope I2C and SPI Decoding（[tek.com 應用說明](https://www.tek.com.cn/documents/application-note/how-troubleshoot-system-problems-using-oscilloscope-i2c-and-spi-decoding)） | 僅搜尋摘要，未開原文。只用於「7-bit＋R/W 與 8-bit 分組兩種顯示」的說明 |
| X3 | Keysight 5989-1250 Infiniium I2C/SPI 觸發與解碼資料表（[連結](https://www.keysight.com/us/en/assets/7018-01228/data-sheets/5989-1250.pdf)） | 僅搜尋摘要，未開原文。只用於「事件表以時間戳列出封包、缺 ACK 以紅色標示」的描述 |

**未取得**：SMBus 3.2（搜尋未找到）、PMBus 規格、X2 與 X3 的原文 PDF。

## 1. I2C、SMBus 與 PMBus 差異

I2C 是實體與位元協定；SMBus 與 PMBus 在 I2C 硬體上加上命令層與額外規則。解碼器應以「I2C 框架＋SMBus 協定 profile」實作，而非獨立寫一套位元解析。〔來源：I1 §4.2、§4.2.1；X1 §4.2〕

| 項目 | I2C（I1） | SMBus 3.1（X1） | 解碼器處置 |
|---|---|---|---|
| SCL 頻率 | Standard 0–100、Fast 0–400、Fm+ 0–1000、Hs 0–3400 kHz | fSMB 10–100／400／1000 kHz 三個 Class（Table 2） | SMBus profile 以 `fSMB,MIN = 10 kHz` 檢查；10 kHz 下限適用於主控時鐘與週期性延展，不適用 idle。單次非週期延展不能據此判定低於下限 |
| 超時 | 無統一 timeout（I1 §4.2.2） | `tTIMEOUT` 25 ms（最小）～35 ms（最大）；指「單一 clock 低期間」的判定與復位窗（Table 2 註 3） | I2C profile 只報告低期間長度；SMBus profile 才標 timeout 候選（見 §5.3、§11 T29、T30） |
| Clock 延展 | 位元層與 byte 層皆可（I1 §3.1.9） | Slave 累計延展 `tLOW:SEXT ≤ 25 ms`，為 START 到 STOP 之間的累計量；master 每 byte 累計 `tLOW:MEXT ≤ 10 ms`（Table 2 註 5、6） | 見 §5.1 |
| 邏輯位準 | VIL = 0.3VDD、VIH = 0.7VDD（I1 Table 10） | `VIL,max = 0.8 V`、`VIH,min = 1.35 V`（X1 Table 4；VIH 的最大值欄為 VDD） | 門檻由使用者設定；SMBus 預設採固定 0.8 V／1.35 V |
| 位址 | 7-bit 與 10-bit 皆可 | 使用 7-bit；`1111 0XX X` 之 10-bit 位址保留供未來使用，超出 SMBus 3.1 範圍（X1 §6.2.2.9） | 看到 10-bit 前綴時可保留 I2C 解析，但標示超出 SMBus 3.1 範圍；保留位址見 §4.1 |
| 特殊位址 | 見 I1 Table 4 | ARA `0001 100b`（讀方向線上 header `0x19`）、Host Notify `0001 000b`（寫方向線上 `0x10`）（X1 §6.2.2.6、§6.5.9、附錄 A） | 見 §4.1、§4.6 |
| 錯誤檢查 | I2C 無 CRC | 每筆交易可選 PEC：CRC-8，多項式 `x⁸+x²+x+1`，依接收位元序計算（X1 §6.4.1.3） | 見 §9.2 |

未取得原文的項目：PMBus 命令表與 ALERT 細節（I1 §4.3 僅有概述）；SMBus 3.2 版本差異。

## 2. 實體層與時序參數

### 2.1 SDA／SCL 與門檻

SDA、SCL 為共地雙向單端線，傳統 I2C 為 open-drain 加上拉，閒置為高。多控制器靠 wired-AND 仲裁。上拉大小依 `tr` 與 Cb 決定，不是 120 Ω 終端。〔來源：I1 §3.1.1、§3.1.2、§7.1〕

I2C 的邏輯位準以 VDD 比例給出：`VIL,max = 0.3VDD`、`VIH,min = 0.7VDD`（I1 Table 10 註腳）。Standard 雜訊容限 `VnL ≥ 0.1VDD`、`VnH ≥ 0.2VDD`（Table 11）。

**解碼器建議**（實作建議，不是規範）：
- 邊沿與脈寬量測用 50% 門檻；
- 「保證辨識區」以 `0.3VDD`／`0.7VDD` 判定，落在中間的樣本標 `unknown`，不強制翻成 0 或 1；
- 規範時序檢查（tSU、tHD 等）須依 0.3／0.7VDD 交越點量測（I1 Table 11 註 2 與 Table 13 註 1 均以 VIL／VIH 為基準）；50% 門檻只用於定位。
- 預設值由使用者覆寫。若波形無法到達 0.7VDD，應標「上拉不足或門檻不符」。〔來源：I1 Table 10–13；總研究 §2〕

### 2.2 各模式時序（抄自 I1）

以下為 UM10204 Table 11（Std／Fm／Fm+）、Table 13（Hs）、Table 15（UFm）逐列核對的結果。`—` 表示該表未列。

**Standard／Fast／Fast-mode Plus（I1 Table 11；tSP 見 Table 10）**

| 參數 | 說明 | Standard | Fast | Fast-mode Plus | 單位 |
|---|---|---:|---:|---:|---|
| fSCL | SCL 頻率上限 | 100 | 400 | 1000 | kHz |
| tHD;STA | START 後保持（重複 START 亦同） | ≥4.0 | ≥0.6 | ≥0.26 | µs |
| tSU;STA | 重複 START 建立 | ≥4.7 | ≥0.6 | ≥0.26 | µs |
| tSU;STO | STOP 建立 | ≥4.0 | ≥0.6 | ≥0.26 | µs |
| tBUF | STOP 到 START 的匯流排空閒 | ≥4.7 | ≥1.3 | ≥0.5 | µs |
| tLOW | SCL 低期間 | ≥4.7 | ≥1.3 | ≥0.5 | µs |
| tHIGH | SCL 高期間 | ≥4.0 | ≥0.6 | ≥0.26 | µs |
| tSU;DAT | 資料建立 | ≥250 | ≥100 | ≥50 | ns |
| tHD;DAT | 資料保持（自 SCL 下降緣） | ≥0 | ≥0 | ≥0 | ns |
| tr | 上升時間 | ≤1000 | 20–300 | ≤120（無最小值列） | ns |
| tf | 下降時間 | ≤300 | 20×VDD/5.5–300 | 20×VDD/5.5–120 | ns |
| tVD;DAT／tVD;ACK | SCL 低到 SDA 有效的時間上限（註 3） | ≤3.45 | ≤0.9 | ≤0.45 | µs |
| Cb | 每條線的電容 | ≤400 | ≤400 | ≤550 | pF |
| tSP | 輸入濾波抑制的脈衝寬 | —（規範未列） | 0–50 | 0–50 | ns |

Table 11 註：`tHD;DAT` 上限 Standard 3.45 µs、Fast 0.9 µs，但須小於 `tVD;DAT` 或 `tVD;ACK` 減去轉換時間，且僅在裝置不延展 tLOW 時適用（註 3）。Fast 裝置進入 Standard 系統時 `tSU;DAT ≥ 250 ns`（註 4）。Fm+ 的 tf 若含串聯保護電阻，須計入（註 7）。

**Hs-mode（I1 Table 13；tSP 見 Table 12）**

| 參數 | 說明 | Cb = 100 pF | Cb = 400 pF | 單位 |
|---|---|---:|---:|---|
| fSCLH | SCLH 頻率上限 | 3.4 | 1.7 | MHz |
| tSU;STA | 重複 START 建立 | ≥160 | ≥160 | ns |
| tHD;STA | START 保持 | ≥160 | ≥160 | ns |
| tSU;STO | STOP 建立 | ≥160 | ≥160 | ns |
| tLOW | SCLH 低期間 | ≥160 | ≥320 | ns |
| tHIGH | SCLH 高期間 | ≥60 | ≥120 | ns |
| tSU;DAT | 資料建立 | ≥10 | ≥10 | ns |
| tHD;DAT | 資料保持 | 0–70 | 0–150 | ns |
| trCL | SCLH 上升 | 10–40 | 20–80 | ns |
| trCL1 | SCLH 上升（重複 START 後與 ACK 後） | 10–80 | 20–160 | ns |
| tfCL | SCLH 下降 | 10–40 | 20–80 | ns |
| trDA／tfDA | SDAH 上升／下降 | 10–80 | 20–160 | ns |
| Cb | SDAH 或 SCLH 每線電容 | 100 | 400 | pF |
| tSP | 輸入濾波抑制 | 0–10 | 0–10 | ns |

Hs 表的 `tHD;DAT` 為最小 0、最大 70（100 pF）或 150（400 pF）。註 3：裝置須內部提供保持時間，以跨越 SCLH 下降緣的未定義區。Cb 在 100–400 pF 之間須線性內插（註 2）。

**UFm（I1 Table 15；tSP 見 Table 14）**

| 參數 | UFm |
|---|---|
| fUSCL | ≤5000 kHz |
| tBUF | ≥80 ns |
| tHD;STA、tSU;STA、tSU;STO | ≥50 ns |
| tHD;DAT | ≥10 ns |
| tSU;DAT | ≥30 ns |
| tLOW、tHIGH | ≥50 ns |
| tr、tf | ≤50 ns（典型 25 ns，30%–70%） |
| tSP | ≤10 ns |
| Cb | 待確認（本次讀取的 Table 14–15 未列） |

UFm 為單向推挽、2 線、無仲裁。第九個 clock 由控制器送高，不使用接收方 ACK；START byte 同樣不得被 ACK。〔來源：I1 §3.2、§3.2.12〕本文只列 UFm 時序；解碼流程另列為可選 profile。

### 2.3 時序說明

- `tHD;STA` 與 `tSU;STA` 在 Standard 為 4.0 µs 與 4.7 µs。`tHD;STA` 指 START 後到第一個 SCL 下降緣的時間；量測點為 SDA 下降緣到 SCL 下降緣，兩者都以 0.3／0.7VDD 交越點判定。
- `tSU;DAT` 是資料在 SCL 上升前的建立時間。解碼取樣點應位於 SCL 上升緣，且 SDA 在上升緣前至少 `tSU;DAT` 已穩定。
- `tHD;DAT` 自 SCL 下降緣起算，最小為 0。SDA 在 SCL 下降同時變化，仍須符合 Table 11 註 2：SCL 先低於 0.3VDD，SDA 才能進入未定義區。解碼器不能以「下降緣同時取樣」當成位元值。

## 3. 位元層與訊框

### 3.1 START、Sr、STOP

- START：SCL 高時 SDA 由高變低；STOP：SCL 高時 SDA 由低變高。START 與 STOP 都只由控制器產生。〔來源：I1 §3.1.4〕
- 匯流排在 START 後為忙碌；STOP 後經 `tBUF` 才回到空閒。Sr（重複 START）與 START 功能相同，只是未送 STOP。〔來源：I1 §3.1.4〕
- **START 後立即 STOP（空訊息）**：I1 §3.1.10 註 5 稱之為 **illegal format**，但許多裝置設計成可正常運作。解碼器應標示 `empty transaction / illegal format`，保留事件；裝置容忍此格式不代表格式合法。
- 解碼器的 `S` 與 `Sr` 標籤：以「前一個 START 之後是否已送 STOP」區分（實作建議）。規範本身把兩者視為功能相同。

### 3.2 位元組與 ACK

- 每個 byte 8 bits、MSB first，接收方在第 9 個 SCL 脈衝拉低 SDA 為 ACK，釋放為 NACK。〔來源：I1 §3.1.5、§3.1.6〕
- 讀取最後一個 byte 時，控制器送 NACK 後接 STOP 或 Sr，屬正常結束。〔來源：I1 §3.1.6〕
- 第 9 位在位址 byte 與資料 byte 都是 ACK slot，I2C 沒有 parity 或 T-bit。PEC 屬 SMBus profile。〔來源：I1 §3.1；X1 §6.4〕

### 3.3 位址 byte 與 R/W

- 7-bit 位址格式：`A6..A0 + R/W`，R/W = 0 表示寫，1 表示讀。〔來源：I1 §3.1.10〕
- 讀取時，目標在 ACK 後送資料，控制器在讀完最後 byte 後送 NACK 結束。
- 目標不 ACK 位址 → `address NACK`，常見於位址錯誤或目標忙碌。〔來源：I1 §3.1.6〕

### 3.4 仲裁與 clock 同步

- 仲裁：多控制器同時送 1 卻讀到 0 即失去仲裁。要判定仲裁失敗，解碼器需要知道各節點「想送的值」；只有匯流排資料時無法判定（見 §6.2、§8.2）。〔來源：I1 §3.1.8〕
- Clock 同步：控制器在 SCL 高期間應能觀察到目標延展造成的低期間。〔來源：I1 §3.1.7〕
- **Hs-mode 不做仲裁與 clock 同步**，見 §6。

## 4. 位址

### 4.1 7-bit 位址與保留位址（I1 Table 4）

| 位址 byte（8-bit） | 7-bit 位址 | R/W 位 | 用途 |
|---|---|---|---|
| `0000 000 0` | 0x00 | 0 | General call（§4.4） |
| `0000 000 1` | 0x00 | 1 | START byte（§4.5） |
| `0000 001 X` | 0x01 | X | CBUS；I2C 裝置不應回應 |
| `0000 010 X` | 0x02 | X | 為其他匯流排格式保留；僅能與其他協定混用的裝置回應 |
| `0000 011 X` | 0x03 | X | 為未來用途保留 |
| `0000 1XX X` | 0x04–0x07 | X | Hs-mode controller code（§6） |
| `1111 1000`（0xF8） | 0x7C | 0 | Device ID 讀取的寫方向前綴（§4.6） |
| `1111 1001`（0xF9） | 0x7C | 1 | Device ID 讀取的讀方向前綴（§4.6） |
| `1111 1XX 0`（其餘） | 0x7C–0x7F | 0 | 保留（Table 4 未定義用途，標 `reserved address`） |
| `1111 1XX 1`（其餘） | 0x7C–0x7F | 1 | Device ID 讀取前綴（§4.6） |
| `1111 0XX X` | 0x78–0x7B | X | 10-bit 位址前綴（§4.2） |

〔來源：I1 §3.1.12、§3.1.17、Table 4〕

Table 4 註：「已確定不會用於其原始目的時，保留位址可作為目標位址」。因此解碼器不能把保留位址的 ACK 一律判為錯誤，應標示保留狀態並保留事件。

### 4.2 10-bit 位址

10-bit 位址由前兩個 byte 組成（I1 §3.1.11）：
- 第一 byte：`1111 0 A9 A8 R/W`。第一 byte 的 bit 2、bit 1 為 A9、A8，bit 0 為 R/W。
- 第二 byte：`A7..A0`（僅在寫方向的位址 header 之後出現）。

**寫（controller-transmitter）**：`S → 11110 A9 A8 W → A1 → A7..A0 → A2 → data … → P`。R/W 不變。目標在第一 byte 的 ACK 為 A1，在第二 byte 的 ACK 為 A2。〔來源：I1 §3.1.11〕

**讀（controller-receiver）**：`S → 11110 A9 A8 W → A1 → A7..A0 → A2 → Sr → 11110 A9 A8 R → A3 → data → NACK → P`。Sr 之後**不再送第二個位址 byte**；收到的第一個 byte 是資料。Sr 後前綴的前七位須與 S 後相同，R/W = 1 時該目標成為發送端。〔來源：I1 §3.1.11（controller-receiver 條目）、Figure 15〕

**解碼規則**：
1. 第一 byte 前五位為 `11110` 時，標為 10-bit 前綴。`A9A8 = bit2..bit1`。
2. 寫方向前綴後，下一 byte 為 A7..A0。`addr10 = (A9A8 << 8) | low_byte`。
3. A1 為 NACK：標 `10-bit address NACK (A1)`，不得虛構第二個 byte。
4. A2 為 NACK：標 `10-bit low byte NACK (A2)`。
5. Sr 後的前綴：若與先前寫方向前綴的前七位相同且 R/W = 1，且 A1、A2 已完整確認 ACK、自該寫前綴之後未見 P 或指向其他目標的 Sr，判定為 10-bit 讀；ACK 後的下一 byte 為資料，**不得**再解析為位址。
6. Sr 後的 `11110 xx R` 若脈絡已失效（未完整取得兩個位址 byte、A1／A2 有 NACK、或中間出現 P 或指向其他目標的 Sr），標 `unresolved 10-bit read`，不推定位址。

### 4.3 解碼器位址顯示

呈現兩種格式（X2 摘要所述，未開原文）：
- 7-bit 位址 + 獨立 R/W 欄位（預設，與規範一致）；
- 8-bit 位址 byte（含 R/W），用於與部分儀器的預設顯示對照。

事件表內部一律存 7-bit 位址與 R/W 分開，顯示格式另外轉換。〔來源：X2 摘要；實作建議〕

### 4.4 General Call（I1 §3.1.13）

- 第一 byte：`0000 000 0`（0x00，寫）。
- 第二 byte 的 bit 0（B）決定意義：
  - **B = 0**：第二 byte 為 `0000 0110`（0x06，重設並寫入可程式位址）、`0000 0100`（0x04，寫入可程式位址但不重設）。`0000 0000`（0x00）**不允許**作為第二 byte。其餘值未定義，裝置應忽略。
  - **B = 1**：為 hardware general call。第二 byte 的高七位是送出此序列的硬體控制器自己的位址，用來識別自身。
- 裝置可選擇不 ACK 第一 byte。第二與之後的 byte 由每個能處理的目標 ACK。控制器無法知道有多少裝置回應。
- 10-bit 目標對 general call 的反應與 7-bit 相同；控制器可在 general call 後送出自己的 10-bit 位址（三 byte 形式，I1 §3.1.11）。

解碼器建議：第二 byte 為 0x06／0x04 時標名稱；為 0x00 時標 `GC second byte forbidden`；B = 1 時標 `hardware GC`，附上高七位位址；其餘值顯示十六進位 `unknown`。第二 byte 的 NACK 不一定是錯誤，因為可能沒有目標需要它。〔來源：I1 §3.1.13；實作建議〕

### 4.5 START byte（I1 §3.1.15）

START byte `0000 0001`（0x01）用於 bit-banging 或無硬體 START 偵測的多控制器系統。**任何裝置都不得 ACK START byte**，其後 Sr 才是真正位址。解碼器應：
- 標示 `START byte`；
- 若第九位得到 ACK，標 `START byte ACKed (protocol violation)`。

〔來源：I1 §3.1.15、Table 4 註 2〕

### 4.6 Device ID（I1 §3.1.17）

Device ID 為選用的 3-byte 唯讀欄位（24 bits）。正確的讀取流程為：
1. `S`
2. 控制器送 `1111 1000`（0xF8，寫）
3. 控制器送要識別的目標位址（LSB 不管）。只有該目標 ACK。
4. 控制器送 `Sr`
5. 控制器送 `1111 1001`（0xF9，讀）
6. 目標送 Device ID：前 12 bits 為製造商，接著 9 bits 為 part，最後 3 bits 為 die revision。
7. 控制器以 NACK 結束。

Device ID 讀取在 STOP 後或 Sr 後存取其他目標時會被重置。解碼器需依此狀態機判定：只有 `S → F8 → target → Sr → F9` 才標為 Device ID；其他情況不得標成 Device ID。〔來源：I1 §3.1.17〕

## 5. Clock stretching 與 bus clear

### 5.1 Clock stretching（I1 §3.1.9；X1 §5.3.3、Figure 17）

- 目標可在 SCL 低期間延展，即延長 tLOW。Standard、Fast、Fm+ 可在位元層與 byte 層延展。Hs 只能在 byte 層延展（I1 §3.1.9、§5.3.2）。
- Hs 的延展窗為 Sr 之後、以及 ACK／NACK 之後的低期間，不是任意 byte 內的低期間（I1 §5.3.2、§5.3.3）。
- SMBus 限制：slave 累計延展 `tLOW:SEXT ≤ 25 ms`；master 每 byte `tLOW:MEXT ≤ 10 ms`（X1 Table 2 註 5、6）。I2C 無此上限（I1 §4.2.2）。
- SMBus 延展應在 SCL 下降後 `tLOW:MIN − tSU:DAT` 內開始（X1 §5.3.3）。

**解碼判定**：
- 單一波形無法區分「控制器慢」與「目標延展」，也無法把延展歸屬某一裝置。解碼器只能標 `SCL low extended` 候選，並量出該段低期間。
- 位元層延展候選門檻（實作建議）：SCL 低期間超過該模式 tLOW 最小值（§2.2），且同一交易中其他位元的低期間明顯較短時，標 `long SCL low (stretch candidate)`。門檻應由使用者覆寫。
- 在 ACK 之後或 byte 邊界延展：標 `byte-boundary stretch`，附上 ACK 所屬 byte 與延展長度。
- 低期間長度於 SCL 上升緣結算（上升緣時取得 `t_rise − t_fall`）。

### 5.2 Bus clear（I1 §3.1.16）

- SCL 卡低：優先用硬體 reset，否則斷電（POR）。
- SDA 卡低：控制器送 9 個 clock，佔用者應在 9 個 clock 內釋放；未釋放則需硬體 reset 或斷電。
- 「9 個 clock」是 **bus-clear 操作程序**，不是一般故障判定門檻。合法的連續 `0x00 + ACK` 就可以跨越任意多個週期。解碼器只在有外部復原操作脈絡時標 `bus-clear candidate`。

### 5.3 卡低判定

- SCL 持續低超過 SMBus `tTIMEOUT,MIN`（25 ms）：在 SMBus profile 標 `timeout candidate`；超過 `tTIMEOUT,MAX`（35 ms）仍未恢復：標 `timeout exceeded`（X1 §4.2.2）。I2C profile 只報告持續時間。
- SDA 持續低、SCL 仍在動：標 `SDA stuck-low candidate`，不得依 25／35 ms clock timeout 判定。X1 §4.2.5 對 SDA 低期間的建議不同於 clock timeout。
- SCL 高、SDA 持續低：同上，僅報 stuck-data candidate。

## 6. Hs-mode

### 6.1 進入與退出（I1 §5.3.2、§5.3.3）

1. 在 F/S 速率下送 START，然後送 8-bit controller code `0000 1XXX`，然後第九位送 NACK。〔來源：I1 §5.3.2〕
2. Controller code 讓多個 Hs 控制器在 F/S 速率下仲裁，贏家進入 Hs。Controller code `0000 1000` 保留為測試用。〔來源：I1 §5.3.2〕
3. NACK 之後，SCLH 拉高到 `tH` 即切換為 Hs 速率；進入 Hs 後的第一個 Sr 本身即以 Hs 規格解析，其後的位址與資料亦使用 Hs 時序。Sr 維持 Hs，**STOP 才退出 Hs**，並在 Fast-mode 的最小 bus-free 時間內完成切回。〔來源：I1 §5.3.3；切換時點 `tH` 的精確數值見圖 34，待確認〕

**解碼器狀態**：`F/S → HS_ENTRY（看到 0000 1XXX + NACK）→ 以 Hs 規格解析的 Sr → HS_ACTIVE → F/S（STOP）`。

### 6.2 Hs 特性與解碼影響

- **無仲裁、無 clock 同步**（I1 §5.3）。因此 Hs 段內不輸出 `arbitration lost`。
- 無節點驅動觀測時，解碼器不能由協定禁止仲裁反推 Hs 衝突。類比異常只標 `signal anomaly`。
- Clock 延展只在 byte 層與 Sr／ACK 後的窗口內（§5.1）。解碼器對 Hs 的 SCL 低期間判定應比 F/S 嚴格。
- Hs 的 SDA 取樣使用 SCL 上升緣；tSU;DAT 只剩 10 ns，取樣點需靠近上升緣並做 setup 檢查。〔來源：I1 Table 13〕
- Hs 段 spike filter 為 10 ns（I1 Table 12），比 F/S 的 50 ns 嚴，因此 Hs 段的 glitch 判定要用 10 ns（見 §8.1）。

## 7. 解碼狀態機（可實作）

### 7.1 輸入與前處理

輸入：兩個已數位化的通道（SCL、SDA），每個樣本點有 `t`（時間）與 `level ∈ {0, 1, unknown}`。

1. 依 §2.1 門檻轉成 `0 / 1 / unknown`。連續 `unknown` 保留為 `unknown` 區段，不補值。
2. 對 SCL 與 SDA 分別建立邊沿列表：`(t, 方向, 前態, 寬度)`。
3. **保留 raw edges**。脈寬 `< tSP` 的脈衝標 `glitch candidate`。解析使用明確選定的「濾波視圖」，由該視圖產生 S／P。`tSP` 依模式：Fast 與 Fm+ 為 50 ns（I1 Table 10）；Hs 為 10 ns（I1 Table 12）；Standard 規範未列，預設採 50 ns 作為實作選項，須標示為實作建議。
4. 解碼結果記錄「濾波差異」：原始邊沿與濾波後事件不一致時，兩者都保留。

### 7.2 條件偵測與延後確認

條件（S、Sr、P）只在 SCL 高時出現。為避免控制器在 ACK 後拉高 SCL 準備 STOP 時，把該上升緣誤當成資料位元，SCL 上升時的取樣要**暫存**，直到 SCL 下降才確認。

```
pending = None                  # (t_rise, sda_sample)
on SCL 上升:
    pending = (t, SDA 目前值)   # 暫存，不計入位元
on SDA 下降 且 SCL 高:
    pending = None              # 條件優先
    emit S（若前一交易未 P 則為 Sr，見 §3.1）
    enter ADDR_BYTE；若 state = HS_ENTRY，此 Sr 以 Hs 規格解析並進入 HS_ACTIVE；若已在 HS_ACTIVE 則維持
on SDA 上升 且 SCL 高:
    pending = None
    emit P；僅當目前 byte 已收 1–7 位（bits 非空且未滿）時附 "STOP inside byte" 並截斷；byte 邊界（bits 為空，例如 ACK 之後）的 P 為正常結束
    若在 HS 中 → 回 F/S；清除交易緩衝；開始 tBUF 計時
on SCL 下降:
    若 pending 存在：commit（見 §7.3）
    pending = None
    記錄 scl_low_start = t
on SDA 變化 且 SCL 低:
    正常資料轉換；不產生條件事件
```

SDA 在 SCL 高時變化，若不是 S 或 P 的定義形式（例如脈衝寬不足、或類比波形不完整），**不是**二值協定事件。解碼器應標為類比異常（§8.2）。〔來源：I1 §3.1.4 條件定義；實作建議〕

### 7.3 位元收集與 ACK

```
commit(pending, state):
    sample_val = pending.sda_sample   # 0 / 1 / unknown
    if state ∈ {ADDR_BYTE, DATA_BYTE}:
        bits.append(sample_val)       # unknown 保留為 unknown，不轉成 0 或 1
        if len(bits) == 8: state = ACK_SLOT
    elif state == ACK_SLOT:
        if sample_val == 0:   ack = ACK
        elif sample_val == 1: ack = NACK
        else:                  ack = UNKNOWN
        emit ack（附 byte 值與方向）
        依 ack 與方向決定下一 state（§7.4、§7.5）
```

每個 byte 在 ACK slot commit 後清空 `bits`。S／Sr 重設目前 byte；P 進入 IDLE；IDLE 不 commit 資料。ACK 為 UNKNOWN 時，後續 byte 標 `limited`，不得推定 ACK 或 NACK。

setup 違規時保留觀測值與 `setup violation` 標示，不得改回較早的穩定值。SDA 在 `tSU;DAT` 窗內變化時，可信度降為 `limited`。〔實作建議〕

### 7.4 位址 byte 解析

```
if any bit is unknown: 標 `address uncertain`，保留遮罩，不進入以下分支
addr_byte = bits[0..7]          # MSB first
rw   = addr_byte & 1
addr7 = addr_byte >> 1

if addr7 == 0x00:
    if rw == 0:  標 General call；下一 byte 為 GC 第二 byte（§4.4）
    else:        標 START byte（§4.5：ACK 為違規）
elif addr7 in (0x01, 0x02, 0x03):   標保留位址（CBUS／其他格式／未來）
elif addr7 in (0x04..0x07):          標 Hs controller code（僅在 F/S 且緊接 S 時有效；NACK 後進入 HS_ENTRY）
elif (addr_byte >> 3) == 0b11110:    10-bit 前綴：依 §4.2 規則；寫方向時下一 byte 為 A7..A0
elif addr_byte == 0xF8:               Device ID 候選（需由 §4.6 完整流程確認）
elif addr_byte == 0xF9 and 有完整 F8／目標／Sr 脈絡: Device ID 資料
elif addr7 in 0x7C..0x7F:              其餘保留（§4.1）
else:                                普通 7-bit 位址
```

Hs controller code 判定依 §6.1。`rw` 不適用於 Hs controller code。

### 7.5 資料 byte 與交易結束

- 寫交易：`ADDR(W) → (DATA + ACK)* → S/Sr/P`。
- 讀交易：`ADDR(R) → (DATA + ACK)* → NACK（控制器結束）→ S/Sr/P`。
- 10-bit 讀：寫方向前綴與第二 byte 之後，Sr 後的前綴（R 方向）之後直接是資料（§4.2）。
- 無 ACK 的資料 byte（DATA NACK）：標 `data NACK`，後續資料仍照常解析。I2C 不會因一個 NACK 自動 STOP。
- 讀取時目標送的資料 byte 第九位為控制器的 ACK／NACK；控制器 NACK 表示結束。

### 7.6 擷取中途開始

若擷取從 byte 中途開始，首個完整 byte 之前的資料無法確定位元對齊。解碼器應：
- 等待第一個 START（S 或 Sr）後才開始解析；
- 在對齊前的區段標 `misaligned segment`，不推定位址；
- 若擷取在交易中途開始且沒有 S，標 `capture starts mid-transaction`；
- 已知位址與方向時，後續 byte 可解析，但不能推定 Hs 模式。

## 8. 錯誤與異常

### 8.1 Glitch 與 spike filter

- I1 規定 Fast、Fm+ 的輸入濾波抑制 `< 50 ns` 雜訊脈衝（Table 10 註 8）；Hs 為 10 ns（Table 12）；UFm 為 10 ns（Table 14）。Standard 規範未列抑制時間。
- 解碼器的 `glitch candidate` 規則：`pulse_width < tSP_mode` 的脈衝標為 glitch，依 §7.1 的濾波視圖處理，原始邊沿保留。
- **同一脈衝在不同模式下結果不同**。例如 20 ns 的 SDA 脈衝發生於 SCL 高期間：
  - Fast／Fm+（tSP 50 ns）：視為 glitch，不產生 S／P，標 `glitch candidate`；
  - Hs（tSP 10 ns）：20 ns 超過濾波限度，濾波視圖會把它當成 S 或 P，但仍標 `short SDA transition while SCL high (Hs)`，供人工確認；
  - Standard：依使用者選定的實作濾波（預設 50 ns），結果與 Fast 相同，並標示為實作選項。

### 8.2 異常表

| 情況 | 偵測 | 標示 | 來源／依據 |
|---|---|---|---|
| 位址 NACK | 位址 byte 第九位為 1 | `address NACK` | I1 §3.1.6 |
| 資料 NACK（寫） | 資料 byte 第九位為 1 | `data NACK` | I1 §3.1.6 |
| 讀取結束 NACK | 控制器讀完最後 byte 後送 NACK | `read end NACK`（正常） | I1 §3.1.6 |
| 缺 STOP（擷取結束） | 擷取結束時交易仍開啟，且未見 P | `truncated / open transaction` | 實作建議 |
| 正常 Sr | 資料 ACK 後出現 SDA 下降 + SCL 高 | `Sr`（合法，不是缺 STOP） | I1 §3.1.4、§3.1.10 |
| byte 中 STOP／START | 在 ADDR 或 DATA 收集中出現 P 或 S | `STOP inside byte` 或 `START inside byte` | I1 §3.1.4 |
| 空訊息 | S 後立即 P | `empty transaction / illegal format` | I1 §3.1.10 註 5 |
| SDA 在 SCL 高時變化，非 S/P 形式 | 脈衝寬不足或類比不完整 | `signal anomaly`（類比異常，非協定事件） | 實作建議 |
| SCL 低期間延展 | 低期間超過模式 tLOW 門檻（§5.1） | `stretch candidate` | I1 §3.1.9 |
| SCL 持續低 | 低期間超過 tTIMEOUT,MIN | SMBus：`timeout candidate`；I2C：只報告時長 | X1 Table 2 註 3 |
| SDA 持續低、SCL 動 | SDA 低期間長，SCL 仍有脈衝 | `SDA stuck-low candidate` | X1 §4.2.5 |
| bus clear | 有外部復原操作脈絡 | `bus-clear candidate` | I1 §3.1.16 |
| 建立／保持違規 | 量測 tSU;DAT、tHD;STA 等 | `setup violation`、`hold violation` | I1 Table 11–13 |
| tLOW、tHIGH 不足 | 量測 SCL 脈寬 | `tLOW violation`、`tHIGH violation` | I1 Table 11–13 |
| 頻率超過模式上限 | 量測 SCL 週期 | `speed mode exceeded`（依使用者模式判定） | I1 Table 11–13 |
| START byte 被 ACK | START byte 的第九位為 0 | `START byte ACKed (protocol violation)` | I1 §3.1.15 |
| General call 第二 byte 異常 | 第二 byte 為 0x00 或未定義值 | `GC second byte forbidden／unknown` | I1 §3.1.13 |
| 10-bit 位址 NACK | A1 或 A2 為 NACK | `10-bit address NACK (A1／A2)` | I1 §3.1.11 |
| Hs 段衝突跡象 | Hs 段內類比波形異常 | `signal anomaly (Hs)`，不得標 arbitration lost | I1 §5.3 |
| 仲裁失敗 | 只有節點驅動值可判定 | 無節點驅動觀測時不輸出 | I1 §3.1.8 |

## 9. 使用者參數、自動偵測與取樣率

### 9.1 使用者參數

| 參數 | 預設 | 說明 |
|---|---|---|
| SCL／SDA 通道 | 必填 | 兩者必須有共同時間基準 |
| 門檻 V↓／V↑ | 0.3VDD／0.7VDD（I2C）；0.8 V／1.35 V（SMBus） | 見 §2.1、§1 |
| 速率模式 | 使用者選擇 Std／Fm／Fm+／Hs | 決定 tLOW、tHIGH 等檢查門檻 |
| 位址格式 | 7-bit | 可選 10-bit 或自動 |
| 顯示格式 | 7-bit＋R/W | 可選 8-bit 含 R/W |
| 協定 profile | I2C | 可選 SMBus（啟用 PEC、timeout、ARA、Host Notify） |
| glitch 策略 | 報告，不濾波 | 可選依 tSP 濾除（但 S／P 仍由 §7.1 的濾波視圖決定，並記錄差異） |
| Hs 切換 | 自動偵測 | 可強制 F/S-only 或 Hs |
| 延展門檻 | 依 §5.1 的預設 | 使用者可覆寫 |

### 9.2 可自動偵測

- Clock 頻率與 tLOW、tHIGH 候選（由 SCL 邊沿）。
- S、Sr、P 位置（由 SDA 與 SCL 條件）。
- 位址 byte、R/W、ACK／NACK。
- 10-bit 前綴與 Sr 後讀方向（§4.2）。
- General call、START byte、保留位址、Device ID 流程（§4.6）。
- Hs controller code（`0000 1XXX` + NACK）。
- Clock stretch 候選。
- ARA 與 Host Notify（SMBus profile）。

**PEC（SMBus profile）**：CRC-8，多項式 `0x07`，初值 `0x00`，依位元接收順序。X1 規定 PEC 涵蓋從第一個 START 起的整筆訊息，包含所有位址、命令與資料 byte；不含 ACK／NACK，也不含 START、STOP、Repeated START 條件本身，因此**跨 Sr 持續累計、不重設**。PEC 是否存在由交易類型、協定與裝置設定決定；未知時只標 `PEC candidate`，不直接報 mismatch。〔來源：X1 §6.4.1–6.4.1.3〕

標準檢查值：`CRC-8("123456789") = 0xF4`，本次以 Python 腳本驗證。

### 9.3 不應自動斷言

- 控制器與目標的實體身分（誰送出、誰仲裁失敗）。
- Hs 切換是否真的發生在硬體層（只能由 controller code 推論）。
- Clock 延展是否由目標造成（與控制器慢無法區分）。
- SMBus timeout 是否為故障（需要使用者設定）。
- 10-bit 位址的目標身分（只看到位址，未看到目標 ID）。
- 仲裁是否失敗（需要節點驅動值）。

### 9.4 建議最低取樣率

依總研究 §2.1 的原則：每 SCL 週期 ≥10 點，最短高脈衝 ≥4 點；glitch 檢查另加 `Fs ≥ 4 / tSP`。

| 模式 | 最高 SCL | SCL 週期 | 每週期 10 點 | 最短 tHIGH 4 點 | 建議 Fs |
|---|---|---|---|---|---|
| Standard | 100 kHz | 10 µs | 1 MSa/s | 4.0 µs → 1 MSa/s | ≥5 MSa/s；做 50 ns glitch 檢查需 ≥80 MSa/s |
| Fast | 400 kHz | 2.5 µs | 4 MSa/s | 0.6 µs → 6.7 MSa/s | ≥10 MSa/s |
| Fm+ | 1 MHz | 1 µs | 10 MSa/s | 0.26 µs → 15.4 MSa/s | ≥20 MSa/s；glitch 檢查 ≥80 MSa/s |
| Hs（3.4 MHz） | 3.4 MHz | 294 ns | 34 MSa/s | 60 ns → 66.7 MSa/s | ≥100 MSa/s；10 ns spike 檢查需 ≥400 MSa/s |
| UFm（5 MHz） | 5 MHz | 200 ns | 50 MSa/s | 50 ns → 80 MSa/s | 不列入主範圍 |

上表與總研究 §2.1 的 I2C 列一致；`4/tSP` 的估計為本研究工程判斷。〔來源：I1 Table 10–15；總研究 §2.1〕

## 10. 事件表與標註列

### 10.1 事件欄位

所有事件共用總研究 §9 的欄位（`index、bus、t_start、t_end、duration、raw sample range、decoded value、status、reason、profile 版本`）。I2C 專用欄位：

| 欄位 | 內容 | 例 |
|---|---|---|
| type | `START`／`Sr`／`STOP`／`ADDR`／`DATA`／`ACK`／`NACK`／`GC`／`START_BYTE`／`HS_CODE`／`DEVID`／`ARA`／`HOSTNOTIFY`／`CONDITION_ERR`／`STRETCH`／`ANOMALY` | `ADDR` |
| addr7 | 7-bit 位址（僅位址事件） | 0x50 |
| rw | 0 寫、1 讀（獨立欄位） | W |
| addr10 | 10-bit 位址（僅 10-bit 事件） | 0x2A5 |
| byte | 8-bit 值（十六進位與二進位皆保留） | 0x12 |
| ack | `ACK`／`NACK`／`unknown` | NACK |
| mode | `Std`／`Fm`／`Fm+`／`Hs`／`UFm` | Hs |
| scl_low_ms | SCL 低期間長度（延展候選） | 2.0 |
| pec | `no PEC`／`PEC ok`／`PEC mismatch`／`PEC candidate` | PEC ok |
| status | `ok`／`limited`／`invalid`，沿用專案既有規則 | limited |
| reason | 異常原因文字（對應 §8.2 標示） | address NACK |

### 10.2 標註列呈現（參考 O2、O3、X2、X3）

- 波形上方或下方一列 bus 標註：`S | Addr 0x50 W | ACK | 0x12 | ACK | 0x34 | NACK | P`。縮小時只顯示 transaction 與 byte，放大才展開 bit、ACK、R/W。〔來源：總研究 §9；O2 摘要〕
- 表格列：`index / time / S / Addr / R/W / ACK / Data / Status`（參考 O2 的 Index、Time、S、Addr、R/W、ACK、Data；O3 的 I2C 含 R/W 與 ID）。
- 缺 ACK 以紅色標示，搜尋結果可匯出 CSV（X3 摘要，未開原文）。
- 點選事件跳回波形，事件與標註以同一 event ID 連結。〔來源：總研究 §9 尾段〕
- 錯誤與警告分色：`status = invalid` 紅，`limited` 黃，`ok` 灰或綠（實作建議）。

## 11. 合成測試波形案例

預設 Standard 100 kHz，除非另註。位元以 MSB first 列出；位址 byte 寫為「8-bit 值（addr7, R/W）」。

| ID | 輸入描述 | 預期解碼事件 |
|---|---|---|
| T01 | 寫：`S → 0xA0（addr7=0x50, W）→ ACK → 0x12 → ACK → 0x34 → ACK → P` | START；ADDR 0x50 W ACK；DATA 0x12 ACK；DATA 0x34 ACK；STOP |
| T02 | 寫後 Sr 讀：`S → 0xA0 → ACK → 0x00 → ACK → Sr → 0xA1（addr7=0x50, R）→ ACK → 0xAB → NACK → P` | START；ADDR 0x50 W ACK；DATA 0x00 ACK；Sr；ADDR 0x50 R ACK；DATA 0xAB NACK（read end）；STOP |
| T03 | 位址 NACK：`S → 0xD0（addr7=0x68, W）→ NACK → P` | START；ADDR 0x68 W NACK（`address NACK`）；STOP |
| T04 | 資料 NACK：`S → 0xA0 → ACK → 0x10 → NACK → P` | DATA 0x10 NACK（`data NACK`），之後 STOP |
| T05 | 合法 combined format：`S → 0xA0 → ACK → 0x12 → ACK → Sr → 0xA1 → ACK → 0x34 → NACK → P` | 第二個 START 標 `Sr`，**不得**標 `missing STOP`；交易正常完成 |
| T06 | 擷取在 `Sr` 後截止，無 P | 交易標 `truncated / open transaction`；不得僅憑 Sr 判缺 STOP |
| T07 | 10-bit 寫：`S → 0xF4（11110 10 W）→ A1 ACK → 0xA5 → A2 ACK → 0x77 → ACK → P`（addr10=0x2A5） | START；ADDR10 0x2A5 W（A1、A2 ACK）；DATA 0x77 ACK；STOP |
| T08 | 10-bit 讀：`S → 0xF4 → A1 ACK → 0xA5 → A2 ACK → Sr → 0xF5（11110 10 R）→ A3 ACK → 0x34 → NACK → P` | ADDR10 0x2A5 W；Sr；ADDR10 0x2A5 R ACK；**DATA** 0x34 NACK（read end），不得把 0x34 當成第二位址 byte |
| T09 | 10-bit 位址 NACK：`S → 0xF4 → NACK → P` | `10-bit address NACK (A1)` |
| T10 | 10-bit 低位址 NACK：`S → 0xF4 → ACK → 0xA5 → NACK → P` | `10-bit low byte NACK (A2)` |
| T11 | General call reset：`S → 0x00（W）→ ACK → 0x06 → ACK → P` | START；GC；GC second byte 0x06（reset）ACK；STOP |
| T12 | General call 第二 byte 為 0x00：`S → 0x00 → ACK → 0x00 → ACK → P` | `GC second byte forbidden` |
| T13 | START byte：`S → 0x01 → NACK → Sr → 0xA0 → ACK → P` | START_BYTE NACK（正確）；Sr；ADDR 0x50 W ACK；STOP |
| T14 | START byte 被 ACK（違規）：`S → 0x01 → ACK` | START_BYTE ACKed（`protocol violation`） |
| T15 | Hs：F/S 送 `S → 0x09（0000 1 001）→ NACK`，SCL 3.4 MHz，tHIGH 60 ns，接 `Sr → 0xA0 → ACK → 0x12 → ACK → P` | START；HS_CODE 0x09 NACK；Sr 後進入 HS；ADDR 0x50 W ACK；DATA 0x12 ACK；STOP 後回 F/S。Hs 段不輸出 `arbitration lost` |
| T16 | Hs 中延展：T15 中在 Sr 之後的 ACK 後把 SCL 低延長 0.5 ms | `STRETCH 0.5 ms`，位於 Hs 允許的延展窗；資料不變 |
| T17 | 延展：T01 中在**位址** byte 的 ACK 後把 SCL 低延長 2 ms | ADDR 0x50 W ACK 後 `STRETCH 2.0 ms`；資料與 ACK 不變 |
| T18 | 20 ns SDA 脈衝發生於 SCL 高期間，解碼採 Fast 或 Fm+ 的 50 ns 濾波視圖 | `glitch candidate`；濾波視圖不產生 S 或 P；原始邊沿保留 |
| T19 | 同 T18，但解碼採 Hs 的 10 ns 濾波視圖 | 20 ns 超過 10 ns 限度，濾波視圖產生 S 或 P，並標 `short SDA transition while SCL high (Hs)`，供人工確認；原始邊沿保留 |
| T20 | SDA 在 byte 中間（SCL 高）上升 300 ns 後再下降 | `STOP inside byte`（P 被保留）截斷目前 byte；隨後的 SDA 下降（SCL 高）產生 S 候選；raw 事件保留 |
| T21 | 擷取從第 4 bit 開始：前 4 bit 之前無 START | 第一段標 `misaligned segment`，不推定位址；等到下一個 START 再解碼 |
| T22 | 時序：tLOW = 3 µs（Standard）與 tSU;DAT = 100 ns（Standard） | `tLOW violation`（≥4.7 µs）與 `setup violation`（≥250 ns）；兩者都保留 |
| T23 | （已知使用 PEC）SMBus PEC 寫：`S → 0xA0 → ACK → 0x12 → ACK → 0x66（PEC）→ ACK → P`，SMBus profile | DATA 0x12 ACK；DATA 0x66 ACK，`PEC ok`。改 PEC 為 0x67 時標 `PEC mismatch` |
| T24 | （已知使用 PEC）SMBus PEC 讀：`S → 0xA0 → ACK → 0x12 → ACK → Sr → 0xA1 → ACK → 0x34 → ACK（控制器）→ 0x0A（PEC）→ NACK（控制器）→ P` | `PEC ok`；I2C profile 下標 `PEC not checked` |
| T25 | Device ID：`S → 0xF8 → ACK → 目標位址 byte（LSB 不管）→ ACK → Sr → 0xF9 → ACK → ID0 → ACK → ID1 → ACK → ID2 → NACK → P` | DEVID 讀取序列完成；12 bits 製造商、9 bits part、3 bits revision 分欄顯示 |
| T26 | ARA（SMBus profile）：`S → 0x19（0001 100 1，讀）→ ACK（目標）→ 0x50 → NACK（控制器）→ P`，回應位址以 7-bit 位於高位 | `ARA`；回應位址 `0x50 >> 1 = 0x28`；最低位依 X1 附錄 A.2 解讀 |
| T27 | Host Notify（SMBus profile）：`S → 0x10（0001 000 0，寫）→ ACK → [來源 7-bit 位址＋0] → ACK → [狀態低 byte] → ACK → [狀態高 byte] → ACK → P` | `HOSTNOTIFY`；來源位址與 16-bit 狀態（低 byte 先送）；無 PEC 變體（X1 §6.4、§6.5.9） |
| T28 | SCL 持續低 30 ms（I2C profile） | `SCL held low 30 ms`，不標 timeout |
| T29 | 同 T28，但 SMBus profile | 超過 25 ms `tTIMEOUT,MIN` 標 `timeout candidate`；未達 35 ms 前恢復則保留事件 |
| T30 | SCL 高、SDA 持續低 30 ms | `SDA stuck-low candidate`；**不得**標 tTIMEOUT |
| T31 | 空訊息：`S → P`（無位元） | `empty transaction / illegal format`；不標 byte 中斷 |
| T32 | 正常結束：T01 尾端 DATA 0x34 的 ACK 之後拉高 SCL 產生 P | 正常 STOP，**不得**標 `STOP inside byte` |
| T33 | ACK slot 電壓位於 0.3–0.7 VDD 之間 | ACK = UNKNOWN；後續 byte 標 `limited`，不推定 ACK 或 NACK |
| T34 | T07 寫前綴與 A1、A2 ACK 後插入 P，接著 `S → 0xF5` | `unresolved 10-bit read`；`0xF5` 不得視為 10-bit 讀延續 |
| T35 | 位址 byte 第 3 bit 位於 unknown 區 | `address uncertain`，不進入 GC、Device ID 或 10-bit 分支 |

T23 與 T24 的 PEC 值是以 Python 依 CRC-8（多項式 `0x07`、初值 0）算出：`[0xA0, 0x12] → 0x66`；`[0xA0, 0x12, 0xA1, 0x34] → 0x0A`。兩者僅用於本文測試案例內部一致性，不是 SMBus 規範範例。CRC 演算法本身以 `"123456789" → 0xF4` 驗證。〔來源：X1 §6.4.1.3；本次計算〕

## 12. 待確認項目

| 項目 | 目前狀態 | 需要的動作 |
|---|---|---|
| UFm Cb 上限 | 本次未在 Table 14–15 讀到 | 查 UM10204 §6.3 前後說明或 errata |
| Hs 切換時點 `tH` 的數值 | §5.3.3 說明 `tH` 為切換時點，數值見圖 34 | 讀圖 34 |
| SMBus 3.1 VIH 欄位 | 已採 VIH,min = 1.35 V、最大值欄 VDD（X1 Table 4） | 無 |
| SMBus 3.2 | 搜尋未找到 | 查 smbus.org 最新版號並比對 timeout、PEC 章節 |
| PMBus 規格 | 未取得 | 取 PMBus 原文，確認命令表、ALERT 與 PEC 與 SMBus 的關係 |
| PEC 與 Sr 的關係 | 已由 X1 §6.4.1 確認：跨 Sr 持續累計 | 無 |
| ARA 回應位址最低位 | X1 附錄 A.2（Figures 65–66） | 逐圖確認位元定義 |
| Host Notify 欄位順序 | X1 §6.5.9 與 Figure 41 | 逐圖核對 16-bit 狀態的低高 byte 順序 |
| Device ID 的 I2C 位址對應 | 依 I1 §3.1.17 流程 | 對照 I1 圖 20 逐位元 |
| 10-bit 讀的 Sr 比對 | 依 I1 §3.1.11 文字與 Figure 15 | 逐圖核對 |
| Keysight／Tek 事件表欄位 | 只見搜尋摘要 | 開 X2、X3 原文 PDF |
| 時序量測門檻基準 | 本文採 50% 定位、0.3／0.7VDD 判規範 | 依實際示波器量測做 CSV 驗證 |

## Codex 審查紀錄

### 第一輪（唯讀審查，原始輸出：scratchpad/codex_i2c_out.txt）

| 主要意見 | 處理 |
|---|---|
| 空訊息寫成「合法」；I1 §3.1.10 註 5 原文為 illegal format | §3.1、§8.2 改為 `empty transaction / illegal format` |
| T05 的正常 Sr 被誤標 missing STOP | T05 改為合法 combined format；缺 STOP 只在擷取結束時判定（T06） |
| Fm+ tr 無最小值；tf 最小值漏列；Standard 規範未列 tSP | §2.2 依 Table 10–11 修正 |
| 50% 門檻與規範時序判定混用 | §2.1、§2.3 分開：50% 定位，規範時序以 0.3／0.7VDD 交越點判定，並引用 Table 11 註 2 |
| SMBus 邏輯位準、10-bit 保留、延展適用條件寫錯或不完整 | §1 修正（原以為 1.35 VDD 為乘積，第二輪確認為最小 1.35 V）；10-bit 保留依 X1 §6.2.2.9；延展依 Table 2 註 5、6 分別說明 |
| Device ID 寫入階段遺漏 | 新增 §4.6，依 I1 §3.1.17 完整流程 |
| 10-bit 讀在 Sr 後誤把資料當第二位址 byte | §4.2、§7.4、§7.5、T08 修正 |
| glitch 規則自相矛盾；T13 不應套同一門檻 | §7.1、§8.1 改為保留 raw edges，依模式分別定義 |
| ACK 後為 STOP 拉高 SCL 會被誤當資料位元；ACK 只有二態 | §7.2 改為上升緣暫存、下降緣確認；§7.3 改三態 ACK |
| 9-clock 規則是 bus-clear 程序，不是故障門檻 | §5.2 改寫；SDA 卡低不套 tTIMEOUT（§5.3） |
| PEC 觸發條件未定 | §9.2 改為未知時只標 candidate |
| UFm 第九 clock 不 ACK；Hs 仲裁不可由 SCL／SDA 推論 | §2.2、§3.4、§6.2、§8.2 修正 |
| General Call B=1 高七位、第二 byte 0x00 禁止；ARA、Host Notify 方向 | §4.4、§1、T26、T27 修正 |
| 3.4 MHz 每週期 10 點應為 34 MSa/s | §9.4 修正 |

### 第二輪（唯讀審查，原始輸出：scratchpad/codex_i2c_out2.txt）

| 主要意見 | 處理 |
|---|---|
| 正常 byte 邊界的 STOP 仍被標 `STOP inside byte` | §7.2：僅 bits 為 1–7 位時才標中斷；T32 新增 |
| 狀態機缺清空、重設與 unknown 分支 | §7.3、§7.4 補充；T33、T35 新增 |
| SMBus VIH 欄位解讀錯誤（1.35 VDD 為最小 1.35 V、最大 VDD） | §1、§12 修正 |
| T25 缺目標位址 byte | T25 補完整序列 |
| Device ID 判定過寬（FB、FD、FF 也被判定） | §7.4 只在 F8 與完整脈絡的 F9 時判定 |
| 10-bit 脈絡有效期限未定義 | §4.2 第 5、6 點補失效條件；T34 新增 |
| Hs 進入的 Sr 應以 Hs 規格解析，狀態圖切換點不一致 | §6.1、§7.2 修正；§12 的 `tH` 改為切換時點 |
| T18、T19 與濾波預設不一致 | §7.1 與 T18、T19 改為明確指定濾波視圖 |
| PEC 跨 Sr 已可由 X1 §6.4.1 確認 | §9.2 修正；§12 更新；T23、T24 標明前提為已知使用 PEC |
| Host Notify 為 16-bit 狀態（低 byte 先送），無 PEC 變體 | T27 與 §12 修正 |
| 建議：補 tVD;DAT 上限；統一 §2.3 量測點；ARA 最低位可移除待確認；補測試 | §2.2 補列；§2.3 修正；T26 與 §12 修正；T31–T35 新增 |

第二輪修正後未再送審（依任務最多兩輪）。第二輪意見中被確認為正確的項目包括：T07、T08 的 10-bit 位元換算；T23、T24 的 PEC 數值；Hs 延展窗、STOP 退出、UFm 第九 clock 與讀取結束 NACK。
