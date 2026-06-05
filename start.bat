@echo off
title SHLOKA
echo.
echo  Starting SHLOKA...
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found.
    echo  Install Python from https://python.org
    echo  Check "Add Python to PATH" during install.
    pause
    exit /b 1
)

python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing packages...
    python -m pip install -r requirements.txt
)

python run.py
pause
