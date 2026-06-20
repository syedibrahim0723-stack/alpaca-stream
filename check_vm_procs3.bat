@echo off
cd /d "%~dp0"
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a --quiet --command="echo ----ALL PYTHON UVICORN PROCESSES----; ps aux | grep -iE 'python|uvicorn' | grep -v grep; echo ----SCREEN SESSIONS----; screen -ls 2>&1; echo ----TMUX SESSIONS----; tmux ls 2>&1; echo ----ROOT CRONTAB----; sudo crontab -l 2>&1; echo ----USER CRONTAB----; crontab -l 2>&1; echo ----SYSTEMD SERVICES ALPACA RELATED----; systemctl list-units --type=service --all | grep -i alpaca; echo ----LISTENING PORTS----; sudo ss -tlnp 2>&1; echo ----OUTBOUND CONNECTIONS----; sudo ss -tnp 2>&1 | grep -i ESTAB" > check_vm_procs3_log.txt 2>&1
exit /b 0
