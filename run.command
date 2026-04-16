#!/bin/bash
# ── Alpaca Live Stream — double-click launcher (macOS) ────────────────────────

# Move to the folder this script lives in
cd "$(dirname "$0")"

echo "⚡ Alpaca Live Stream"
echo "─────────────────────"

# Check .env
if [ ! -f .env ]; then
  echo ""
  echo "❌  .env file not found!"
  echo "    Create a file named .env in this folder with:"
  echo "      ALPACA_API_KEY=your_key"
  echo "      ALPACA_SECRET_KEY=your_secret"
  echo "      XAI_API_KEY=your_xai_key"
  echo ""
  read -p "Press Enter to close…"
  exit 1
fi

# Install / update dependencies
echo "📦  Checking dependencies…"
pip install alpaca-py websockets python-dotenv fastapi "uvicorn[standard]" pytz requests -q
echo "✅  Dependencies ready"
echo ""

# Open browser after a short delay
(sleep 2 && open http://localhost:8000) &

echo "🚀  Server starting at http://localhost:8000"
echo "    Press Ctrl+C to stop"
echo "─────────────────────"

uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Keep terminal open if server crashes so you can read the error
echo ""
echo "⚠️  Server stopped."
read -p "Press Enter to close…"
