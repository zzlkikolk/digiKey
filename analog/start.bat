@echo off
chcp 65001 >nul
title analog Scraper

cd /d "%~dp0"

echo ========================================
echo   analog Scraper
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

REM Create venv and install dependencies on first run
set FIRST_RUN=0
if not exist "venv\" (
    set FIRST_RUN=1
    echo [First Run] Creating virtual environment...
    python -m venv venv
    echo [Done] Virtual environment created
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

if %FIRST_RUN%==1 (
    echo Upgrading pip...
    python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    echo Installing dependencies...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    echo Installing Playwright Chromium browser...
    python -m playwright install chromium
)

echo.
echo Starting scraper...
echo.
python main.py

echo.
echo ========================================
echo Done! Press any key to exit...
pause >nul
