#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "========================================"
echo "  analog Scraper"
echo "========================================"

# Check Python
if ! command -v python3 >/dev/null 2>&1; then
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

echo "Activating virtual environment..."
# shellcheck disable=SC1091
source venv/bin/activate

if [ "$FIRST_RUN" = "1" ]; then
    echo "Upgrading pip..."
    python -m pip install --upgrade pip
    echo ""
    echo "Installing dependencies..."
    pip install -r requirements.txt
    echo ""
    echo "Installing Playwright Chromium browser..."
    python -m playwright install chromium
fi

echo ""
echo "Starting scraper..."
echo ""
python main.py

echo ""
echo "========================================"
echo "Done!"
echo "========================================"
