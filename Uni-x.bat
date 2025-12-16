@echo off
:: ===========================================
:: UNI-X VOICE TO VIDEO - SILENT LAUNCHER
:: ===========================================
:: Chạy tool hoàn toàn ẩn, không CMD window
:: ===========================================

cd /d "%~dp0"

:: Method 1: Dùng pythonw (Python GUI - không console)
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" /B pythonw ve3_pro.py
    exit
)

:: Method 2: Dùng VBS để chạy hidden
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "python ""%~dp0ve3_pro.py""", 0, False
) > "%temp%\unixrun.vbs"
wscript "%temp%\unixrun.vbs"
del "%temp%\unixrun.vbs" 2>nul
exit
