@echo off
cd /d "%~dp0"
(
echo --- python processes ---
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' } | Select-Object ProcessId,Name,CommandLine | Format-List"
echo --- listening on port 8000 ---
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess"
echo --- netstat fallback ---
netstat -ano | findstr :8000
) > check_local_log.txt 2>&1
exit /b 0
