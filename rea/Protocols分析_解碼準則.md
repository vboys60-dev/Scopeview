# Protocols 解碼準則分析（Opus ＋ Codex 雙審）

- 對象：`rea/Protocols/`（Keysight Infiniium 協定 XML）對本專案可採用的解碼準則
- 涵蓋：I2C、I3C、SPI、eSPI、CAN、CAN FD、RS-232、RS-485、USB PD
- 產出日期：2026-11-12；兩方各自獨立分析，下方先列交叉比對，再附兩份完整報告。只讀分析，未改動專案程式。

## 〇、交叉比對結論

**兩方一致（可信度高）**
1. XML 是「欄位表／列舉／固定值檢查」，不是波形解碼器；判位、時鐘復原、去填充、CRC 都要自己寫，並用測試向量驗證。
2. SPI、RS-232、RS-485 **無對應 XML**（QuadSPI.xml 只有 8-bit Command；LIN.xml 只可借 UART 字元層建模）。RS-485 = 差動實體層 + 既有 UART。
3. 版本對應：I3C 三版（0.80／1.00／1.1.1）、USB PD 三版（2.0／3.0／3.1）、eSPI 僅一版、I2CIgnoreRW 只是把 R/W 併入位址顯示。
4. `MIPI_I3C_01_1_1.xml:84`、`USB_PD_03_11.xml:1524` 不是合法 XML；I3C 1.1.1 標頭仍寫 1.0 版註記。
5. I3C SDR：寫入 T-bit 為奇同位、讀取 T-bit 不當同位；HDR 規則不可套 SDR。
6. CAN CRC-15：多項式 0x4599、初值 0、範圍為去填充後 SOF～Data。

**兩方補充／差異**
| 項目 | Opus | Codex | 採用 |
|---|---|---|---|
| CAN CRC-15 | 以 `x6000can.csv` 實證 208/209 相符（唯一不符列示波器也標 CRC 錯） | 僅引規格 | **採實證**；CSV 可直接當測試向量 |
| CAN 阻礙 | H5 每位元約 2.6 點，不足以可靠解碼；建議試 `:WAVeform:POINts:MODE RAW` | 未提 | 採 Opus，但 RAW 是否足夠仍待實測 |
| CAN FD CRC | 多項式 0x3685B／0x302899（含最高次項），ISO 初值最高位為 1，標〔未確認〕 | 0x1685B／0x102899（省略最高次項），初值未定 | **兩者是同一多項式的不同寫法**；ISO 初值為最高位 1、其餘 0（CRC-17＝0x10000、CRC-21＝0x100000），有公開資料支持，仍待向量驗證 |
| USB PD CRC32 | 標準 CRC-32（0x04C11DB7、反射、init/xorout 0xFFFFFFFF），可用 `zlib.crc32` 計算 | 因 DLL 函式不明，列為未驗證 | 參數正確；**殘值要看表示法**：規格的 0xC704DD7B 是非反射暫存器表示，`zlib.crc32(data + crc_le)` 應得 **0x2144DF1C**（已實算） |
| 實作順序 | SPI → CAN → RS-485 → CAN FD → eSPI → USB PD → I3C HDR | I2C/UART 補驗證 → SPI/RS-485 → CAN → I3C SDR → CAN FD → eSPI/PD → HDR | 大方向一致：先做低風險重用，最後做 HDR |
| XML 缺陷 | 另指出 `CAN.xml:192-193` 未夾 DLC≤8、I2C XML 10-bit 讀取 Sr 依欄位定義有誤讀風險（引擎實際行為未驗證）、`CAN_FD.xml:338-339` 固定填充語意不明 | CAN FD 的 `Length=21/26` 含填充位，非純 CRC 寬度 | 全部納入；本專案 `i2c_decode.py` 比 XML 正確，應保留 |
| eSPI CRC8 | 0x07、init 0、MSB first，標〔未確認〕 | 同參數，引 Intel eSPI 規格 §5.2；command/response 涵蓋範圍排除 WAIT_STATE | 一致，採用 |

**仍待向量確認**：CAN FD CRC-17/21、I3C CRC5／P0／P1、eSPI CRC8 的參數都有公開規格支持，但都還沒有用真實封包驗過；USB PD ordered set 的 K 碼對應仍是推論。

## 〇之二、審查修正（2026-11-12，Claude 與 Codex 兩輪討論後定案）

審查方式：Claude 重跑 CAN CRC-15 並逐行抽查 XML；Codex 獨立審查並抽查 38 處行號引用（36 處吻合、2 處部分吻合）；兩輪討論後下列各點雙方一致。附錄 A 內對應文字已直接改正，附錄 B 保留原樣。

**確定錯誤，已改正**
1. **USB PD 殘值**：原寫「把 CRC 一起算入後得 0xC704DD7B」。用 `zlib.crc32` 時正確比較值是 0x2144DF1C；0xC704DD7B 是規格所用的另一種暫存器表示。
2. **RS-485 極性**：原寫「A−B > 0 通常為 mark」。TIA-485 的定義相反（A 低於 B 為 mark／1），而多數收發器晶片的 A/B 腳位命名又與標準相反。結論改為：極性必須可設定，並以實際收發器資料手冊與探棒接法確認。
3. **CAN intermission**：原寫 IFS 2 位。`CAN.xml:201` 的欄位確實只有 2 位，但標準 intermission 是 3 個 recessive 位，不能照 XML 實作。
4. **`addr_bits=8`**：只涵蓋一般 7-bit 位址的 8-bit 顯示；`I2CIgnoreRW.xml` 還把 10-bit 位址改成 11-bit 顯示，本專案選項不含這部分。
5. **CAN FD 的 CRC delimiter／ACK 長度**：XML 的 1 或 2 位是接收端容差（相位差造成），發送端名義上各 1 位。

**措辭過強，已放寬**
- 「I2C XML 的 10-bit Restart 會解錯」→ 依欄位定義有誤讀風險，原廠引擎實際行為未驗證。
- 「CAN H5 無法解、必須 RAW」→ 約 2.6 點／位元不足以可靠解碼；RAW 擷取是否足夠要實測。
- 「CAN CSV 是欄位真值」→ CSV 是示波器的解碼輸出，可當參考向量；用它反向合成波形再解回來是閉環測試，不能證明判位與時序正確。CSV 共 212 列，其中 209 列有 CRC。
- 「XML 不含演算法」→ XML 有宣告校驗函式、傳輸順序與錯誤規則，但演算法在外部引擎與 DLL，單靠 XML 不足以從波形解碼。
- QuadSPI「由 CS 定框」、CAN FD「DLL 一定另有填充資訊來源」都是推論，不是 XML 可證明的事實。
- I3C HDR preamble 列舉只代表 1.00 版 XML；新版有提前終止等差異。

**討論後升級為「有規格依據、待向量驗證」**
- **CAN FD CRC 輸入範圍**：含動態填充位與 stuff count（含 parity），不含固定填充位。本地佐證：`CAN_FD.xml:340-343` 的 Stuff Count 在 `FrameCRCData` 容器內且未標 `ExcludeCRC`，前後固定填充位（`:337-339`、`:344-345`）都標了。
- **CAN FD 固定填充位**：CRC-17 訊框共 6 個、CRC-21 共 7 個（stuff count 前 1、後 1，CRC 內 4 或 5）；XML 的 `Length=21/26` 只含 CRC 內那 4 或 5 個。
- **CAN FD 邊界**：Data（或 DLC=0 時的控制欄位）末尾剛好 5 個同值位時，只插第一個固定填充位，不再插動態填充位，且該位不計入 stuff count。
- **I3C CRC5**：多項式 x⁵+x²+1、初值 0x1F，輸入是 Command 與各 Data word 的 16-bit payload（不含 preamble 與 parity）。
- **I3C HDR-DDR 同位**：P1＝奇數位（D15、D13…D1）XOR；P0＝偶數位（D14…D0）XOR 後再 XOR 1（MIPI I3C Basic v1.1.1 §5.2.2）。
- **eSPI**：CRC8 為 0x07、初值 0、MSB first（Intel eSPI 規格 §5.2）；target 在時鐘上升緣取樣、下降緣推出資料，不是可任意設定的 CPOL／CPHA。

**維持不變**：CAN CRC-15 實證（208/209，重跑確認）、兩個 XML 無法解析、`CAN.xml` 未限制 DLC≤8、I3C SDR 讀寫 T-bit 區別、CAN IDE offset 的 12 與 13 不矛盾（前者相對 SOF 之後，後者相對 SOF）、實作順序 SPI → CAN → RS-485 → CAN FD → eSPI → USB PD → I3C HDR（CAN 階段先驗證 RAW 擷取可行性）。

---

# 附錄 A：Opus 完整報告


> 範圍：`rea/Protocols/`（119 個 XML、`agProtocols.dll`、`解碼定義.md`、`低速訊號判斷準則.md`），對照本專案 `scope_tool/web/*_decode.py` 與 `X6000A-解碼/` 實測樣本。只讀分析，沒有修改任何專案檔案。
> 引用格式為 `檔名:行號`，XML 路徑都相對於 `rea/Protocols/`。標「〔規格知識〕」的內容不在本目錄內，來自公開標準的一般知識，實作前要以正式規格或測試向量核對。標「〔未確認〕」的是我沒把握的地方。

---

## 0. 結論摘要

1. **XML 不是波形解碼器**。所有 XML 的 `Bus/Label` 都假設上游（示波器 framer）已經完成類比判位、時鐘復原、去填充、BMC/4b5b 解碼，並送進 `IsSop/IsEop/IsValid/Mode` 這幾個框架旗標（例：`I2C.xml:22-33`、`CAN.xml:19-30`、`USB_PD_03_11.xml:24-37`）。XML 能直接沿用的只有**欄位表、長度表達式、列舉值、固定值檢查與錯誤名稱**。實體層判位、填充和多數 CRC 都要自己實作（CRC 只有 DLL 函式名稱，見 §1.4）。
2. 已實證：**CAN CRC-15**（多項式 0x4599、初值 0、MSB first、範圍為去填充後的 SOF 到 Data 末位）與 `X6000A-解碼/CAN/x6000can.csv` 對照，**208/209 列相符**。唯一不符的那列在示波器 CSV 也標了 `CRC` 錯誤（算出 0x1170，CSV 為 0x1171），所以這份 CSV 可以直接當 CRC 測試向量。腳本：`/private/tmp/claude-501/-Users-lianshi-Desktop-claude-cowork-------html/59abe1e3-4e68-4fe7-8ea5-3e9abc51ed03/scratchpad/crc/crc15.py`。
3. 對應關係：

| 協定 | 目錄內 XML | 本專案現況 |
|---|---|---|
| I2C | `I2C.xml`、`I2CIgnoreRW.xml`（另 I3C XML 內含 Legacy I2C） | 已實作 `i2c_decode.py`，實機 48 列相符 |
| I3C | `MIPI_I3C_00_80.xml`、`MIPI_I3C_01_00.xml`、`MIPI_I3C_01_1_1.xml` | SDR 已實作；HDR 只標區段「未解碼」（`i3c_decode.py:156-157`） |
| SPI | **無**通用 SPI。只有 `QuadSPI.xml`（8-bit Command 一欄） | `analysis_decode.NAMES` 已列 `spi`，但沒有模組（`analysis_decode.py:20,30-36`） |
| eSPI | `eSPI.xml`（Rev 0.75） | 無 |
| CAN | `CAN.xml` | `NAMES` 已列 `can`，沒有模組；實機 H5 每位元約 2.6 點，無法解 |
| CAN FD | `CAN_FD.xml`（ISO FD，含 stuff count）；另有 `CAN_XL.xml` | 無 |
| RS-232 | **無**。UART 字元框架可參考 `LIN.xml` | 已實作 `uart_decode.py`，實機 130/131 列相符 |
| RS-485 | **無** | 無；可沿用 UART 加差動（`analysis_decode.py:73-78` 的 `DIFF` 機制） |
| USB PD | `USB_PD_02_10.xml`、`USB_PD_03_11.xml`、`USB_PD_31_15.xml` | 無 |

4. 建議下一步的順序：**SPI → CAN（先解決 RAW 擷取）→ RS-485（UART＋差動）→ CAN FD → eSPI → USB PD → I3C HDR-DDR**。理由見 §11。

---

## 1. XML 共通解碼模型

### 1.1 結構

| 元素 | 意義 | 例 |
|---|---|---|
| `Bus` / `Label` | 上游送進來的資料寬度與框架旗標。`Mode`（Status）是 framer 判定的事件類型，**不屬於封包欄位** | `I2C.xml:22-33`；`CAN.xml:36-48` 的註解直接寫 "part of the framing not a part of the protocol header" |
| `BusProtocol Select` | 依 `Mode` 或前幾位元選封包根協定 | `I2C.xml:55-60` |
| `PacketType` / `PacketMask` | 顯示分類與觸發／搜尋用的位元遮罩（BitOffset 從封包第 0 位算起） | `CAN.xml:65-93` |
| `Protocol` / `Header` / `Payload` / `Trailer` | 依序消耗位元的欄位串 | `CAN.xml:114-202` |
| `Field Type="Lookahead"` | 只偷看、不前進指標。BitOffset 相對於**目前指標** | `CAN.xml:143-145`（SOF 已吃掉，所以 IDE 在 offset 12）與 `CAN_FD.xml:144-148`（SOF 尚未吃，所以 IDE 在 offset 13）。兩檔的基準不同 |
| `Field Type="Protocol" Select=…` | 條件式子協定（相當於 switch） | `eSPI.xml:525-534` |
| `SegmentedField` | 把不連續的位段拼成一個值（例：29-bit ID） | `CAN.xml:156-159` |
| `RepetitiveFields Length=…` | 依剩餘長度重複 | `I2C.xml:192-195` |
| `FieldContainer` + `ValueFunction="agProtocols:X" ValueInput="容器名"` | 校驗欄位：對容器內的位元呼叫 DLL 函式 | `CAN.xml:115,196` |
| `Value` + `ValueError` | 固定值檢查（form error） | `CAN.xml:197-200` |
| `ExcludeCRC="T"` | 欄位不納入 CRC 計算 | `CAN_FD.xml:337-345` |
| `TransmissionOrder="LSBFirst"` | 線上 LSB 先，顯示時轉成 MSB | `LIN.xml:16`、`USB_PD_03_11.xml:19` |
| 特殊變數 `#PACKET_LENGTH`、`#BIT_OFFSET`、`#VARIABLE` | 由引擎提供 | `I2C.xml:192`、`eSPI.xml:1021` |

### 1.2 與本專案架構的對應

本專案解碼模組的介面是 `ROLES / BASE / options() / run()`（`uart_decode.py:10-37`、`i2c_decode.py:10-16`），差動由模組宣告 `DIFF` 後在 `analysis_decode.py:73-78` 相減，判位用 `logic.to_edges / levels_at`。對照起來：

- XML 的「上游 framer」= 本專案的 `logic.py` 判位加上各協定 `Decoder` 狀態機，這部分都要自己寫。
- XML 的「欄位表」= 本專案 `*_fields.py` 和 `frame / field` 輸出。這部分可以照 XML 抄。
- XML 的 `ValueError` 名稱可以對應到本專案的 `reason(f, code, level)`（`uart_decode.py:207-208`）。

### 1.3 解讀注意

- `data[a:b]` 的位元編號方向在不同檔案之間不一致。例：`USB_PD_03_11.xml:41` 用 `data[30:28]`，`I2C.xml:55` 用 `data[0:4]`。運算子優先序與位序都由原廠引擎解釋，**不能直接翻譯成 Python 切片**，要以已知封包反推驗證。
- `ProtocolErrors` 是空的，不代表沒有錯誤可判（例：`I2C.xml:233-234`）。
- 兩個 XML 無法通過標準 XML 解析（本次用 Python `ElementTree` 實測）：
  - `MIPI_I3C_01_1_1.xml:84`：註解 `<!------…` 含連續 `--`。
  - `USB_PD_03_11.xml:1524`：`Length="1"Enumset=` 屬性之間少了空白。

  若要程式化讀這兩個 XML，需要容錯掃描。其餘相關 XML 解析正常。

### 1.4 `agProtocols.dll` 內的校驗函式（以 `strings` 確認名稱存在）

`CANCRC15`、`CANFD_CRC17`、`CANFD_CRC21`、`CANFD_StuffCount`、`LINChecksum`、`LINParity`、`OddParity`、`MIPI_I3C_CRC5`、`MIPI_I3C_P0/P1`（含 Ternary）、`MIPI_I3C_BT_Even_Bits/Odd_Bits` 等。XML 也引用了 `eSPICRC8`（`eSPI.xml:537`）與 `USB3LCRC32`（`USB_PD_03_11.xml:1170`）。**DLL 只提供名稱，多項式、初值與輸入位序都不在 XML 裡**，必須依規格實作，再用向量驗證。

---

## 2. I2C

**(1) XML 與版本差異**
- `I2C.xml`：來源為 I2C-bus spec v2.1（2000），見 `I2C.xml:8-9`，族名 "7/10-bit Addr"（`:16`）。
- `I2CIgnoreRW.xml`：與前者逐行 diff，**唯一的語意差異**是把 R/W 併進位址：8-bit `Addr`（對應 `I2C.xml:131-132`）、11-bit 段 `Segment BitOffset=5 Length=3`（對應 `I2C.xml:164-165`），並刪除 `ReadWriteFrame` 列舉。這是顯示制式，不是新的位址模式。本專案 `addr_bits=8` 的顯示選項涵蓋一般 7-bit 位址的這個需求（HANDOFF.md:225），不含 10-bit 的 11-bit 顯示。
- 另見 `MIPI_I3C_01_00.xml:5081-5218` 的 Legacy I2C。它的 header 多算 1 個 S 位（payload 用 `#PACKET_LENGTH - 10`），與 `I2C.xml` 的 `-9` 不同，因為兩者的上游框架不同。

**(2) 實體層**〔規格知識〕開汲極加上拉。SCL 高期間 SDA 下降為 START、上升為 STOP，未出現 STOP 就再 START 為 Sr。資料在 SCL 上升緣（高電位期間）取樣，MSB first，速率 100k / 400k / 1M / 3.4M。XML 只在描述中寫了起停定義（`I2C.xml:69,72`）。

**(3) 訊框**
- 7-bit：Addr7 + R/W1 + ACK1（`I2C.xml:129-135`），之後重複 Data8 + ACK1（`:187-197`）。
- 10-bit：`11110` + A9:8 + R/W + ACK + A7:0 + ACK（`:162-176`）。
- 判別條件：第一 byte 前 5 位為 `11110`（`:50-55`）。
- Mode 定義：0=Start、1=Restart、2=Start 或 Restart、3=Start only、4=Stop（`:44-48`）。

**(4) 錯誤判定** 只有列舉：ACK 0=Ack、1=Nack（`:217-220`），R/W 0=Write、1=Read（`:212-215`）。沒有 CRC。`ProtocolErrors` 是空的（`:233-234`）。

**(5) 可沿用 vs. 自行實作**
- 可沿用：欄位順序與長度、10-bit 判別樣式、列舉值。
- **不可照抄的 XML 缺陷**：
  - 10-bit 讀取的標準流程是「S + 11110xx0 + A7:0，再 Sr + 11110xx1」，第二段沒有 A7:0。XML 的 10-bit Restart（`:56,146-149`）仍套用 18-bit header，依欄位定義有把第一個資料 byte 讀成 `Addr[7:0]` 的風險（原廠引擎實際行為未驗證）。本專案 `i2c_decode.py:36,93` 已用「Sr 承接同目標 10-bit 脈絡」處理，**比 XML 正確，應保留**。
  - Mode 2 寫在註解裡（`:46`），但沒有任何 `BusProtocol` 使用它；`PacketType "7-bit Addr"`（`:80`）掛在 Start Packet 上。這只影響顯示，不必跟。
- 必須自行實作：起停偵測、clock stretching、glitch、截斷、讀取末 byte 的 NACK 是否為正常結束（本專案 CSV 規則已處理，HANDOFF.md:219）。

**(6) 驗證** 已有實機 `x6000i2c2.h5` 與 `x6000i2c3.csv`。建議補合成向量：10-bit 寫、10-bit 讀（Sr 只送 1 byte）、General Call、START byte、clock stretching、SDA 在 SCL 高時的 glitch，確認不會誤判成起停。

---

## 3. I3C

**(1) XML 與版本差異**

| 檔案 | 族名 | 標頭註記 | 差異 |
|---|---|---|---|
| `MIPI_I3C_00_80.xml` | V0.80（`:16`） | 註記寫 "Version 0.7 Rev 13, 2016-05"（`:9`），與族名不一致 | Mode 0–8；SDR 封包不檢查 Mode（`:62-71`）；有 "HDR-DDR Master Abort" 錯誤（`:6019`） |
| `MIPI_I3C_01_00.xml` | V1.00（`:16`） | v1.0 r13, 2016-12（`:9`） | Mode 0–16（`:44-60`），新增 Private / Legacy Private、Direct without Sr、GETMXDS turnaround、SETMRL+IBI、HDR Exit/Restart（`:68-88`）；新增 "SDR Broadcast NACK"（`:7519`） |
| `MIPI_I3C_01_1_1.xml` | V1.1.1（`:16`） | 標頭仍寫 v1.0（`:9`），註記未更新 | Mode 擴到 0x22：Dual/Quad lane、HDR-BT（`:79-119`），BT 欄位用 `MIPI_I3C_BT_Even/Odd_Bits`（`:6235-6236`）；用語改為 Controller/Target；**標準 XML 解析失敗**（`:84`） |

**(2) 實體層**〔規格知識〕SDR 的 SCL 由主控端推挽驅動，SDA 在仲裁與 ACK 時為開汲極，其餘推挽；速率最高 12.5 MHz。HDR-DDR 在 SCL 雙緣取樣。HDR-TSP/TSL 是三元符號，需要另一套符號層。本專案研究文件 `docs/研究_解碼協定.md` §3 已有詳述。

**(3) 訊框（以 1.00 為準）**
- SDR header：S + Addr7 + R/W + ACK（`MIPI_I3C_01_00.xml:5127-5134`）。CCC 判別：`data[1:7]==0x7E`；`data[10]` 為 CCC 碼的最高位，0=Broadcast、1=Direct（`:82-83`）。
- SDR 寫資料：Data8 + T，T 為奇同位（`:5220-5233`）。SDR 讀資料：Data8 + T，**T 不檢查同位**（`:5235-5246`），因為讀取時 T 是結束或延續的指示。這與本專案 `i3c_decode.py:124-130`（`ninth='tbit' if reading else 'parity'`）一致。
- HDR-DDR（`:7266-7342`）：
  - Command word = Preamble2 + R/W1 + CmdCode7 + Addr7 + Rsv1 + P1 + P0，共 20 bits（`:7280-7290`）。
  - Data word = Preamble2 + Data16 + P1 + P0。
  - CRC word = Preamble2 + Token4（固定 0xC）+ CRC5 + Setup2，共 13 bits（`:7337-7342`）。

**(4) 錯誤判定**
- SDR 寫的 T 位用 `OddParity`（`:5230`）；ENTDAA 的動態位址同位也用 `OddParity`（`:5768` 等）。
- HDR-DDR 的 P1/P0 用 `MIPI_I3C_P1/P0`（`:7288-7289`），CRC5 用 `MIPI_I3C_CRC5`，輸入範圍是 Command 加全部 Data 容器（`:7268,7340`）。
- Preamble 合法值（`:7376-7402`）：Cmd=01；首個 Data：10=ACK、11=Target NACK；後續 Data：11=data follows、10=Controller abort；CRC=01。
- 〔規格知識，未確認〕CRC5 多項式 x⁵+x²+1、初值 0x1F；P1/P0 分別為奇位與偶位 XOR（P0 再反相）。正式規格可能以 Command 與 Data 的 16-bit 半字為單位計算，須核對。
- 〔未確認〕「後續 Data preamble 11=data follows」是否同時適用讀和寫（`:7311` 寫入也用同一個列舉），需要規格確認。

**(5) 可沿用 vs. 自行實作**
- 可沿用：CCC 碼列舉與各 CCC 的欄位表（00_80 / 01_00 有大量 CCC 結構，例如 `:5629-6300`）、HDR-DDR 的 word 長度與 preamble 列舉、錯誤名稱。
- 必須自行實作：OD/PP 切換判位、Sr 與 HDR Exit pattern、ENTDAA 仲裁、IBI、HDR-DDR 雙緣取樣、CRC5/P0/P1 演算法，以及 TSP/TSL 的三元符號層（XML 只有 `P0_Ternary` 函式名稱）。

**(6) 驗證** 本專案已有 `i3c_vectors.py` / `i3c_synth.py`，但**沒有實機 I3C 波形**（HANDOFF.md:204）。HDR-DDR 建議等取得 MIPI 規格或原廠解碼截圖，再做 CRC5 和 P0/P1 向量，不要只依 XML 名稱推定。

---

## 4. SPI

**(1) XML** **無通用 SPI.xml**。替代參考：
- `QuadSPI.xml`：只定義 8-bit `Command` 欄位（`:49-51`）。`SOPEOPOnSameSymbol="T"`（`:19`）表示框架由 CS 給定，命令後的位址、dummy cycle 與資料全部沒有定義，**幾乎沒有可沿用的內容**。
- `eSPI.xml` 是建立在 SPI 實體層上的命令層，可以示範「CS 期間的位元流→封包」的模型，但不適用一般 SPI。

**(2) 實體層**〔規格知識；`docs/研究_解碼協定.md` §5.1 已有表〕CPOL/CPHA 四種模式，CS 多為低有效。CPHA=0 在前緣取樣，CPHA=1 在後緣取樣（前緣定義為離開閒置電位的第一個邊緣）。字長可設，常見 MSB first。

**(3) 訊框** CS 有效期間每個取樣緣讀 MOSI/MISO 各 1 bit，湊滿字長即輸出一個 word，CS 解除時結束 transaction。沒有位址、ACK 或 CRC。

**(4) 錯誤判定** 協定本身沒有校驗。只能標記：不完整 word（CS 解除時位數不是字長整數倍）、CS glitch、取樣緣附近資料不穩、clock glitch。**不得自行報 NACK 或 CRC 錯誤。**

**(5) 可沿用 vs. 自行實作** XML 沒有可沿用的規則，全部自行實作。好處是時鐘由外部提供，不需要做時鐘復原。

**(6) 實作與驗證**
- 角色可定為 `ROLES={'sclk':True,'cs':False,'mosi':False,'miso':False}`。至少需要一條資料線；沒有 CS 時以閒置間隔切段。
- 取樣：在 SCLK 的取樣緣用 `levels_at` 取資料線電平；為避免在邊緣當點上取樣，可取緣前一個樣本。
- 測試向量：用 `synth.py` 產生四種模式 × 字長 8/16/12 × MSB/LSB × CS 有／無 × 最後一個 word 截斷的波形。另加反向測試：用錯誤的 CPHA 解，應該得到移位的資料。
- 目前沒有實機資料（HANDOFF.md:232）。

---

## 5. eSPI

**(1) XML** `eSPI.xml`，來源為 eSPI spec **Rev 0.75（2013-06）**（`:10`）。現行規格是 1.0 以後的版本，0.75 之後的新增功能都不在這個檔案裡〔未確認具體差異〕。

**(2) 實體層**〔規格知識〕CS#、CLK、IO[3:0]，可為單、雙或四線；命令與回應之間有 turnaround（TAR）。資料在 CLK 上升緣輸出、下降緣取樣（或反之，依規格設定）〔未確認〕。XML 只透過 Mode 區分命令階段與回應階段：0=Command、1=Response（`:45-51`）。

**(3) 訊框**
- Command：Opcode8（`:523`），依 opcode 分派子協定（`:525-534`），結尾為 CRC8（`:537`）。
- Opcode 表（`:541-576`）：PUT_PC 00、GET_PC 01、PUT_NP 02、GET_NP 03、PUT_VWIRE 04、GET_VWIRE 05、PUT_OOB 06、GET_OOB 07、PUT_FLASH_C 08、GET_FLASH_NP 09、GET_CONFIGURATION 21、SET_CONFIGURATION 22、GET_STATUS 25、Short IO/Mem 40–4F、RESET FF。未知範圍為 0A–20、23–24、26–39、50–FE。
- Response：RespOpcode8，加上 append 封包，再加 Status16，最後 CRC8（`:582-595`）。Response opcode：08 ACCEPT、48/88/C8 為 ACCEPT 加上 PC/VW/Flash append、01 DEFER、02/03 錯誤、0F WAIT_STATE、FF NO_RESPONSE（`:607-617`）。WAIT_STATE 可重複（`:597-601`）。
- Status 傳輸順序：先 bit7..0，再 bit15..8（`:619-634`），也就是低位 byte 先送、byte 內 MSB 先。
- 欄位：PC/Flash header 為 Tag4 + Length12 + Address32/64 + Data（Length×8）（`:829-852,1028-1068`）；Short 指令為 Addr32 或 Addr16 加 1/2/4 byte（`:857-880`）；VW 為 Rsv2 + Count6，之後 (Count+1) 組 Index8 + Data8（`:738-761`，Count 從 0 起算）；OOB 為 SMBus 位址、命令、byte count 與 PEC（`:1008-1023`）。

**(4) 錯誤判定**
- CRC8（`eSPICRC8`）的範圍是整個 Command 容器，或 Response 容器（不含 FF/0F）（`:521-538,583-594`）。〔規格知識，未確認〕多項式 x⁸+x²+x+1（0x07）、初值 0、MSB first。
- 固定值檢查：`VWIRE_FREE`、`FLASH_C_FREE` 必須為 1（`:625,633`）；保留位必須為 0（`:628,631,740`）；無資料完成的 Length 必須為 0（`:988`）。
- 錯誤名稱：`:1088-1093`。

**(5) 可沿用 vs. 自行實作**
- 可沿用：opcode、回應碼、cycle type 列舉（`:699-733`）、各封包欄位長度、Status 位元定義。
- 必須自行實作：CS/CLK 取樣、單／雙／四線的位元重組、TAR 與命令／回應邊界判定（XML 假設上游已用 Mode 分好）、CRC8、Alert。

**(6) 驗證** 目前沒有樣本。先用 GET_STATUS（25 加 CRC）、回應 ACCEPT 加 Status 加 CRC 這組最短交易，以合成向量驗 CRC8 和位元順序，再逐步擴到 PUT_PC / VW。若有實機，應取 Intel 平台 BIOS 開機階段的 GET_CONFIGURATION 序列。

---

## 6. CAN（Classical）

**(1) XML** `CAN.xml`（`:13`，授權名 CAN_Packet_Decode）。另有 `CAN_FD.xml` 內建的 `CANStandardFrame`（`CAN_FD.xml:162-250`）可解 classic 訊框，與 `CAN.xml` 的差別是 EOF 接受 `1111110`（`:246-248`，容許最後一個 EOF 位為 dominant）。

**(2) 實體層**〔規格知識；`docs/研究_解碼協定.md` §8.1〕
- 電平：差動 CANH−CANL，約 2 V 為 dominant（0），約 0 V 為 recessive（1）；判位門檻約 0.5–0.9 V。
- 位元率：125k / 250k / 500k / 1M。
- 取樣：SOF 下降緣做 hard sync，之後每個 recessive→dominant 邊緣做 resync，取樣點在位元時間的 75–87.5%。
- 填充：SOF 到 CRC 序列之間，連續 5 個同值位後插入 1 個反相位。
- XML **假設上游已去填充**：欄位長度不含填充位，"Six successive dominant bits" 列為 Error Frame（`:237`）。

**(3) 訊框**（以去填充後的位元計，SOF 為第 0 位）
- 標準：SOF1、ID11、RTR1、IDE1、r0 1、DLC4、Data（DLC×8）、CRC15、CRC delim 1、ACK1、ACK delim 1、EOF7、Intermission（XML 欄位為 2 位，`:117-201`；標準 intermission 為 3 個 recessive 位，不可照 XML）。
- 延伸：SOF、ID 高 11、SRR、IDE、ID 低 18、RTR、r1、r0、DLC…（`:156-176`）。
- 類型判別（`:58-63,69-90`）：IDE 位於 offset 13；延伸格式的 RTR 位於 offset 32。

**(4) 錯誤判定**
- **CRC-15：已用實機 CSV 驗證**（208/209）。多項式 x¹⁵+x¹⁴+x¹⁰+x⁸+x⁷+x⁴+x³+1 = 0x4599、初值 0、無最終 XOR，輸入為去填充後 SOF 到 Data 末位，MSB first（XML 中為 `FrameCRCData` 容器，`:115-196`）。
- 固定值：CRC delimiter=1、ACK delimiter=1、EOF=1111111 → Form Error；ACK slot=0，否則 ACK Error；r0=0（`:181`）。
- Intermission：`01` 視為 Form Error；`00`、`10` 視為 Overload（`:223-228`）。
- 另需自行判定：stuff error（6 個同值位）、error frame、bit timing。

**(5) 可沿用 vs. 自行實作**
- 可沿用：欄位表、類型判別、固定值與 ACK 規則。
- **XML 缺陷**：`Data Length='DLC'*8`（`:192-193`）沒有把 DLC 上限夾到 8。Classical CAN 的 DLC 9–15 代表 8 bytes，必須自行加上 `min(DLC,8)`。
- 必須自行實作：差動判位、位元時序與 resync、去填充、stuff error、error/overload frame 辨識、CRC 計算。

**(6) 驗證**
- `X6000A-解碼/CAN/x6000can.csv` 有 209 列帶 ID / Type / DLC / Data / CRC / Errors，涵蓋 11/29-bit、Data/RMT、`Stuff`、`Ack`、`Fr`、`CRC` 錯誤。這是**現成的 CRC 與欄位參考向量**（示波器的解碼輸出，不是獨立真值）。
- 但目前的 H5 每位元約 2.6 點，不足以可靠解碼（HANDOFF.md:216），建議先試在擷取流程加入 `:WAVeform:POINts:MODE RAW` 取完整記憶體（HANDOFF.md:234）。
- 在此之前，可以用 CSV 的欄位反向合成「加填充後的波形」作為 `can_synth` 的輸入，閉環驗證解碼器。

---

## 7. CAN FD

**(1) XML** `CAN_FD.xml`。它是 **ISO CAN FD**：有 stuff count（`:340-343`）。**不支援 non-ISO（Bosch 原版）**。`CAN_XL.xml` 是 XL 格式，目前不需要。

**(2) 實體層**〔規格知識〕兩套位元率與取樣點（nominal / data）。BRS=1 時，從 BRS 位的取樣點切到 data 速率，到 CRC delimiter 的取樣點切回 nominal。SOF 到 Data 使用動態填充；CRC 欄位改用**固定填充**：stuff count 前一位、之後每 4 位插入一個反相位。

**(3) 訊框**
- 頂層判別（`:144-158`，此處 offset 含 SOF）：標準格式 offset 12=RRS、13=IDE、14=FDF；延伸格式 offset 32=RRS、33=FDF。
- FD 控制欄位：FDF、res（=0）、BRS、ESI、DLC4（`:312-316`）。
- DLC 對照（`:325-334`）：0–8 直接對應；9/A/B/C/D/E/F 對應 12/16/20/24/32/48/64 bytes。
- Data 之後依序為：固定填充位（`:337-339`）、stuff count（Gray 3 位 + parity 1 位，`:340-343`）、固定填充位（`:344-345`）、CRC。
- CRC 欄位長度：**21 = CRC-17 + 4 個固定填充位**（DLC≤A）；**26 = CRC-21 + 5 個固定填充位**（DLC>A）（`:347-348`）。XML 的長度包含填充位，不是多項式寬度。
- 後段（`:349-357`）：CRC delimiter 與 ACK slot 在 XML 中可解讀為 1 或 2 位，這是接收端對相位差的容差；發送端名義上各 1 位。

**(4) 錯誤判定**
- CRC 函式：`CANFD_CRC17/21`（`:347-348`），Stuff count 用 `CANFD_StuffCount`（`:340`），固定填充位錯誤視為 Form Error（`:337-345`）。
- 〔規格知識〕CRC-17 多項式 0x3685B、CRC-21 多項式 0x302899。ISO FD 的初值為最高位為 1（CRC-17 為 1<<16、CRC-21 為 1<<20）〔未確認，需向量核對〕。
- 〔規格知識〕ISO FD 的 CRC **包含 SOF 到 Data 的動態填充位與 stuff count**，排除固定填充位（與 XML 的 `ExcludeCRC="T"` 一致）。XML 的 `FrameCRCData` 是去填充後的位元，DLL 如何取得填充資訊無從得知，**不能照 XML 容器範圍直接算**。
- Stuff count：動態填充位數 mod 8 轉 Gray 碼（0→000、1→001、2→011、3→010、4→110、5→111、6→101、7→100），再加偶同位。
- 〔未確認〕固定填充值的選擇 `Data[0]==0 → 1`（`:338-339`）。依規格，固定填充位應為「前一位的反相」，而 XML 用的 `Data[0]` 的位序意義不明，實作時應直接取前一個線上位元的反相。

**(5) 可沿用 vs. 自行實作**
- 可沿用：DLC 對照表、欄位順序、固定填充與 stuff count 的位置、CRC 欄位長度、CRC delimiter／ACK 的容錯寬度。
- 必須自行實作：雙速率位元時序（跨界位元由兩種速率組成）、動態與固定填充、Gray 碼、CRC-17/21（含填充位的輸入域）。

**(6) 驗證** 目前沒有 FD 樣本。建議：
- 先拿 ISO 11898-1:2015 或 CiA 公開範例，或用另一台示波器（例如 MXR / 6000A 的 FD 解碼）錄一組 BRS=0 和一組 BRS=1、DLC 分別為 8、9、F 的訊框，取得 CRC 真值。
- 自製向量時特別測：動態填充恰好落在 Data 末位、stuff count 跨 mod 8。

---

## 8. RS-232（UART）

**(1) XML** **無**。替代參考是 `LIN.xml`，它是 UART 字元層上的協定，可借用的概念有：
- `TransmissionOrder="LSBFirst"`（`:16`）
- Break 以長 dominant（0）偵測（`:56-123`）
- Sync=0x55（`:70`），可做為鮑率估計基準
- ID 同位（`LINParity`，`:79`）與 checksum（`LINChecksum`，`:88`，同時支援 LIN 1.3 與 2.1，見 `:143`）

**(2) 實體層**〔規格知識〕
- RS-232 線上電平：邏輯 1（mark）為 −3 至 −15 V，0（space）為 +3 至 +15 V，與 TTL 相反。
- 取樣：以起始位下降緣同步，在每個位元中心取樣，LSB first。
- 本專案已實作，實機為 19200 baud、需反相（HANDOFF.md:220）。

**(3) 訊框** Start(0)、Data 5–9 位、可選 parity（N/E/O/M/S）、Stop 1 或 2 位。實作見 `uart_decode.py:18-37,82-157`。

**(4) 錯誤判定** framing（stop≠1）、parity、break（整個字元為 0 且低電位超過一個字元時間）、false start。已實作於 `uart_decode.py:121-151`。

**(5) 可沿用 vs. 自行實作** XML 無可沿用規則，已全部自行實作。LIN 若日後要做，可以疊在 UART 之上，直接套用 `LIN.xml` 的欄位與錯誤名稱。

**(6) 驗證** 已完成實機 130/131 列比對。建議補合成向量：2 stop、9 bit、Mark/Space parity、鮑率偏差 ±3%、break 加 truncated。

---

## 9. RS-485

**(1) XML** **無**。RS-485 只是實體層，沒有對應的 XML。上層若是 UART，可沿用 `uart_decode.py`；若是 Modbus RTU，目錄內也沒有相關定義。

**(2) 實體層**〔規格知識〕
- 平衡差動 A/B，|VAB| ≥ 200 mV 才能判定邏輯；TIA-485 定義 A 低於 B 為 mark（1），但多數收發器晶片的 A/B 腳位命名與標準相反，**極性必須可設定**，並以實際收發器資料手冊確認。
- 半雙工有驅動方向切換，閒置時靠 failsafe 偏壓，可能出現不確定區。

**(3)(4)** 字元框架與錯誤判定同 UART。若有 Modbus RTU：幀間隔超過 3.5 個字元時間、CRC-16（多項式 0xA001 反射形式、初值 0xFFFF）〔規格知識〕。

**(5) 自行實作**
- 最小方案是新增一個薄模組。這個模組重用 `uart_decode` 的 `options/_lane/run`，加上 `ROLES` 的 `a`、`b` 角色與 `DIFF={'b':'a'}`。`analysis_decode.py:73-78` 已經會做 `volts[pos] - volts[neg]`，`thresholds` 鍵也已排除 `DIFF` 角色（`:45`）。
- 也可以不新增模組：使用者直接用數學通道 A−B 跑 UART。
- 門檻預設 ±0.2 V，以遲滯方式判位。

**(6) 驗證** 用合成的 A/B 波形（含共模偏移、三態閒置），確認差動判位後的結果與 UART 向量一致。另做一組 A/B 對調的波形，應觸發「可能需反相」的警告（`uart_decode.py:166-167`）。

---

## 10. USB PD

**(1) XML 與版本差異**

| 檔案 | 規格 | 差異 |
|---|---|---|
| `USB_PD_02_10.xml` | PD R2.0 V1.0（2014，`:9,19`） | 只有 Control 與 Data（`:41-43`） |
| `USB_PD_03_11.xml` | PD R3.0 V1.1（2017，`:19`） | 新增 Extended（`data[31]==1`，`:41-44`）、Extended header（Data Size 9、Request Chunk、Chunk Number 4、Chunked）；**標準 XML 解析失敗**（`:1524`） |
| `USB_PD_31_15.xml` | PD R3.1 V1.5（2024，`:19`） | 新增 EPR_Mode、EPR_Request、Source_Info、Revision 等（`:651-683,1328`）；SpecRev 列舉 0–2（`:3513-3518`）；Extended header 見 `:1740-1756` |

**(2) 實體層**〔規格知識〕
- 走 CC 線，振幅約 1.1 V，BMC 編碼，300 kbps ±10%。BMC 規則：每個位元邊界都轉態，「1」在位元中間多一次轉態。
- 前導碼 64 位為 0/1 交替。之後為 4b5b 編碼的 SOP*、header、data、CRC、EOP。
- XML 假設上游已完成 BMC 與 4b5b 解碼，並以 `IsKChar` 標出 K 碼（`USB_PD_03_11.xml:24-37`）。錯誤名稱也反映了這一點：Sampler Error 表示無法判定 BMC 的 0/1，另有 Preamble Error、Invalid 5b code（`:2727-2734`）。

**(3) 訊框**
- Ordered set 的 16-bit 值（`USB_PD_03_11.xml:1141-1150,2481-2500`）：SOP=0x1888、SOP'=0x6688、SOP''=0x6868、SOP'_Debug=0x6998、SOP''_Debug=0x1698、Hard Reset=0x9777、Cable Reset=0x6787。
  - 推論：Keysight 以「5b K 碼的低 4 位」表示 K 符號，LSB 先。對應為 Sync-1 11000→8、Sync-2 10001→1、Sync-3 00110→6、RST-1 00111→7、RST-2 11001→9、EOP 01101→D。用 SOP = Sync1×3 + Sync2 和 Cable Reset 的組成逐一核對，結果自洽，但這仍是推論。
- Message header 16 位，LSB 先（`:1174-1184`）：MsgType5、Port Data Role 1（SOP'/'' 時為保留位）、SpecRev2、Port Power Role 1（SOP'/'' 時為 Cable Plug）、MsgID3、NumDO3、Extended1。
- Control 訊息固定長度 68（`:41`）。Data 訊息帶 NumDO 個 32 位 data object。
- 結尾：CRC32、EOP（固定 0xD，`:1170-1171`）。

**(4) 錯誤判定**
- CRC32 用 `USB3LCRC32`（`:1170`），範圍為 header 加 data（`32-bit CRC` 容器，不含 SOP）。〔規格知識〕這是標準 CRC-32（0x04C11DB7、反射、初值 0xFFFFFFFF、最終 XOR 0xFFFFFFFF），與 Python 的 `zlib.crc32` 相同。
- 其他檢查：
  - Bad EOP。
  - Bad Reserved（`:1176`）。
  - 依 SOP 類型限制可出現的 MsgType，不符時判為 Invalid SOP（`:1159-1162`）。
  - Bad Sync Code（`PacketSignaling` 的 Default，`:2481-2489`）。
- 〔規格知識〕GoodCRC 必須在 tReceive 內回覆、MsgID 要相符，這屬於時序與協定層檢查，XML 未涵蓋。

**(5) 可沿用 vs. 自行實作**
- 可沿用：ordered set 值、header 位元配置、各版本的 Control / Data / Extended 訊息列舉與 PDO 結構（例如 `Source_Capabilities` 在 `USB_PD_03_11.xml:1449`）、SOP 類型與 MsgType 的合法性表。
- 必須自行實作：BMC 時鐘復原（由轉態間距判定半位元或全位元）、4b5b 查表、K 碼對齊、CRC32。

**(6) 驗證**
- CRC 可直接用 `zlib.crc32` 自檢，並檢查殘值：`zlib.crc32(data + crc 的 little-endian bytes)` 應得 0x2144DF1C（已實算）；規格所列 0xC704DD7B 是另一種暫存器表示，不能直接拿來比。
- 波形方面，建議用一般 PD 誘騙器或充電器錄製 Source_Capabilities → Request → Accept → PS_RDY 序列，取樣率至少 10 MSa/s（每位元約 33 點以上）。

---

## 11. 難度與優先順序建議

| 順序 | 協定 | 難度 | 理由 |
|---|---|---|---|
| 1 | SPI | 低 | 時鐘外部提供；`NAMES` 已預留；沒有 XML 也不需要。唯一風險是沒有實機資料 |
| 2 | CAN | 中 | **已有 CRC-15 實證與 209 列真值**；XML 欄位可直接抄。阻礙是擷取需要 RAW 記憶體 |
| 3 | RS-485 | 低 | 幾乎全部重用 UART 加現成的 `DIFF`；主要工作是設定極性與門檻 |
| 4 | CAN FD | 中高 | 在 CAN 之上加雙速率、固定填充、Gray stuff count、CRC-17/21 的輸入域，需要外部向量 |
| 5 | eSPI | 中 | XML 欄位最完整，但需要 IO 線數、TAR 和命令／回應邊界；CRC8 參數待確認；沒有樣本 |
| 6 | USB PD | 中高 | BMC + 4b5b 的實體層要全部新寫；CRC32 容易驗證；XML 欄位多但結構清楚 |
| 7 | I3C HDR-DDR | 高 | 雙緣取樣、preamble 換手、CRC5/P0/P1 參數未經向量確認；SDR 已完成 |
| — | I3C HDR-TSP/TSL/BT、多 lane | 很高 | 需要三元符號與會員規格；建議繼續只標「未解碼區段」 |

---

## 12. 風險與不確定處

1. **XML 位序與 offset 基準不一致**：`CAN.xml` 與 `CAN_FD.xml` 的 lookahead 基準相差 1 位；`data[a:b]` 的方向也因檔而異。抄欄位時要以實際封包反推驗證，不能直接把表達式翻成程式。
2. **CRC 參數不在 XML 內**：只有 CAN-15 已實證。eSPI CRC8、CAN FD CRC-17/21（特別是初值與是否含填充位）、I3C CRC5/P0/P1、USB PD CRC32 都是依規格知識寫的，需要測試向量。
3. **XML 自身缺陷**（實作時要避開）：
   - `CAN.xml:192-193` 沒有夾住 DLC。
   - `I2C.xml` 的 10-bit Sr 讀取流程不正確。
   - `CAN_FD.xml:338-339` 的固定填充值依 `Data[0]` 決定，語意不明。
   - `MIPI_I3C_00_80.xml:9` 與 `MIPI_I3C_01_1_1.xml:9` 的版本註記錯誤。
   - 兩個檔案無法解析（§1.3）。
4. **版本老舊**：eSPI 為 Rev 0.75；I2C XML 依 v2.1，未涵蓋 Ultra-Fast 模式。這些 XML 也不能當成合規判定依據。
5. **樣本不足**：只有 I2C 與 UART 有可解的實機資料；CAN 有真值但波形解析度不足；其餘協定為零。SPI、eSPI、FD、PD、I3C HDR 都只能先用合成向量，**合成向量只能證明「與自己對規格的理解一致」**，不能證明符合規格。
6. **K 碼數值推論**：USB PD ordered set 的 16-bit 值為「5b K 碼低 4 位」是本次推論，數值自洽但沒有原廠文件佐證。
7. `解碼定義.md` 與 `低速訊號判斷準則.md` 是靜態整理，文件本身也聲明未在波形上驗證（`低速訊號判斷準則.md:84`、`解碼定義.md:3,22`）。本報告直接引用原始 XML，不以它們為準。

---

## 附：本次產生的驗證腳本

- `/private/tmp/claude-501/-Users-lianshi-Desktop-claude-cowork-------html/59abe1e3-4e68-4fe7-8ea5-3e9abc51ed03/scratchpad/crc/crc15.py`：讀 X6000A CAN CSV，從 ID / Type / DLC / Data 重建去填充後的位元串，計算 CRC-15 並與 CSV 比對。結果：`ok 208 bad 1`（不符的那列在示波器上也標了 CRC 錯誤）。日後實作 `can_decode.py` 時可以改寫成它的自檢。

---

# 附錄 B：Codex 完整報告


## 結論與適用範圍

本專案可先以**既有 I2C、UART、I3C SDR 核心**為基礎，補強實測驗證，再依序加入 SPI、Classic CAN、CAN FD、eSPI、USB PD 與 I3C HDR。XML 最有價值的是封包分類、欄位長度、條件分支和顯示語意；它們大多假設 Infiniium 已先把波形轉成有邊界的符號或位元資料，**不是完整的波形解碼演算法**。

本次為只讀分析，未修改專案。`解碼定義.md` 未整檔讀取；判斷主要依個別 XML、現有程式、實測 CSV 摘要與下方引用的原始資料。CRC 等未能從 XML 或可靠資料完整確認的參數，以下明確標示為待確認，不能作為驗證通過的依據。

### 對應檔案總覽

| 協定 | 對應 XML | 主要限制 |
|---|---|---|
| I2C | [I2C.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2C.xml:16>)、[I2CIgnoreRW.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2CIgnoreRW.xml:16>) | 後者將 R/W 納入顯示地址；不是另一種線路協定 |
| I3C | [MIPI_I3C_00_80.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/MIPI_I3C_00_80.xml:6>)、[MIPI_I3C_01_00.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/MIPI_I3C_01_00.xml:6>)、[MIPI_I3C_01_1_1.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/MIPI_I3C_01_1_1.xml:6>) | 後者標示 1.1.1，但標頭沿用 1.0 文件資訊，且不是標準合法 XML |
| SPI | **無一般 SPI XML**；可參考 [QuadSPI.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/QuadSPI.xml:49>) | 只有簡略的 8-bit Command，不能推導通用 SPI 時序或裝置命令 |
| eSPI | [eSPI.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/eSPI.xml:17>) | 命令與回應欄位豐富，實體取樣仍須另做 |
| CAN | [CAN.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN.xml:13>) | CRC 實作委派給外部函式 |
| CAN FD | [CAN_FD.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN_FD.xml:13>) | XML 的 CRC 欄位長度包含額外位元，不能直接視為純 CRC 寬度 |
| RS-232 | **無**；[LIN.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/LIN.xml:54>) 僅可參考 LIN 封包建模 | LIN 有專屬 break、sync、ID、parity、checksum，不能當一般 UART |
| RS-485 | **無**；LIN 不可作為 RS-485 上層協定定義 | RS-485 本身是差動實體層，沒有固定封包格式 |
| USB PD | [USB_PD_02_10.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/USB_PD_02_10.xml:6>)、[USB_PD_03_11.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/USB_PD_03_11.xml:6>)、[USB_PD_31_15.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/USB_PD_31_15.xml:6>) | 分別標示 PD 2.0 v1.0、3.0 v1.1、3.1 v1.5；3.0 檔不是標準合法 XML |

使用 Python 標準 XML parser 的只讀檢查中，I3C 1.1.1 在第 84 行、USB PD 3.0 v1.1 在第 1524 行出現不合法 token；其餘上述 I3C 和 USB PD 版本可解析。這不表示內容完全不可參考，但應先以原始文字核對，不可假設一般 XML parser 能直接載入。

## XML 共通解碼模型

典型資料流是：

1. **前端輸入**：示波器或自寫解碼器先把電壓波形轉成邏輯電平、邊緣、符號與時間戳。
2. **Bus／Label**：XML 以 `Data`、`IsValid`、`IsSop`、`IsEop`、`Mode` 描述儀器交給封包層的資料。例如 [I2C.xml:22](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2C.xml:22>)。
3. **分類與欄位**：`BusProtocol`、`PacketMask`、`Select`、`Lookahead`、`Field`、`SegmentedField` 和 `RepetitiveFields` 描述選擇條件、欄位和重複結構。
4. **檢查與顯示**：`Enumset`、`ValueError`、`ProtocolErrors` 及顯示設定提供名稱和部分錯誤條件；`ValueFunction="agProtocols:..."` 則把計算交給外部函式，例如 [CAN.xml:196](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN.xml:196>)。

**實作界線**：不能因資料夾內有 `agProtocols.dll` 就假定其函式的介面、行為、跨平台可用性或授權已確定。建議把 XML 當作人工核對的規則來源；CRC、訊號時序、位元填充、同步及錯誤復原，以有測試向量的獨立程式實作。

現有程式實際位於 `scope_tool/web/`：入口列有 I3C、I2C、SPI、UART、CAN，但以動態匯入檢查，目前目錄內有 I2C、I3C、UART 的 Python 核心，沒有 `spi_decode.py` 或 `can_decode.py`；缺少模組時入口會回報尚未實作。[analysis_decode.py:20](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/scope_tool/web/analysis_decode.py:20>)、[analysis_decode.py:27](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/scope_tool/web/analysis_decode.py:27>)

---

## I2C

**XML 與版本。** `I2C.xml` 標示源自 I2C 規格 2.1，提供一般 7／10-bit 地址顯示；`I2CIgnoreRW.xml` 將 R/W 納入地址顯示，因而是 8／11-bit 表示方式。兩者比較 CSV 時要先統一地址表示，避免把同一地址誤認為不同裝置。[I2C.xml:6](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2C.xml:6>)、[I2CIgnoreRW.xml:16](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2CIgnoreRW.xml:16>)

**實體與時序。** SDA、SCL 通常為開漏加上拉；高低門檻應依供電、量測點設定。SCL 高時 SDA 高→低為 START、低→高為 STOP；一般資料在 SCL 高期間穩定，在穩定高電平區取樣。支援 clock stretching，不應以固定時鐘週期假設下一個位元時間。常見標準速率為 100 kbit/s、400 kbit/s、1 Mbit/s，另有高速模式；不得用頻率單獨識別協定。[NXP I2C 規格](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/other/16345/1/UM10204.pdf)

**結構與檢查。**

- 7-bit：START → 地址 7 + R/W 1 + ACK 1 → 每筆資料 8 + ACK 1 → STOP 或 repeated START。
- 10-bit：首 byte `11110` + 地址高 2 + R/W，再 ACK；一般起始地址階段再傳地址低 8 + ACK。10-bit 讀取的 repeated START 需保留前一個地址脈絡，不能一律要求重送第二地址 byte。
- byte MSB first；ACK 為低、NACK 為高。讀取最後一個 byte 的 NACK 可是正常終止。
- **基本 I2C 無通用 CRC 或 parity**；例如 SMBus PEC 屬上層延伸，不能自動套用。

**可沿用／自行實作。** 起停描述、7-bit 欄位、10-bit 分段地址和 ACK 列舉，可分別參考 [I2C.xml:67](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2C.xml:67>)、[I2C.xml:129](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2C.xml:129>)、[I2C.xml:162](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2C.xml:162>)、[I2C.xml:217](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/I2C.xml:217>)。門檻、毛刺、SCL 時序、截斷及 repeated START 狀態需由程式處理。

**建議驗證。** 既有 [i2c_decode.py:35](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/scope_tool/web/i2c_decode.py:35>) 已處理 10-bit 脈絡；用合成波形覆蓋 7／10-bit 讀寫、address/data NACK、正常讀尾 NACK、clock stretch、重啟、毛刺與截斷。再對照 [實測 CSV](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/X6000A-解碼/I2C/x6000i2c3.csv:1>)，先確認 CSV 的地址是否包含 R/W；其 `E2W` 等顯示不能直接當作 7-bit 地址。

## I3C

**XML 與版本。** 三檔分別標示 V0.80、V1.00、V1.1.1。注意 V0.80 檔的標頭引用 0.7 revision 13；1.1.1 檔標頭仍寫 1.0 revision 13，不能僅靠註解確定其完整規格覆蓋。V1.00 的分類包括 legacy I2C、private、CCC 與 HDR 模式。[MIPI_I3C_01_00.xml:68](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/MIPI_I3C_01_00.xml:68>)

**實體與時序。** SDA/SCL 需依階段處理開漏、推挽與釋放；I3C SDR 基本原始速率可達 12.5 Mbit/s，並可與 legacy I2C 共存。HDR-DDR 在時鐘雙邊緣傳輸，TSP/TSL、BT 和多 lane 則需不同解碼器，不能只把 SDR 位元率調高。[MIPI I3C FAQ](https://www.mipi.org/resources/I3C-frequently-asked-questions)、[MIPI 功能資料](https://www.mipi.org/hubfs/Webinars/MIPI-Webinar-Whats-New-with-I3C-15-Sep-2021.pdf)

**結構與檢查。** SDR 私有傳輸通常由 START／地址 7 + R/W + 地址 ACK 開始，再傳 8-bit 資料與第九個 T-bit，最後 STOP／重啟。寫入資料的 T-bit 為奇同位；讀取時 T-bit 具有繼續／結束等不同語意，不能統一當 ACK 或 parity。CCC 可經廣播地址 `0x7E` 分派；DAA、IBI、Hot-Join 與 legacy I2C 均需狀態脈絡。HDR 有各自的 parity／CRC，**不能套用 SDR 規則**。

XML 列出 HDR parity、HDR-DDR CRC5 等錯誤，但 CRC5 的多項式、初值、涵蓋範圍未由本次查閱確定，應先標示「未驗證」，不要只憑欄位名稱實作。[MIPI_I3C_01_1_1.xml:6586](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/MIPI_I3C_01_1_1.xml:6586>)

**可沿用／自行實作。** CCC 分類、欄位及錯誤名稱可參考 XML；電氣狀態、總線仲裁、T-bit 語意與 HDR 前端必須自行實作。既有 [i3c_decode.py:3](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/scope_tool/web/i3c_decode.py:3>) 明確標示為單 lane SDR、待真機驗證，且已區分讀取 T-bit、寫入 parity 與 I2C ACK。[i3c_decode.py:124](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/scope_tool/web/i3c_decode.py:124>)

**建議驗證。** 先以 SDR 的 private read/write、奇同位錯誤、CCC、DAA、IBI、legacy 混合波形及截斷建立向量；取得真機波形後核對。HDR 依模式、版本分期實作，每種 CRC 要有獨立標準向量。

## SPI

**XML。** 一般 SPI XML：**無**。`QuadSPI.xml` 的 transaction 層只定義 8-bit Command；可參考封包呈現，不能據此推定所有裝置的 command、地址或 dummy cycles。[QuadSPI.xml:49](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/QuadSPI.xml:49>)

**實體、結構與檢查。** 通常由 SCLK、CS、MOSI、MISO 組成；電平及上限頻率依裝置。設定 CPOL／CPHA 四種模式，選定前緣或後緣取樣；CS 有效期間依設定字長組字，常見 8-bit、MSB first，但字長與位序都不通用。SPI 本身沒有固定封包、ACK、parity 或 CRC；命令、地址、dummy、資料及任何檢查碼由裝置協定決定。多 IO SPI 必須按階段設定線數與方向。

**實作與驗證。** 自行實作 CS 邊界、四模式、位序、可變字長、MOSI/MISO 同步與部分字截斷；以四模式 × 兩種位序產生已知 `0x96` 等非對稱資料，加入 CS 中斷、空閒時鐘及缺線情境。裝置層再用其資料手冊的實例驗證。

## eSPI

**XML。** [eSPI.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/eSPI.xml:17>) 有 command／response 分類、opcode、通道結構與 CRC 欄位。

**實體與結構。** 以 CLK、CS# 和設定的單／雙／四線 IO 傳輸；取樣邊緣、線寬和方向需依實際協商及階段處理。交易可概括為 command phase：8-bit opcode + 視命令存在的 header/data + CRC-8；response phase：等待狀態、8-bit response code + 可選 header/data + status + CRC-8。各命令長度並不相同，例如 XML 的部分 header 有 4-bit tag、12-bit length 與 32／64-bit 地址。[eSPI.xml:885](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/eSPI.xml:885>)

**CRC 與回應。** CRC-8 多項式 `0x07`、初值 `0x00`，各 byte MSB first；command 涵蓋 opcode、header、data；response 涵蓋 response code、header、data、status，排除 WAIT_STATE。CRC 產生是必要的，但接收端檢查啟用與否由設定決定，因此解碼器應分開報告「計算不符」與「裝置當時是否啟用檢查」。[Intel eSPI 規格 §5.2](https://cdrdv2-public.intel.com/841685/841685_ESPI_IBS_TS_Rev_1_6.pdf)

**可沿用／自行實作。** XML 直接提供命令篩選和欄位、CRC 容器、`ACCEPT`、`DEFER`、`WAIT_STATE` 等回應；CRC 函式本身委派 DLL。[eSPI.xml:520](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/eSPI.xml:520>)、[eSPI.xml:582](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/eSPI.xml:582>)。自行實作線寬切換、turnaround、等待、CRC 和跨 command/response 關聯。

**驗證。** 從 `GET_STATUS`、設定讀寫和不同回應開始，測單／雙／四線、WAIT_STATE 排除 CRC、錯誤 CRC 與被截斷回應；取得控制器已知交易做交叉比對。

## Classic CAN

**XML。** [CAN.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN.xml:13>)；`CAN_FD.xml` 也包含 Classic CAN 分支，可交叉檢查，但應留意兩者 EOF 等呈現差異。

**實體與時序。** 典型 CAN_H/CAN_L 差動：顯性為邏輯 0、隱性為邏輯 1；也可量收發器邏輯端，但需設定極性。依 nominal bit rate 和可配置 sample point 取樣，並以有效邊緣重同步。SOF 到 CRC sequence 結束間，連續五個相同位元後插入相反動態 stuff bit；填充檢查須在正確區段進行。[Microchip CAN 錯誤說明](https://developerhelp.microchip.com/xwiki/bin/view/applications/can/overview/errors/)

**結構。** SOF 1 → 標準 11-bit ID、RTR、IDE、保留位，或延伸格式的 11-bit ID、SRR、IDE、18-bit ID、RTR、保留位 → DLC 4 → data 0–8 byte（remote 無 data）→ CRC 15 → CRC delimiter 1 → ACK slot 1 → ACK delimiter 1 → EOF 7 → intermission。XML 列出選擇分支與欄位。[CAN.xml:143](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN.xml:143>)

**檢查。** CRC-15/CAN 多項式 `0x4599`（省略最高次項）、初值 0；涵蓋去除動態 stuff bits 後的 SOF 至 data 欄位末尾。CRC delimiter、ACK delimiter 和 EOF 應為隱性；ACK slot 顯性代表至少有接收端確認。還須區分 stuff、form、CRC、ACK、error／overload frame；ACK 缺失不等於 CRC 必定錯誤。XML 將 CRC 委派 `agProtocols:CANCRC15`。[CAN.xml:196](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN.xml:196>)

**實作與驗證。** 自行實作取樣同步、去填充、CRC 與錯誤復原；不要把 XML 的 intermission 顯示欄位當作完整總線規範。用標準／延伸、data／remote、0／8 byte、stuff 邊界、CRC 錯與無 ACK 向量；對照 [CAN 實測 CSV](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/X6000A-解碼/CAN/x6000can.csv:1>) 的 ID、類型、DLC、data、CRC 與時間。Classic DLC 9–15 的處理需依適用規範和控制器行為確認，不能直接讀成 9–15 byte。

## CAN FD

**XML。** [CAN_FD.xml](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN_FD.xml:143>) 同時分派 Classic 與 FD；以 FDF／EDL 等欄位及完整結構辨識，不可只看是否換速。

**實體與時序。** 使用 CAN 差動實體層；nominal 與 data phase 的 bit rate、sample point 須分開設定。BRS 開啟時才切換資料階段速率，BRS 關閉仍可能是 FD。動態 stuff bits 與 CRC 欄位的固定 stuff bits 規則不同，必須分開處理；切換點和重同步應依實際 ISO 版本驗證。

**結構。** 標準或延伸 ID → RRS／IDE → FDF → res → BRS → ESI → DLC 4 → data → stuff count／parity、CRC → delimiter、ACK、EOF。FD 無 Classic remote frame。DLC 0–8 為 0–8 byte；9、A、B、C、D、E、F 分別為 12、16、20、24、32、48、64 byte。[CAN_FD.xml:312](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN_FD.xml:312>)、[CAN_FD.xml:326](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN_FD.xml:326>)

**檢查。** ISO FD 對至多 16 byte 用 CRC-17，20 byte 以上用 CRC-21；多項式分別為 `0x1685B`、`0x102899`，省略最高次項。ISO 格式另有 modulo-8 Gray 編碼 stuff count、parity 和固定 stuff bits；CRC 計算與 Classic CAN 的去填充資料流不同，動態填充和計數欄位的處理需依 ISO 規格實作。**本次未能從本地 XML 確認完整初值、輸入範圍與 bit ordering；不要把通用 CRC 型錄的零初值直接當 ISO 線路 CRC 初值。** Non-ISO FD 格式另有差異。[Microchip ISO／non-ISO 欄位圖](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP251XXFD-CAN-FD-Controller-Module-Family-Reference-Manual-20005678B.pdf)、[CiA CRC 說明](https://www.can-cia.org/can-knowledge/cyclic-redundancy-check-crc-in-can-frames)

**可沿用／自行實作。** XML 的 DLC 對照、FDF/BRS/ESI 和錯誤類型可沿用；其 `Length="21"`／`Length="26"` 欄位並非純 21／26-bit CRC，且計算由外部函式處理。[CAN_FD.xml:337](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/CAN_FD.xml:337>) 應自行處理實際位元與 CRC，並將 ISO／non-ISO 明確分模式。

**驗證。** 使用獨立控制器或已知標準向量，測 DLC `A/B` 的 CRC-17／21 邊界、BRS 開關、動態與固定填充、stuff count parity、錯誤 ACK、兩個速率及 ISO／non-ISO；未完成向量核對前，CRC 結果標為未驗證。

## RS-232

**XML。** 對應 XML：**無**。LIN 的 UART 類傳輸可提供位元順序及檢查欄位的建模參考，但其 break、`0x55` sync、6-bit ID、2-bit parity 與 checksum 都是 LIN 專屬。[LIN.xml:70](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/LIN.xml:70>)

**實體與時序。** RS-232 是電氣介面；線路端邏輯 1 通常為負電壓、0 為正電壓，接收端典型規格區分小於 −3 V 與大於 +3 V；收發器後的 MCU 邏輯端極性可能相反。設定 baud、極性、資料位數、parity、stop；UART 常見 idle 1、start 0，從 start 邊緣確認半個 bit 後，在每 bit 中央取樣。[ADI RS-232／RS-485 資料](https://www.analog.com/en/resources/analog-dialogue/articles/digital-isolators-protect-rs232-bus.html)

**結構與檢查。** UART 字元為 start 1 → 資料位，通常 LSB first → 可選 parity 1 → stop；沒有通用封包邊界、ACK 或 CRC。偶／奇 parity、mark／space、stop framing error 應依設定檢查；上層封包與 CRC 另定。

**實作與驗證。** 現有 [uart_decode.py:18](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/scope_tool/web/uart_decode.py:18>) 支援 5–9 資料位、N/E/O/M/S、1／2 stop、反相與 baud 設定；現行選項並未列出 1.5 stop。用 8N1、7E1、錯 parity、錯 stop、反相、baud 誤差和截斷向量，再對照 [RS-232 實測 CSV](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/X6000A-解碼/RS-232/x6000rs235.csv:1>)。CSV 有未知錯誤與時間 `?`，應保留為待核對資料，不能直接視為完整真值。

## RS-485

**XML。** 對應 XML：**無**。RS-485 只定義平衡式差動介面；`LIN.xml` 不能當 RS-485 或 Modbus 定義。若實際上層是 UART，可重用既有 UART 核心。

**實體與時序。** 量測差動電壓並確認設備的 A/B 定義與極性；傳統接收器對約 ±200 mV 差動訊號的判斷能力是參考，實際門檻、遲滯、fail-safe 依收發器而異。可為兩線半雙工或四線全雙工；bit rate、編碼和取樣點由上層決定。[ADI RS-485 接收門檻說明](https://www.analog.com/en/resources/app-notes/an-1399.html)

**結構與檢查。** RS-485 本身沒有固定訊框、CRC、parity 或 ACK；若承載 UART，套用上一節字元格式；若承載 Modbus RTU，則需另依 Modbus 規格處理幀間隔與 CRC，不能由差動波形自動斷言是 Modbus。

**實作與驗證。** 加入雙通道差動或外部差動探棒輸入、極性與門檻設定，再交給指定上層解碼器。測試 A/B 交換、共模變化、低差動振幅、總線空閒、半雙工方向切換與 UART parity／framing 錯誤。

## USB PD

**XML 與版本。** 三版檔案分別對應標頭所述 PD 2.0 v1.0、3.0 v1.1、3.1 v1.5；應明確選擇版本，不能把新版訊息直接套到舊版。

**實體與編碼。** 本項建議先限定 **Type-C CC 上的 BMC**：名目 300 kbit/s，先恢復 BMC 位元，再將 5-bit 符號解成 4-bit 資料或特殊控制符號；資料 LSB first。不同 PD 實體傳輸方式不可一概以此處理。CC 電壓門檻需考慮附著狀態、供電角色及量測配置，不能硬編單一固定閾值。XML 明示位元 LSB first。[USB_PD_03_11.xml:16](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/USB_PD_03_11.xml:16>)

**結構。** 一般訊息為 preamble → SOP ordered set → 16-bit message header → 0–7 個 32-bit data objects，或依版本有 extended header/data → CRC-32 → EOP。SOP、SOP′、SOP″、Hard Reset、Cable Reset 使用不同 ordered set；reset ordered set 不能當成一般有 header 的訊息。XML 的 ordered-set 值是**已解碼後的內部表示**，不能直接當線路上的 5-bit 符號。[USB_PD_03_11.xml:1141](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/USB_PD_03_11.xml:1141>)

**檢查。** 驗證 BMC 時序、合法 4b/5b 符號、ordered set、header 長度／版本、CRC、EOP 與訊息 ID；`GoodCRC` 是回應訊息，需依 SOP 類型及 ID 關聯，不是單一 ACK 位。XML 的 32-bit CRC 欄位以 header／內容容器為輸入，委派 `agProtocols:USB3LCRC32`。[USB_PD_03_11.xml:1166](</Users/lianshi/Desktop/claude-cowork/示波器截圖_html/rea/Protocols/USB_PD_03_11.xml:1166>)

**CRC 限制。** 本次沒有從可核對的本地定義確認該函式的多項式表示、初值、反射、最後 XOR 和線路 bit order 的完整組合；雖名稱為 CRC32，不能只因名稱相同就宣稱已符合 USB PD。正式驗證前應取得適用版本 USB-IF 規格與獨立訊息向量，逐位確認 header/data 的涵蓋及傳送順序。

**實作與驗證。** 分層建立 BMC 邊緣恢復、4b/5b 表、ordered-set、訊息 parser、版本化 payload 與 GoodCRC 關聯。向量涵蓋 SOP／SOP′／SOP″、reset、0／多 data object、extended message、非法符號、錯 CRC、缺 EOP 與截斷；再以 PD 分析儀或已知控制器波形交叉確認。

## 實作優先順序與風險

| 順序 | 建議範圍 | 難度與依據 |
|---|---|---|
| 1 | I2C、UART／RS-232 | 低至中；已有核心、合成檢查與實測資料，先建立可重現的 CSV 對照 |
| 2 | SPI、RS-485 + 已知上層 UART | 中；SPI 前端需新作，RS-485 可重用 UART，但需處理差動輸入 |
| 3 | Classic CAN | 中至高；有真機資料，但同步、填充、CRC 與錯誤復原需完整實作 |
| 4 | I3C SDR | 中至高；已有程式但明標待真機驗證，需混合總線與狀態測試 |
| 5 | CAN FD | 高；兩速率、ISO／non-ISO 與 CRC／stuff 處理必須由獨立向量驗證 |
| 6 | eSPI、USB PD | 高；多線方向／階段或 BMC／符號恢復，且本地缺真機樣本 |
| 7 | I3C HDR | 很高；多種編碼、模式及版本，應逐模式訂範圍 |

共通前端建議保留原始時間軸、通道與門檻，輸出每個欄位的時間範圍、原始位元、解碼值及錯誤／截斷狀態；低取樣率、門檻不明或擷取窗口不完整時標示可信度不足。CRC、同位或 ACK 無法驗證時應顯示「未驗證」，不要與「通過」混在一起。

最主要的不確定處是：**XML 的內部符號格式與 DLL 函式契約不完整、部分版本 XML 無法標準解析、FD／PD／I3C HDR 的完整 CRC 參數尚待規格與向量核對**。本次沒有執行真機比對，也沒有聲稱現有解碼器已通過樣本驗證。
