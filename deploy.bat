@echo off
title Alpaca Stream - Deploy to GCP
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo =======================================
echo  Alpaca Stream - Deploy to GCP VM
echo =======================================
echo.

:: -- CONFIG - edit these three lines --------------------------------------------
set PROJECT_ID=project-062a1e95-5575-43f3-adf
set VM_NAME=instance-20260402-210914
set ZONE=us-central1-a
:: --------------------------------------------------------------------------------

echo   Project : %PROJECT_ID%
echo   VM      : %VM_NAME%
echo   Zone    : %ZONE%
echo.

:: -- Save this version to GitHub ------------------------------------------------
echo [1/6] Saving version to GitHub...
where git >nul 2>&1
if errorlevel 1 (
    echo [WARN]  git not found - skipping GitHub commit. Install from: https://git-scm.com/download/win
    goto :after_git
)

git add -A
if errorlevel 1 (
    echo [ERROR] git add failed - see error above.
    if exist .git\index.lock (
        echo         A stale .git\index.lock file is blocking git. Close VS Code / GitHub
        echo         Desktop / any other git tool, then delete .git\index.lock and re-run.
    )
    echo         Skipping GitHub push for this deploy.
    goto :after_git
)
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Deploy %date% %time%" >nul
    git push origin main
    if errorlevel 1 (
        echo [WARN]  git push failed - check your connection/credentials. Continuing with VM deploy anyway.
    ) else (
        echo [OK]    Pushed to GitHub
    )
) else (
    echo [OK]    No code changes since last deploy - skipping commit
)
:after_git

:: -- Check gcloud is installed ---------------------------------------------------
where gcloud >nul 2>&1
if errorlevel 1 (
    echo [ERROR] gcloud CLI not found!
    echo         Install from: https://cloud.google.com/sdk/docs/install
    echo         Then run: gcloud init
    pause
    exit /b 1
)

:: -- Set active project ----------------------------------------------------------
echo [2/6] Setting active project...
gcloud config set project %PROJECT_ID% --quiet
if errorlevel 1 (
    echo [ERROR] Failed to set project. Make sure %PROJECT_ID% exists.
    pause
    exit /b 1
)
echo [OK]    Project set

:: -- Copy app files to VM ---------------------------------------------------------
echo.
echo [3/6] Copying app files to VM (this may take 30-60s)...

gcloud compute scp --zone=%ZONE% --recurse ^
    main.py ^
    launcher.py ^
    requirements.txt ^
    %VM_NAME%:/opt/alpaca-stream/ --quiet

if errorlevel 1 (
    echo [ERROR] File copy failed. Is the VM running?
    echo         Check: gcloud compute instances list
    pause
    exit /b 1
)

:: Copy static folder
gcloud compute scp --zone=%ZONE% --recurse ^
    static ^
    %VM_NAME%:/opt/alpaca-stream/ --quiet

echo [OK]    Files copied

:: -- Copy setup script and run it (first deploy only) -----------------------------
echo.
echo [4/6] Uploading setup script...
gcloud compute scp --zone=%ZONE% ^
    setup_vm.sh ^
    %VM_NAME%:~/setup_vm.sh --quiet

echo [OK]    Setup script uploaded

:: -- Copy .env securely -------------------------------------------------------------
echo.
echo [5/6] Uploading .env file...
if not exist .env (
    echo [WARN]  No .env file found locally - skipping.
    echo         You will need to manually create /opt/alpaca-stream/.env on the VM.
) else (
    gcloud compute scp --zone=%ZONE% ^
        .env ^
        %VM_NAME%:~/alpaca-stream.env --quiet
    :: Move it into place on the VM
    gcloud compute ssh %VM_NAME% --zone=%ZONE% --quiet ^
        --command="sudo mv ~/alpaca-stream.env /opt/alpaca-stream/.env && sudo chown $USER:$USER /opt/alpaca-stream/.env && chmod 600 /opt/alpaca-stream/.env"
    echo [OK]    .env deployed
)

:: -- Restart service -------------------------------------------------------------
echo.
echo [6/6] Restarting alpaca-stream service...
gcloud compute ssh %VM_NAME% --zone=%ZONE% --quiet ^
    --command="sudo systemctl restart alpaca-stream && sudo systemctl status alpaca-stream --no-pager -l"

echo.
echo =======================================
echo  [OK] Deploy complete!
echo.

echo  The dashboard is not public. To view it, run:
echo    gcloud compute ssh %VM_NAME% --zone=%ZONE% -- -L 8000:localhost:8000
echo  Then open: http://localhost:8000
echo =======================================
echo.
echo  To stream live logs:
echo    gcloud compute ssh %VM_NAME% --zone=%ZONE% --command="sudo journalctl -u alpaca-stream -f"
echo.
pause
