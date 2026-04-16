@echo off
title Alpaca Live Stream
cd /d "%~dp0"

echo ⚡ Alpaca Live Stream
echo ─────────────────────

if not exist .env (
    echo.
    echo ❌  .env file not found!
    echo     Create a file named .env in this folder with:
    echo       ALPACA_API_KEY=your_key
    echo       ALPACA_SECRET_KEY=your_secret
    echo       XAI_API_KEY=your_xai_key
    echo.
    pause
    exit /b 1
)

echo 📦  Checking dependencies...
pip install alpaca-py websockets python-dotenv fastapi "uvicorn[standard]" pytz requests -q
echo ✅  Dependencies ready
echo.

echo 🚀  Starting server at http://localhost:8000
echo     Press Ctrl+C to stop
echo ─────────────────────

:: Open browser after 2 seconds
start "" timeout /t 2 >nul && start http://localhost:8000

python launcher.py

echo.
echo ⚠️  Server stopped.
pause
