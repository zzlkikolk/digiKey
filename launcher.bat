@echo off
chcp 65001 >nul
title digiKey Scraper Launcher

cd /d "%~dp0"

echo ========================================
echo   digiKey Scraper Launcher
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 goto :no_python

echo Starting GUI...
echo.
python launcher.py
if errorlevel 1 goto :run_failed

goto :end

:no_python
echo [ERROR] Python not found. Please install Python 3.8+ first.
pause
exit /b 1

:run_failed
echo.
echo [ERROR] Launcher failed to start. Check Python environment.
pause
exit /b 1

:end
pause
