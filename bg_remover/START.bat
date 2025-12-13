@echo off
title BG Remover Pro
color 0A

echo.
echo  ======================================
echo      BG REMOVER PRO - Starting...
echo  ======================================
echo.

cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo Please install Python from python.org
    pause
    exit /b
)

:: Install dependencies if needed
if not exist "venv" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: Run the app
echo.
echo [INFO] Starting server...
echo [INFO] Opening browser at http://127.0.0.1:5000
echo.
python run.py

pause
