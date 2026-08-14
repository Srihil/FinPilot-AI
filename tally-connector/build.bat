@echo off
title FinPilot Connector — Build
echo.
echo  =============================================
echo   FinPilot Tally Connector — Build .exe
echo  =============================================
echo.

:: Ensure venv exists
if not exist venv (
    echo  Creating virtual environment...
    python -m venv venv
)

:: Install build dependencies
echo  Installing dependencies + PyInstaller...
venv\Scripts\pip install -r requirements.txt --quiet
venv\Scripts\pip install pyinstaller --quiet

:: Clean previous build
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

:: Build
echo.
echo  Building .exe — this takes ~30 seconds...
echo.
venv\Scripts\pyinstaller finpilot_connector.spec

echo.
if exist dist\finpilot-tally-connector.exe (
    echo  =============================================
    echo   BUILD SUCCESSFUL
    echo  =============================================
    echo.
    echo   Output: dist\finpilot-tally-connector.exe
    for %%A in (dist\finpilot-tally-connector.exe) do echo   Size:   %%~zA bytes
    echo.
    echo   Next steps:
    echo   1. Test:  dist\finpilot-tally-connector.exe
    echo   2. Upload to GitHub Releases as:
    echo      finpilot-tally-connector.exe
    echo.
) else (
    echo  BUILD FAILED — check errors above
)

pause
