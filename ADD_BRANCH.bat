@echo off
:: Chi can chay file nay va paste ten branch
cd /d "%~dp0"

echo ========================================
echo   THEM BRANCH MOI VAO DANH SACH SYNC
echo ========================================
echo.
echo Khi bat dau session moi, Claude se noi:
echo   "Develop on branch claude/xxx-xxx"
echo.
echo Copy ten branch do va paste vao day:
echo.

set /p BRANCH="Ten branch: "

if "%BRANCH%"=="" (
    echo [!] Khong nhap gi, thoat.
    pause
    exit /b
)

:: Them vao file
echo %BRANCH%>> "config\sync_branches.txt"

echo.
echo [OK] Da them: %BRANCH%
echo.
echo Danh sach branches hien tai:
echo ----------------------------------------
type "config\sync_branches.txt" | findstr /v "^#"
echo ----------------------------------------
echo.

pause
