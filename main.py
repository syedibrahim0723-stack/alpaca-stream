"""
Alpaca Live Trade Stream — FastAPI backend
- Streams all trades via Alpaca StockDataStream (SIP feed)
- Aggregates ticks into 1-min OHLCV bars (whole day)
- Streams news via NewsDataStream + 7-day history via NewsClient REST
- Broadcasts trades/news to WebSocket; serves /bars and /news REST endpoints

Optimisations applied:
  [1] Thread-safety: aggregate_tick moved into queue_processor (event-loop only)
      news_store guarded by _news_lock for cross-thread writes
  [2] Singleton StockHistoricalDataClient / NewsClient — no per-request instantiation
      Blocking HTTP calls wrapped in asyncio.to_thread
  [3] news_store uses deque(maxlen=200) per symbol — O(1) inserts
  [4] broadcast() fans out concurrently with asyncio.gather
  [5] cleanup() throttled to once every 60 seconds
  [6] twitter_cache has a 1-hour TTL
  [7] Alert file I/O is async via asyncio.to_thread
"""

import asyncio
import csv
import json
import os
import re
import sqlite3
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Queue

# ── Windows: force SelectorEventLoop ─────────────────────────────────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytz
import requests as req_lib
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
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
BAD_CONDITIONS = {"U", "W", "Z"}

# ── Universe files ─────────────────────────────────────────────────────────────
UNIVERSE_CSV       = Path(__file__).parent / "stock_universe_full.csv"
YESTERDAY_VOL_FILE = Path(__file__).parent / "yesterday_volume.json"

# ── Cap-tier thresholds for volume spike detection ─────────────────────────────
# These are passed to the frontend via /universe/meta so the JS uses real market
# caps instead of a price proxy.
CAP_TIERS = [
    {"name": "nano",  "max_cap": 300_000_000,    "spike": 20, "min_vol":  5_000, "delta_pct": 8.0},
    {"name": "small", "max_cap": 2_000_000_000,  "spike": 15, "min_vol": 10_000, "delta_pct": 5.0},
    {"name": "mid",   "max_cap": 10_000_000_000, "spike": 10, "min_vol": 15_000, "delta_pct": 3.0},
    # "large" / "mega" won't appear — excluded entirely
]
_UNKNOWN_TIER = {"name": "unknown", "spike": 10, "min_vol": 10_000, "delta_pct": 3.0}


def _cap_tier(market_cap) -> dict:
    if market_cap is None:
        return _UNKNOWN_TIER
    for t in CAP_TIERS:
        if market_cap < t["max_cap"]:
            return t
    return _UNKNOWN_TIER   # shouldn't reach here — large-caps are excluded


# ── Dynamic exclusion + metadata (populated by load_universe()) ────────────────
EXCLUDE_SYMS:   set[str]        = set()   # all ETFs + top-100 stocks by market cap
SYM_META:       dict[str, dict] = {}      # sym → {market_cap, cap_tier, spike_thresh, …}
YESTERDAY_TOP50: set[str]       = set()   # top-50 by dollar volume from yesterday

# ── Fallback hardcoded exclude (used if CSV not found yet) ────────────────────
_FALLBACK_EXCLUDE: frozenset = frozenset({
    "AAPL","MSFT","NVDA","GOOGL","GOOG","AMZN","META","TSLA","AVGO","LLY",
    "BRK.A","BRK.B","WMT","JPM","V","UNH","XOM","MA","ORCL","COST",
    "HD","JNJ","PG","ABBV","MRK","CVX","AMD","NFLX","CRM","PEP",
    "KO","ADBE","ACN","TMO","LIN","MCD","BAC","GE","WFC","CSCO",
    "ABT","PM","NEE","TXN","DHR","IBM","QCOM","SPGI","RTX","LOW",
    "HON","UNP","CAT","GS","AMGN","BKNG","INTU","ISRG","VRTX","SYK",
    "AXP","BLK","T","VZ","CMCSA","C","USB","MMM","DE","ADP",
    "SPY","QQQ","IWM","DIA","VOO","VTI","GLD","TLT","HYG","LQD",
    "EEM","EFA","VXX","SQQQ","TQQQ","UVXY","IBIT","SLV","USO","GDX",
    "XLF","XLE","XLK","XLV","XLU","XLP","XLRE","XLI","XLB","XLY","XLC",
    "ARKK","ARKW","ARKF","ARKG","ARKQ",
    "SDS","SPXU","SDOW","UDOW","SPXL","LABU","LABD","SOXL","SOXS",
})


def load_universe() -> None:
    """
    Read stock_universe_full.csv and build:
      - EXCLUDE_SYMS  : all ETFs + pre-flagged exclusions + top 100 stocks by market cap
      - SYM_META      : per-symbol metadata (market cap, sector, name)

    CSV column notes:
      - Market cap column is ' market_cap ' (with surrounding spaces)
      - Values are formatted like ' 64,227,090 ' (commas, spaces, no $)
      - is_etf / is_stock / is_excluded are 'TRUE'/'FALSE' strings
      - is_excluded already flags warrants, preferred shares, special securities
    """
    global EXCLUDE_SYMS, SYM_META

    if not UNIVERSE_CSV.exists():
        EXCLUDE_SYMS = set(_FALLBACK_EXCLUDE) | _load_etf_cache()
        print(f"[universe] ⚠  {UNIVERSE_CSV.name} not found — using fallback list "
              f"({len(EXCLUDE_SYMS)} symbols). Run: python ticker_universe.py")
        return

    import re as _re

    rows: list[dict] = []
    with open(UNIVERSE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    def _parse_cap(v) -> float | None:
        """Parse ' 64,227,090 ' or ' 4,775,193,000,000 ' → float."""
        if not v:
            return None
        cleaned = _re.sub(r"[\$,\s]", "", str(v))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    def _truthy(v: str) -> bool:
        return str(v).strip().upper() in ("TRUE", "1", "YES")

    # ── Build exclusion set ───────────────────────────────────────────────────
    # 1. All ETFs (is_etf == TRUE)
    etf_syms = {r["ticker"].strip() for r in rows if _truthy(r.get("is_etf", ""))}

    # 2. Pre-flagged exclusions (warrants, preferreds, special instruments)
    pre_excluded = {r["ticker"].strip() for r in rows if _truthy(r.get("is_excluded", ""))}

    # 3. Top 100 tradeable stocks by market cap
    stocks = [r for r in rows if _truthy(r.get("is_stock", ""))]
    for r in stocks:
        r["_cap"] = _parse_cap(r.get(" market_cap ", r.get("market_cap", "")))
    stocks_with_cap = sorted(
        (r for r in stocks if r["_cap"] is not None),
        key=lambda r: r["_cap"], reverse=True,
    )
    top100_syms = {r["ticker"].strip() for r in stocks_with_cap[:100]}

    # 4. Merge with ETF cache from background fetcher
    EXCLUDE_SYMS = etf_syms | pre_excluded | top100_syms | _load_etf_cache()

    # ── Build per-symbol metadata for tradeable symbols ───────────────────────
    SYM_META = {}
    for r in rows:
        sym = r.get("ticker", "").strip().upper()
        if not sym or sym in EXCLUDE_SYMS:
            continue
        # Only include actual stocks (skip REITs, BDCs, funds etc. from SYM_META
        # but they remain in the stream — just won't have cap metadata)
        cap = _parse_cap(r.get(" market_cap ", r.get("market_cap", "")))
        SYM_META[sym] = {
            "market_cap": cap,
            "sector":     r.get("sector", "").strip(),
            "name":       r.get("company_name", "").strip(),
        }

    print(
        f"[universe] ✅ {len(rows):,} instruments — "
        f"{len(etf_syms):,} ETFs + {len(pre_excluded)} pre-excluded + "
        f"{len(top100_syms)} top-100 stocks = {len(EXCLUDE_SYMS):,} excluded | "
        f"{len(SYM_META):,} symbols with metadata"
    )


# ── ETF cache file — written by _fetch_etf_tickers_sync, read on subsequent startups ──
ETF_CACHE_FILE = Path(__file__).parent / "etf_tickers.json"


def _fetch_etf_tickers_sync() -> set[str]:
    """
    Fetch all ETF tickers from NASDAQ's ETF screener endpoint (no auth required).
    Returns a set of uppercase ticker strings.  Updates ETF_CACHE_FILE as a side-effect
    so the next startup is instant even if the network is unavailable.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    tickers: set[str] = set()

    # ── NASDAQ ETF screener (covers SPY, QQQ, IVV, and most NYSE Arca ETFs) ──
    try:
        r = req_lib.get(
            "https://api.nasdaq.com/api/screener/etf",
            headers=headers,
            params={"limit": 25, "offset": 0, "download": "true"},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("data", {}).get("data", {}).get("rows", []) or \
               data.get("data", {}).get("rows", [])
        tickers |= {str(row.get("symbol", "")).upper().strip()
                    for row in rows if row.get("symbol")}
        print(f"[etf-fetch] NASDAQ ETF screener → {len(tickers)} ETFs")
    except Exception as exc:
        print(f"[etf-fetch] ⚠ NASDAQ ETF screener failed: {exc}")

    # ── etfdb.com screener (most complete — catches leveraged/inverse/thematic) ──
    try:
        all_rows = []
        page = 1
        while True:
            resp = req_lib.post(
                "https://etfdb.com/api/screener/",
                json={"page": page, "per_page": 250, "only": ["meta", "data"]},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                         "Referer": "https://etfdb.com/screener/",
                         "X-Requested-With": "XMLHttpRequest"},
                timeout=20,
            )
            resp.raise_for_status()
            d = resp.json()
            rows = d.get("data", [])
            if not rows:
                break
            all_rows.extend(rows)
            total_pages = d.get("meta", {}).get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.4)

        def _sym(row):
            v = row.get("symbol", "")
            return (v.get("text") or v.get("value") or v) if isinstance(v, dict) else v

        etfdb_syms = {str(_sym(r)).upper().strip() for r in all_rows if _sym(r)}
        tickers |= etfdb_syms
        print(f"[etf-fetch] etfdb screener → {len(etfdb_syms)} ETFs  (total so far: {len(tickers)})")
    except Exception as exc:
        print(f"[etf-fetch] ⚠ etfdb screener failed: {exc}")

    if tickers:
        ETF_CACHE_FILE.write_text(
            json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "tickers": sorted(tickers)}),
            encoding="utf-8",
        )
        print(f"[etf-fetch] ✅ {len(tickers):,} ETF tickers cached → {ETF_CACHE_FILE.name}")

    return tickers


def _load_etf_cache() -> set[str]:
    """Read previously cached ETF tickers (used on startup before async fetch completes)."""
    if not ETF_CACHE_FILE.exists():
        return set()
    try:
        data = json.loads(ETF_CACHE_FILE.read_text(encoding="utf-8"))
        syms = set(data.get("tickers", []))
        print(f"[etf-cache] loaded {len(syms):,} ETF tickers from cache (ts: {data.get('ts','?')})")
        return syms
    except Exception as exc:
        print(f"[etf-cache] ⚠ failed to read: {exc}")
        return set()


async def _refresh_etf_exclude() -> None:
    """
    Background task: fetch fresh ETF list from NASDAQ + etfdb, then add to EXCLUDE_SYMS.
    Runs once at startup (in background so server starts immediately), then daily at 07:00 ET.
    """
    refreshed_date: str | None = None
    first_run = True
    while True:
        now_et = datetime.now(ET)
        today  = now_et.strftime("%Y-%m-%d")
        # Run immediately on first startup, then daily at 07:00 ET
        if first_run or (now_et.hour == 7 and now_et.minute == 0 and refreshed_date != today):
            first_run = False
            refreshed_date = today
            try:
                new_etfs = await asyncio.to_thread(_fetch_etf_tickers_sync)
                if new_etfs:
                    before = len(EXCLUDE_SYMS)
                    EXCLUDE_SYMS.update(new_etfs)
                    print(f"[etf-refresh] exclude set: {before} → {len(EXCLUDE_SYMS):,} (+{len(EXCLUDE_SYMS)-before} ETFs)")
            except Exception as exc:
                print(f"[etf-refresh] ⚠ refresh failed: {exc}")
        await asyncio.sleep(60)


YF_CACHE_FILE = Path(__file__).parent / "yf_marketcap_cache.json"


def _enrich_with_yfinance() -> None:
    """
    For every symbol in SYM_META that has no market cap, fetch it from Yahoo Finance.
    Results are cached in yf_marketcap_cache.json — only missing symbols are fetched
    so subsequent calls are fast.  Runs in a background thread at startup.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("[yf] yfinance not installed — run: pip install yfinance")
        return

    # Load existing cache
    cache: dict[str, float | None] = {}
    if YF_CACHE_FILE.exists():
        try:
            cache = json.loads(YF_CACHE_FILE.read_text(encoding="utf-8"))
            print(f"[yf] loaded {len(cache):,} cached market caps")
        except Exception as exc:
            print(f"[yf] ⚠ cache read failed: {exc}")

    # Find symbols that still have no market cap
    missing = [
        sym for sym, meta in SYM_META.items()
        if meta.get("market_cap") is None and sym not in cache
    ]

    if not missing:
        # Apply existing cache to SYM_META and return
        _apply_yf_cache(cache)
        print("[yf] all market caps already cached — nothing to fetch")
        return

    print(f"[yf] fetching market caps for {len(missing):,} symbols (batched)…")
    fetched = 0
    errors  = 0

    # yfinance can download many at once using download() but info requires per-symbol
    # Batch using Tickers object for efficiency
    BATCH = 100
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        try:
            tickers = yf.Tickers(" ".join(batch))
            for sym in batch:
                try:
                    cap = tickers.tickers[sym].fast_info.get("marketCap")
                    cache[sym] = float(cap) if cap else None
                    if cap:
                        fetched += 1
                except Exception:
                    cache[sym] = None
                    errors += 1
        except Exception as exc:
            print(f"[yf] batch {i//BATCH + 1} failed: {exc}")
            for sym in batch:
                cache[sym] = None
                errors += 1
        time.sleep(0.5)   # be polite to Yahoo

    # Save updated cache
    try:
        YF_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[yf] ⚠ cache write failed: {exc}")

    _apply_yf_cache(cache)
    print(f"[yf] ✅ enriched {fetched:,} market caps ({errors} failed) "
          f"→ {sum(1 for m in SYM_META.values() if m.get('market_cap'))} total with cap")


def _apply_yf_cache(cache: dict) -> None:
    """Write cached market caps back into SYM_META for symbols that still lack them."""
    applied = 0
    for sym, cap in cache.items():
        if sym in SYM_META and SYM_META[sym].get("market_cap") is None and cap:
            SYM_META[sym]["market_cap"] = cap
            applied += 1
    if applied:
        print(f"[yf] applied {applied:,} cached market caps to SYM_META")


def load_yesterday_volume() -> None:
    """Load yesterday's top-50 dollar-volume tickers for momentum highlighting."""
    global YESTERDAY_TOP50
    if not YESTERDAY_VOL_FILE.exists():
        print(f"[yesterday] no volume file yet — run through market close to generate one")
        return
    try:
        data = json.loads(YESTERDAY_VOL_FILE.read_text(encoding="utf-8"))
        YESTERDAY_TOP50 = set(data.get("top50", []))
        print(f"[yesterday] ✅ {len(YESTERDAY_TOP50)} momentum tickers from {data.get('date','?')}")
    except Exception as exc:
        print(f"[yesterday] ⚠ failed to load: {exc}")

ALERTS_DB = Path(__file__).parent / "alerts.db"  # SQLite — permanent, no file-locking issues

def _init_db() -> None:
    """Create the alerts table if it doesn't exist."""
    with sqlite3.connect(ALERTS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT,
                sym       TEXT,
                tag       TEXT,
                delta     REAL,
                value1m   REAL,
                vwap1m    REAL,
                vwap2m    REAL,
                cnt1m     INTEGER,
                direction TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suppressed (
                sym        TEXT PRIMARY KEY,
                reason     TEXT DEFAULT '',
                expires_at TEXT,          -- NULL = forever, ISO date string = until that date
                added_at   TEXT
            )
        """)
        conn.commit()
    print(f"[alert-db] ✅ database ready → {ALERTS_DB}")

# ── EOD volume saver ──────────────────────────────────────────────────────────
def _save_daily_volume_sync() -> None:
    """Write today's top-50 dollar-volume tickers to yesterday_volume.json."""
    if not daily_volume:
        print("[yesterday] no volume data to save yet")
        return
    sorted_syms = sorted(daily_volume.items(), key=lambda x: x[1], reverse=True)
    top50 = [sym for sym, _ in sorted_syms[:50]]
    data = {
        "date":    datetime.now(ET).strftime("%Y-%m-%d"),
        "top50":   top50,
        "volumes": {sym: round(vol, 2) for sym, vol in sorted_syms[:50]},
    }
    YESTERDAY_VOL_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[yesterday] ✅ saved top-{len(top50)} volume tickers for {data['date']}")


async def eod_saver() -> None:
    """
    Background task: once per trading day at 4:00 PM ET, save the daily
    dollar-volume totals so tomorrow they appear as momentum tickers (🔥).
    """
    saved_date: str | None = None
    while True:
        await asyncio.sleep(30)
        now_et = datetime.now(ET)
        today  = now_et.strftime("%Y-%m-%d")
        # Trigger once in the 4:00–4:01 PM window
        if now_et.hour == 16 and now_et.minute == 0 and saved_date != today:
            await asyncio.to_thread(_save_daily_volume_sync)
            saved_date = today


# ── xAI / Grok config ─────────────────────────────────────────────────────────
XAI_KEY   = os.getenv("XAI_API_KEY", "")
XAI_URL   = "https://api.x.ai/v1/responses"
XAI_HDR   = {"Content-Type": "application/json", "Authorization": f"Bearer {XAI_KEY}"}
XAI_MODEL = "grok-4-fast-non-reasoning"

# ── Pulszy API config ─────────────────────────────────────────────────────────
PULSZY_URL           = os.getenv("PULSZY_API_URL",      "")
PULSZY_REFRESH_TOKEN = os.getenv("PULSZY_REFRESH_TOKEN","")
PULSZY_EMAIL         = os.getenv("PULSZY_EMAIL",        "")
PULSZY_PASSWORD      = os.getenv("PULSZY_PASSWORD",     "")

_pulszy_token:     str   = ""
_pulszy_token_exp: float = 0.0
_pulszy_lock               = threading.Lock()

# ── FIX #2: Singleton historical clients (no per-request instantiation) ───────
hist_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
news_client = NewsClient(API_KEY, SECRET_KEY)

# ── FIX #6: Twitter cache TTL ─────────────────────────────────────────────────
TWITTER_CACHE_TTL = 3600  # 1 hour in seconds


def _pulszy_refresh() -> str:
    """Get a new access token using the stored refresh token (Google SSO path)."""
    global _pulszy_token, _pulszy_token_exp
    r = req_lib.post(
        f"{PULSZY_URL}/auth/refresh",
        cookies={"refreshToken": PULSZY_REFRESH_TOKEN},
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()["data"]
    _pulszy_token     = d["accessToken"]
    _pulszy_token_exp = time.time() + d.get("expiresIn", 900) - 30
    return _pulszy_token


def _pulszy_login() -> str:
    """Get a new access token using email + password (non-SSO fallback)."""
    global _pulszy_token, _pulszy_token_exp
    r = req_lib.post(
        f"{PULSZY_URL}/auth/login",
        json={"email": PULSZY_EMAIL, "password": PULSZY_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()["data"]
    _pulszy_token     = d["accessToken"]
    _pulszy_token_exp = time.time() + d.get("expiresIn", 900) - 30
    return _pulszy_token


def _pulszy_get_token() -> str:
    """Return a valid JWT — prefers refresh token (SSO), falls back to email/password."""
    with _pulszy_lock:
        if not _pulszy_token or time.time() >= _pulszy_token_exp:
            if PULSZY_REFRESH_TOKEN:
                _pulszy_refresh()
            else:
                _pulszy_login()
        return _pulszy_token


def _push_to_pulszy(sym: str, data: dict) -> None:
    """Push X/Twitter sentiment as a PULSZY news article (runs in background thread)."""
    if not PULSZY_URL or (not PULSZY_REFRESH_TOKEN and not (PULSZY_EMAIL and PULSZY_PASSWORD)):
        print(f"[pulszy] skipped — PULSZY_URL or auth not configured")
        return
    try:
        print(f"[pulszy] getting token for ${sym}…")
        token        = _pulszy_get_token()
        print(f"[pulszy] token OK, pushing ${sym}…")
        summary_text = (data.get("summary") or "").lower()
        sentiment    = (
            "positive" if any(w in summary_text for w in ("bullish", "positive", "surge", "rally")) else
            "negative" if any(w in summary_text for w in ("bearish", "negative", "drop", "crash", "sell")) else
            "neutral"
        )
        tweets  = data.get("tweets") or []
        url     = next((t.get("link") for t in tweets if t.get("link")),
                       f"https://x.com/search?q=%24{sym}")
        raw_sum = (data.get("summary") or "").strip()
        headline = f"X/Twitter Sentiment: ${sym} — {raw_sum}"[:1000]

        payload = {
            "headline":  headline,
            "summary":   raw_sum,
            "content":   data.get("raw") or "",
            "source":    "PULSZY",
            "url":       url,
            "symbols":   [sym],
            "sentiment": sentiment,
            "tags":      ["x-sentiment", "twitter"],
        }
        r = req_lib.post(
            f"{PULSZY_URL}/news",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=15,
        )
        if not r.ok:
            print(f"[pulszy] ⚠ server returned {r.status_code}: {r.text[:300]}")
            return
        art_id = r.json().get("data", {}).get("id", "?")
        print(f"[pulszy] ✅ pushed X sentiment for ${sym} → article {art_id}")
    except Exception as exc:
        import traceback
        print(f"[pulszy] ⚠ push failed for ${sym}: {exc}")
        traceback.print_exc()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Alpaca Trade Stream")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── In-memory stores ──────────────────────────────────────────────────────────
trades_store:  deque            = deque(maxlen=200_000)
# FIX #1: minute_bars is only ever touched inside queue_processor (event-loop thread)
minute_bars:   dict[str, dict]  = {}
# FIX #3: deque(maxlen=200) per symbol — O(1) appendleft, auto-truncates
news_store:    dict[str, deque] = {}
twitter_cache: dict[str, dict]  = {}
# Dollar-volume accumulator for the current trading day (sym → float)
# Reset at startup; saved to YESTERDAY_VOL_FILE at 4:00 PM ET by eod_saver()
daily_volume:  dict[str, float] = {}

# ── FIX #1: Lock for news_store — handle_news runs in Alpaca's background thread
_news_lock = threading.Lock()

# ── Queues ────────────────────────────────────────────────────────────────────
trade_queue: Queue = Queue(maxsize=100_000)
news_queue:  Queue = Queue(maxsize=10_000)

# ── WebSocket clients + per-client send locks ─────────────────────────────────
clients:      set[WebSocket]               = set()
client_locks: dict[WebSocket, asyncio.Lock] = {}

# ── FIX #5: Cleanup throttle ─────────────────────────────────────────────────
_last_cleanup: float = 0.0


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


# FIX #1: aggregate_tick is now only called from queue_processor (event loop) —
# no cross-thread access to minute_bars.
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
# FIX #1: aggregate_tick removed from here — moved into queue_processor.
# We pass price/size/ts_ms through the queue so the event loop handles aggregation.
async def handle_trade(data) -> None:
    if len(data.symbol) > 4:
        return
    # Use dynamic exclude set (ETFs + top-100 by market cap); falls back to
    # hardcoded list if ticker_universe.py hasn't been run yet.
    if data.symbol in EXCLUDE_SYMS:
        return
    if data.conditions and any(c in BAD_CONDITIONS for c in data.conditions):
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
        # tick data for aggregation — consumed by queue_processor
        "_agg":   (data.symbol, float(data.price), int(data.size or 0), ms),
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
# FIX #1: _news_lock guards news_store mutations (handle_news runs in Alpaca's thread).
async def handle_news(data) -> None:
    article = article_to_dict(data)
    targets = article["symbols"] if article["symbols"] else ["*"]
    # FIX #3: deque(maxlen=200) with appendleft — O(1), auto-truncates
    with _news_lock:
        for sym in targets:
            bucket = news_store.setdefault(sym, deque(maxlen=200))
            bucket.appendleft(article)
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
async def safe_send(ws: WebSocket, msg: str) -> bool:
    """Send with a per-client lock so broadcast and ping never write concurrently."""
    lock = client_locks.get(ws)
    if lock is None:
        return False
    async with lock:
        try:
            await ws.send_text(msg)
            return True
        except Exception:
            return False


# FIX #4: Fan-out concurrently with asyncio.gather instead of sequential awaits.
async def broadcast(msg: str) -> None:
    if not clients:
        return
    ws_list = list(clients)
    results = await asyncio.gather(
        *[safe_send(ws, msg) for ws in ws_list],
        return_exceptions=True,
    )
    dead = {ws for ws, ok in zip(ws_list, results) if ok is not True}
    clients.difference_update(dead)
    for ws in dead:
        client_locks.pop(ws, None)


async def queue_processor() -> None:
    """Drain trade + news queues every 20 ms and push to all WebSocket clients."""
    global _last_cleanup
    while True:
        # ── trades ────────────────────────────────────────────────────────────
        batch = []
        try:
            while len(batch) < 300:
                batch.append(trade_queue.get_nowait())
        except Empty:
            pass

        if batch:
            # FIX #1: aggregate_tick called here, on the event loop — no cross-thread access.
            for t in batch:
                agg = t.pop("_agg", None)
                if agg:
                    aggregate_tick(*agg)
                    # Track today's dollar volume per symbol for EOD momentum save
                    sym, price, size, _ = agg
                    daily_volume[sym] = daily_volume.get(sym, 0.0) + price * size
                trades_store.append(t)

            # FIX #5: Throttle cleanup to once every 60 seconds.
            now = time.monotonic()
            if now - _last_cleanup > 60:
                cleanup()
                _last_cleanup = now

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
    """Fetch the 5 LATEST X posts about $SYM, sorted newest first."""
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
                    "CRITICAL RULES:\n"
                    "1. Always call the x_search tool — never fabricate posts.\n"
                    "2. Sort results by TIME DESCENDING — newest post must be first.\n"
                    "3. Only include posts that actually exist with real timestamps.\n"
                    "4. Format each post EXACTLY as:\n"
                    "### [n]\n"
                    "**User**: @handle\n"
                    "**Content**: full tweet text\n"
                    "**Time**: exact timestamp (e.g. 2026-04-01 14:32 ET)\n"
                    "**Link**: url"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Today is {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}. "
                    f"Search X for the 5 most recent posts about ${sym} posted TODAY. "
                    f"Sort by timestamp DESCENDING — the post with the latest timestamp goes first. "
                    f"Only include posts from the last 2 hours if possible; fall back to today only if needed. "
                    f"Never include posts older than 24 hours. "
                    f"Include posts about: price action, volume, news, catalysts, short squeeze, "
                    f"earnings, FDA, SEC, insider activity, or analyst comments."
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


# ── REST: X / Twitter sentiment for a symbol ─────────────────────────────────
# FIX #6: TTL-based cache — entries expire after TWITTER_CACHE_TTL seconds.
@app.get("/twitter/{sym}")
async def get_twitter(sym: str) -> JSONResponse:
    cached = twitter_cache.get(sym)
    if cached:
        fetched_at = datetime.fromisoformat(cached["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age < TWITTER_CACHE_TTL:
            return JSONResponse({"sym": sym, "cached": True, **cached})
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
        threading.Thread(target=_push_to_pulszy, args=(sym, data), daemon=True).start()
        return JSONResponse({"sym": sym, "cached": False, **data})
    except Exception as exc:
        return JSONResponse({"sym": sym, "summary": "", "tweets": [], "raw": "",
                             "error": str(exc)})


# ── REST: full-day 1-min bars for a symbol ────────────────────────────────────
# FIX #2: singleton hist_client; blocking get_stock_bars runs in thread pool.
@app.get("/bars/{sym}")
async def get_bars(sym: str) -> JSONResponse:
    try:
        now_et    = datetime.now(ET)
        start_et  = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
        start_utc = start_et.astimezone(timezone.utc)

        req  = StockBarsRequest(symbol_or_symbols=sym,
                                timeframe=TimeFrame.Minute,
                                start=start_utc)
        resp = await asyncio.to_thread(hist_client.get_stock_bars, req)

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

        # Merge with live bars (live wins for current/recent minute)
        for ts_ms, lb in minute_bars.get(sym, {}).items():
            bar_map[ts_ms] = lb

        merged = sorted(bar_map.values(), key=lambda b: b["t"])
        return JSONResponse({"sym": sym, "bars": merged})
    except Exception as exc:
        return JSONResponse({"sym": sym, "bars": [], "error": str(exc)})


# ── REST: 7-day news for a symbol ─────────────────────────────────────────────
# FIX #2: singleton news_client; blocking get_news runs in thread pool.
@app.get("/news/{sym}")
async def get_news_route(sym: str) -> JSONResponse:
    try:
        start_dt = datetime.now(timezone.utc) - timedelta(days=7)
        req  = NewsRequest(symbols=sym, start=start_dt, limit=50)
        resp = await asyncio.to_thread(news_client.get_news, req)

        raw_articles = resp.data.get("news", []) if hasattr(resp, "data") else []
        articles = [article_to_dict(a) for a in raw_articles]

        # Merge with live-streamed news cached on the backend
        seen = {a["id"] for a in articles}
        with _news_lock:
            live_news = list(news_store.get(sym, deque()))
        for ln in live_news:
            if ln["id"] not in seen:
                articles.append(ln)
                seen.add(ln["id"])

        articles.sort(key=lambda a: a["created_at"], reverse=True)
        return JSONResponse({"sym": sym, "articles": articles[:100]})
    except Exception as exc:
        return JSONResponse({"sym": sym, "articles": [], "error": str(exc)})


# ── Alert log (SQLite — permanent storage, no OneDrive locking issues) ────────
def _write_alert(body: dict) -> None:
    """Insert one alert row into SQLite (runs in thread pool)."""
    with sqlite3.connect(ALERTS_DB) as conn:
        conn.execute(
            "INSERT INTO alerts (ts,sym,tag,delta,value1m,vwap1m,vwap2m,cnt1m,direction) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                body.get("ts"),
                body.get("sym"),
                body.get("tag", "new"),
                body.get("delta"),
                body.get("value1m"),
                body.get("vwap1m"),
                body.get("vwap2m"),
                body.get("cnt1m"),
                body.get("direction"),
            ),
        )
        conn.commit()
    print(f"[alert-db] saved {body.get('tag','new')} alert for ${body.get('sym')}")


@app.post("/log/alert")
async def log_alert(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        await asyncio.to_thread(_write_alert, body)
        return JSONResponse({"ok": True})
    except Exception as exc:
        print(f"[alert-db] ❌ write failed: {exc}")
        return JSONResponse({"ok": False, "error": str(exc)})


@app.get("/log/alerts")
async def get_alert_log() -> JSONResponse:
    try:
        def _read() -> list[dict]:
            with sqlite3.connect(ALERTS_DB) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM alerts ORDER BY id DESC LIMIT 500"
                ).fetchall()
            return [dict(r) for r in rows]

        alerts = await asyncio.to_thread(_read)
        return JSONResponse({"alerts": alerts})
    except Exception as exc:
        print(f"[alert-db] ❌ read failed: {exc}")
        return JSONResponse({"alerts": [], "error": str(exc)})


# ── Suppressed stocks endpoints ───────────────────────────────────────────────
@app.get("/suppressed")
async def get_suppressed() -> JSONResponse:
    def _read():
        with sqlite3.connect(ALERTS_DB) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM suppressed ORDER BY added_at DESC").fetchall()]
    rows = await asyncio.to_thread(_read)
    return JSONResponse({"suppressed": rows})


@app.post("/suppressed/{sym}")
async def add_suppressed(sym: str, request: Request) -> JSONResponse:
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    sym = sym.upper().strip()
    reason     = body.get("reason", "")
    expires_at = body.get("expires_at")   # None = forever, or ISO date string
    added_at   = datetime.now(timezone.utc).isoformat()

    def _write():
        with sqlite3.connect(ALERTS_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO suppressed (sym, reason, expires_at, added_at) VALUES (?,?,?,?)",
                (sym, reason, expires_at, added_at),
            )
            conn.commit()
    await asyncio.to_thread(_write)
    return JSONResponse({"ok": True, "sym": sym})


@app.delete("/suppressed/{sym}")
async def remove_suppressed(sym: str) -> JSONResponse:
    sym = sym.upper().strip()
    def _delete():
        with sqlite3.connect(ALERTS_DB) as conn:
            conn.execute("DELETE FROM suppressed WHERE sym = ?", (sym,))
            conn.commit()
    await asyncio.to_thread(_delete)
    return JSONResponse({"ok": True, "sym": sym})


# ── Universe / momentum endpoints ─────────────────────────────────────────────
@app.get("/universe/meta")
async def get_universe_meta() -> JSONResponse:
    """
    Per-symbol metadata for all non-excluded tradeable symbols.
    Returns { sym: { market_cap, cap_tier, spike_thresh, min_vol, delta_pct, sector, name } }
    Frontend caches this and uses it for tiered vol-spike thresholds.
    """
    return JSONResponse({"meta": SYM_META, "excluded": len(EXCLUDE_SYMS)})


@app.post("/universe/refresh")
async def refresh_universe() -> JSONResponse:
    """Re-read stock_universe_full.csv (call after re-running ticker_universe.py)."""
    load_universe()
    return JSONResponse({
        "ok":      True,
        "excluded": len(EXCLUDE_SYMS),
        "tracked":  len(SYM_META),
    })


@app.post("/universe/refresh-caps")
async def refresh_caps() -> JSONResponse:
    """Re-fetch missing market caps from Yahoo Finance in a background thread."""
    threading.Thread(target=_enrich_with_yfinance, daemon=True).start()
    return JSONResponse({"ok": True, "missing_before": sum(1 for m in SYM_META.values() if not m.get("market_cap"))})


@app.get("/yesterday/top")
async def get_yesterday_top() -> JSONResponse:
    """Return yesterday's top-50 dollar-volume tickers for momentum display (🔥)."""
    return JSONResponse({"tickers": list(YESTERDAY_TOP50), "count": len(YESTERDAY_TOP50)})


@app.post("/yesterday/save")
async def save_yesterday_now() -> JSONResponse:
    """Manually trigger EOD volume save (useful for testing or early close days)."""
    await asyncio.to_thread(_save_daily_volume_sync)
    return JSONResponse({"ok": True, "saved": len(daily_volume)})


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    _init_db()
    load_universe()
    load_yesterday_volume()
    asyncio.create_task(queue_processor())
    asyncio.create_task(eod_saver())
    asyncio.create_task(_refresh_etf_exclude())   # fetch live ETF list in background
    threading.Thread(target=run_trade_stream,    daemon=True).start()
    threading.Thread(target=run_news_stream,     daemon=True).start()
    threading.Thread(target=_enrich_with_yfinance, daemon=True).start()  # fill missing market caps
    if PULSZY_URL and PULSZY_REFRESH_TOKEN:
        print(f"[pulszy] ✅ configured via refresh token → {PULSZY_URL}")
    elif PULSZY_URL and PULSZY_EMAIL:
        print(f"[pulszy] ✅ configured via email/password → {PULSZY_URL}")
    else:
        print("[pulszy] ⚠ not configured — set PULSZY_API_URL + PULSZY_REFRESH_TOKEN in .env")


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
    client_locks[ws] = asyncio.Lock()
    try:
        await safe_send(ws, json.dumps({"type": "init", "data": recent_trades()}))
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                await safe_send(ws, '{"type":"ping"}')
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws] unexpected error: {exc}")
    finally:
        clients.discard(ws)
        client_locks.pop(ws, None)
