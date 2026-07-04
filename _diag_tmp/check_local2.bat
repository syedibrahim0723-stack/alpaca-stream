@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_local2.ps1" > check_local2_log.txt 2>&1
exit /b 0
