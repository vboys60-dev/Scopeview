# 開發規則與界線

**寫任何一行程式碼前先讀完這份。違反硬規則的產出一律退回重做。**

先備知識：`CONTEXT.md`（術語）、`docs/示波器命令規格書.md`（權威 SCPI 規格）、`scope_tool/contracts.py`（契約）。

---

## 一、硬規則（不可協商）

1. **`scope_tool/contracts.py` 不准改。** 它是所有並行任務的唯一共同依賴，改它會讓別人的工作全部作廢。覺得非改不可 → 停下來回報，不要自己動。
2. **不准安裝新的第三方套件。** 可用的只有：`pyvisa`、`pyqtgraph`、`numpy`、`h5py`、`zeroconf`、`PySide6`、`pywebview==6.2.1`（Web 版視窗；平台相依 macOS pyobjc、Windows pythonnet／clr_loader，及 bottle、proxy_tools、typing_extensions），以及 Python 標準函式庫。缺什麼就用標準庫湊。前端不得依賴 CDN；第三方 JS 若要引入（如 uPlot），須放 `static/vendor/` 並附版本、授權、SHA-256。
3. **Qt 綁定只能用 PySide6。** 機器上 PyQt5 / PyQt6 / PySide6 三套並存，混用會直接 crash。程式進入點必須在 `import pyqtgraph` **之前**執行 `os.environ["QT_API"] = "pyside6"`。任何模組都不准 `import PyQt5` 或 `import PyQt6`。Web 入口（`scope_tool/web/`）不啟動 Qt GUI，但 `web/app.py` 開頭同樣先設 `QT_API=pyside6`（防 pywebview 退到 qt 時三套綁定相撞）；`instruments/infiniivision.py` 仍用 `QImage`，故 PySide6 在 Web 版仍是執行期相依。
4. **UI 執行緒不准做 VISA I/O。** 所有 `driver.*()` 呼叫一律丟進 `ui/worker.py` 的 QThread，結果用 signal 回傳。UI 裡出現 `self.res.query(...)` 就是錯的。**Web 入口：** `driver.*()` 只能以函式參照交給 `web/jobs.py` 的 `submit()`，由專用儀器工作執行緒執行（全域儀器鎖，搶不到回 BUSY）；HTTP 請求執行緒與 pywebview 主執行緒不得做 VISA I/O。驗收：`grep -nE "driver\.(screenshot|capture|channels|max_points)\(" scope_tool/web/*.py` 必須 0 筆。
5. **擷取一律存 HDF5。** 擷取頁沒有格式選單、不自動轉檔。CSV 只能從分析頁把已開啟的波形檔匯出：範圍選「全部」或「兩條垂直游標之間」；可勾「縮點」並輸入點數上限（預設 10,000,000），超過就每 N 點取 1 點；欄名照契約 `Time(s),CH1(V)`；數值一律科學記號，位數依資料自動決定（不損失、不出現浮點尾巴）。
6. **檔名一律加時間戳，永不覆蓋。** 格式 `{name}_{YYYYMMDD}_{HHMMSS}.{ext}`。
7. **VISA 例外一律轉成 `ScopeError` 子類別再往外丟。** UI 只 catch `ScopeError`。SCPI Error 273 必須轉成 `RemoteDesktopError`。
8. **寫入型 SCPI 命令後要 `*OPC?`。** 逾時：截圖 15 秒、大檔傳輸 60 秒。逾時或失敗前，要清掉自己在儀器上留下的暫存檔（`:DISK:DELete`）。
9. **示波器只因「使用者手動」或「按下擷取」而停止。** 擷取時若在 RUN：先等一整筆（`10×時基+1` 秒）再 `:STOP`；勾「重新觸發」則 `:DIGitize`。擷取後**維持 STOP**，不准自動 `:RUN`。除此之外不准改使用者的採集設定（例如記憶體深度）。
10. **每個模組留一個 `if __name__ == "__main__":` 自我檢查**，用 `assert`。不要 pytest、不要 fixture、不要測試框架。執行方式一律 `python3 -m scope_tool.<模組路徑>`，必須印出 `xxx self-check OK` 且 exit code 0。前端 JS 例外：用 `node scope_tool/web/static/js/selfcheck_node.js` 或 `static/selfcheck.html`，同樣印 `xxx self-check OK`（Node 僅開發機輔助，不進產品）。
11. **離線分析只作用於已開啟的檔案，不碰儀器。** 量測、FFT、數學／濾波的定義照 `docs/離線分析功能規格.md`（依 Infiniium 手冊）；與 Infiniium 有差異的地方要在畫面或註解標明。衍生波形（F1、F2…）不進 CSV 匯出。只用 numpy，不准用 scipy。

## 二、風格規則

- 註解、docstring、UI 文字全部**繁體中文**。變數與函式名用英文。
- 函式簽章寫型別註記。`from __future__ import annotations` 放檔案最上面。
- 不寫只有一個實作的介面、不寫工廠、不為固定值寫設定。`contracts.py` 裡的 `ScopeDriver` 是唯一允許的抽象，因為它真的有兩個以上實作。
- 檔案路徑一律用 `pathlib.Path`。SCPI 裡的 Windows 路徑一律用 raw string（`r"C:\temp\x.h5"`）。
- 單一檔案超過 300 行就是設計有問題，停下來回報。

## 三、明確不做（別自作主張加回去）

掃網段搜尋、傳輸中途取消、示波器面板存到 USB 的 CSV 解析、自訂的 HDF5 結構、非 Keysight 機型、多語系、深色主題。

> 打包：Mac 維持 `啟動示波器截圖.command`；Windows 版允許用 PyInstaller 打包成 exe（使用者 2026-10-22 同意，於 Win10 上打包）。PyInstaller 僅是打包工具，不隨程式執行；其餘硬規則（不新增執行期第三方套件）不變。

## 四、檔案擁有權（並行的關鍵）

**只准改自己 task 名下的檔案。** 需要別人的檔案時，照 `contracts.py` 的介面寫，不要去改對方的實作。

| 檔案 | 擁有者 |
|---|---|
| `scope_tool/contracts.py` | **凍結** |
| `scope_tool/config.py` | **凍結** |
| `scope_tool/instruments/fake.py` | **凍結** |
| `scope_tool/instruments/base.py`、`registry.py`、`discovery.py` | T1 |
| `scope_tool/instruments/infiniivision.py` | T2 |
| `scope_tool/instruments/infiniium.py` | T3 |
| `scope_tool/storage/writer.py`、`csv_export.py` | T4 |
| `scope_tool/storage/reader.py` | T5 |
| `scope_tool/ui/main_window.py`、`ui/worker.py` | T6 |
| `scope_tool/ui/tab_analysis.py`、`analysis_*.py`、`scope_tool/analysis/*.py` | T7 |
| `scope_tool/ui/tab_screenshot.py` | T8 |
| `scope_tool/ui/tab_capture.py` | T9 |
| `scope_tool/main.py` | T10 |

## 五、交付前自我驗收

1. `python3 -m scope_tool.<你的模組>` 印出 OK、exit 0。
2. `git diff --stat`（或 `ls`）確認沒動到別人的檔案。
3. 沒真機的路徑，在 docstring 裡寫明 `# 待真機驗證`，不要假裝驗證過。
4. 回報格式：改了哪些檔、自我檢查結果、哪些行為只有紙上驗證。三行以內。

### Web 版（pywebview）檔案擁有權（2026-10-22 起；詳見 `docs/pywebview-GUI規劃建議書.html` 第 6 節）

只准改自己 lane 名下的檔案；契約（L0 檔案）凍結後只有 lead 能改，其他 lane 提需求不自行加欄位。

| Lane | 擁有 |
|---|---|
| L0 契約 | `docs/web-api契約.md`、`web/static/api_contract.json`、`static/index.html`、`static/js/{bridge,mock_backend,mock_catalog,mock_dsp,ui,fmt,main}.js`、`static/js/{l0_check,l0_util,l0_sem}.mjs`、`static/js/analysis/{store,scales}.js` |
| L1a 後端橋接 | `web/{__init__,app,server,jobs,api}.py` |
| L1b 分析服務 | `web/{analysis_api,analysis_util,analysis_fft,analysis_export,analysis_check,analysis_params,decimate}.py` |
| L2 連線列＋截圖頁 | `static/js/{connbar,tab_screenshot}.js` |
| L3 擷取頁 | `static/js/tab_capture.js` |
| L4 圖表核心 | `static/js/analysis/{tab_analysis,plotcore,mainplot,overview,fftpane,handles,gestures,axes,layout,splitter,voltage}.js`、`static/css/analysis.css` |
| L5 表格／側欄／游標 | `static/js/analysis/{chanbar,vertical,toolbar,results,measure,cursors}.js`、`static/css/vertical.css` |
| L6 樣式 | `static/css/app.css`、`static/styleguide.html` |
| L7 打包 | `packaging/**`、`requirements-web.txt`、`啟動示波器截圖_web.command` |
| L8 驗證 | `web/e2e_check.py`、`static/selfcheck.html`、`static/js/selfcheck_node.js`、`static/js/analysis/{l4_check,l5_check,p1_check,p2_check,p2b_check,p2b2_check}.mjs`、`web/browser_check.py`、`docs/web版驗收清單.md` |

分析頁 GUI 新 command（`view.undo`／`view.redo`／`view.mode`／`view.history`／`view.historyGroup`／`layout.*`）屬 `store.command` 字串，不在凍結契約內，命名由 lead 於 `docs/分析頁GUI改善計劃書.md` 管理。

凍結（所有 Web lane 唯讀）：`contracts.py config.py instruments/* storage/* analysis/* ui/* main.py`。JS 檔同樣 300 行上限（vendor 豁免）。
