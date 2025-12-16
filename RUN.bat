@echo off
:: Uni-x Voice to Video - Auto Update & Run

cd /d "%~dp0"

echo ========================================
echo   Uni-x Voice to Video
echo ========================================
echo.

:: Auto update qua git (KHONG xoa data cua user)
where git >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Checking for updates...

    :: Huy merge dang do (neu co)
    git merge --abort 2>nul

    :: Reset chi cac file TRACKED (khong xoa PROJECTS, config, v.v.)
    git reset --hard HEAD 2>nul

    :: Fetch va reset ve code moi nhat
    git fetch origin claude/vtv-tool-image-support-01MrKhJPx1cecuLNUkJLpyNr 2>nul
    git reset --hard origin/claude/vtv-tool-image-support-01MrKhJPx1cecuLNUkJLpyNr 2>nul

    if %errorlevel% equ 0 (
        echo [OK] Updated to latest version
    ) else (
        echo [!] Update failed, using local version
    )
) else (
    echo [!] Git not found, skipping update
)

echo.
echo [*] Starting...
echo.

python ve3_pro.py

pause
