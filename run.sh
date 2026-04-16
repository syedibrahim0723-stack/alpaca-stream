#!/bin/bash
# ── Alpaca Live Stream — one-click launcher ───────────────────────────────────

cd "$(dirname "$0")"

echo "⚡ Alpaca Live Stream"
echo "─────────────────────"

# Check .env
if [ ! -f .env ]; then
  echo "❌  .env file not found — create one with ALPACA_API_KEY, ALPACA_SECRET_KEY, XAI_API_KEY"
  exit 1
fi

# Install / update dependencies quietly
echo "📦  Checking dependencies…"
pip install -r requirements.txt -q

# Open browser after short delay (works on mac & linux)
(sleep 2 && (open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null)) &

echo "🚀  Starting server at http://localhost:8000"
echo "    Press Ctrl+C to stop"
echo "─────────────────────"

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
