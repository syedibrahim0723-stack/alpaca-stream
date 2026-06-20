@echo off
cd /d "%~dp0"
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a --quiet --command="sudo systemctl status alpaca-stream --no-pager -l; echo ----HTTP-CHECK----; curl -s -o /dev/null -w 'HTTP_CODE:%%{http_code}\n' http://localhost:8000" > check_service_log.txt 2>&1
exit /b 0
