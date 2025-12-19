@echo off
setlocal enabledelayedexpansion
:: ========================================
:: DOI BRANCH CHINH
:: Khi session cu het, dung file nay de chuyen sang branch moi
:: ========================================

cd /d "%~dp0"

echo.
echo ========================================
echo   DOI BRANCH CHINH
echo ========================================
echo.

:: Hien thi branch hien tai
echo [*] Branch chinh hien tai:
echo ----------------------------------------
if exist "config\main_branch.txt" (
    for /f "usebackq tokens=* eol=#" %%B in ("config\main_branch.txt") do (
        if not "%%B"=="" (
            echo     %%B
            set CURRENT=%%B
        )
    )
) else (
    echo     (Chua cau hinh)
)
echo ----------------------------------------

:: Fetch tat ca branches
echo.
echo [*] Dang lay danh sach branches...
git fetch --all >nul 2>&1

:: Hien thi tat ca branches
echo.
echo [*] Tat ca branches co san:
echo ----------------------------------------
git branch -r | findstr "claude/"
echo ----------------------------------------

:: Hoi branch moi
echo.
echo Nhap ten branch moi (hoac Enter de giu nguyen):
set /p NEW_BRANCH="Branch moi: "

if "%NEW_BRANCH%"=="" (
    echo [*] Giu nguyen branch hien tai.
    pause
    exit /b
)

:: Kiem tra branch ton tai
git show-ref --verify --quiet refs/remotes/origin/%NEW_BRANCH% 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Branch khong ton tai: %NEW_BRANCH%
    pause
    exit /b 1
)

:: Cap nhat file config
echo # Branch chinh de sync> "config\main_branch.txt"
echo # Khi session cu het, doi thanh branch moi o day>> "config\main_branch.txt"
echo.>> "config\main_branch.txt"
echo %NEW_BRANCH%>> "config\main_branch.txt"

:: Them vao danh sach sync neu chua co
findstr /x "%NEW_BRANCH%" "config\sync_branches.txt" >nul 2>&1
if %errorlevel% neq 0 (
    echo %NEW_BRANCH%>> "config\sync_branches.txt"
    echo [OK] Da them vao danh sach sync
)

:: Checkout branch moi
echo.
echo [*] Chuyen sang branch moi...
git checkout %NEW_BRANCH% 2>nul || git checkout -b %NEW_BRANCH% origin/%NEW_BRANCH%

echo.
echo ========================================
echo   DA DOI BRANCH CHINH THANH:
echo   %NEW_BRANCH%
echo ========================================
echo.

pause
