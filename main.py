"""
Alpaca Live Trade Stream — FastAPI backend
- Streams all trades via Alpaca StockDataStream (SIP feed)
- Keeps only the last 5 minutes of data in memory
- Broadcasts trades to all WebSocket clients in real-time
- Serves the frontend from static/index.html
"""

import asyncio
import json
import os
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Queue

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from alpaca.data.enums import DataFeed
from alpaca.data.live.stock import StockDataStream

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY    = os.getenv("ALPACA_API_KEY", "")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
MAX_AGE_SECONDS = 300  # 5 minutes

if not API_KEY or not SECRET_KEY:
    raise RuntimeError(
        "Missing API keys. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
    )

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Alpaca Trade Stream")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── State ────────────────────────────────────────────────────────────────────
trades_store: deque        = deque(maxlen=200_000)   # rolling buffer
trade_queue:  Queue        = Queue(maxsize=100_000)  # thread-safe bridge
clients:      set[WebSocket] = set()


# ── Helpers ──────────────────────────────────────────────────────────────────
def get_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=MAX_AGE_SECONDS)


def cleanup() -> None:
    """Remove trades older than MAX_AGE_SECONDS from the front of the deque."""
    cutoff = get_cutoff()
    while trades_store and trades_store[0]["_ts"] < cutoff:
        trades_store.popleft()


def to_utc(ts) -> datetime:
    """Convert any timestamp to a UTC-aware datetime."""
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def serialize(trade: dict) -> dict:
    """Strip internal fields (prefixed _) before sending to clients."""
    return {k: v for k, v in trade.items() if not k.startswith("_")}


def recent_trades() -> list[dict]:
    cutoff = get_cutoff()
    return [serialize(t) for t in trades_store if t["_ts"] >= cutoff]


# ── Alpaca stream (runs in its own thread + event loop) ──────────────────────
async def handle_trade(data) -> None:
    # ── Filter: only short tickers (≤ 4 chars, e.g. AAPL, TSLA, not GOOGL) ──
    if len(data.symbol) > 4:
        return

    ts = to_utc(data.timestamp)
    ms = int(ts.timestamp() * 1000)
    trade = {
        "symbol": data.symbol,
        "price":  float(data.price),
        "size":   int(data.size or 0),
        "time":   ts.strftime("%H:%M:%S.") + f"{ts.microsecond // 1000:03d}",
        "ts_ms":  ms,
        "_ts":    ts,
    }
    try:
        trade_queue.put_nowait(trade)
    except Exception:
        pass  # drop when queue is full (extreme load)


def run_stream() -> None:
    stream = StockDataStream(API_KEY, SECRET_KEY, feed=DataFeed.SIP)
    stream.subscribe_trades(handle_trade, "*")
    stream.run()


# ── FastAPI background task: drain queue → store + broadcast ─────────────────
async def broadcast(msg: str) -> None:
    dead = set()
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


async def queue_processor() -> None:
    """Drain up to 300 trades every 20 ms and broadcast them."""
    while True:
        batch = []
        try:
            while len(batch) < 300:
                batch.append(trade_queue.get_nowait())
        except Empty:
            pass

        if batch:
            cleanup()
            for t in batch:
                trades_store.append(t)
            if clients:
                payload = json.dumps([serialize(t) for t in batch])
                await broadcast(payload)

        await asyncio.sleep(0.02)   # 50 Hz


# ── Lifecycle ────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    threading.Thread(target=run_stream, daemon=True).start()
    asyncio.create_task(queue_processor())


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/")
async def root() -> HTMLResponse:
    html = Path("static/index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/trades")
async def api_trades():
    return recent_trades()


@app.get("/api/stats")
async def api_stats():
    trades = recent_trades()
    symbols = {t["symbol"] for t in trades}
    return {
        "trade_count":    len(trades),
        "symbol_count":   len(symbols),
        "window_minutes": MAX_AGE_SECONDS // 60,
        "queue_size":     trade_queue.qsize(),
        "clients":        len(clients),
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    try:
        # Send up to 2 000 recent trades as init payload
        init = recent_trades()[-2000:]
        await ws.send_text(json.dumps({"type": "init", "data": init}))
        # Keep-alive loop
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"ping"}')
    except (WebSocketDisconnect, Exception):
        clients.discard(ws)
