#!/bin/bash
# bom.ai Scraper - MacOS/Linux startup script

set -e

cd "$(dirname "$0")"

echo "========================================"
echo "  bom.ai Scraper"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found. Please install Python 3.8+"
    exit 1
fi

# Create venv and install dependencies on first run
FIRST_RUN=0
if [ ! -d "venv" ]; then
    FIRST_RUN=1
    echo "[First Run] Creating virtual environment..."
    python3 -m venv venv
    echo "[Done] Virtual environment created"
fi

# Activate venv
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies only on first run
if [ "$FIRST_RUN" -eq 1 ]; then
    echo "Upgrading pip..."
    python3 -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo ""
    echo "Installing dependencies..."
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

echo ""
echo "Starting scraper..."
echo ""
python main.py

echo ""
echo "========================================"
echo "Done!"
echo "========================================"
