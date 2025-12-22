@echo off
:: VE3 Tool - Switch to new branch (run once)
:: Chay file nay MOT LAN de chuyen sang phien ban moi

cd /d "%~dp0"

echo ========================================
echo   SWITCH TO NEW BRANCH
echo ========================================
echo.

:: Check git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git not found!
    echo Please install git or download ZIP manually:
    echo https://github.com/criggerbrannon-hash/ve3-tool/archive/refs/heads/claude/veo3-tool-review-rdu8g.zip
    goto :end
)

echo [*] Fetching new branch...
git fetch origin claude/veo3-tool-review-rdu8g

echo [*] Switching to new branch...
git checkout claude/veo3-tool-review-rdu8g
git reset --hard origin/claude/veo3-tool-review-rdu8g

echo.
echo ========================================
echo   DONE! Now run RUN.bat as usual
echo ========================================
echo.

:end
pause
