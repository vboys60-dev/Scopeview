#!/bin/bash
# 雙擊啟動示波器截圖工具（Web 版 / pywebview）
PY=/opt/anaconda3/bin/python3
cd "$(dirname "$0")" || exit 1
if ! "$PY" -c "import webview" 2>/dev/null; then
  echo "找不到 pywebview。請先執行："
  echo "  $PY -m pip install -r requirements-web.txt"
  read -r -p "按 Enter 關閉..." _
  exit 1
fi
exec "$PY" -m scope_tool.web.app
