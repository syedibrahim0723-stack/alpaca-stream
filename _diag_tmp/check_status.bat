@echo off
cd /d "%~dp0"
gcloud compute instances describe instance-20260402-210914 --zone=us-central1-a --format="value(status)" > check_status_log.txt 2>&1
exit /b 0
