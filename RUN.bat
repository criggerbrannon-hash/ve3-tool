@echo off
setlocal enabledelayedexpansion
:: VE3 Tool - Auto Update & Run
:: Tu dong sync code tu tat ca sessions

cd /d "%~dp0"

echo ========================================
echo   VE3 Tool - Multi-Session Sync
echo ========================================
echo.

:: Thu update bang git truoc (neu co)
where git >nul 2>&1
if %errorlevel% equ 0 (
    if exist ".git" (
        echo [*] Git found, syncing from all sessions...

        :: Fetch tat ca branches
        git fetch --all 2>nul

        :: Doc danh sach branches tu file config
        if exist "config\sync_branches.txt" (
            echo [*] Reading branches from config\sync_branches.txt
            for /f "usebackq tokens=* eol=#" %%B in ("config\sync_branches.txt") do (
                if not "%%B"=="" (
                    git show-ref --verify --quiet refs/remotes/origin/%%B 2>nul
                    if !errorlevel! equ 0 (
                        echo     Merging: %%B
                        git merge origin/%%B --no-edit -m "Auto-merge from %%B" 2>nul
                    )
                )
            )
        ) else (
            :: Fallback: merge tu branches mac dinh
            echo [*] No config found, using default branches
            git merge origin/claude/ve3-image-generation-vmOC4 --no-edit 2>nul
        )

        echo.
        echo [OK] Synced!
        echo.
        echo [*] Latest commits:
        git log --oneline -3
        echo.
        goto :run
    )
)

:: Neu khong co git, dung Python updater
echo [*] Checking for updates (no git)...
python UPDATE.py 2>nul
if %errorlevel% neq 0 (
    echo [!] Update skipped, using local version
)

:run
echo.
echo [*] Starting VE3 Tool...
echo.

python ve3_pro.py

pause
