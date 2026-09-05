# 開發計畫：分階段、可並行

每個 task 都是**一段獨立對話**的份量。開新對話時只要貼：
`RULES.md` + `scope_tool/contracts.py` + 底下該 task 的整個區塊。不需要整個專案的上下文。

## 依賴圖

```
Phase 0（已完成）  contracts.py / config.py / fake.py
        │
        ├──────────┬──────────┬──────────┐
Phase 1 T1 儀器骨架  T4 writer  T6 UI 殼   T7 分析頁      ← 這四條完全並行
        │          T5 reader   │          （T7 全程不碰儀器）
        ├────┬────┘            │
        T2   T3                │
   InfiniiVision Infiniium     │
        └────┬─────────────────┘
Phase 2      ├── T8 截圖頁 ──┐                            ← T8/T9 可並行
             └── T9 擷取頁 ──┤
Phase 3                      └── T10 串接 ── T11 真機驗證
```

**並行建議**：一次最多開 4 段對話跑 Phase 1。Phase 2 開 2 段。
每完成一個 task，在下面的表打勾。

| Task | 狀態 | 產出檔案 |
|---|---|---|
| T0 契約層 | ✅ 完成 | `contracts.py` `config.py` `instruments/fake.py` |
| T1 儀器骨架 | ✅ 完成 | `instruments/base.py` `registry.py` `discovery.py` |
| T2 InfiniiVision | ✅ 完成 | `instruments/infiniivision.py` |
| T3 Infiniium | ✅ 完成 | `instruments/infiniium.py` |
| T4 寫檔 | ✅ 完成 | `storage/writer.py` |
| T5 讀檔 | ✅ 完成 | `storage/reader.py` |
| T6 UI 殼 | ✅ 完成 | `ui/main_window.py` `ui/worker.py` |
| T7 分析頁 | ✅ 完成 | `ui/tab_analysis.py` |
| T8 截圖頁 | ✅ 完成 | `ui/tab_screenshot.py` |
| T9 擷取頁 | ✅ 完成 | `ui/tab_capture.py` |
| T10 串接 | ✅ 完成 | `main.py` |
| T11 真機驗證 | ✅ 完成 | `docs/真機驗證清單.md` |

---

## T1 — 儀器骨架：連線、型號辨識、搜尋

**依賴**：Phase 0　**可與 T4/T5/T6/T7 並行**
**產出**：`instruments/base.py`、`instruments/registry.py`、`instruments/discovery.py`

### 要做的事

`base.py`：一個 `SCPIDriver(ScopeDriver)` 中介類別，放兩家共用的東西。
```python
class SCPIDriver(ScopeDriver):
    def _write(self, cmd: str) -> None:      # 送命令 + *OPC? + 例外轉 ScopeError
    def _query(self, cmd: str) -> str:
    def _query_binary(self, cmd: str, datatype: str) -> np.ndarray:
    def _check_error(self) -> None:          # :SYSTem:ERRor? → 273 轉 RemoteDesktopError
    def _timeout(self, ms: int):             # context manager，暫時改 VISA timeout 後還原
    def _run_state(self):                    # context manager，記住 RUN/STOP，離開時還原
    def channels(self) -> list[str]:         # 查 :CHANnel<n>:DISPlay?，兩家一樣
```

`registry.py`：
```python
def parse_idn(idn: str) -> tuple[str, str]   # "KEYSIGHT,MSO-X 3054G,..." → (廠牌, 型號)
def driver_for(resource, idn: str, override: Series | None = None) -> ScopeDriver
    # 用 model_prefixes 前綴比對；比不到就丟 UnsupportedError，UI 據此要求使用者手選系列
def register(cls: type[ScopeDriver]) -> None
```
註冊表用一個 module-level list，不要寫 metaclass 或 plugin 掃描。

`discovery.py`：
```python
def find_all(manual: list[str], timeout: float = 3.0) -> list[FoundInstrument]
    # 三個來源合併去重：
    #   1. pyvisa ResourceManager().list_resources()          source="visa"
    #   2. zeroconf 查 _hislip._tcp / _lxi._tcp / _scpi-raw._tcp，
    #      IP 組成 TCPIP0::<ip>::hislip0::INSTR              source="mdns"
    #   3. manual 傳進來的 IP 字串                            source="manual"
    # zeroconf 沒裝或壞掉 → 只回 visa + manual，不要拋例外。
```
**不准掃網段。**

### 驗收
- `python3 -m scope_tool.instruments.registry` 自我檢查：用 `FakeDriver` 註冊，餵 `"FAKE,FAKE-SCOPE,0,1"` 拿得回 driver；餵未知型號拋 `UnsupportedError`；`parse_idn` 對逗號數不足的字串不會爆。
- `python3 -m scope_tool.instruments.discovery` 自我檢查：實際跑 `find_all([], timeout=1.0)` 不拋例外、回傳 list（本機沒儀器，回空或只有序列埠都算過）；再驗 `find_all(["1.2.3.4"])` 裡有一筆 `source="manual"`。
- `base.py` 的 SCPI 互動路徑無法在沒真機下驗證，docstring 標 `# 待真機驗證`。

---

## T2 — InfiniiVision 驅動（3000G / 3000X）

**依賴**：T1　**可與 T3 並行**
**產出**：`instruments/infiniivision.py`
**先讀**：`docs/reference/infiniivision-*.md`、`docs/示波器命令規格書.md`

### 要做的事
```python
class InfiniiVisionDriver(SCPIDriver):
    series = Series.INFINIIVISION
    model_prefixes = ("MSO-X 3", "DSO-X 3", "MSOX3", "DSOX3")
```

`screenshot(opts)`：
- 反轉色 → `:HARDcopy:INKSaver ON|OFF`
- 區域 → `:HARDcopy:AREA GRAT|SCReen`（**待真機驗證**：文件沒明說 `:DISPlay:DATA?` 會不會跟隨這個設定；驗不過就在 UI 停用區域選項並回報）
- `:DISPlay:DATA? PNG|BMP` → `query_binary_values` 取回，timeout 15s

`capture(channels, points, retrigger)`：**只能走直讀**，`:SAVE:*` 只能寫面板 USB、PC 端無法取回，不要嘗試。
- `_run_state()` 包住全程
- retrigger=True → `:DIGitize`；否則 `:STOP`
- 每個通道：`:WAVeform:SOURce` → `:FORMat WORD` → `:UNSigned 1` → `:BYTeorder LSBFirst` → `:POINts:MODE RAW` → `:POINts <n>` → `PREamble?` → `DATA?`
- `max_points()`：`:ACQuire:POINts:MAXimum?`，查不到就回 4_000_000

### 驗收
- `python3 -m scope_tool.instruments.infiniivision`：用一個假的 resource 物件（自己在 `__main__` 裡寫個 20 行的 stub，記錄收到的命令、對 `PREamble?` 回固定字串、對 `DATA?` 回固定陣列），驗證
  1. 送出的命令順序正確且 `:POINts` 在 `:POINts:MODE` 之後
  2. `capture` 回來的 `CaptureResult.series` 是 `INFINIIVISION`
  3. `screenshot(inverted=True)` 有送出 `INKSaver ON`
  4. 全程沒送出任何 `:DISK:` 或 `:SAVE:` 命令
- 真機路徑標 `# 待真機驗證`。

---

## T3 — Infiniium 驅動（EXR / MXR / S）

**依賴**：T1　**可與 T2 並行**
**產出**：`instruments/infiniium.py`
**先讀**：`docs/reference/infiniium-*.md`、`docs/示波器命令規格書.md`

### 要做的事
```python
class InfiniiumDriver(SCPIDriver):
    series = Series.INFINIIUM
    model_prefixes = ("EXR", "MXR", "DSOS", "MSOS")
```

`screenshot(opts)`：`:DISPlay:DATA? <PNG|BMP>,<SCReen|GRATicule>,<COLor|INVert>`（參數直接帶，不需要預先設定命令）。timeout 15s。

`capture(channels, points, retrigger)`：**兩條路線**
- `points < 100_000` → 直讀，流程同 T2 但用 Infiniium 的命令寫法
- `points >= 100_000` → 存檔轉取：
  1. `:DISK:SAVE:WAVeform ALL,r"C:\temp\st_<timestamp>.h5",H5INt,ON`
  2. `*OPC?`
  3. `:DISK:GETFILE? r"C:\temp\st_<timestamp>.h5"` → bytes 放進 `CaptureResult.native_file`
  4. **`finally` 裡** `:DISK:DELete`——逾時、例外、成功都要刪
  5. `waveforms` 同時也要填（用 T5 的 reader 解 native_file，或直接用 h5py 從 bytes 讀），UI 才能立刻預覽
  - timeout 60s
- 開頭 `_check_error()`，Error 273 → `RemoteDesktopError`

### 驗收
- `python3 -m scope_tool.instruments.infiniium`：同樣用 `__main__` 裡的 stub resource，驗證
  1. `points=1000` 走直讀，沒有任何 `:DISK:` 命令
  2. `points=200000` 有送 `:DISK:SAVE` → `:DISK:GETFILE?` → `:DISK:DELete`，順序正確
  3. `GETFILE?` 拋例外時，`:DISK:DELete` **仍然**有被送出
  4. `:SYSTem:ERRor?` 回 `273,...` 時 `screenshot` 拋 `RemoteDesktopError`
  5. 路徑字串是 raw string，沒有被跳脫字元吃掉
- 真機路徑標 `# 待真機驗證`。

---

## T4 — 寫檔

**依賴**：Phase 0（不需要任何 driver）　**可與 T1/T5/T6/T7 並行**
**產出**：`storage/writer.py`

### 要做的事
```python
def timestamped(directory: Path, name: str, ext: str) -> Path
    # {name}_{YYYYMMDD}_{HHMMSS}.{ext}；同秒撞名就接 _2、_3，永不覆蓋

def write_screenshot(directory: Path, name: str, data: bytes, fmt: ImageFormat) -> Path

def write_waveform(directory: Path, name: str, result: CaptureResult,
                   fmt: WaveformFormat) -> Path
    # result.native_file 不是 None 且 fmt 是 HDF5 → 直接把原生位元組寫檔，不要重組
    # 其他情況照 contracts.py 檔頭的格式規格寫 CSV 或 HDF5
```
CSV 與 HDF5 的**確切格式寫在 `contracts.py` 的模組 docstring**，照抄，不要自己發明欄位。

### 驗收
`python3 -m scope_tool.storage.writer`，全部寫進 `tempfile.TemporaryDirectory()`：
1. 連寫兩次同名 → 兩個不同檔名，第一個檔沒被覆蓋
2. CSV 內容首列是 `Time(s),CH1(V),CH2(V)`，列數 = 點數 + 1
3. HDF5 用 h5py 開回來，`/Waveforms/Channel 1/Channel 1Data` 存在、長度對、attrs 六個都在
4. `native_file` 有值時，寫出來的位元組與傳入的完全相同
資料來源用 `FakeDriver().capture(...)`。

---

## T5 — 讀檔（統一 loader）

**依賴**：Phase 0　**可與 T1/T4/T6/T7 並行**
**產出**：`storage/reader.py`

### 要做的事
```python
def read_waveform_file(path: Path) -> list[Waveform]
    # 副檔名 .csv → 解本工具的 CSV
    # 副檔名 .h5 / .hdf5 → h5py 開，走 /Waveforms/Channel N/Channel NData
    #   本工具產的檔與 Keysight 原生檔結構相同，同一條路吃；
    #   /ScopeTool group 可能不存在，要容忍。
    # 認不得的格式 → 拋 ScopeError，訊息要講人話（UI 直接顯示給使用者看）

def read_waveform_bytes(data: bytes) -> list[Waveform]
    # 給 T3 用：直接從記憶體裡的 h5 位元組解，不落地
```
時間軸：HDF5 從 attrs 的 `XInc`/`XOrg` 重建；CSV 直接用第一欄。

**不支援示波器面板存到 USB 的 CSV**，遇到就拋 `ScopeError`（訊息：「不支援示波器面板匯出的 CSV，請用本工具擷取」）。

### 驗收
`python3 -m scope_tool.storage.reader`：`__main__` 裡自己用 h5py 與 csv 現寫兩個小檔（**不要 import writer**，兩個 task 要能各自獨立驗），讀回來驗
1. 通道數、點數、時間軸首末值正確
2. 少了 `/ScopeTool` group 仍能讀
3. 餵 `.txt` 拋 `ScopeError`
4. `read_waveform_bytes` 吃 `Path.read_bytes()` 的結果，結果與 `read_waveform_file` 相同

---

## T6 — UI 外殼：主視窗、連線列、背景執行緒

**依賴**：Phase 0（用 `FakeDriver` 開發，**不需要等 T1**）　**可與 T1/T4/T5/T7 並行**
**產出**：`ui/main_window.py`、`ui/worker.py`

### 要做的事

`worker.py`：
```python
class Job(QThread):
    """把一個 callable 丟到背景跑。所有 VISA I/O 都經過這裡。"""
    done = Signal(object)      # 成功，帶回傳值
    failed = Signal(str)       # 失敗，帶給使用者看的中文訊息
    def __init__(self, fn, *args, **kwargs)
    def run(self)              # try: self.done.emit(fn(...))
                               # except ScopeError as e: self.failed.emit(str(e))
                               # except Exception: 也要接，訊息前綴「未預期錯誤：」
```
就這一個類別，不要做 thread pool、不要做任務佇列。

`main_window.py`：
```python
class MainWindow(QMainWindow):
    # 上方連線列：[搜尋] 按鈕 + 儀器下拉 + [手動輸入 IP] + [連線]/[斷線] + 狀態文字
    # 下方 QTabWidget 三頁，用延遲 import 掛上：
    #   tab_screenshot.ScreenshotTab / tab_capture.CaptureTab / tab_analysis.AnalysisTab
    # 三個分頁模組還不存在時，掛一個 QLabel("尚未實作") 佔位，不要讓程式開不起來。
    # 對外提供：self.driver: ScopeDriver | None，分頁從這裡拿。
    #           self.driver_changed = Signal(object)，連線／斷線時發。
    # 未連線時截圖頁與擷取頁整頁 disable；分析頁永遠可用。
    # 關窗時 config.save()。
```
搜尋與連線也要走 `Job`，不准卡住 UI。

### 驗收
`python3 -m scope_tool.ui.main_window`：`__main__` 裡建 `QApplication`、開視窗、用 `QTimer.singleShot(0, ...)` 塞一個 `FakeDriver` 進去、驗證分頁 enable 狀態變了、然後 `app.quit()`。印 OK。
（無頭環境跑不動 Qt 就設 `QT_QPA_PLATFORM=offscreen`。）

---

## T7 — 波形分析頁

**依賴**：Phase 0 + T5 的介面（**不必等 T5 寫完**，照 `read_waveform_file` 簽章寫，`__main__` 裡自己造資料）
**可與 T1/T4/T5/T6 並行。全程不碰儀器。**
**產出**：`ui/tab_analysis.py`

### 要做的事
```python
class AnalysisTab(QWidget):
    # [開啟波形檔] 按鈕 → QFileDialog（*.csv *.h5 *.hdf5）→ read_waveform_file
    # pyqtgraph.PlotWidget，多通道多條線不同顏色，圖例顯示通道名
    # 大檔效能：setDownsampling(auto=True, mode='peak') + setClipToView(True)
    # 兩條垂直游標 + 兩條水平游標，都是可拖曳的 InfiniteLine
    # 右側即時數值面板：t1 t2 ΔT 1/ΔT v1 v2 ΔV
    # 縮放平移用 pyqtgraph 內建滑鼠操作，不要自己寫
```
**游標讀值一律取原始資料，不准用 downsample 後的點。** 用 `np.searchsorted` 在原始 `time` 陣列上找最近點。
**不做自動量測**（Vpp／頻率／上升時間）。

### 驗收
`python3 -m scope_tool.ui.tab_analysis`（`QT_QPA_PLATFORM=offscreen`）：
1. 直接餵一組 `Waveform` 進去（不經檔案），畫得出來
2. 把游標移到已知位置，驗算出的 ΔT 與預期值差 < 一個取樣週期
3. 100 萬點的資料載入不拋例外
印 OK。

---

## T8 — 截圖頁

**依賴**：T1 + T2 或 T3 之一 + T6　**可與 T9 並行**
**產出**：`ui/tab_screenshot.py`

### 要做的事
```python
class ScreenshotTab(QWidget):
    # 路徑選擇（QFileDialog）+ 檔名輸入
    # 格式 PNG/BMP、正常色/反轉色、全螢幕/格線區  ← 三組 radio 或 combo
    # [開始存圖] → Job(driver.screenshot, opts) → writer.write_screenshot
    #            → QLabel 顯示 QPixmap 預覽（等比縮放）+ 狀態列顯示存檔完整路徑
    # 存圖期間按鈕 disable，避免連點
    # 失敗 → QMessageBox 顯示 Job.failed 帶回的中文訊息
    # 所有設定進出 config
```
連線的機型若是 InfiniiVision 且區域選項尚未通過真機驗證，把區域選項標成「(待驗證)」但仍保留可選。

### 驗收
`python3 -m scope_tool.ui.tab_screenshot`（offscreen）：塞 `FakeDriver`，觸發存圖，驗證檔案真的產生在 temp 目錄、預覽 QPixmap 非空。印 OK。

---

## T9 — 波形擷取頁

**依賴**：T1 + T2/T3 + T4 + T6　**可與 T8 並行**
**產出**：`ui/tab_capture.py`

### 要做的事
```python
class CaptureTab(QWidget):
    # 路徑 + 檔名
    # 通道多選（QCheckBox，連線後用 driver.channels() 填）
    # 格式 CSV / HDF5
    # 點數輸入（單位是點）。連線後查 driver.max_points()，超過就擋下並提示上限。
    # 「擷取前重新觸發單次擷取」勾選框，預設【關】
    # [開始擷取] → 檢查 → Job(driver.capture, ...) → writer.write_waveform
    #            → 狀態列顯示完整路徑
```
**CSV 大點數守門**：格式 CSV 且點數 ≥ 100000 → `QMessageBox` 兩顆按鈕「改用 HDF5」／「我知道，照存」。按前者才改格式（並且把 UI 上的選項也一起改掉，不能只改內部值）；按後者照 CSV 存。**不准自動決定。**

### 驗收
`python3 -m scope_tool.ui.tab_capture`（offscreen）：塞 `FakeDriver`，
1. 點數 1000 + CSV → 直接存成，檔案存在
2. 點數 200000 + CSV → 有跳守門對話框（用 monkeypatch 掉 `QMessageBox` 攔截即可）
3. 點數超過 `max_points()` → 擋下，不呼叫 `capture`
印 OK。

---

## T10 — 串接

**依賴**：T1–T9 全部完成
**產出**：`main.py`

```python
import os
os.environ["QT_API"] = "pyside6"     # 必須在任何 pyqtgraph / Qt import 之前
...
def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())
```

### 驗收
1. `python3 -m scope_tool.main` 開得起來、三個分頁都在、不會 crash
2. 逐一重跑所有模組的自我檢查，全部 OK
3. 未連線狀態下分析頁可以開檔畫圖（這是唯一能在沒真機下走完的完整流程）

---

## T11 — 真機驗證清單

**依賴**：T10　**產出**：`docs/真機驗證清單.md`

把所有標了 `# 待真機驗證` 的地方整理成一張表，每列：檔案:行號、要驗什麼、怎麼驗、預期結果。至少要涵蓋：

- InfiniiVision `:HARDcopy:AREA GRAT` 對 `:DISPlay:DATA?` 是否生效 ← **最高風險，驗不過要改設計**
- `model_prefixes` 是否真的比對得中實機 `*IDN?`
- Infiniium 存檔轉取三步驟與 `:DISK:DELete` 的清理
- Error 273 的實際觸發與訊息
- 4M 點直讀在 15s／60s 逾時設定下夠不夠
- zeroconf 在實際網段上找不找得到儀器
