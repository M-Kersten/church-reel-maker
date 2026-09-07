@echo off
setlocal
title Church Reel Maker
cd /d "%~dp0"

rem --- 1. Find Python 3.10+ (install it with winget when missing) ---------------
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
    echo Python was not found. Trying to install it with winget ...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo.
        echo Please install Python 3.12 from https://www.python.org/downloads/windows/
        echo and tick "Add python.exe to PATH" during installation. Then run start.bat again.
        pause
        exit /b 1
    )
    echo Python was installed. Please close this window and run start.bat again.
    pause
    exit /b 0
)

rem --- 2. Create the Python environment on first run ----------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Setting up the app for the first time, this takes a few minutes ...
    %PY% -m venv .venv || goto :fail
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt || goto :fail
)

rem --- 3. Start (downloads FFmpeg on first run, opens the browser) ---------------
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo Something went wrong. Read the messages above, then press any key to close.
pause >nul
exit /b 1
