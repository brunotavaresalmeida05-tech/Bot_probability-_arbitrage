@echo off
title Trading Bot V6 - Watchdog
setlocal

:: ─── Configuration ───────────────────────────────────────────
set RESTART_DELAY=30
set LOG_FILE=logs\watchdog.log
set BOT_SCRIPT=run_live.py
set MAX_RESTARTS=50

:: ─── Ensure logs directory exists ────────────────────────────
if not exist logs mkdir logs

set RESTART_COUNT=0

:loop
set /A RESTART_COUNT+=1
if %RESTART_COUNT% GTR %MAX_RESTARTS% (
    echo [%date% %time%] ERROR: Max restarts (%MAX_RESTARTS%) reached. Exiting watchdog.
    echo [%date% %time%] ERROR: Max restarts reached >> %LOG_FILE%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  [%date% %time%] Starting bot (attempt #%RESTART_COUNT%)
echo ============================================================
echo [%date% %time%] Starting bot attempt #%RESTART_COUNT% >> %LOG_FILE%

:: Activate virtual environment if present
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

:: Run the bot
python %BOT_SCRIPT%

set EXIT_CODE=%ERRORLEVEL%
echo.
echo [%date% %time%] Bot exited with code %EXIT_CODE%. Restarting in %RESTART_DELAY%s...
echo [%date% %time%] Bot exited code=%EXIT_CODE%, restart #%RESTART_COUNT% >> %LOG_FILE%

:: Short pause so Ctrl+C can interrupt the loop
timeout /t %RESTART_DELAY% /nobreak >nul

goto loop
