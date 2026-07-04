@echo off
title Alpaca Stream - Start GCP VM
cd /d "%~dp0"

echo =======================================
echo  Alpaca Stream - Start GCP VM
echo =======================================
echo.

:: -- CONFIG - keep these in sync with deploy.bat --------------------------------
set PROJECT_ID=project-062a1e95-5575-43f3-adf
set VM_NAME=instance-20260402-210914
set ZONE=us-central1-a
:: --------------------------------------------------------------------------------

where gcloud >nul 2>&1
if errorlevel 1 (
    echo [ERROR] gcloud CLI not found! Install from: https://cloud.google.com/sdk/docs/install
    pause
    exit /b 1
)

gcloud config set project %PROJECT_ID% --quiet >nul

echo Starting %VM_NAME% in %ZONE%...
gcloud compute instances start %VM_NAME% --zone=%ZONE% --quiet

if errorlevel 1 (
    echo [ERROR] Start failed - check VM name/zone/project above, and that gcloud is authenticated.
    pause
    exit /b 1
)

echo [OK]    %VM_NAME% is starting (~20-30s to boot - systemd auto-starts the app, no manual step needed)
echo.
echo The dashboard is NOT exposed to the public internet. To view it:
echo   1. Run:  gcloud compute ssh %VM_NAME% --zone=%ZONE% -- -L 8000:localhost:8000
echo   2. Leave that window open, then open a browser to: http://localhost:8000
echo.
pause
