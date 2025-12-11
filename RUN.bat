@echo off
:: Uni-x Voice to Video - Auto Update & Run (Silent)
:: Tự động cập nhật và chạy tool mà không hiện CMD

cd /d "%~dp0"

:: Auto update qua git (im lặng)
where git >nul 2>&1
if %errorlevel% equ 0 (
    git fetch origin main >nul 2>&1
    git fetch origin claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 >nul 2>&1
    git reset --hard origin/claude/ve3-tool-context-01No6Tm2bwFA7SBkjT9Sytv5 >nul 2>&1
    if %errorlevel% neq 0 (
        git reset --hard origin/main >nul 2>&1
    )
)

:: Chạy tool ẩn hoàn toàn
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw ve3_pro.py
    exit /b 0
)

:: Fallback: VBS hidden run
echo Set WshShell = CreateObject("WScript.Shell") > "%temp%\run_hidden.vbs"
echo WshShell.Run "python ""%~dp0ve3_pro.py""", 0, False >> "%temp%\run_hidden.vbs"
wscript "%temp%\run_hidden.vbs"
del "%temp%\run_hidden.vbs"
