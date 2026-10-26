直接用瀏覽器開啟 `layout_editor.html`，不需伺服器或網路。
可選擇畫布尺寸，拖曳移動、使用八向把手縮放，並加入部件或全域註解。
按「輸出」複製或下載 layout.json 與 Markdown 摘要，交給 Claude 修改實際版面。
`components.json` 是現況實測資料；重新量測後需將完整內容重新嵌入 HTML 的 `components-data`。

真實畫面：部件以實際 GUI 截圖裁切顯示（shots/ 目錄，需與 HTML 同資料夾）；工具列勾「顯示真實畫面」可切回色塊。app 版面改動後需重截 shots/ 並更新 components.json。
