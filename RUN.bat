@echo off
:: Uni-x Voice to Video - Auto Update & Run
:: Logs: logs/app.log

cd /d "%~dp0"

echo ========================================
echo   Uni-x Voice to Video - Launcher
echo ========================================
echo.

:: Auto update qua git
where git >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Checking for updates...
    git fetch origin claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 2>nul
    git reset --hard origin/claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 2>nul
    if %errorlevel% equ 0 (
        echo [OK] Updated to latest version
    ) else (
        echo [!] Update failed, using local version
    )
) else (
    echo [!] Git not found, skipping update
)

echo.
echo [*] Starting app...
echo.

python ve3_pro.py

echo.
echo [*] App closed
pause
