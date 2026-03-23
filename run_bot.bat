@echo off
cd /d "%~dp0"
:loop
    echo [%TIME%] Starting bot...
    python main.py
    echo [%TIME%] Bot stopped. Restarting in 30 seconds...
    timeout /t 30
goto loop
