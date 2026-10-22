#!/bin/bash
# 雙擊啟動示波器截圖工具
cd "$(dirname "$0")/scope_tool" || exit 1
exec /opt/anaconda3/bin/python3 main.py
