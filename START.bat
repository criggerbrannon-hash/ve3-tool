@echo off
:: Uni-x Voice to Video - Silent Launcher
:: Chạy tool mà không hiện cửa sổ CMD

cd /d "%~dp0"

:: Kiểm tra pythonw (Python GUI mode - không có console)
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw ve3_pro.py
    exit /b 0
)

:: Fallback: dùng python với hidden window qua VBS
echo Set WshShell = CreateObject("WScript.Shell") > "%temp%\run_hidden.vbs"
echo WshShell.Run "python ""%~dp0ve3_pro.py""", 0, False >> "%temp%\run_hidden.vbs"
wscript "%temp%\run_hidden.vbs"
del "%temp%\run_hidden.vbs"
