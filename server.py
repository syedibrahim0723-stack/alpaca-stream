"""
Alpaca Live News — WebSocket Relay Server
-----------------------------------------
1. Connects to Alpaca NewsDataStream (real-time)
2. Classifies each article by importance (High / Medium / Low)
3. Broadcasts JSON to all connected browser clients via ws://localhost:8765

Usage:
    pip install -r requirements.txt
    python server.py
"""

import asyncio
import json
import os
import threading
from datetime import datetime

import websockets
from dotenv import load_dotenv
from alpaca.data.live import NewsDataStream

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY    = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_API_SECRET")
WS_HOST    = "localhost"
WS_PORT    = 8765

# ── Importance Keywords ───────────────────────────────────────────────────────
HIGH_KEYWORDS = [
    "earnings", "eps", "beat", "miss", "fda", "approval", "approved",
    "rejected", "merger", "acquisition", "acquired", "buyout", "takeover",
    "bankruptcy", "bankrupt", "chapter 11", "recall", "sec", "subpoena",
    "guidance", "restatement", "fomc", "federal reserve", "rate decision",
    "insider trading", "short squeeze", "delisted", "halt", "investigation",
    "indictment", "settlement", "class action", "revenue miss", "profit warning",
]

MEDIUM_KEYWORDS = [
    "upgrade", "downgrade", "price target", "analyst", "outperform",
    "underperform", "neutral", "buy rating", "sell rating",
    "partnership", "collaboration", "launch", "contract", "awarded",
    "forecast", "outlook", "dividend", "buyback", "repurchase",
    "ipo", "offering", "secondary", "raises",
]

def classify(headline: str, summary: str = "") -> str:
    text = (headline + " " + (summary or "")).lower()
    for kw in HIGH_KEYWORDS:
        if kw in text:
            return "high"
    for kw in MEDIUM_KEYWORDS:
        if kw in text:
            return "medium"
    return "low"

# ── State ─────────────────────────────────────────────────────────────────────
connected_clients: set = set()
main_loop: asyncio.AbstractEventLoop | None = None

# ── Broadcast ─────────────────────────────────────────────────────────────────
async def broadcast(payload: str):
    dead = set()
    for client in connected_clients.copy():
        try:
            await client.send(payload)
        except Exception:
            dead.add(client)
    connected_clients.difference_update(dead)

# ── Article formatter ─────────────────────────────────────────────────────────
def format_article(data) -> dict:
    headline = getattr(data, "headline", "") or ""
    summary  = getattr(data, "summary",  "") or ""
    created  = getattr(data, "created_at", None)
    symbols  = getattr(data, "symbols",   []) or []

    return {
        "id":         getattr(data, "id", str(datetime.utcnow().timestamp())),
        "headline":   headline,
        "summary":    summary,
        "source":     getattr(data, "source", "Unknown") or "Unknown",
        "url":        getattr(data, "url",    "") or "",
        "symbols":    symbols,
        "created_at": created.isoformat() if created else datetime.utcnow().isoformat(),
        "importance": classify(headline, summary),
    }

# ── Alpaca stream (runs in background thread) ──────────────────────────────────
def start_alpaca_stream():
    async def _run():
        stream = NewsDataStream(API_KEY, API_SECRET)

        async def handler(data):
            article = format_article(data)
            print(f"[{article['importance'].upper():6}] {article['headline'][:80]}")
            if main_loop:
                asyncio.run_coroutine_threadsafe(
                    broadcast(json.dumps(article)), main_loop
                )

        stream.subscribe_news(handler, "*")
        await stream._run_forever()

    asyncio.run(_run())

# ── WebSocket server (browser clients) ────────────────────────────────────────
async def ws_handler(websocket):
    connected_clients.add(websocket)
    print(f"✅ Browser connected   | clients: {len(connected_clients)}")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        print(f"❌ Browser disconnected | clients: {len(connected_clients)}")

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    if not API_KEY or not API_SECRET:
        print("❌  Missing ALPACA_API_KEY or ALPACA_API_SECRET in .env")
        return

    # Alpaca stream in background thread
    thread = threading.Thread(target=start_alpaca_stream, daemon=True)
    thread.start()
    print("🔌  Alpaca news stream connecting...")

    async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
        print(f"🚀  WebSocket server → ws://{WS_HOST}:{WS_PORT}")
        print("📰  Open app.html in your browser\n")
        await asyncio.Future()   # run forever

if __name__ == "__main__":
    asyncio.run(main())
