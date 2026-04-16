@echo off
title Alpaca Stream — Deploy to GCP
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo  Alpaca Stream — Deploy to GCP VM
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

:: ── CONFIG — edit these three lines ─────────────────────────────────────────
set PROJECT_ID=alpaca-stream-live
set VM_NAME=alpaca-stream-vm
set ZONE=us-east1-b
:: ─────────────────────────────────────────────────────────────────────────────

echo   Project : %PROJECT_ID%
echo   VM      : %VM_NAME%
echo   Zone    : %ZONE%
echo.

:: ── Check gcloud is installed ─────────────────────────────────────────────────
where gcloud >nul 2>&1
if errorlevel 1 (
    echo ❌  gcloud CLI not found!
    echo     Install from: https://cloud.google.com/sdk/docs/install
    echo     Then run: gcloud init
    pause
    exit /b 1
)

:: ── Set active project ────────────────────────────────────────────────────────
echo [1/5] Setting active project...
gcloud config set project %PROJECT_ID% --quiet
if errorlevel 1 (
    echo ❌  Failed to set project. Make sure %PROJECT_ID% exists.
    pause
    exit /b 1
)
echo ✅  Project set

:: ── Copy app files to VM ──────────────────────────────────────────────────────
echo.
echo [2/5] Copying app files to VM (this may take 30-60s)...

gcloud compute scp --zone=%ZONE% --recurse ^
    main.py ^
    launcher.py ^
    requirements.txt ^
    %VM_NAME%:/opt/alpaca-stream/ --quiet

if errorlevel 1 (
    echo ❌  File copy failed. Is the VM running?
    echo     Check: gcloud compute instances list
    pause
    exit /b 1
)

:: Copy static folder
gcloud compute scp --zone=%ZONE% --recurse ^
    static ^
    %VM_NAME%:/opt/alpaca-stream/ --quiet

echo ✅  Files copied

:: ── Copy setup script and run it (first deploy only) ─────────────────────────
echo.
echo [3/5] Uploading setup script...
gcloud compute scp --zone=%ZONE% ^
    setup_vm.sh ^
    %VM_NAME%:~/setup_vm.sh --quiet

echo ✅  Setup script uploaded

:: ── Copy .env securely ────────────────────────────────────────────────────────
echo.
echo [4/5] Uploading .env file...
if not exist .env (
    echo ⚠️   No .env file found locally — skipping.
    echo     You will need to manually create /opt/alpaca-stream/.env on the VM.
) else (
    gcloud compute scp --zone=%ZONE% ^
        .env ^
        %VM_NAME%:~/alpaca-stream.env --quiet
    :: Move it into place on the VM
    gcloud compute ssh %VM_NAME% --zone=%ZONE% --quiet ^
        --command="sudo mv ~/alpaca-stream.env /opt/alpaca-stream/.env && sudo chown $USER:$USER /opt/alpaca-stream/.env && chmod 600 /opt/alpaca-stream/.env"
    echo ✅  .env deployed
)

:: ── Restart service ───────────────────────────────────────────────────────────
echo.
echo [5/5] Restarting alpaca-stream service...
gcloud compute ssh %VM_NAME% --zone=%ZONE% --quiet ^
    --command="sudo systemctl restart alpaca-stream && sudo systemctl status alpaca-stream --no-pager -l"

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo  ✅  Deploy complete!
echo.

:: Print the external IP
echo  Getting external IP...
for /f "tokens=*" %%i in ('gcloud compute instances describe %VM_NAME% --zone=%ZONE% --format="get(networkInterfaces[0].accessConfigs[0].natIP)" 2^>nul') do set EXTERNAL_IP=%%i

if defined EXTERNAL_IP (
    echo  Dashboard: http://%EXTERNAL_IP%:8000
    echo  Flow diagram: http://%EXTERNAL_IP%:8000/flow.html
    echo  Alerts log: http://%EXTERNAL_IP%:8000/log/alerts
) else (
    echo  Run this to get your IP:
    echo    gcloud compute instances describe %VM_NAME% --zone=%ZONE% --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
)

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo  To stream live logs:
echo    gcloud compute ssh %VM_NAME% --zone=%ZONE% --command="sudo journalctl -u alpaca-stream -f"
echo.
pause
