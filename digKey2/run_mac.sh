#!/bin/bash

# ============================================
# Digikey 爬虫 - MacOS/Linux 执行脚本
# ============================================

echo "=========================================="
echo "  Digikey 爬虫启动 (MacOS/Linux)"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查Python3是否安装
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3，请先安装 Python3"
    exit 1
fi

# 检查依赖是否已安装
if ! python3 -c "import requests" &> /dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "错误: 依赖安装失败"
        exit 1
    fi
    echo "依赖安装完成"
fi

echo ""
echo "开始爬取数据..."
echo ""

# 运行爬虫
python3 main.py

echo ""
echo "=========================================="
echo "  执行完成!"
echo "=========================================="
echo "Excel文件位置: $SCRIPT_DIR/output/digikey_stock.xlsx"
echo ""

# 自动打开Excel文件（可选，取消注释即可启用）
# open "$SCRIPT_DIR/output/digikey_stock.xlsx"
