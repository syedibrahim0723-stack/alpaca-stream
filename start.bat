@echo off
title Alpaca Stream — Live Trading Dashboard
cd /d "%~dp0"

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo  Alpaca Stream — Live Trading Dashboard
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

:: ── Check .env exists ─────────────────────────────────────────────────────────
if not exist .env (
    echo  WARNING: .env file not found!
    echo  Copy .env.example to .env and fill in your API keys.
    echo.
    pause
    exit /b 1
)

:: ── Start server ──────────────────────────────────────────────────────────────
echo  Starting server on http://localhost:8000
echo  Press Ctrl+C to stop.
echo.

python launcher.py

echo.
echo  Server stopped.
pause
