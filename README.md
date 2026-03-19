# ⚡ Alpaca Live Trade Stream

A real-time stock trade dashboard powered by Alpaca's Paper Trading API.

- **Backend**: FastAPI + WebSocket, streaming all trades via `StockDataStream`
- **Frontend**: Dark dashboard with live scrolling trade table + Chart.js price chart
- **Data window**: Only the last **5 minutes** of trades are kept in memory

---

## Quick Start

### 1. Clone / set up the repo

```bash
git clone https://github.com/YOUR_USERNAME/alpaca-stream.git
cd alpaca-stream
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure your API keys

Copy `.env.example` to `.env` and fill in your Alpaca Paper credentials:

```bash
cp .env.example .env
```

```
ALPACA_API_KEY=your_paper_api_key_here
ALPACA_SECRET_KEY=your_paper_secret_key_here
```

> ⚠️ `.env` is in `.gitignore` — your keys will **never** be committed to GitHub.

### 4. Run the app

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at: **http://localhost:8000**

---

## Architecture

```
Alpaca WebSocket (SIP)
        │
   handle_trade()          ← async, runs in Alpaca's event loop (thread)
        │
   thread-safe Queue
        │
   queue_processor()       ← FastAPI background task, runs every 20 ms
        │
   ┌────┴──────────────────┐
   │  trades_store (deque) │  ← rolling buffer, last 5 min only
   └───────────────────────┘
        │
   WebSocket broadcast → browser
```

## Notes

- Uses **SIP** (consolidated tape) feed. If you only have an IEX entitlement, change `DataFeed.SIP` → `DataFeed.IEX` in `main.py`.
- Subscribes to **all symbols** (`*`). Expect high throughput during market hours (thousands of trades/sec).
- `trades_store` holds at most 200 000 records. The 5-minute cleanup runs automatically.
- The chart shows prices for whichever symbol you select in the dropdown.

---

## Pushing to GitHub

```bash
git init
git add .
git commit -m "feat: alpaca live trade stream"

# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/alpaca-stream.git
git branch -M main
git push -u origin main
```

> ✅ `.env` is gitignored — only `.env.example` (with placeholders) gets pushed.
