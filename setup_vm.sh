#!/bin/bash
# ── Alpaca Stream — VM setup script (run this ONCE on the GCP VM) ─────────────
# Usage: bash setup_vm.sh

set -e
APP_DIR="/opt/alpaca-stream"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Alpaca Stream — VM Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/5] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git

# ── 2. App directory ──────────────────────────────────────────────────────────
echo "[2/5] Creating app directory at $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# ── 3. Python venv + dependencies ─────────────────────────────────────────────
echo "[3/5] Setting up Python virtual environment..."
python3 -m venv $APP_DIR/venv
$APP_DIR/venv/bin/pip install --upgrade pip -q
$APP_DIR/venv/bin/pip install \
    alpaca-py websockets python-dotenv \
    "fastapi>=0.111.0" "uvicorn[standard]>=0.30.0" \
    pytz requests -q
echo "✅ Dependencies installed"

# ── 4. Systemd service ────────────────────────────────────────────────────────
echo "[4/5] Installing systemd service..."
sudo tee /etc/systemd/system/alpaca-stream.service > /dev/null <<EOF
[Unit]
Description=Alpaca Live Stream
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --ws-ping-interval 0 --ws-ping-timeout 0
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable alpaca-stream
echo "✅ Service installed and enabled"

# ── 5. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Done! Next steps:"
echo "  1. Copy your app files:  (run deploy.bat on your Windows machine)"
echo "  2. Copy your .env file to $APP_DIR/.env"
echo "  3. Start the service:    sudo systemctl start alpaca-stream"
echo "  4. Check logs:           sudo journalctl -u alpaca-stream -f"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
