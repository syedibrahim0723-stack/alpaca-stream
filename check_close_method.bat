@echo off
cd /d "%~dp0"
gcloud compute ssh instance-20260402-210914 --zone=us-central1-a --quiet --command="sed -n '1,40p' /opt/alpaca-stream/venv/lib/python3.11/site-packages/alpaca/data/live/websocket.py | grep -n 'def close' -A 12 ; echo ----FULL CLOSE----; grep -n 'async def close' -A 15 /opt/alpaca-stream/venv/lib/python3.11/site-packages/alpaca/data/live/websocket.py" > check_close_method_log.txt 2>&1
exit /b 0
