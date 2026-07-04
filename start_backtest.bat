@echo off
echo Starting RSI Backtester on http://localhost:2222
echo.
cd /d "%~dp0backtest"
pip install fastapi uvicorn httpx pydantic --quiet

echo Freeing port 2222 if it's already in use...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":2222" ^| findstr "LISTENING"') do (
    echo   Stopping existing process %%a on port 2222
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

start "RSI Backtester Server" cmd /k python backtest_app.py
timeout /t 3 /nobreak >nul
start "" http://localhost:2222/
