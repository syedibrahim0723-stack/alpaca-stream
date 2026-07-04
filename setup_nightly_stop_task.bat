@echo off
title Alpaca Stream - Set Up Nightly Auto-Stop
cd /d "%~dp0"

echo =======================================
echo  Alpaca Stream - Register Nightly Auto-Stop
echo =======================================
echo.
echo This is a ONE-TIME setup. It registers a Windows Task Scheduler job
echo that runs vm_stop.bat every day at the time below.
echo.
echo NOTE: this only fires if your PC is on and awake at that time. If you
echo want the VM to stop even when your laptop is off, also set up the
echo GCP-side instance schedule described in GCP_SETUP.md.
echo.

:: -- CONFIG - edit the time (24h format, local PC time) -------------------------
set STOP_TIME=20:00
set TASK_NAME=AlpacaStreamNightlyStop
:: --------------------------------------------------------------------------------

echo Registering task "%TASK_NAME%" to run vm_stop.bat daily at %STOP_TIME%...
schtasks /create /tn "%TASK_NAME%" /tr "\"%~dp0vm_stop.bat\"" /sc daily /st %STOP_TIME% /f

if errorlevel 1 (
    echo [ERROR] Failed to register the scheduled task. Try running this .bat as Administrator.
    pause
    exit /b 1
)

echo.
echo [OK]    Done. "%TASK_NAME%" will run vm_stop.bat every day at %STOP_TIME%.
echo.
echo Useful commands:
echo   Check it:    schtasks /query /tn "%TASK_NAME%"
echo   Remove it:   schtasks /delete /tn "%TASK_NAME%" /f
echo   Change time: edit STOP_TIME above and re-run this script
echo.
pause
