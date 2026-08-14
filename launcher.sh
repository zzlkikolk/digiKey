#!/usr/bin/env bash
# digiKey 爬虫启动器（macOS / Linux）
cd "$(dirname "$0")"

echo "========================================"
echo "  digiKey 爬虫启动器"
echo "========================================"

# 检查 Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 未检测到 python3，请先安装 Python 3.8+"
    exit 1
fi

echo "正在启动图形界面..."
python3 launcher.py
