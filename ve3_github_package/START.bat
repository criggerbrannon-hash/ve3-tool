@echo off
title VE3 Tool Pro
cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python khong tim thay!
    echo Vui long cai dat Python tu python.org
    pause
    exit /b 1
)

REM Run
python ve3_pro.py
pause
