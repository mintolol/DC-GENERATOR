@echo off
title DC-GENERATOR Installer

echo.
echo  ============================================
echo   DC-GENERATOR - Library Installer
echo  ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo          Please install from https://www.python.org/downloads/
    echo          Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo  [OK] Python found:
python --version
echo.

echo  [*] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo  [OK] pip upgraded
echo.

echo  [*] Installing required libraries...
echo.

echo  [1/15] flask
python -m pip install flask --quiet
if errorlevel 1 (echo  [WARN] flask failed) else (echo  [OK] flask)

echo  [2/15] pywebview
python -m pip install pywebview --quiet
if errorlevel 1 (echo  [WARN] pywebview failed) else (echo  [OK] pywebview)

echo  [3/15] requests
python -m pip install requests --quiet
if errorlevel 1 (echo  [WARN] requests failed) else (echo  [OK] requests)

echo  [4/15] primp
python -m pip install primp --quiet
if errorlevel 1 (echo  [WARN] primp failed) else (echo  [OK] primp)

echo  [5/15] tls-client
python -m pip install tls-client --quiet
if errorlevel 1 (echo  [WARN] tls-client failed) else (echo  [OK] tls-client)

echo  [6/15] stealth-requests
python -m pip install stealth-requests --quiet
if errorlevel 1 (echo  [WARN] stealth-requests failed) else (echo  [OK] stealth-requests)

echo  [7/15] urllib3
python -m pip install urllib3 --quiet
if errorlevel 1 (echo  [WARN] urllib3 failed) else (echo  [OK] urllib3)

echo  [8/15] websockets
python -m pip install websockets --quiet
if errorlevel 1 (echo  [WARN] websockets failed) else (echo  [OK] websockets)

echo  [9/15] websocket-client
python -m pip install websocket-client --quiet
if errorlevel 1 (echo  [WARN] websocket-client failed) else (echo  [OK] websocket-client)

echo  [10/15] python-socks
python -m pip install "python-socks[asyncio]" --quiet
if errorlevel 1 (echo  [WARN] python-socks failed) else (echo  [OK] python-socks)

echo  [11/15] Pillow
python -m pip install Pillow --quiet
if errorlevel 1 (echo  [WARN] Pillow failed) else (echo  [OK] Pillow)

echo  [12/15] colorama
python -m pip install colorama --quiet
if errorlevel 1 (echo  [WARN] colorama failed) else (echo  [OK] colorama)

echo  [13/15] pystyle
python -m pip install pystyle --quiet
if errorlevel 1 (echo  [WARN] pystyle failed) else (echo  [OK] pystyle)

echo  [14/15] keyboard
python -m pip install keyboard --quiet
if errorlevel 1 (echo  [WARN] keyboard failed) else (echo  [OK] keyboard)

echo  [15/15] truedriver
python -m pip install truedriver --quiet
if errorlevel 1 (echo  [WARN] truedriver failed - may require manual install) else (echo  [OK] truedriver)

echo.
echo  ============================================
echo   Installation complete!
echo   Run: python start.py
echo  ============================================
echo.
pause
