@echo off
REM ============================================
REM Digikey Spider V2 - Windows Runner
REM ============================================

echo ==========================================
echo   Digikey Spider V2 Starting...
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

REM Install Python dependencies
echo [1/2] Checking Python dependencies...
python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Error: Failed to install dependencies
        pause
        exit /b 1
    )
    echo Dependencies installed successfully.
) else (
    echo Dependencies already installed.
)

REM Install Playwright Chromium browser
echo.
echo [2/2] Checking Playwright browser...
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); b.close(); p.stop()" >nul 2>&1
if errorlevel 1 (
    echo Installing Chromium browser for Playwright...
    python -m playwright install chromium
    if errorlevel 1 (
        echo Error: Failed to install Playwright browser
        pause
        exit /b 1
    )
    echo Playwright browser installed successfully.
) else (
    echo Playwright browser already installed.
)

echo.
echo Starting crawl...
echo.

REM Run the spider
python spider_v2.py

echo.
echo ==========================================
echo   Done!
echo ==========================================
echo Excel file: %~dp0output\
echo.

pause
