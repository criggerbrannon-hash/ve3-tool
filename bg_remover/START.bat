@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title BG Remover Pro - AI Background Removal
mode con: cols=70 lines=35
color 0B

:splash
cls
echo.
echo    ██████╗  ██████╗    ██████╗ ███████╗███╗   ███╗ ██████╗
echo    ██╔══██╗██╔════╝    ██╔══██╗██╔════╝████╗ ████║██╔═══██╗
echo    ██████╔╝██║  ███╗   ██████╔╝█████╗  ██╔████╔██║██║   ██║
echo    ██╔══██╗██║   ██║   ██╔══██╗██╔══╝  ██║╚██╔╝██║██║   ██║
echo    ██████╔╝╚██████╔╝   ██║  ██║███████╗██║ ╚═╝ ██║╚██████╔╝
echo    ╚═════╝  ╚═════╝    ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝
echo.
echo              ██████╗ ██████╗  ██████╗
echo              ██╔══██╗██╔══██╗██╔═══██╗
echo              ██████╔╝██████╔╝██║   ██║
echo              ██╔═══╝ ██╔══██╗██║   ██║
echo              ██║     ██║  ██║╚██████╔╝
echo              ╚═╝     ╚═╝  ╚═╝ ╚═════╝
echo.
echo    ══════════════════════════════════════════════════════════
echo         AI-Powered Background Removal ^& 4K Upscaling
echo    ══════════════════════════════════════════════════════════
echo.
timeout /t 1 /nobreak >nul

cd /d "%~dp0"

:: Animated loading
echo    [*] Checking system requirements...
call :loading 3

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo    [X] ERROR: Python not found!
    echo.
    echo    Please install Python from: https://python.org
    echo    Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo    [OK] Python %PYVER% detected
echo.

:: Check/Create virtual environment
if not exist "venv" (
    echo    [*] Creating virtual environment...
    call :loading 2
    python -m venv venv
    if %errorlevel% neq 0 (
        color 0C
        echo    [X] Failed to create virtual environment!
        pause
        exit /b
    )
    echo    [OK] Virtual environment created
    echo.

    call venv\Scripts\activate.bat

    echo    [*] Installing dependencies...
    echo    This may take a few minutes on first run...
    echo.
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        color 0C
        echo.
        echo    [X] Failed to install dependencies!
        pause
        exit /b
    )
    echo.
    echo    [OK] All dependencies installed!
) else (
    echo    [*] Activating virtual environment...
    call :loading 2
    call venv\Scripts\activate.bat
    echo    [OK] Environment ready
)

echo.
echo    ══════════════════════════════════════════════════════════
echo.
echo    [*] Starting BG Remover Pro server...
call :loading 3
echo.
color 0A
echo    ╔════════════════════════════════════════════════════════╗
echo    ║                                                        ║
echo    ║     Server running at: http://127.0.0.1:5000          ║
echo    ║                                                        ║
echo    ║     Browser will open automatically...                 ║
echo    ║     Press Ctrl+C to stop the server                    ║
echo    ║                                                        ║
echo    ╚════════════════════════════════════════════════════════╝
echo.

:: Run the app
python run.py

echo.
echo    Server stopped.
pause
exit /b

:loading
setlocal
set "chars=|/-\"
set /a count=%1*4
for /L %%i in (1,1,%count%) do (
    set /a idx=%%i %% 4
    for %%j in (!idx!) do (
        <nul set /p "=   [!chars:~%%j,1!] Loading... "
        timeout /t 0 /nobreak >nul
        <nul set /p "="
    )
)
echo.
endlocal
exit /b
