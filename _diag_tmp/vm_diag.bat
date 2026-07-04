@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
(
echo === !date! !time! ===
echo --- where gcloud ---
where gcloud
echo where_errorlevel: !errorlevel!
echo --- gcloud --version ---
gcloud --version
echo version_errorlevel: !errorlevel!
echo --- gcloud config list ---
gcloud config list
echo --- setting project ---
gcloud config set project project-062a1e95-5575-43f3-adf --quiet
echo set_project_errorlevel: !errorlevel!
echo --- starting VM ---
gcloud compute instances start instance-20260402-210914 --zone=us-central1-a --quiet
echo start_errorlevel: !errorlevel!
echo --- instance status ---
gcloud compute instances describe instance-20260402-210914 --zone=us-central1-a --format="value(status)"
echo === DONE ===
) > vm_diag_log.txt 2>&1
exit /b 0
