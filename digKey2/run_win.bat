@echo off
REM ============================================
REM Digikey Spider - Windows Runner
REM ============================================

echo ==========================================
echo   Digikey Spider Starting...
echo ==========================================
echo.

cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python first.
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Error: Failed to install dependencies
        pause
        exit /b 1
    )
    echo Dependencies installed successfully
)

echo.
echo Starting crawl...
echo.

REM Run the spider
python main.py

echo.
echo ==========================================
echo   Done!
echo ==========================================
echo Excel file: %~dp0output\
echo.

REM Auto open Excel file (uncomment to enable)
REM start "" "%~dp0output\digikey_stock_*.xlsx"

pause