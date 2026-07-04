@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_running.ps1" > check_running_log.txt 2>&1
exit /b 0
