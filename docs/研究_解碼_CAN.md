# 研究：CAN 2.0A/B 與 CAN FD 離線解碼規格草案

研究日期：2026-10-26。範圍：從示波器類比波形（CANH/CANL 差動，或 CAN 收發器 RXD 單線）被動離線解碼 CAN 2.0A/B 與 CAN FD。本文件是實作前的規格，不含程式碼。

本文與 `docs/研究_數位解碼協定定義.md` 的關係：該文件 §8 已有 CAN 概要（實體層、位元時序、Classical／FD 差異、CRC 多項式、設定與錯誤分類）。本文不重抄 §8 的敘述，只補上可直接實作的欄位位元數、步驟、測試向量，並更正 §8.3 的一處多項式錯誤（見 §5.3）。引用既有段落時寫「見 研究_數位解碼協定定義 §8.x」。

來源代號沿用既有文件（C1、C2、C3、C4、O1、O3），新增 K 系列。來源可得性以「已取得原文」「僅取得摘要或二手引用」「未取得」三級標示。

---

## 0. 來源與可得性

| 代號 | 文件 | 性質 | 本次狀態 |
|---|---|---|---|
| ISO 11898-1:2015 | CAN 資料鏈路層 | 付費（ISO 商店） | 未取得全文；公開摘要頁未取得。位元填充與 FD 條文以下列二手引用為準，全部標「待確認原文」 |
| Bosch CAN 2.0 規格（1991） | 經典 CAN 原始規格 | 公開流通 PDF | 未取得本次原文；位元數（EOF、intermission、error flag）標「待確認」 |
| Bosch CAN FD 規格 v1.0（2012） | FD 歷史基線 | 公開 PDF（Bosch 官網） | 未取得。Bosch 產品頁（K4）僅列出技術論文與 M_CAN 頁，沒有規格 PDF 連結，版本號與日期以「待確認」處理 |
| K1（= 既有文件 C2） CiA，Cyclic redundancy check in CAN frames | CRC 多項式、Classical／FD、ISO／non-ISO 說明 | 公開網頁 | 本次已 WebFetch 取得原文，引用於 §4.3 |
| K2 Linux kernel 補丁 `can: length: fix bitstuffing count`（lkml 2306.1/09479） | 引用 ISO 11898-1:2015 的 FD CRC 填充條文 | 公開郵件存檔（二手引用 ISO） | 已取得，引用字句標為「二手引用」 |
| K3 reveng CRC catalogue，CRC-17/CAN-FD 條目 | 多項式與檢查值（check value） | 公開目錄 | 由搜尋摘要取得（poly 0x1685B、check 0x04F03）；本文另以程式獨立重算驗證（§5.3） |
| K4（= 既有文件 C4） Bosch CAN FD 產品頁 | 協定總覽 | 公開網頁 | 已 WebFetch；確認 FD 基線為 ISO 11898-1:2015、Classical 上限 1 Mbps |
| K5 搜尋摘要：Tektronix CAN/LIN/FlexRay 除錯應用筆記、Teledyne LeCroy CANbus TD 規格、Rigol「Technical Analysis of Automotive CAN-FD Bus」、Keysight CAN/CAN FD 資料表 | 呈現與欄位 | 公開 | 僅取得搜尋摘要，未開啟全文。引用僅作呈現參考 |
| C1 Microchip MCP251XXFD RM（DS20005678B） | 訊框、位元時序 | 公開 PDF | 本次 WebFetch 無法讀取 PDF 文字層，沿用既有文件的定位，未重新核對 |
| C3 TI TCAN1042-Q1 | 收發器門檻與終端 | 公開 | 沿用既有文件 §8.1 |
| Vector 線上課程 | 錯誤框架等 | 公開 | 本次 404，未取得 |

結論：本文所有「位元數、欄位順序」屬於經典 CAN 眾所周知的基本事實，但仍需以 ISO／Bosch 原文核對後才能當作測試斷言。CRC 多項式與檢查值已獨立驗證（§5.3）。FD 的 stuff count 編碼順序、奇偶性、CRC 覆蓋範圍仍有未確認項目（§5.4、§12）。

---

## 1. 實體層與取樣輸入

本節補充既有 §8.1，只列解碼器需要的實作參數。

- **輸入來源三種**：
  1. CANH 與 CANL 兩通道差動（建議）：`Vdiff = V(CANH) − V(CANL)`。
  2. 差動探棒直接量測 `Vdiff`。
  3. 收發器 RXD 單端數位輸出（最接近協定，但不是總線電壓；只能驗證收發器後的邏輯，無法觀察總線實際位準）。
  4. 只接 CANH 或 CANL 單線：標「單線近似」，抗共模能力差，不能作為合規依據。
- **位準判定**：recessive（邏輯 1）與 dominant（邏輯 0）。典型 5 V 系統中，dominant 時 CANH 約 3.5 V、CANL 約 1.5 V（差動約 2 V）；recessive 時兩線約 2.5 V（差動約 0 V）。這只是典型描述，解碼器不應寫死，應由 `Vdiff` 門檻決定（見 既有文件 §8.1）。
- **建議預設門檻（實作建議，非規格值）**：`Vdiff` 以遲滯兩門檻，dominant 判定 `Vdiff ≥ 0.9 V`、recessive 判定 `Vdiff ≤ 0.5 V`，中間區維持前態。來源：C3 收發器接收器特性（既有文件 §8.1 已引用 VID 約 0.5 V／0.9 V 的敘述）。使用者可覆寫，並可依 CAN 收發器規格改為 CANH/CANL 單端門檻。
- **終端**：兩端各 120 Ω，或分裂終端（split termination）。這只影響波形外觀，不影響解碼邏輯。來源：C3 §9（既有文件）。
- **共模**：差動解碼應報告 `(CANH+CANL)/2` 的共模準位。共模偏離大幅（例如 CANH 與 CANL 同時大幅偏移）時標「實體層可疑」，不要直接判 CRC 錯誤。

## 2. 位元時序與取樣（軟體解碼的簡化）

### 2.1 位元時間結構

位元時間 = `Sync_Seg + Prop_Seg + Phase_Seg1 + Phase_Seg2`，以 Time Quantum（TQ）計。取樣點位於 `Sync_Seg + Prop_Seg + Phase_Seg1` 結束處。

`SamplePoint = (Sync + Prop + Phase1) / (Sync + Prop + Phase1 + Phase2)`

- Sync_Seg 固定 1 TQ（經典 CAN 規格，待確認原文）。
- 再同步寬度 SJW 限制 Phase_Seg1 可延長、Phase_Seg2 可縮短的量；SJW ≤ min(Phase1, Phase2)（待確認原文）。
- 硬同步：SOF 的 recessive→dominant 邊緣重設位元時間。之後每個有效 recessive→dominant 邊緣做再同步（受 SJW 限制）。來源：C1 §3（既有文件 §8.1 引用）；SJW 上限為 CAN 規格通則，待確認原文。
- 建議取樣點百分比（CiA 慣例約 75–87.5%）：**待確認**，本次未取得 CiA 301 或 CiA 603 原文。

### 2.2 軟體解碼的簡化策略

示波器解碼器看不到節點內部 TQ、BRP、SJW，只能看到電壓波形與取樣。因此採用「以邊緣重新對齊」策略，不反推內部參數：

1. 使用者提供 nominal bit time（或 data bit time）。這是唯一必要參數；取樣點百分比為選用參數（預設 75%）。
2. 偵測 SOF：在 idle（recessive 長時間）後第一個 recessive→dominant 邊緣記為 `t0`。
3. 對每一個位元 `k`，理想位元中心 `c_k = t0 + (k + sp) × T_nom`。
4. 每遇到一個 recessive→dominant 邊緣（且在 stuffed 區，不是 idle），用它與 `t0` 估計自上次同步後的累積誤差；若誤差在 SJW 範圍內，調整 `t0` 與 `T` 的估計值（最小平方或指數平滑），否則標記「時序不一致」。
5. 取樣仍對每個位元內的實際樣本點取值，不以邊緣取代取樣。

簡化要點：只在 recessive→dominant 邊緣上做修正；dominant→recessive 邊緣不修正（與 CAN 的 hard／resync 規則一致，待確認原文）。這避免在 stuff 位元附近誤用 recessive 尾段。

**FD 的 BRS 切換**：`c_k = t0 + (k+sp)×T_nom` 只適用於 nominal phase。BRS=1 時，取樣點切換到 data timing（BRS 位元之後的 data 位元用 `T_data`）；CRC delimiter 的取樣點切回 nominal。跨界位元含兩種時序，解碼器須為它保留兩段時間估計，不能只用單一 bit width 切割。

**Stuff 位元不影響取樣節奏**：stuff 位元仍佔一個位元時間，應照常取樣並從位元流移除。

**已知限制**：長時間同一位準（最長 5 個相同位元，stuff 之前）之後的邊緣最遠，誤差最大；FD data phase 若使用不同 nominal T，必須有獨立的時間估計。

## 3. 訊框格式逐欄位

以下位元數依 Classical CAN 慣例整理，**欄位位元數以 Bosch CAN 2.0 規格與 ISO 11898-1 為準，本次未取得原文，標「待確認原文」的項目需核對**。已在本次二手來源中確認的部分以「（K1／K2）」標示。

### 3.1 Classical CAN 2.0A（標準 11-bit ID）

| 序 | 欄位 | 位元數 | 值與意義 | 參與 CRC | 參與 stuffing | 備註 |
|---|---|---|---|---|---|---|
| 1 | SOF | 1 | dominant（0） | 是 | 是 | 硬同步點 |
| 2 | ID[10:0] | 11 | MSB first | 是 | 是 | 低值優先仲裁 |
| 3 | RTR | 1 | 0=data frame，1=remote frame | 是 | 是 | 2.0A 位於控制段 |
| 4 | IDE | 1 | 0=標準格式（2.0A） | 是 | 是 | 2.0B 另有擴充 |
| 5 | r0 | 1 | 保留，dominant 送出 | 是 | 是 | 待確認原文「必須為 0」或「接收器忽略」 |
| 6 | DLC[3:0] | 4 | 資料長度；0–8 有效，9–15 解為 8 | 是 | 是 | 遠端訊框的 DLC 表示請求長度 |
| 7 | DATA | 0–64 | DLC≤8 時 0–8 bytes | 是 | 是 | 遠端訊框無資料段 |
| 8 | CRC | 15 | CRC-15，見 §5.1 | — | 是（CRC 序列本身也參與填充） | 含於動態填充區 |
| 9 | CRC delimiter | 1 | recessive | 否 | 否 | 固定形狀，偏離要標 form error |
| 10 | ACK slot | 1 | 發送者送 recessive；接收者有效接受時拉 dominant | 否 | 否 | 單節點錄製無法判定哪個節點 ACK |
| 11 | ACK delimiter | 1 | recessive | 否 | 否 | 固定形狀 |
| 12 | EOF | 7 | recessive | 否 | 否 | 「填充規則不適用」 |
| 13 | Intermission | 3 | recessive | 否 | 否 | 待確認原文 |

### 3.2 Classical CAN 2.0B（擴充 29-bit ID）

| 序 | 欄位 | 位元數 | 值與意義 |
|---|---|---|---|
| 1 | SOF | 1 | dominant |
| 2 | ID-A[10:0] | 11 | base ID |
| 3 | SRR | 1 | 擴充格式中 recessive（與 2.0A 的 RTR 位置相同但意義不同） |
| 4 | IDE | 1 | recessive=擴充格式 |
| 5 | ID-B[17:0] | 18 | 擴充 ID 低段 |
| 6 | RTR | 1 | 位於擴充控制段 |
| 7 | r1, r0 | 2 | 保留 |
| 8 | DLC[3:0] | 4 | 同 2.0A |
| 9 | DATA、CRC、ACK、EOF、IFS | 同 2.0A | 同 3.1 |

完整 29-bit ID = `ID-A << 18 | ID-B`。SRR 與 IDE 的位置決定 base 與 extended 的仲裁分界（同 base ID 時 base 可優先於 extended，待確認原文）。來源：K1 與 C1 既有文件 §8.2 已述。

### 3.3 CAN FD 訊框（ISO-style 欄位順序）

基本格式欄位順序：SOF、ID、RRS、IDE、FDF、res、BRS、ESI、DLC。擴充格式順序：SOF、ID-A、SRR、IDE、ID-B、RRS、FDF、res、BRS、ESI、DLC。表列 11–18 序號沿用原表（DLC 起）。

| 序 | 欄位 | 位元數 | 值與意義 | 參與 CRC | 參與 dynamic stuffing |
|---|---|---|---|---|---|
| 1 | SOF | 1 | dominant | 是 | 是（nominal 速率） |
| 2 | ID（base 或 ID-A） | 11 | | 是 | 是 |
| 3 | 基本格式：RRS（位於 RTR 位置）；擴充格式：SRR（recessive） | 1 | FD 無 remote frame，基本格式 RRS 固定 dominant（待確認原文） | 是 | 是 |
| 4 | IDE | 1 | 1=擴充 | 是 | 是 |
| 5 | ID-B（僅擴充） | 18 | 接在 IDE 之後 | 是 | 是 |
| 6 | RRS（僅擴充） | 1 | 擴充格式在 ID-B 之後，位於 RTR 位置 | 是 | 是 |
| 7 | FDF（EDL） | 1 | recessive=CAN FD 訊框；dominant 表示 Classical。擴充格式時位於 r1 位置 | 是 | 是 |
| 8 | res（r0） | 1 | 保留；**ISO 原文 res 位準：待確認**。收到 FDF=1 且 res=1 時可能屬於 protocol exception（列為 E12，見 §6） | 是 | 是 |
| 9 | BRS | 1 | recessive=切換到 data bit rate；dominant=全程 nominal | 是 | 是（BRS 位元的取樣點仍在 nominal 時序） |
| 10 | ESI | 1 | 0=error active 發送者；1=error passive 發送者 | 是 | 是 |
| 11 | DLC[3:0] | 4 | 見 §3.4 長度表 | 是 | 是 |
| 12 | DATA | 0–64 bytes | 以 data bit rate 傳送（BRS=1 時） | 是 | 是（動態填充仍適用） |
| 13 | stuff count（SBC） | 4 | 3 位元 Gray code＋1 parity（見 §5.4） | 依 §5.4 | **固定填充** |
| 14 | CRC | 17 或 21 | CRC-17 用於 ≤16 bytes；CRC-21 用於 20–64 bytes（K1）。16 bytes 與 20 bytes 之間不存在的長度 | 見 §5.2 | **固定填充** |
| 15 | CRC delimiter | 1 | recessive，本位元切回 nominal 速率 | 否 | 否 |
| 16 | ACK slot | 1 | nominal | 否 | 否 |
| 17 | ACK delimiter | 1 | recessive | 否 | 否 |
| 18 | EOF | 7 | recessive | 否 | 否 |
| 19 | Intermission | 3 | recessive | 否 | 否 |

來源：K1、K2（ISO 條文二手引用）、K4（FD 位元率切換與長度擴充）、C1（既有文件 §8.2）。**BRS 位置與 CRC delimiter 切回的時點，依 K1 與 K4 的描述，但 ISO 原文字句未取得，需逐條核對。**

### 3.4 DLC 與資料長度

| DLC | Classical CAN（bytes） | CAN FD（bytes） |
|---|---|---|
| 0–8 | 0–8 | 0–8 |
| 9 | 8 | 12 |
| 10 | 8 | 16 |
| 11 | 8 | 20 |
| 12 | 8 | 24 |
| 13 | 8 | 32 |
| 14 | 8 | 48 |
| 15 | 8 | 64 |

Classical CAN 的 DLC 9–15 規格要求送 8 bytes（接收器應解為 8，待確認原文），既有文件 §8.2 已記載。CAN FD 表與 K1、K4 一致。解碼器應保留原始 DLC 值，並同時顯示解碼後 bytes，因為 Classical 的 DLC>8 與 FD 解讀不同。

### 3.5 Error frame 與 overload frame

下列位元數為經典 CAN 規格的常見描述，**本次未取得 Bosch CAN 2.0 原文，全部標待確認**：

- Active error flag：6 個 dominant 位元（有意破壞填充規則，之後是 8 個 recessive error delimiter）。
- Passive error flag：6 個 recessive 位元（在共用總線上可能與 idle 無法區分）。
- Overload frame：6 個 dominant overload flag，接 8 個 recessive delimiter；通常在 intermission 階段發送。
- 解碼器判斷：連續 dominant 超過 5 位元（或填充違規）時，先標為「疑似 error flag」，再看後續 recessive 長度與位置，決定是 error frame、overload frame 或雜訊。
- Overload 的觸發與旗標分開描述：intermission 第 1 或第 2 位元偵測到 dominant 時，節點於下一位元開始發送 overload flag（第 2 位元觸發時，旗標自第 3 位元開始）；第 3 位元 dominant 按 SOF 接收（Codex 引用 Bosch CAN 2.0 Part B，本次未核實，待確認原文）。
- FD 資料段偵測到錯誤時，節點切回 nominal bit rate 發送 error frame；解碼器應在進入 error frame 時就恢復 nominal 取樣（Codex 引用 Microchip C1 §1.4，本次未重新核實全文，見 §12）。
- 錯誤框架會導致其他節點也發送 error flag，重疊時 dominant 段可更長；正常旗標疊加可觀察到約 6–12 個 dominant 位元，delimiter 中再次 dominant 時須依 Bosch 規則處理（待確認原文）。單一錄製通常無法判定哪個節點發出。來源：C1 既有文件 §8.4 與 Rigol 摘要（K5）敘述相符，數字待確認原文。

---

## 4. 位元填充與去填充

### 4.1 規則總覽

| 區段 | 規則 | 來源 |
|---|---|---|
| SOF 到 CRC 序列結束（Classical） | 動態填充：連續 5 個相同位元後插入一個相反位元 | K1、既有文件 §8.3 |
| CRC delimiter 之後 | 不填充 | K1 |
| CAN FD：SOF 到資料段結束 | 動態填充（同 Classical 規則） | K2 |
| CAN FD：stuff count＋CRC 區段 | 固定填充：在 stuff count 前插入一個固定填充位元，之後每 4 個位元插入一個固定填充位元；固定填充位元值與前一位元相反 | K2 引用 ISO 11898-1:2015 |
| CAN FD 固定填充位元數 | `1 + floor(len(CRC field) / 4)`，其中 `len(CRC field) = 4 + len(CRC)`；CRC-17 得 6 個、CRC-21 得 7 個 | K2（二手推導，待確認） |

固定填充位元還同時作為 stuff count 與 CRC 的第二層保護，此為 K1 的說明。

### 4.2 解碼器步驟（虛擬碼）

```
// 輸入：已判位的線上位元流 line[]（含所有填充位元）、is_FD、profile
// 狀態：DYN  — 動態填充（FD：SOF 到資料段結束；Classical：SOF 到 CRC 序列結束）
//       TAIL — Classical 專用：CRC 最末位後，處理可能的最後一個動態填充位元
//       FIX  — FD 固定填充區（SBC＋CRC，共 L = 4 + crc_len 個資料位元）
//       DELIM — CRC delimiter 及之後固定欄位（不填充）
state = DYN; run_val = None; run_len = 0
fields = []                 // 去填充後欄位位元
dyn_stuff = 0               // 動態填充計數（SBC 比對用）

for each bit b at line index i:
    if state == DYN:
        if run_len == 5:                       // 此位元必為填充
            if b == run_val: STUFF_ERROR(i); ERROR_HANDLING; stop
            run_val, run_len = b, 1            // 填充位元是下一段 run 的第一位
            dyn_stuff += 1
            continue
        fields.append(b)
        run_len = run_len + 1 if b == run_val else 1
        run_val = b
        if is_FD and len(fields) == data_end_index:   // FD 資料段最後一位
            state = FIX; prev = b; fixed_pos = 0; nfix = 0
        if (not is_FD) and len(fields) == crc_end_index:
            state = TAIL

    elif state == TAIL:                        // Classical
        if run_len == 5:                       // CRC 最末位形成五連，此位元為動態填充
            if b == run_val: STUFF_ERROR(i); ERROR_HANDLING; stop
            run_len = 0; continue
        state = DELIM; process b as CRC delimiter   // 填充不存在時，此位元即 delimiter

    elif state == FIX:                         // FD：固定填充位於 fixed_pos = 0, 5, 10, ...
        if fixed_pos % 5 == 0:                 // 固定填充位元，值必須與前一位元相反
            if b == prev: FORM_ERROR(i, "fixed stuff"); ERROR_HANDLING; stop
            prev = b; fixed_pos += 1; continue
        fields.append(b); prev = b; fixed_pos += 1
        if nfix_data_bits_read == L: state = DELIM   // 讀完 SBC＋CRC（L = 21 或 25）
        // 注意：最後一個資料位元之後不插入固定位元（L 不是 4 的倍數）
    elif state == DELIM:
        // 固定形狀：delimiter 應為 recessive；ACK、ACK delimiter、EOF 依 §8.1 規則
```

- `data_end_index`、`crc_end_index` 依 DLC 與 ID 格式在 `fields` 中計算（見 §3）。
- `FIX` 狀態的 `prev` 初值為資料段最後一個線上位元；`fixed_pos` 從 0 起算，因此固定位元位於 0、5、10…（前置 1 個，之後每 4 個資料位元 1 個）。
- `nfix_data_bits_read` 為 FIX 狀態已讀資料位元數（SBC 4 位元＋CRC 17 或 21 位元）。
- 偽碼僅示意狀態轉移；`STUFF_ERROR`、`FORM_ERROR` 等事件與 §6 對應。
- 動態填充、TAIL 與 FIX 的 `prev` 規則不可省略，否則 CRC 尾段會錯位（審查指出的常見錯誤）。

關鍵細節：
- 動態填充的 run 計數必須在**線上位元流（含填充位元）**上進行：填充位元本身是下一段 run 的第一位。例如 `00000` 後插入 `1`，之後再出現四個 `1` 即形成五連，必須再插入 `0`。實作上應在 `run_len==5` 時無條件檢查下一位元，並把它當作填充位元或錯誤。
- Classical CRC 計算輸入為 `bits_out`（去填充後），範圍為 SOF 到資料段最後一位。
- FD CRC 的輸入範圍見 §5.2。
- 邊界：FD 資料段最後一位若與前面形成五連，之後先讀一個固定填充位元，不另外讀動態填充位元，也不增加 SBC 計數（K2 引用條文的推論，待確認）。Classical 若 CRC 最末位形成五連，delimiter 之前仍有一個動態填充位元。

### 4.3 錯誤：填充違規與 error flag 的關係

- 連續 6 個相同位元出現在動態填充區內即為 stuff error。但 active error flag 的 6 個 dominant 本身就是有意的填充違規，因此「6 個 dominant」應同時標為 stuff error 與 error flag 候選。
- 固定填充區內，若某固定位元與前一位元相同，為 form error，不應歸為 stuff error（ISO 規則，待確認原文）。
- 六個連續 recessive 不能單獨作為錯誤判準：delimiter、EOF、intermission 與 idle 都可能出現連續 recessive。只有在動態填充適用的區域（SOF 到 CRC 序列結束，Classical；SOF 到資料段結束，FD）內，連續 6 個相同位元才直接構成 stuff error；其他區域依固定欄位形狀檢查。

---

## 5. CRC

### 5.1 CRC-15（Classical）

- 多項式：`x^15 + x^14 + x^10 + x^8 + x^7 + x^4 + x^3 + 1`，十六進位 `0x4599`（K1 文字與既有文件 §8.3 相符；K3 與本次獨立計算相符）。
- 初值 0，無反射，無最後 XOR，MSB first（K3 參數表）。
- 輸入：`SOF` 到資料段最後一位，去填充後的位元流（與 §4.2 的 `bits_out` 一致；覆蓋範圍與 K1 的「CAN CC」敘述相符，但 K1 未逐位元列出，待確認原文）。
- 輸出：15 位元，MSB first 送出，後接 CRC delimiter。
- 標準檢查值（check value，ASCII "123456789" 以位元輸入）：`0x059E`（K3 目錄值；本次獨立計算相符，見 §5.3）。

**手算步驟**（以 §11 的 T01 為例）：把 35 位元輸入逐位元送入 15 位元暫存器，移位時若最高位與輸入位元不同則 XOR `0x4599`，最後暫存器即為 CRC。35 位元手算工作量大，建議以第二實作交叉比對，本文提供 python 驗證值（§11）。

### 5.2 CRC-17 與 CRC-21（CAN FD）

- CRC-17：用於 ≤16 bytes；多項式 `x^17+x^16+x^14+x^13+x^11+x^6+x^4+x^3+x+1`，hex `0x1685B`（不含 x^17 的 top bit 表示）。K3 目錄 poly 為 `0x1685b`，check value `0x04F03`；本次獨立計算相符（§5.3）。Vector 的寫法 `0x3685B` 表示含 x^17 的 top bit，與 `0x1685B` 在 17 位元遮罩下相等（本次計算一併確認，待 Vector 原文確認）。
- CRC-21：用於 20–64 bytes；多項式 `x^21+x^20+x^13+x^11+x^7+x^4+x^3+1`，hex `0x302899`（同 top bit 規則）。本次獨立計算以 `0x302899` 得 "123456789" 檢查值 `0x0ED841`，與 K3 目錄值相符（K3 摘要中 CRC-21 條目僅本次記憶值，見 §5.3 註）。
- 初值：K1 未列出。K3 的 CRC-17/CAN-FD、CRC-21/CAN-FD 條目引用的是 **2012 Bosch 早期版**，列 init=0。Codex 審查引用 CiA 說明指出 ISO 版改用 MSB=1 的暫存器初值（CRC-17 為 `0x10000`、CRC-21 為 `0x100000`，於本文移位算法下）。此點本次未獨立核實，列為**待確認**。因此 K3 的零初值檢查值只驗證目錄算法，不能直接證明 ISO FD 訊框 CRC 實作正確。
- 輸入範圍（待確認）：Codex 審查引用 Vector 與 Bosch 作者說明，認為 FD CRC 輸入包含 SOF 到資料段結束的**線上位元（含動態填充位元）**，再加 3-bit Gray stuff count 與 parity；固定填充位元不納入。此與 Classical（去填充後計算）不同。本文以此作為 ISO profile 的候選規則，**仍須 ISO 原文確認**；實作時應把「線上位元流」與「去填充欄位位元」保留為兩條資料流。
- 本文提供的 CRC-17 示例（§11.3）只給零初值、無 SBC 的原始計算值，**不作為已驗證向量**。

### 5.3 本次驗證與既有文件更正

證據分三級：(1) 本次以程式重算（算法自洽）；(2) 外部目錄或來源核對（K3、K1）；(3) 實際訊框交叉驗證（尚未進行）。三級不等同於「已確認協定」。

獨立計算方法：以 `crc = (crc << 1) ^ (poly if msb ^ bit)` 形式的位元迴圈，對 "123456789" 的 72 位元輸入，計算 15、17、21 位元暫存器。結果：

| 多項式 | 寬度 | 計算的檢查值 | K3 目錄值 | 結論（等級 1 + 2） |
|---|---|---|---|---|
| 0x4599 | 15 | 0x059E | 0x059E | 相符 |
| 0x1685B | 17 | 0x04F03 | 0x04F03 | 相符 |
| 0x302899 | 21 | 0xED841 | 0x0ED841（K3 CRC-21 條目未取得，僅記憶值，未計為等級 2） | 程式重算相符（僅等級 1） |
| 0x1685B 去掉 x^3 項（即 CiA 文字式） | 17 | 0x0EB96 | — | **不相符** |

**更正**：既有文件 `研究_數位解碼協定定義.md` §8.3 寫 CRC-17 為 `x^17+x^16+x^14+x^13+x^11+x^6+x^4+x+1`，缺少 x^3 項。依本次計算，正確式為含 x^3 項的 `x^17+x^16+x^14+x^13+x^11+x^6+x^4+x^3+x+1`（0x1685B）。K1 的 CiA 文字也寫成不含 x^3 的式子，與 K3 及本次計算不一致，判定為 CiA 網頁的抄寫或排版問題，需以 ISO 原文確認後，再修正既有文件。

### 5.4 Stuff count 與 FD CRC 細節

依 K2 引用的 ISO 11898-1:2015 條文（二手）：
- 「For FD Frames, the CRC field shall also contain the stuff count.」
- 「The Stuff Bit Count is always coded on 4 bits」。
- 「It shall consist of the stuff bit count modulo 8 in a 3-bit gray code followed by a parity bit」。
- 「There shall be a fixed stuff bit before the first bit of the stuff count」。
- 「A further fixed stuff bit shall be inserted after each fourth bit of the CRC field」。
- stuff count 計數的是動態填充位元（不含固定填充位元），由發送者計算（K2 摘要）。

K1 補充：固定填充位元值與前一位元相反；它同時作為 stuff count 的第二層保護（以 parity 的角色）。

**Gray code 表**（3 位元 stuff count mod 8，由反射 Gray code 推導，K2 指出 Gray code 為正確形式）：

| stuff count mod 8 | Gray（3 位元） | 
|---|---|
| 0 | 000 |
| 1 | 001 |
| 2 | 011 |
| 3 | 010 |
| 4 | 110 |
| 5 | 111 |
| 6 | 101 |
| 7 | 100 |

**Parity（待確認）**：Codex 審查引用 CiA CNLM 15-1 表 1，建議為對 3 個 Gray 位元做偶同位 `p = g2 ⊕ g1 ⊕ g0`，傳送順序 `g2, g1, g0, p`，得四位編碼 `0000、0011、0110、0101、1100、1111、1010、1001`（count 0–7）。本次未獨立核實該表；一份大學講義曾列為普通二進位表，與 K2 指出的 Gray 衝突，判定以 Gray 為準。ISO 原文仍待確認。

**Non-ISO CAN FD（Bosch 早期版）**：沒有 stuff count 欄位，與 ISO 不相容（K1）。CiA 建議不要在同一網路混用 ISO 與 non-ISO 裝置。解碼器應提供 profile 選擇；若 CRC 只在 non-ISO 下相符，應標「疑似 non-ISO」，而不是「CRC 錯誤」。

---

## 6. 錯誤與異常分類

| 代碼 | 名稱 | 觸發條件 | 解碼器標示 | 可能性提示 |
|---|---|---|---|---|
| E1 | `STUFF_ERROR` | 動態填充區內連續 6 個相同位元 | 錯誤，定位到第 6 個位元 | 可能是 error flag 起點，需 §3.5 判定 |
| E2 | `CRC_MISMATCH` | 接收 CRC ≠ 計算 CRC；計算輸入依所選 profile（Classical：去填充後位元；FD：見 §5.2 候選規則），輸入未定時不報此項 | 錯誤；顯示兩個值 | 常見於填充或取樣錯誤，不代表物理損壞 |
| E3 | `CRC_UNCHECKED` | 缺少 SOF、資料段不完整，或 CRC 序列不完整（如 T14） | 不是錯誤；標「未驗證」 | 避免與 E2 混用 |
| E4 | `FORM_ERROR` | 固定位置（delimiter、EOF、FDF、SRR 等）形狀不符；FD 固定填充位元不反相 | 錯誤，列出欄位名稱 | 有時是 bit-rate 切換點的取樣偏移。Classical EOF 最後一位 dominant 依 Bosch 接收端規則不判為 FORM_ERROR（Codex 引用 Bosch CAN 2.0 Part B，待確認）；離線仍保留該位準 |
| E5 | `NO_ACK` | ACK slot 無 dominant | 警告 `ack_status=no_ack`，不直接斷言錯誤；只有在使用者確認有其他接收者時才升級為 ACK_ERROR | 單節點錄製無法區分「無接收者」與「接收者錯誤」 |
| E6 | `STUFF_COUNT_ERROR` | FD stuff count 解碼與實際動態填充數不符，或 parity 失敗 | 錯誤；與 E2 分開 | 非 ISO 裝置會正常缺少此欄位，需 profile 判定 |
| E7 | `ERROR_FRAME` | §3.5 的 error flag 形狀 | 事件，不是資料錯誤 | 節點可能不是錄製者 |
| E8 | `OVERLOAD_FRAME` | §3.5 的 overload 形狀 | 事件 | 常因接收器處理慢 |
| E9 | `TRUNCATED` | 訊框在 EOF 前結束（擷取視窗或記憶體邊界） | 部分解碼 | 不應標為錯誤 |
| E10 | `TIMING_UNCERTAIN` | 再同步誤差超出 SJW 估計、或取樣點落在邊緣附近 | 警告 | 建議提高取樣率或檢查 nominal bit time |
| E12 | `PROTOCOL_EXCEPTION` | FDF=1 且 res=1 等 ISO 未允許的保留位組合 | 事件，保存 raw bits，不一律當 form error | 可能是未來擴充或不相容實作（待確認原文） |
| E11 | `BITRATE_SWITCH_BOUNDARY` | BRS=1 時的 CRC delimiter 切換附近取樣 | 警告；標示切換點前後的時序 | 切換點的 bit 可能含兩段時間 |

Q 系列為品質警告，不改判資料或 CRC：

| 代碼 | 名稱 | 觸發 | 處理 |
|---|---|---|---|
| Q1 | `TIMING_DEVIATION` | 估計 T 與設定 T 偏差 ≥ 3%（門檻可調） | 警告；不得以此改判 CRC |
| Q2 | `SAMPLE_LOW` | 每位元點數低於 §7.3 建議 | 警告 |

- 「錯誤」與「事件」分開：E7、E8 是協定事件；E1、E2、E4 是資料錯誤。
- CRC 不一致時，應優先確認 E10 與 E11 是否成立，再報 E2。
- 單靠 CANH/CANL 無法推斷 bus-off、錯誤計數器或是哪個節點送出 error flag。FD 的 ESI 只提供發送者錯誤狀態，不是全體節點狀態。來源：C1 既有文件 §8.4、K5。

---

## 7. 使用者參數與自動偵測

### 7.1 必要參數

| 參數 | 預設 | 說明 |
|---|---|---|
| 來源 | CANH−CANL 差動 | 可選 RXD 單端、單線近似 |
| 門檻（dominant／recessive） | 0.9 V／0.5 V（差動） | 遲滯；使用者可覆寫 |
| 格式 profile | Classical 2.0A/B＋FD（ISO） | 另可選「non-ISO FD」 |
| nominal bit rate | 500 kbit/s（使用者必填） | 單位 bit/s |
| data bit rate（FD） | 2 Mbit/s（使用者必填，FD 時） | |
| sample point nominal | 75% | 僅用於取樣位置，不影響邊緣對齊 |
| sample point data | 75% | |
| 重同步策略 | 每個 recessive→dominant 邊緣 | 可選「僅 SOF」（較不準） |
| SJW（時間，ns） | 使用者可選，預設為 nominal T 的 5% 或使用者填入 | 限制 §2.2 第 4 步的再同步修正量；超出時標 E10，並以不修正處理 |

### 7.2 可自動偵測的項目

- **idle 位準與 SOF 位置**：可自動偵測。
- **Base 或 extended 格式**：依 IDE 位元自動判定（IDE 位於控制段，FD 與 Classical 相同位置）。
- **Classical 或 FD**：依 FDF（EDL）位元自動判定。基本格式中 Classical 的 r0 與 FD 的 FDF 位於相同位置；擴充格式中 FDF 位於 r1 位置。判定必須依格式與順序逐欄進行，不能只看單一位元（K5 與 K1 描述；擴充順序見 §3.3）。
- **Data bit rate 切換點**：依 BRS 位元自動判定。
- **Bit rate 候選**：可用邊緣間距的最大公因數或最頻繁間距估計 nominal T，但對短資料容易歧義，應列出候選。
- **CRC 與 stuff count 一致性**：可作為 profile 驗證，但無法證明參數正確。

**不能自動還原的項目**：節點的 TQ、BRP、SJW、取樣點百分比（只能估計）；ECU 內部的仲裁結果、是否收到 ACK 的具體節點；DBC 內容解釋（需另載）。

### 7.3 建議最低取樣率

依既有文件 §2.1 的經驗估計，以下為本文沿用的起步值（非標準保證）：

| 位元率 | 起步 Fs | 較佳 Fs | 說明 |
|---|---|---|---|
| Classical 125 kbit/s–1 Mbit/s | 10 MSa/s（1 Mbit/s） | 20–50 MSa/s | 每位元 ≥10 點 |
| CAN FD nominal（≤1 Mbit/s） | 同上 | 同上 | nominal phase 要獨立復原 |
| CAN FD data 2 Mbit/s | 20 MSa/s | 40–100 MSa/s | 取較快 phase 作上限 |
| CAN FD data 5 Mbit/s | 50 MSa/s | 100–250 MSa/s | |
| CAN FD data 8 Mbit/s | 80 MSa/s | 160–400 MSa/s | 同既有文件 §2.1 |

以上數值與既有文件表格一致，取自 C1、C3 與既有文件 §2.1 的估計；**不是 ISO 的最低值**。

---

## 8. 事件表與標註呈現

### 8.1 事件欄位（每個 frame 一列，展開後可看 field）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `event_id` | 字串 | 與標註列連結 |
| `frame_kind` | data／remote／error／overload／truncated | 與 `complete`、`aborted` 分開 |
| `complete` | true／false／unknown | 是否完整到 EOF |
| `format` | Classical／FD | |
| `id_format` | base／extended | |
| `id` | 整數 | 11 或 29 bits |
| `rtr_rrs` | 0／1 | 依格式 |
| `srr` | 0／1 | 擴充格式 |
| `fdf` | 0／1 | FD 判定 |
| `brs` | 0／1 | FD |
| `esi` | 0／1 | FD |
| `dlc_raw` | 0–15 | 原始值 |
| `request_len` | 整數 | 遠端訊框的請求長度（由 DLC 解出） |
| `payload_len` | 整數 | 實際 payload 長度（remote 為 0） |
| `res_bit` | 0／1／unknown | FD res 位元原始值 |
| `data_hex` | 字串 | 原始 bytes |
| `stuff_count_dyn` | 整數 | 動態填充位元總數 |
| `sbc_raw` | 4 位元 | FD 的 Gray 3 位元＋parity 原始值 |
| `sbc_status` | ok／parity_error／count_mismatch／incomplete／n_a | count_mismatch：parity 正確但計數與實際動態填充數不同（E6）；incomplete：擷取不完整，未驗證 |
| `crc_width` | 15／17／21 | |
| `crc_rx` | 十六進位 | |
| `crc_calc` | 十六進位 | |
| `crc_status` | ok／mismatch／unchecked | |
| `ack_status` | ack／no_ack／unknown | |
| `eof_ok` | true／false／unknown | 三態 |
| `nominal_bitrate` | 數值 | 使用者或估計 |
| `data_bitrate` | 數值 | FD，無則空白 |
| `t_start`、`t_end` | 時間 | 訊框起訖 |
| `bit_range` | 整數範圍 | 線上位元索引範圍 |
| `sample_range` | 整數範圍 | 原始樣本索引範圍 |
| `errors` | 陣列 | E1–E12、Q1–Q2 代碼與位置 |
| `profile_version` | 字串 | 解碼設定 hash |

### 8.2 標註列

呈現參考 O1、O3 與 K5（LeCroy 規格敘述：顏色分為 FRAME、ID、DLC、DATA、CRC、ACK、stuff bits；錯誤訊框盡可能解碼）。本專案建議：

- 標註列依欄位分色：FRAME（SOF／EOF）、ID、CTRL（RTR／IDE／FDF／BRS／ESI）、DLC、DATA、CRC、ACK、STUFF（動態與固定，用不同淡色）、ERR（紅）、事件（灰）。
- 縮小時一列顯示整個 frame；放大時展開 field 及 bit。
- 點擊事件跳到波形上對應的 `t_start`。
- 錯誤以區間標示，不只標起點。
- 固定填充位元與動態填充位元分開顯示，避免誤讀為資料。

---

## 9. 解碼器實作建議（只限 CAN）

資料流：差動電壓 → 門檻與遲滯（得 0/1/unknown）→ 邊緣清單 → 位元取樣（§2.2）→ 去填充（§4）→ 欄位解析（§3）→ CRC（§5）→ 事件（§6、§8）。

建議實作順序：
1. 只做 Classical 2.0A，固定 nominal T，無再同步；驗證 T01、T02、T03。
2. 加上再同步與 2.0B。
3. 加 CRC 與錯誤分類。
4. 加 FD：先 nominal-only（BRS=0）的 FD 長度與 CRC-17／21，再做 BRS 切換。
5. 加 non-ISO profile。

CAN XL：本次僅確認 K1 列有 CAN XL 的 13-bit preface CRC 與 32-bit frame CRC，但未取得 CAN XL 的實體層與訊框規格。建議**本階段不支援**，遇到不符合 FD 格式的訊框時標為「未知格式」即可。是否支援待確認（需要實際 XL 測試波形與規格）。

---

## 10. 測試案例（合成波形）

測試資料以 bit stream 描述，合成時使用指定 nominal T 與取樣率產生差動電壓。每個案例給出「輸入描述 → 預期事件」。

| 編號 | 輸入描述 | 預期解碼事件 |
|---|---|---|
| T01 | Classical 2.0A，ID 0x123，RTR=0，IDE=0，DLC=2，data `12 34`，正確 CRC（0x36B7），ACK 有效，500 kbit/s | 1 個 data frame；ID 0x123；DLC 2；data `12 34`；CRC ok；ACK ok；EOF ok；動態填充 1 個（§11） |
| T02 | 同 T01，但將 data 第 1 位元起連續改為 6 個 dominant（不重算填充，即破壞填充規則） | E1 STUFF_ERROR，定位第 6 個 0；之後不得產生有效 data frame（除非 §3.5 形狀判定為 error flag） |
| T03 | 同 T01，data 第 1 bit 翻轉並重算填充 | E2 CRC_MISMATCH，顯示 rx=0x36B7，calc 不同值 |
| T04 | 同 T01，ACK slot 為 recessive（無接收者） | E5 NO_ACK 警告，`ack_status=no_ack`；不得斷言 ACK_ERROR 或節點錯誤 |
| T05 | 擴充格式 29-bit ID `0x1ABCDEF`，SRR=1，IDE=1，RTR=0，r1=r0=0，DLC=1，data `A5`，ACK dominant | id=0x1ABCDEF；id_format=extended；payload_len=1；CRC-15 rx=calc=0xD9；去填充 47 位元＋CRC 15 位元，動態填充 4 個（§11.4） |
| T06 | Remote frame（ID 0x123，RTR=1），DLC=4，無 data 段，CRC-15 rx=calc=0x4352 | frame_kind=remote；request_len=4；payload_len=0；不得輸出 4 bytes 資料 |
| T07 | DLC=9 的 Classical 訊框，8 bytes | payload_len=8；dlc_raw=9 保留顯示 |
| T08 | CAN FD，BRS=0（全速率），DLC=9，data 12 bytes（0x00…0x0B），CRC-17 | payload_len=12；crc_width=17；固定填充 6 個（CRC 區段 21 位元）。FD CRC 數值待 ISO 確認，見 §11.3 |
| T08b | CAN FD，DLC=11（20 bytes），CRC-21 | payload_len=20；crc_width=21；固定填充 7 個（CRC 區段 25 位元） |
| T09 | CAN FD，BRS=1，ID 0x123，DLC=1，data `A5`，data 段以 data rate 傳送，CRC-17 | 兩種 phase 切換點事件；data 以 data bit rate 取樣；CRC 比對依 §5.2 的待確認輸入範圍（原始計算值，不作為已驗證向量） |
| T10 | CAN FD，將 CRC 區段第 1 個固定填充位元（stuff count 前）改為與前一位元相同 | E4 FORM_ERROR，定位在該固定位元；不得誤判為 E1 STUFF_ERROR |
| T11 | Active error flag（6 個 dominant）後接 8 個 recessive | E7 ERROR_FRAME；同時標 E1 作為來源（若無訊框前綴則只保留 E7） |
| T12 | 訊框 EOF 之後，intermission 第 1 位元起出現 6 個 dominant，接 8 個 recessive | E8 OVERLOAD_FRAME（起始位置規則見 §3.5，待確認原文）；不得判為 data frame |
| T13 | 同 T01，取樣率 2 MSa/s（500 kbit/s 時每位元 4 點，低於 §7.3 建議） | 輸出 Q2 SAMPLE_LOW；若解碼與 CRC 仍正確，不得改判為錯誤 |
| T14 | 同 T01，波形截斷在 CRC 中途 | TRUNCATED；crc_status=unchecked，不得輸出 CRC_MISMATCH |
| T15 | 同 T01，CANH 與 CANL 各加 +2 V（共模偏移，差動不變） | 結果與無偏移相同；共模報告值改變 |
| T16 | 同 T01，全訊框每位元時間固定慢 1%（常數誤差） | 欄位與 CRC 全部正確；允許估計 T 後不輸出 Q1；不強制輸出 E10 |
| T18 | DLC=0 的 Classical data frame（無 data 段） | payload_len=0；CRC 範圍仍含 DLC 欄位 |
| T19 | 兩個 data frame 背靠背（中間 intermission 3 位元，第二個 SOF 緊接） | 兩個獨立事件；第二個 SOF 不得被當成第一個 frame 的 overload |
| T17 | 同 T01，每位元時間固定慢 5%，設定 T 為標稱值且鎖定不估計 | 必須輸出 Q1（或 E10）；若取樣仍全部正確，不得省略 Q1；不得以 CRC_MISMATCH 取代 |

---

## 11. 可手算的 CRC 範例

### 11.1 T01 的位元流

以 ID=0x123、RTR=0、IDE=0、r0=0、DLC=2、data `12 34` 為例，**逐欄位位元（去填充，SOF 到資料段結束，共 35 位元）**：

```
SOF=0
ID    00100100011
RTR   0
IDE   0
r0    0
DLC   0010
DATA  00010010  00110100
```

完整 35 位元字串：`00010010001100000100001001000110100`

- CRC-15（多項式 0x4599，初值 0，MSB first）= `0x36B7`，15 位元 `011011010110111`。
- 動態填充後，SOF 到 CRC 結束（35 位元欄位加 CRC 15 位元，共 50 位元）共插入 1 個填充位元：

```
stuffed SOF..CRC (51 bits):
000100100011000001100001001000110100011011010110111
```

- 其後依序：CRC delimiter=1、ACK slot=0（有接收者拉 dominant；若無接收者則為 1，見 T04）、ACK delimiter=1、EOF=1111111、IFS=111。

### 11.2 驗證方法

- 以逐位元移位 CRC 計算：暫存器 15 位元，初值 0；每個輸入位元 `b`：若 `reg[14] ^ b == 1` 則 `reg = ((reg << 1) ^ 0x4599) & 0x7FFF`，否則 `reg = (reg << 1) & 0x7FFF`。結果 `0x36B7`。
- 以長除法（`數 × x^15 mod G(x)`）交叉計算，結果相同 `0x36B7`。
- 去填充後共 50 位元（35 位元欄位＋15 位元 CRC），線上 51 位元，移除 1 個填充位元後得 50 位元（與本次腳本一致）。

來源：本次以 python 獨立實作計算，腳本不屬於專案檔案。檢查值方法與 K3 目錄一致（§5.3）。

### 11.3 CAN FD 的 CRC-17 中間值（不作為已驗證向量）

以 ID=0x123、BRS=1、DLC=1、data `A5` 為例，SOF 到資料段結束的未填充欄位位元（30 位元，此例中無動態填充）：

```
000100100011001010000110100101
```

- 零初值、無 SBC、僅此 30 位元的 CRC-17 原始暫存器：`0x18BC6`（本次 python 計算）。
- 此值**不是**完整 ISO FD CRC：未包含 SBC 4 位元，也未套用 ISO 版初值（§5.2 待確認）。
- 實作前須以 ISO 原文或已知正確的第二實作確認完整輸入（含 SBC、初值）後，才能作為測試期望值。

### 11.4 T05 擴充格式的 CRC-15 與位元流

- 去填充欄位位元（SOF 到 data，47 位元）：`00000110101011111100110111101111000000110100101`
- CRC-15 = `0xD9`（15 位元 `000000011011001`）。
- 線上 SOF 到 CRC 結束共 66 位元，含 4 個動態填充位元（本次 python 計算）。

## 12. 仍待確認項目

| 項目 | 目前依據 | 確認方式 |
|---|---|---|
| ISO 11898-1:2015 的 FD CRC 輸入範圍（是否含動態填充位元與 SBC） | K1、K2 描述不完整；Codex 引用 Vector／Bosch 作者說明（本次未核實） | 取得 ISO 原文或 vendor 文件 |
| ISO 版 CRC-17／21 初值（MSB=1 候選） | K3 條目為 2012 Bosch 版零初值；Codex 引用 CiA 說明（未核實） | 同上；以已知好的測試向量驗證 |
| Stuff count parity 極性與範圍 | Codex 引用 CiA CNLM 15-1 表 1 建議偶同位（未核實） | 同上 |
| Gray code 順序的最終條文 | K2 與反射 Gray 定義一致；一講義表有衝突 | 同上 |
| FD 固定填充數與 SBC 位置（CRC-17 得 6、CRC-21 得 7） | K2 與 Codex 公式一致，ISO 原文未取得 | 同上 |
| CRC-17 多項式在 K1 文字中缺少 x^3 | 本文以計算與 K3 確認 0x1685B | 以 ISO 原文確認後修正既有文件 §8.3 |
| res（r0）位元的 FD 預期位準與 protocol exception 處理 | 未取得 | ISO 原文 |
| Classical r0 位元是否必須為 0 | 未取得 | Bosch CAN 2.0 原文 |
| Intermission、error flag、overload 的位元數與起始規則 | 經典常見描述；Codex 提示起始位置規則，未取得原文 | Bosch CAN 2.0／FD 原文 |
| FD error frame 之後恢復 nominal 取樣 | Codex 提示，未取得原文 | Bosch CAN FD 原文 |
| 建議取樣點百分比（CiA 慣例） | 未取得 | CiA 301、CiA 603 |
| CAN FD 規格版本與日期（Bosch v1.0） | 未取得 | Bosch 公開 PDF |
| 擴充格式基本 FD RRS 位準（dominant） | 未取得 | ISO 原文 |
| CAN XL 規格與是否支援 | K1 只給 CRC 多項式 | 另案 |
| 測試波形的實際節點 TQ、SJW 來源 | 無 | 實機對照或 vendor 工具 |

## Codex 審查紀錄

本節記錄 Codex 唯讀審查兩輪（上限兩輪）。審查指令見 scratchpad 下 `codex_can_review.md`、`codex_can_review2.md`；輸出分別為 `codex_can_out.txt`、`codex_can_out2.txt`。

### 第一輪（審查整份草案）

| 主要意見 | 處理 |
|---|---|
| extended FD 缺 RRS，FDF 位置寫錯 | 已修正 §3.3，改為 ID-A、SRR、IDE、ID-B、RRS、FDF（r1 位置）、res… |
| CRC-17/21 ISO 初值混用早期 Bosch 版 | 改列為待確認；K3 零初值檢查值只驗證目錄算法（§5.2、§5.3） |
| FD CRC 輸入應含動態填充位元 | 列為候選規則，待 ISO 確認，並建議保留線上位元流與欄位位元兩條資料流（§5.2） |
| 動態填充 run 計數應在線上位元流上計算 | 已修正 §4.2 文字 |
| 偽碼 stuff error 分支與 FD／Classical 分支不完整 | 已修正；第二輪又指出仍不完整，再次修正 |
| 固定填充索引、尾段交界規則 | 已加入（索引 0、5、10…；FD 末位後一個固定位元，不另加動態填充） |
| Gray code parity 規格 | 採 Codex 建議的偶同位表述，標為待確認，未獨立核實 |
| T08 的 DLC=9 應為 CRC-17、6 個固定填充 | 已修正；新增 T08b（DLC=11，CRC-21） |
| BRS 跨界取樣、SJW 單位矛盾 | 已補 §2.2 FD 段；SJW 統一為時間單位（§7.1） |
| 「EOF 外連續 6 個 recessive」不能作判準 | 已改寫 §4.3 |
| overload 起始位置 | 已加入，待確認原文 |
| §11.3 變體 B 不可重現 | 已刪除，改為僅列原始值，並標為非已驗證向量 |
| 事件欄位不足（remote、部分解碼、SBC 狀態） | 已擴充 §8.1 |
| 測試案例不可重現、與 §6 矛盾（T04、T13、T15、T16） | 已改寫，並新增 T17–T19 |
| 共模與電壓敘述 | 已修正（recessive 約 2.5 V；共模為 (CANH+CANL)/2） |
| 既有文件 §8.3 CRC-17 缺 x^3 | 確認更正；本次不改既有檔案，建議另案修正 |

### 第二輪（核對第一輪修正）

| 主要意見 | 處理 |
|---|---|
| Classical 尾端填充：CRC 最末位形成五連時，偽碼需先讀填充位元 | 已改用 TAIL 狀態 |
| FD 固定填充狀態缺少初始化、prev 與結束條件 | 已重寫 FIX 狀態，明列 `prev`、`fixed_pos`、結束條件 |
| error frame 的 nominal 恢復時機 | 改為進入 error frame 時恢復（Codex 引用 C1，待本文重新核實） |
| overload 觸發位置與旗標起點混淆 | 已分開描述（Codex 引用 Bosch Part B，待確認） |
| 輸出定義（E12、sbc_status、E3、E2 profile） | 已補 E12、sbc 狀態、CRC 不完整及 profile 計算規則；新增 Q1、Q2 品質警告 |
| T16、T17 的結果寫成必然 | T16 改為允許估計；T17 改為鎖定 T 時必須輸出 Q1（或 E10） |
| Classical EOF 最後一位 dominant 不判 E4 | 已加註（Codex 引用，待確認） |
| §3.3 表格被說明段切斷 | 已把順序說明移到表前 |
| §5.3 CRC-21 證據等級過度確定 | 已改為僅等級 1 |
| 其他（T07 欄位名、一致性） | 已改為 payload_len |

第二輪後未再送審（已達兩輪上限）。第二輪的新修正尚未經過 Codex 獨立核對，其正確性以本文 §12 的待確認項目為準。

