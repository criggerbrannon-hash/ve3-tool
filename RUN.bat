@echo off
chcp 65001 >nul
title VE3 Tool - Auto Update & Run
cd /d "%~dp0"

echo ============================================
echo    VE3 TOOL - Auto Update
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python khong tim thay!
    echo     Vui long cai dat Python tu python.org
    pause
    exit /b 1
)

:: Check Git and auto update
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Git not found, running without update...
    goto :run
)

:: Auto pull latest code
echo [*] Checking for updates...
git fetch origin main 2>nul
git fetch origin claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 2>nul

:: Reset to remote (dam bao code moi nhat)
git reset --hard origin/claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 2>nul
if %errorlevel% neq 0 (
    git reset --hard origin/main 2>nul
)

echo [OK] Code updated!
echo.

:run
echo ============================================
echo    Starting VE3 Tool...
echo ============================================
echo.

python ve3_pro.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Error running tool.
    pause
)
