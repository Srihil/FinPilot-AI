@echo off
title FinPilot TallyPrime Connector
cd /d "%~dp0tally-connector"

echo.
echo =====================================================
echo    FinPilot TallyPrime Connector  v1.7.0
echo    Connected to: finpilot-backend-w1im.onrender.com
echo =====================================================
echo.

REM Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Please install Python 3.10+ from https://python.org
    echo         and make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/2] Installing / updating dependencies...
pip install httpx python-dotenv pystray Pillow --quiet --upgrade
if errorlevel 1 (
    echo [WARNING] Some dependencies may not have installed correctly.
    echo           Trying to start anyway...
)

echo [2/2] Starting connector...
echo.
echo IMPORTANT: Make sure TallyPrime is running on this PC
echo            and set to port 9000 (default).
echo.
echo To pair with FinPilot:
echo   1. Log in to FinPilot at https://finpilot-frontend-vbdf.onrender.com
echo   2. Go to TallyPrime section
echo   3. Click "Generate Pairing Code"
echo   4. Enter the code in the connector window that opens
echo.

python app.py

echo.
echo [INFO] Connector stopped. Close this window or press any key to exit.
pause >nul
