@echo off
:: MT5 GoonBot — Background runner with auto-restart.
:: Loads .env, runs the bot, restarts on crash.
title GoonBot Runner
cd /d "%~dp0"

:: Load .env if it exists
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "%%A=%%B"
    )
)

:loop
    echo [%DATE% %TIME%] Starting bot...
    python main.py %*
    echo [%DATE% %TIME%] Bot exited (code %ERRORLEVEL%). Restarting in 30 seconds...
    echo     Press Ctrl+C to stop permanently.
    timeout /t 30
goto loop
