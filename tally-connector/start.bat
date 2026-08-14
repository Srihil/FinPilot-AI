@echo off
title FinPilot Tally Connector
echo.
echo  =============================================
echo   FinPilot Tally Connector for TallyPrime
echo  =============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python is not installed or not in PATH.
    echo  Download Python 3.12 from https://python.org
    pause
    exit /b 1
)

:: Install dependencies if needed
if not exist venv (
    echo  Creating virtual environment...
    python -m venv venv
    echo  Installing dependencies...
    venv\Scripts\pip install -r requirements.txt --quiet
)

:: Copy .env.example if .env does not exist
if not exist .env (
    copy .env.example .env >nul
    echo.
    echo  IMPORTANT: Edit .env and set FINPILOT_API_URL to your FinPilot backend URL.
    echo  Then run this file again.
    echo.
    notepad .env
    pause
    exit /b 0
)

echo  Starting connector...
echo.
venv\Scripts\python connector.py

pause
