@echo off
chcp 65001 >nul
title VE3 Tool Launcher
color 0A

echo ╔═══════════════════════════════════════════════════════╗
echo ║           VE3 TOOL - Auto Update Launcher             ║
echo ╚═══════════════════════════════════════════════════════╝
echo.

set "INSTALL_DIR=%~dp0"
set "REPO_URL=https://github.com/criggerbrannon-hash/ve3-tool.git"
set "CODE_DIR=%INSTALL_DIR%code"
set "CONFIG_DIR=%INSTALL_DIR%config"
set "PROJECTS_DIR=%INSTALL_DIR%PROJECTS"

REM ===== Check Git =====
where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git chua duoc cai dat!
    echo Tai tai: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM ===== Check Python =====
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python chua duoc cai dat!
    echo Tai tai: https://python.org
    pause
    exit /b 1
)

REM ===== Create directories =====
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
if not exist "%PROJECTS_DIR%" mkdir "%PROJECTS_DIR%"

REM ===== Clone or Pull =====
if exist "%CODE_DIR%\.git" (
    echo [UPDATE] Dang cap nhat code moi nhat...
    cd /d "%CODE_DIR%"
    git pull origin main --quiet
    if errorlevel 1 (
        echo [WARN] Khong the cap nhat. Chay ban hien tai...
    ) else (
        echo [OK] Da cap nhat thanh cong!
    )
) else (
    echo [INSTALL] Dang tai code lan dau...
    if exist "%CODE_DIR%" rmdir /s /q "%CODE_DIR%"
    git clone "%REPO_URL%" "%CODE_DIR%" --quiet
    if errorlevel 1 (
        echo [ERROR] Khong the tai code! Kiem tra ket noi mang.
        pause
        exit /b 1
    )
    echo [OK] Da tai thanh cong!
)

REM ===== Link config =====
echo [INFO] Kiem tra config...

REM Copy default config if not exists
if not exist "%CONFIG_DIR%\accounts.json" (
    if exist "%CODE_DIR%\config\accounts.json" (
        copy "%CODE_DIR%\config\accounts.json" "%CONFIG_DIR%\accounts.json" >nul
        echo [INFO] Da tao file config mau. Vui long sua truoc khi chay!
        echo        %CONFIG_DIR%\accounts.json
        notepad "%CONFIG_DIR%\accounts.json"
        pause
    )
)

REM ===== Install requirements =====
echo [INFO] Kiem tra dependencies...
cd /d "%CODE_DIR%"
pip install -r requirements.txt --quiet 2>nul

REM ===== Run =====
echo.
echo ╔═══════════════════════════════════════════════════════╗
echo ║                   KHOI DONG VE3 TOOL                  ║
echo ╚═══════════════════════════════════════════════════════╝
echo.

REM Set environment variables for the tool
set "VE3_CONFIG_DIR=%CONFIG_DIR%"
set "VE3_PROJECTS_DIR=%PROJECTS_DIR%"

python ve3_pro.py

pause
