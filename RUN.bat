@echo off
setlocal enabledelayedexpansion
:: ========================================
:: VE3 Tool - Auto Sync & Run
:: TU DONG dong bo tu TAT CA sessions
:: ========================================

cd /d "%~dp0"

echo ========================================
echo   VE3 Tool - Auto Sync
echo ========================================
echo.

:: Kiem tra git
where git >nul 2>&1
if %errorlevel% equ 0 (
    if exist ".git" (
        echo [*] Syncing from all sessions...

        :: Fetch TAT CA branches
        git fetch --all --prune 2>nul

        :: Tu dong merge tu TAT CA branches co prefix "claude/"
        for /f "tokens=*" %%B in ('git branch -r ^| findstr "origin/claude/"') do (
            set "BRANCH=%%B"
            set "BRANCH=!BRANCH:origin/=!"
            set "BRANCH=!BRANCH: =!"
            if not "!BRANCH!"=="" (
                echo     Merging: !BRANCH!
                git merge origin/!BRANCH! --no-edit -m "Auto-merge" >nul 2>&1
            )
        )

        echo.
        echo [OK] Synced from all sessions!
        echo.
        goto :run
    )
)

:: Fallback: Python updater
echo [*] Using Python updater...
python UPDATE.py 2>nul

:run
echo [*] Starting VE3 Tool...
echo.

python ve3_pro.py

pause
