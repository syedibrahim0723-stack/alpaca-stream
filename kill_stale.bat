@echo off
cd /d "%~dp0"
(
echo --- before ---
tasklist /FI "PID eq 44776"
echo --- killing ---
taskkill /PID 44776 /F /T
echo kill_errorlevel: %errorlevel%
echo --- after ---
tasklist /FI "PID eq 44776"
) > kill_stale_log.txt 2>&1
exit /b 0
