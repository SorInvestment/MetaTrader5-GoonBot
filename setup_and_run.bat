@echo off
:: ============================================================
::  MT5 GoonBot — One-Click Windows Setup & Launch
::  Run this script as Administrator for best results.
::  It will: install Python, install deps, validate, and start.
:: ============================================================
title GoonBot Setup
color 0A
echo.
echo ============================================================
echo   MT5 GoonBot — Automated Setup
echo ============================================================
echo.

:: -----------------------------------------------------------
:: Step 1: Check if Python 3.9+ is already available
:: -----------------------------------------------------------
echo [1/6] Checking Python...
python --version 2>nul | findstr /R "3\.1[0-9] 3\.9" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo       Python already installed:
    python --version
    goto :skip_python
)

py -3.11 --version 2>nul >nul
if %ERRORLEVEL%==0 (
    echo       Python 3.11 found via py launcher
    set PYTHON=py -3.11
    goto :skip_python
)

echo       Python 3.9+ not found. Downloading Python 3.11.9...
echo.

:: Download Python installer
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\python-installer.exe' }"

if not exist "%TEMP%\python-installer.exe" (
    echo       ERROR: Failed to download Python. Please install manually from:
    echo       https://www.python.org/downloads/
    pause
    exit /b 1
)

echo       Installing Python 3.11.9 (this may take a minute)...
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1

:: Refresh PATH in current session
set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%PATH%"
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

:: Verify
python --version 2>nul | findstr /R "3\.11" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo       Python installed successfully:
    python --version
) else (
    echo       WARNING: Python installed but PATH may need a restart.
    echo       Close this window, reopen Command Prompt, and run this script again.
    pause
    exit /b 1
)

:skip_python
echo.

:: -----------------------------------------------------------
:: Step 2: Navigate to project directory
:: -----------------------------------------------------------
echo [2/6] Setting up project directory...
cd /d "%~dp0"
echo       Working in: %CD%
echo.

:: -----------------------------------------------------------
:: Step 3: Create .env with demo credentials
:: -----------------------------------------------------------
echo [3/6] Configuring credentials...
if not exist ".env" (
    (
        echo MT5_LOGIN=5048716399
        echo MT5_PASSWORD=S@MpHu4f
        echo MT5_SERVER=MetaQuotes-Demo
    ) > .env
    echo       Created .env with demo account credentials
) else (
    echo       .env already exists — keeping existing credentials
)
echo.

:: -----------------------------------------------------------
:: Step 4: Install Python dependencies
:: -----------------------------------------------------------
echo [4/6] Installing dependencies...
echo.
python -m pip install --upgrade pip 2>nul
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo       ERROR: pip install failed. Check errors above.
    pause
    exit /b 1
)
echo.
echo       All dependencies installed successfully.
echo.

:: -----------------------------------------------------------
:: Step 5: Validate setup
:: -----------------------------------------------------------
echo [5/6] Validating setup...
echo.
python validate_setup.py
echo.

:: -----------------------------------------------------------
:: Step 6: Confirm MT5 is running, then launch
:: -----------------------------------------------------------
echo [6/6] Ready to launch!
echo.
echo ============================================================
echo   IMPORTANT: Make sure MetaTrader 5 is running and logged
echo   into your demo account before continuing.
echo.
echo   Login:    5048716399
echo   Password: S@MpHu4f
echo   Server:   MetaQuotes-Demo
echo ============================================================
echo.
echo   Choose an option:
echo     1 = Start bot (DRY RUN — signals only, no real trades)
echo     2 = Start bot (LIVE — will place real demo trades)
echo     3 = Run single test cycle (dry run) then exit
echo     4 = Exit setup
echo.
set /p choice="  Enter choice (1-4): "

if "%choice%"=="1" (
    echo.
    echo   Starting bot in DRY RUN mode...
    echo   Press Ctrl+C to stop.
    echo.
    python main.py --dry-run
) else if "%choice%"=="2" (
    echo.
    echo   Starting bot in LIVE mode on demo account...
    echo   Press Ctrl+C to stop.
    echo.
    python main.py
) else if "%choice%"=="3" (
    echo.
    echo   Running single test cycle...
    echo.
    python main.py --once --dry-run
) else (
    echo.
    echo   Setup complete. Run 'python main.py' when ready.
)

echo.
pause
