@echo off
chcp 65001 >nul
title VE3 Tool - Auto Update & Run
cd /d "%~dp0"

echo ============================================
echo    VE3 TOOL - Auto Update
echo ============================================
echo.

:: Check if git exists
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Git not found, running without update...
    goto :run
)

:: Auto pull latest code
echo [*] Checking for updates...
git fetch origin main 2>nul
git fetch origin claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 2>nul

:: Merge main
git merge origin/main --no-edit 2>nul

:: Merge feature branch if exists
git merge origin/claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 --no-edit 2>nul

echo [OK] Code updated!
echo.

:run
echo ============================================
echo    Starting VE3 Tool...
echo ============================================
echo.

python ve3_pro.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Error running tool. Check Python installation.
    pause
)
