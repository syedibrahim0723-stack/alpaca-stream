@echo off
cd /d "%~dp0"
call vm_start.bat < nul > vm_start_log.txt 2>&1
exit /b 0
