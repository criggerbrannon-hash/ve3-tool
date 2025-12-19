@echo off
setlocal enabledelayedexpansion
:: ========================================
:: VE3 TOOL - SETUP MAY MOI
:: Chay file nay tren may moi de cai dat
:: ========================================

cd /d "%~dp0"

echo.
echo ========================================
echo   VE3 TOOL - CAI DAT MAY MOI
echo ========================================
echo.

:: Kiem tra Python
echo [1/5] Kiem tra Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo      [X] Python CHUA CAI!
    echo      Vui long tai tai: https://www.python.org/downloads/
    echo      Nho tick "Add Python to PATH" khi cai!
    set MISSING=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo      [OK] Python %%v
)

:: Kiem tra Node.js
echo [2/5] Kiem tra Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo      [X] Node.js CHUA CAI!
    echo      Vui long tai tai: https://nodejs.org/
    set MISSING=1
) else (
    for /f %%v in ('node --version 2^>^&1') do echo      [OK] Node.js %%v
)

:: Kiem tra Git
echo [3/5] Kiem tra Git...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo      [X] Git CHUA CAI!
    echo      Vui long tai tai: https://git-scm.com/downloads
    set MISSING=1
) else (
    for /f "tokens=3" %%v in ('git --version 2^>^&1') do echo      [OK] Git %%v
)

:: Neu thieu phan mem
if defined MISSING (
    echo.
    echo ========================================
    echo   THIEU PHAN MEM! Vui long cai dat:
    echo ========================================
    echo.
    echo   1. Python: https://www.python.org/downloads/
    echo   2. Node.js: https://nodejs.org/
    echo   3. Git: https://git-scm.com/downloads
    echo.
    echo   Sau khi cai xong, CHAY LAI file nay!
    echo.
    pause
    exit /b 1
)

:: Cai thu vien Python
echo [4/5] Cai thu vien Python...
pip install -r requirements.txt >nul 2>&1
if %errorlevel% equ 0 (
    echo      [OK] Da cai xong thu vien Python
) else (
    echo      [!] Co loi khi cai, thu chay: pip install -r requirements.txt
)

:: Cai imagefx-api
echo [5/5] Cai imagefx-api...
call npm i -g @rohitaryal/imagefx-api >nul 2>&1
if %errorlevel% equ 0 (
    echo      [OK] Da cai xong imagefx-api
) else (
    echo      [!] Co loi khi cai, thu chay: npm i -g @rohitaryal/imagefx-api
)

:: Fetch code moi nhat
echo.
echo [*] Dang dong bo code moi nhat...
git fetch --all >nul 2>&1

:: Doc branches tu config
if exist "config\sync_branches.txt" (
    for /f "usebackq tokens=* eol=#" %%B in ("config\sync_branches.txt") do (
        if not "%%B"=="" (
            git merge origin/%%B --no-edit >nul 2>&1
        )
    )
)

echo.
echo ========================================
echo   CAI DAT HOAN TAT!
echo ========================================
echo.
echo   De chay tool: Double-click RUN.bat
echo.
echo   Hoac mo CMD va chay:
echo     cd %cd%
echo     python ve3_pro.py
echo.

pause
