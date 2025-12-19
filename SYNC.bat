@echo off
setlocal enabledelayedexpansion
:: VE3 Tool - Sync Code Between Sessions
:: ======================================

cd /d "%~dp0"

echo ========================================
echo   VE3 Tool - SYNC CODE
echo ========================================
echo.

:: Kiem tra git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git chua duoc cai dat!
    pause
    exit /b 1
)

:: Fetch tat ca branches
echo [1/4] Fetching all branches...
git fetch --all 2>nul

:: Hien thi branches hien co trong config
echo.
echo [2/4] Branches dang duoc sync:
echo ----------------------------------------
if exist "config\sync_branches.txt" (
    type "config\sync_branches.txt" | findstr /v "^#"
) else (
    echo (Chua co file config)
)
echo ----------------------------------------

:: Hien thi tat ca branches co san
echo.
echo [*] Tat ca branches tren remote:
git branch -r | findstr "claude/"
echo.

:: Hoi co muon them branch moi khong
set /p ADD_NEW="Them branch moi vao danh sach sync? (y/n): "
if /i "%ADD_NEW%"=="y" (
    set /p NEW_BRANCH="Nhap ten branch (vd: claude/xxx-xxx): "
    if not "!NEW_BRANCH!"=="" (
        :: Kiem tra branch co ton tai khong
        git show-ref --verify --quiet refs/remotes/origin/!NEW_BRANCH! 2>nul
        if !errorlevel! equ 0 (
            echo !NEW_BRANCH!>> "config\sync_branches.txt"
            echo [OK] Da them: !NEW_BRANCH!
        ) else (
            echo [ERROR] Branch khong ton tai: !NEW_BRANCH!
        )
    )
)

:: Sync tu tat ca branches trong config
echo.
echo [3/4] Syncing from all branches...
if exist "config\sync_branches.txt" (
    for /f "usebackq tokens=* eol=#" %%B in ("config\sync_branches.txt") do (
        if not "%%B"=="" (
            git show-ref --verify --quiet refs/remotes/origin/%%B 2>nul
            if !errorlevel! equ 0 (
                echo     Merging: %%B
                git merge origin/%%B --no-edit -m "Sync from %%B" 2>nul
            )
        )
    )
)

echo.
echo [4/4] Done!
echo ========================================
echo   Code da duoc sync!
echo ========================================
echo.

:: Hien thi commit moi nhat
echo Latest commits:
git log --oneline -5
echo.

pause
