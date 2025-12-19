@echo off
:: VE3 Tool - Sync Code Between Sessions
:: ======================================
:: Chay file nay de dong bo code tu cac session khac

cd /d "%~dp0"

echo ========================================
echo   VE3 Tool - SYNC CODE
echo ========================================
echo.

:: Kiem tra git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git chua duoc cai dat!
    echo Download tai: https://git-scm.com/downloads
    pause
    exit /b 1
)

:: Fetch tat ca branches
echo [1/4] Fetching all branches...
git fetch --all

:: Hien thi cac branch co san
echo.
echo [2/4] Available branches:
echo ----------------------------------------
git branch -a | findstr "claude/"
echo ----------------------------------------
echo.

:: Hoi nguoi dung muon sync tu branch nao
set /p BRANCH="Nhap ten branch muon sync (Enter = ve3-image-generation-vmOC4): "
if "%BRANCH%"=="" set BRANCH=claude/ve3-image-generation-vmOC4

:: Kiem tra branch co ton tai khong
git show-ref --verify --quiet refs/remotes/origin/%BRANCH% 2>nul
if %errorlevel% neq 0 (
    :: Thu them prefix claude/
    git show-ref --verify --quiet refs/remotes/origin/claude/%BRANCH% 2>nul
    if %errorlevel% equ 0 (
        set BRANCH=claude/%BRANCH%
    ) else (
        echo [ERROR] Branch '%BRANCH%' khong ton tai!
        pause
        exit /b 1
    )
)

:: Pull code moi nhat
echo.
echo [3/4] Pulling latest code from: %BRANCH%
git checkout -B local-sync origin/%BRANCH% 2>nul
if %errorlevel% neq 0 (
    git reset --hard origin/%BRANCH%
)

echo.
echo [4/4] Done!
echo ========================================
echo   Code da duoc sync tu: %BRANCH%
echo ========================================
echo.

:: Hien thi commit moi nhat
echo Commit moi nhat:
git log --oneline -3
echo.

pause
