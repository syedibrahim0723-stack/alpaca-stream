"""
Alpaca Live Trade Stream — FastAPI backend
- Streams all trades via Alpaca StockDataStream (SIP feed)
- Aggregates ticks into 1-min OHLCV bars (whole day)
- Streams news via NewsDataStream + 7-day history via NewsClient REST
- Broadcasts trades/news to WebSocket; serves /bars and /news REST endpoints
"""

import asyncio
import json
import os
import re
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Queue

import pytz
import requests as req_lib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from alpaca.data.enums import DataFeed
from alpaca.data.live.stock import StockDataStream
from alpaca.data.live.news import NewsDataStream
from alpaca.data.historical import StockHistoricalDataClient, NewsClient
from alpaca.data.requests import StockBarsRequest, NewsRequest
from alpaca.data.timeframe import TimeFrame

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY    = os.getenv("ALPACA_API_KEY", "")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")

if not API_KEY or not SECRET_KEY:
    raise RuntimeError(
        "Missing API keys. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
    )

ET = pytz.timezone("America/New_York")
BAD_CONDITIONS = {"U", "W", "Z"}   # keep T (extended hours) and V (contingent)

# ── xAI / Grok config ─────────────────────────────────────────────────────────
XAI_KEY   = os.getenv("XAI_API_KEY", "")
XAI_URL   = "https://api.x.ai/v1/responses"
XAI_HDR   = {"Content-Type": "application/json", "Authorization": f"Bearer {XAI_KEY}"}
XAI_MODEL = "grok-4-fast-non-reasoning"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Alpaca Trade Stream")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── In-memory stores ──────────────────────────────────────────────────────────
trades_store:    deque           = deque(maxlen=200_000)
minute_bars:     dict[str, dict] = {}   # sym → {min_ts_ms: {t,o,h,l,c,v}}
news_store:      dict[str, list] = {}   # sym → [article, ...] most-recent-first
twitter_cache:   dict[str, dict] = {}   # sym → {summary, tweets, raw, fetched_at}  — resets on restart

# ── Queues ────────────────────────────────────────────────────────────────────
trade_queue: Queue = Queue(maxsize=100_000)
news_queue:  Queue = Queue(maxsize=10_000)

# ── WebSocket clients ─────────────────────────────────────────────────────────
clients: set[WebSocket] = set()


# ── Helpers ───────────────────────────────────────────────────────────────────
def to_utc(ts) -> datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def serialize(trade: dict) -> dict:
    return {k: v for k, v in trade.items() if not k.startswith("_")}


def get_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=5)


def recent_trades(n: int = 2000) -> list[dict]:
    cutoff = get_cutoff()
    return [serialize(t) for t in trades_store if t["_ts"] >= cutoff][-n:]


def cleanup() -> None:
    cutoff = get_cutoff()
    while trades_store and trades_store[0]["_ts"] < cutoff:
        trades_store.popleft()


def aggregate_tick(sym: str, price: float, size: int, ts_ms: int) -> None:
    """Roll a single tick into the per-symbol 1-min OHLCV bar."""
    min_key = (ts_ms // 60_000) * 60_000
    bars = minute_bars.setdefault(sym, {})
    if min_key not in bars:
        bars[min_key] = {"t": min_key, "o": price, "h": price,
                         "l": price, "c": price, "v": size}
    else:
        b = bars[min_key]
        if price > b["h"]: b["h"] = price
        if price < b["l"]: b["l"] = price
        b["c"] = price
        b["v"] += size


def article_to_dict(a) -> dict:
    """Works for both News model objects and raw dicts (from live stream cache)."""
    if isinstance(a, dict):
        return a
    return {
        "id":         str(getattr(a, "id", "")),
        "headline":   getattr(a, "headline", "") or "",
        "summary":    getattr(a, "summary",  "") or "",
        "url":        getattr(a, "url",      "") or "",
        "source":     getattr(a, "source",   "") or "",
        "created_at": a.created_at.isoformat() if getattr(a, "created_at", None) else "",
        "symbols":    list(getattr(a, "symbols", []) or []),
    }


# ── Trade stream ──────────────────────────────────────────────────────────────
async def handle_trade(data) -> None:
    if len(data.symbol) > 4:
        return
    if data.conditions and any(c in BAD_CONDITIONS for c in data.conditions):
        return

    ts = to_utc(data.timestamp)
    ms = int(ts.timestamp() * 1000)

    aggregate_tick(data.symbol, float(data.price), int(data.size or 0), ms)

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
        pass


def run_trade_stream() -> None:
    stream = StockDataStream(API_KEY, SECRET_KEY, feed=DataFeed.SIP)
    stream.subscribe_trades(handle_trade, "*")
    stream.run()


# ── News stream ───────────────────────────────────────────────────────────────
async def handle_news(data) -> None:
    article = article_to_dict(data)
    # Store per-symbol (and under "*" for market-wide news)
    targets = article["symbols"] if article["symbols"] else ["*"]
    for sym in targets:
        bucket = news_store.setdefault(sym, [])
        bucket.insert(0, article)
        if len(bucket) > 200:
            del bucket[200:]
    try:
        news_queue.put_nowait({"type": "news_item", "data": article})
    except Exception:
        pass


def run_news_stream() -> None:
    try:
        nstream = NewsDataStream(API_KEY, SECRET_KEY)
        nstream.subscribe_news(handle_news, "*")
        nstream.run()
    except Exception as exc:
        print(f"[news-stream] failed to start: {exc}")


# ── WebSocket broadcast ───────────────────────────────────────────────────────
async def broadcast(msg: str) -> None:
    dead = set()
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


async def queue_processor() -> None:
    """Drain trade + news queues every 20 ms and push to all WebSocket clients."""
    while True:
        # ── trades ────────────────────────────────────────────────────────────
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
                await broadcast(json.dumps([serialize(t) for t in batch]))

        # ── news ──────────────────────────────────────────────────────────────
        news_batch = []
        try:
            while len(news_batch) < 20:
                news_batch.append(news_queue.get_nowait())
        except Empty:
            pass
        for item in news_batch:
            if clients:
                await broadcast(json.dumps(item))

        await asyncio.sleep(0.02)


# ── xAI / Grok helpers (sync — called via asyncio.to_thread) ─────────────────
def _xai_post(payload: dict, timeout: int = 45) -> str:
    """POST to xAI Responses API and return the concatenated output_text."""
    r = req_lib.post(XAI_URL, headers=XAI_HDR, json=payload, timeout=timeout)
    r.raise_for_status()
    text = ""
    for item in r.json().get("output", []):
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    text += block.get("text", "")
    return text.strip()


def _search_tweets(sym: str) -> str:
    """Fetch 5 most recent X posts about $SYM from the last 24 h."""
    return _xai_post({
        "model": XAI_MODEL,
        "stream": False,
        "temperature": 0,
        "tools": [{"type": "x_search"}],
        "input": [
            {
                "role": "system",
                "content": (
                    "You have real-time access to X via x_search. "
                    "Always use the tool. Never fabricate posts. "
                    "Format each post exactly as:\n"
                    "### [n]\n"
                    "**User**: @handle\n"
                    "**Content**: full tweet text\n"
                    "**Time**: timestamp\n"
                    "**Link**: url"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Search X for the 5 most recent trading-relevant posts about ${sym} "
                    f"from the last 24 hours. Include posts about price moves, catalysts, "
                    f"earnings, news, or notable analyst comments."
                ),
            },
        ],
    }, timeout=50)


def _summarize_tweets(sym: str, raw: str) -> str:
    """Summarize tweet raw text into a 2-3 sentence trading insight."""
    return _xai_post({
        "model": XAI_MODEL,
        "stream": False,
        "temperature": 0,
        "tools": [],
        "input": [
            {
                "role": "system",
                "content": "You are a concise trading assistant. Be factual, brief, and specific.",
            },
            {
                "role": "user",
                "content": (
                    f"Recent X posts about ${sym}:\n\n{raw}\n\n"
                    f"In 2-3 sentences summarise: what traders are discussing, "
                    f"the overall sentiment (bullish / bearish / mixed), "
                    f"and any specific catalysts or price targets mentioned."
                ),
            },
        ],
    }, timeout=25)


def _parse_tweets(raw: str, sym: str) -> list[dict]:
    """Parse ### blocks from xAI response into tweet dicts."""
    tweets = []
    blocks = re.split(r'\n(?=###)', raw.strip())
    for block in blocks:
        if not block.strip().startswith('###'):
            continue
        def field(name):
            m = re.search(rf'\*\*{name}:?\*\*:?\s*(.+?)(?=\n\s*\*\*|\Z)', block,
                          re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else ""
        u = re.search(r'\*\*User(?:name)?:?\*\*:?\s*(@[\w]+)', block)
        tweets.append({
            "user":    u.group(1) if u else f"${sym}",
            "content": field("Content"),
            "time":    field("Time"),
            "link":    field("Link"),
        })
    return [t for t in tweets if t["content"]]


# ── REST: X / Twitter sentiment for a symbol (first alert only) ───────────────
@app.get("/twitter/{sym}")
async def get_twitter(sym: str) -> JSONResponse:
    # Return cached result if already fetched today
    if sym in twitter_cache:
        return JSONResponse({"sym": sym, "cached": True, **twitter_cache[sym]})
    try:
        raw     = await asyncio.to_thread(_search_tweets, sym)
        summary = await asyncio.to_thread(_summarize_tweets, sym, raw) if raw else "No recent posts found."
        tweets  = _parse_tweets(raw, sym)
        data    = {
            "summary":    summary,
            "tweets":     tweets,
            "raw":        raw,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        twitter_cache[sym] = data
        return JSONResponse({"sym": sym, "cached": False, **data})
    except Exception as exc:
        # Don't cache on error — allow retry
        return JSONResponse({"sym": sym, "summary": "", "tweets": [], "raw": "",
                             "error": str(exc)})


# ── REST: full-day 1-min bars for a symbol ────────────────────────────────────
@app.get("/bars/{sym}")
async def get_bars(sym: str) -> JSONResponse:
    try:
        hclient   = StockHistoricalDataClient(API_KEY, SECRET_KEY)
        now_et    = datetime.now(ET)
        # Start from 4 AM ET (pre-market open) today
        start_et  = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
        start_utc = start_et.astimezone(timezone.utc)

        req  = StockBarsRequest(symbol_or_symbols=sym,
                                timeframe=TimeFrame.Minute,
                                start=start_utc)
        resp = hclient.get_stock_bars(req)

        bar_map: dict[int, dict] = {}
        try:
            sym_bars = resp[sym]
        except (KeyError, TypeError):
            sym_bars = []

        for bar in sym_bars:
            ts_ms = int(bar.timestamp.timestamp() * 1000)
            bar_map[ts_ms] = {
                "t": ts_ms,
                "o": float(bar.open),
                "h": float(bar.high),
                "l": float(bar.low),
                "c": float(bar.close),
                "v": int(bar.volume),
            }

        # Merge with live bars (live wins for the current / recent minute)
        for ts_ms, lb in minute_bars.get(sym, {}).items():
            bar_map[ts_ms] = lb

        merged = sorted(bar_map.values(), key=lambda b: b["t"])
        return JSONResponse({"sym": sym, "bars": merged})
    except Exception as exc:
        return JSONResponse({"sym": sym, "bars": [], "error": str(exc)})


# ── REST: 7-day news for a symbol ─────────────────────────────────────────────
@app.get("/news/{sym}")
async def get_news_route(sym: str) -> JSONResponse:
    try:
        nclient  = NewsClient(API_KEY, SECRET_KEY)
        start_dt = datetime.now(timezone.utc) - timedelta(days=7)

        # symbols = comma-separated string; resp.data["news"] is the article list
        req  = NewsRequest(symbols=sym, start=start_dt, limit=50)
        resp = nclient.get_news(req)

        raw_articles = resp.data.get("news", []) if hasattr(resp, "data") else []
        articles = [article_to_dict(a) for a in raw_articles]

        # Merge with live-streamed news cached on the backend
        seen = {a["id"] for a in articles}
        for ln in news_store.get(sym, []):
            if ln["id"] not in seen:
                articles.append(ln)
                seen.add(ln["id"])

        articles.sort(key=lambda a: a["created_at"], reverse=True)
        return JSONResponse({"sym": sym, "articles": articles[:100]})
    except Exception as exc:
        return JSONResponse({"sym": sym, "articles": [], "error": str(exc)})


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(queue_processor())
    threading.Thread(target=run_trade_stream, daemon=True).start()
    threading.Thread(target=run_news_stream,  daemon=True).start()


# ── Serve frontend ────────────────────────────────────────────────────────────
@app.get("/")
async def root() -> HTMLResponse:
    html = Path("static/index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/stats")
async def api_stats():
    trades = recent_trades()
    return {
        "trade_count":  len(trades),
        "symbol_count": len({t["symbol"] for t in trades}),
        "queue_size":   trade_queue.qsize(),
        "clients":      len(clients),
        "bar_syms":     len(minute_bars),
        "news_syms":    len(news_store),
    }


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "init", "data": recent_trades()}))
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"ping"}')
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        clients.discard(ws)
