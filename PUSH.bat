@echo off
:: VE3 Tool - Push Code to Shared Branch
:: =====================================
:: Chay file nay sau khi co thay doi muon chia se voi cac session khac

cd /d "%~dp0"

echo ========================================
echo   VE3 Tool - PUSH CODE
echo ========================================
echo.

:: Kiem tra git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git chua duoc cai dat!
    pause
    exit /b 1
)

:: Hien thi trang thai
echo [1/5] Current status:
echo ----------------------------------------
git status --short
echo ----------------------------------------
echo.

:: Hoi co muon continue khong
set /p CONTINUE="Co thay doi nao muon push? (y/n): "
if /i not "%CONTINUE%"=="y" (
    echo Cancelled.
    pause
    exit /b 0
)

:: Add all changes
echo.
echo [2/5] Adding all changes...
git add -A

:: Commit
echo.
set /p MSG="Nhap commit message: "
if "%MSG%"=="" set MSG=Update from session

git commit -m "%MSG%"

:: Push to current branch
echo.
echo [3/5] Pushing to current branch...
git push origin HEAD 2>nul

:: Merge to shared branch
echo.
echo [4/5] Merging to shared branch (ve3-image-generation-vmOC4)...

:: Save current branch
for /f "tokens=*" %%a in ('git rev-parse --abbrev-ref HEAD') do set CURRENT_BRANCH=%%a

:: Try to push to shared branch (may fail if no permission)
git push origin HEAD:claude/ve3-image-generation-vmOC4 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Khong the push truc tiep den shared branch.
    echo        Session khac co the pull tu branch: %CURRENT_BRANCH%
)

echo.
echo [5/5] Done!
echo ========================================
echo   Code da duoc push!
echo   Branch hien tai: %CURRENT_BRANCH%
echo ========================================
echo.

git log --oneline -3
echo.

pause
