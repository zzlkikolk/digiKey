#!/bin/bash

# ============================================
# Digikey Spider V2 - MacOS/Linux 执行脚本
# ============================================

echo "=========================================="
echo "  Digikey Spider V2 (MacOS/Linux)"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3，请先安装 Python3"
    exit 1
fi

# 安装 Python 依赖
echo "[1/2] 检查 Python 依赖..."
if ! python3 -c "import playwright" &> /dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "错误: 依赖安装失败"
        exit 1
    fi
    echo "依赖安装完成"
else
    echo "依赖已安装"
fi

# 安装 Playwright Chromium 浏览器
echo ""
echo "[2/2] 检查 Playwright 浏览器..."
if ! python3 -c "
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.launch()
b.close()
p.stop()
" &> /dev/null; then
    echo "正在安装 Chromium 浏览器..."
    python3 -m playwright install chromium
    if [ $? -ne 0 ]; then
        echo "错误: Playwright 浏览器安装失败"
        exit 1
    fi
    echo "Playwright 浏览器安装完成"
else
    echo "Playwright 浏览器已安装"
fi

echo ""
echo "开始爬取数据..."
echo ""

# 运行爬虫
python3 spider_v2.py

echo ""
echo "=========================================="
echo "  执行完成!"
echo "=========================================="
echo "Excel 文件位置: $SCRIPT_DIR/output/"
echo ""
