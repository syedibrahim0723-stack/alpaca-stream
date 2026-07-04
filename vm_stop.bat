@echo off
title Alpaca Stream - Stop GCP VM
cd /d "%~dp0"

echo =======================================
echo  Alpaca Stream - Stop GCP VM
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

echo Stopping %VM_NAME% in %ZONE%...
gcloud compute instances stop %VM_NAME% --zone=%ZONE% --quiet

if errorlevel 1 (
    echo [ERROR] Stop failed - check VM name/zone/project above, and that gcloud is authenticated.
) else (
    echo [OK]    %VM_NAME% is stopped. No compute charges while it's off.
)

echo.
pause
