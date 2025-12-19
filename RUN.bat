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
        echo [*] Checking for updates...

        :: Fetch chi branch hien tai
        for /f "tokens=*" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CURRENT_BRANCH=%%B"

        if defined CURRENT_BRANCH (
            echo     Current branch: !CURRENT_BRANCH!
            git fetch origin !CURRENT_BRANCH! 2>nul

            :: Chi pull neu co update moi (khong merge nhieu branches)
            git pull origin !CURRENT_BRANCH! --ff-only 2>nul
            if !errorlevel! equ 0 (
                echo [OK] Updated successfully!
            ) else (
                echo [WARN] Cannot fast-forward, keeping local version
            )
        ) else (
            echo [WARN] Could not determine current branch
        )

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
