@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo ======================================
    echo ERROR: Administrator privileges required
    echo ======================================
    echo.
    echo This application requires administrator rights to function properly.
    echo Please run this batch file with administrator privileges.
    echo.
    echo Right-click on start.bat and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo.
echo Administrator privileges confirmed.
echo.
cd /d %~dp0
python start.py
pause
