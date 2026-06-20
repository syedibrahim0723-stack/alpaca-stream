@echo off
cd /d "%~dp0"
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a --quiet --command="sudo systemctl restart alpaca-stream; sleep 8; sudo systemctl status alpaca-stream --no-pager -l; echo ----RECENT-LOG----; sudo journalctl -u alpaca-stream --no-pager -n 25" > restart_check_log.txt 2>&1
exit /b 0
