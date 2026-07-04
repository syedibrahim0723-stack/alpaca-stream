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

import ssl
ssl._create_default_https_context = ssl._create_unverified_context  # fix: Basic Constraints cert error on Windows

import asyncio
import csv
import json
import math
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
from fastapi.staticfiles import StaticFiles

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from alpaca.data.enums import DataFeed
from alpaca.data.live.stock import StockDataStream
from alpaca.data.live.news import NewsDataStream
from alpaca.data.historical import StockHistoricalDataClient, NewsClient
from alpaca.data.requests import StockBarsRequest, NewsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        LimitOrderRequest, MarketOrderRequest, GetOrdersRequest,
        TrailingStopOrderRequest,
    )
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    _TRADING_AVAILABLE = True
except ImportError:
    _TRADING_AVAILABLE = False
    print("[trading] alpaca trading module not found — run: pip install alpaca-py")

try:
    import anthropic as _anthropic_lib
    _ANTHROPIC_IMPORT_OK = True
except ImportError:
    _anthropic_lib = None
    _ANTHROPIC_IMPORT_OK = False

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY       = os.getenv("ALPACA_API_KEY", "")
SECRET_KEY    = os.getenv("ALPACA_SECRET_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MASSIVE_API_KEY  = os.getenv("MASSIVE_API_KEY", "yWMvK3UVQjIYOUHq7l_zOXdhq8Abh4d3")
MASSIVE_BASE_URL = "https://api.massive.com/v1"

if not API_KEY or not SECRET_KEY:
    raise RuntimeError(
        "Missing API keys. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
    )

ET = pytz.timezone("America/New_York")
# Filter only end-of-day auction prints that produce giant single-print distortions:
# M = Market Center Close (MOC auction), Q = Market Center Official Close
BAD_CONDITIONS = {"M", "Q"}

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

# ── News Intelligence ──────────────────────────────────────────────────────────
PROMPTS_DIR   = Path(__file__).parent / "prompts"
RULES_FILE    = Path(__file__).parent / "classification_rules.json"
NEWS_INTEL_DB = Path(__file__).parent / "news_intel.db"

# ── Sweep Board ────────────────────────────────────────────────────────────────
SWEEP_BOARD_DIR = Path(__file__).parent / "data"

# Minimum total sweep dollar value to appear on the board (per cap tier)
_SB_THRESHOLDS: dict[str, float] = {
    "nano":    200_000,
    "small":   1_000_000,
    "mid":     5_000_000,
    "unknown": 200_000,
}
_SB_THRESHOLD_DEFAULT = 5_000_000   # large / mega / anything not listed

# In-memory tally: sym → row dict (accumulates all day 4 AM–8 PM ET)
_sweep_board: dict[str, dict] = {}
_sweep_board_lock = threading.Lock()


def _sb_threshold(cap_tier: str) -> float:
    return _SB_THRESHOLDS.get(cap_tier, _SB_THRESHOLD_DEFAULT)


def _sb_score(bull: int, bear: int, total_value: float) -> int:
    """0-100 composite score: conviction(40) + sweep_count(30) + value(30)."""
    total = bull + bear
    if total == 0:
        return 0
    conviction = abs(bull - bear) / total   # 0.0–1.0

    if total == 1:   sc = 100
    elif total == 2: sc = 90
    elif total == 3: sc = 70
    elif total <= 6: sc = 40
    else:            sc = 10

    if   total_value < 100_000:   vs = 100
    elif total_value < 200_000:   vs = 80
    elif total_value < 500_000:   vs = 50
    elif total_value < 1_000_000: vs = 25
    else:                         vs = 10

    return min(100, max(0, int(conviction * 40 + sc * 0.30 + vs * 0.30)))


def _sb_signal(bull: int, bear: int, score: int) -> str:
    total = bull + bear
    if total == 0:
        return "⚪ NO DATA"
    direction = "BULL" if bull >= bear else "BEAR"
    emoji = "🟢" if direction == "BULL" else "🔴"
    if score >= 75:
        return f"{emoji} STRONG {direction}"
    elif score >= 50:
        return f"🟡 LEAN {direction}"
    else:
        return "⚪ TWO-SIDED"


def _sb_row_to_dict(row: dict) -> dict:
    """Build the public dict for a sweep board row."""
    bull    = row["bull"]
    bear    = row["bear"]
    neutral = row.get("neutral", 0)
    total   = bull + bear + neutral
    tv      = row["total_value"]
    score   = _sb_score(bull, bear, tv)
    return {
        "sym":          row["sym"],
        "cap_tier":     row["cap_tier"],
        "name":         row.get("name", ""),
        "bull":         bull,
        "bear":         bear,
        "neutral":      neutral,
        "total_sweeps": total,
        "conviction":   round(abs(bull - bear) / (bull + bear) * 100) if (bull + bear) else 0,
        "total_value":  tv,
        "score":        score,
        "signal":       _sb_signal(bull, bear, score),
        "first_ts":     row.get("first_ts", ""),
        "last_ts":      row.get("last_ts", ""),
    }


def _update_sweep_board(body: dict) -> dict | None:
    """
    Update in-memory sweep board from a sweep alert body.
    Returns the updated public row dict (unfiltered by threshold) or None if skipped.
    Neutral sweeps count toward activity/value but not bull or bear directional count.
    """
    if body.get("type") != "sweep":
        return None

    # Only count sweeps within extended trading hours (4 AM – 8 PM ET)
    from datetime import time as _t
    now_et = datetime.now(ET)
    if not (_t(4, 0) <= now_et.time() < _t(20, 0)):
        return None

    sym = (body.get("sym") or "").upper().strip()
    if not sym:
        return None

    # Resolve direction — supports "bull"/"bear" direct or embedded in tag
    # "neutral" sweeps still count toward activity and value, just not bull/bear
    direction = (body.get("direction") or "").lower()
    if direction not in ("bull", "bear", "neutral"):
        tag = (body.get("tag") or "").lower()
        if "bull" in tag:
            direction = "bull"
        elif "bear" in tag:
            direction = "bear"
        else:
            direction = "neutral"   # count as activity, no directional lean

    value  = float(body.get("value1m") or 0)
    ts_now = datetime.now(timezone.utc).isoformat()

    # Cap tier from metadata
    meta     = SYM_META.get(sym, {})
    cap      = meta.get("market_cap")
    cap_tier = "unknown"
    for tier in CAP_TIERS:
        if cap and cap < tier["max_cap"]:
            cap_tier = tier["name"]
            break

    with _sweep_board_lock:
        row = _sweep_board.get(sym)
        if row is None:
            row = {
                "sym": sym, "bull": 0, "bear": 0, "neutral": 0,
                "total_value": 0.0, "cap_tier": cap_tier,
                "name": meta.get("name", ""),
                "first_ts": ts_now, "last_ts": ts_now,
            }
            _sweep_board[sym] = row
        if direction == "bull":
            row["bull"] += 1
        elif direction == "bear":
            row["bear"] += 1
        else:
            row["neutral"] = row.get("neutral", 0) + 1
        row["total_value"] += value
        row["last_ts"]      = ts_now
        row["cap_tier"]     = cap_tier   # refresh if metadata loaded after first sweep
        return _sb_row_to_dict(row)


def _sb_load_today() -> None:
    """
    On startup, backfill today's sweep alerts (4 AM–now) from alerts.db
    so the board survives server restarts.
    """
    try:
        today_et  = datetime.now(ET)
        start_et  = today_et.replace(hour=4,  minute=0, second=0, microsecond=0)
        end_et    = today_et.replace(hour=20, minute=0, second=0, microsecond=0)
        start_iso = start_et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        end_iso   = end_et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        with sqlite3.connect(ALERTS_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT sym, direction, tag, value1m, ts FROM alerts "
                "WHERE type='sweep' AND ts >= ? AND ts < ? ORDER BY ts",
                (start_iso, end_iso),
            ).fetchall()

        count = 0
        for r in rows:
            sym       = (r["sym"] or "").upper()
            direction = (r["direction"] or "").lower()
            # Some rows store tier name (old format) or "neutral" — resolve direction
            if direction not in ("bull", "bear", "neutral"):
                tag = (r["tag"] or "").lower()
                if "bull" in tag:   direction = "bull"
                elif "bear" in tag: direction = "bear"
                else:               direction = "neutral"
            if not sym:
                continue

            value    = float(r["value1m"] or 0)
            ts_str   = r["ts"] or datetime.now(timezone.utc).isoformat()
            meta     = SYM_META.get(sym, {})
            cap      = meta.get("market_cap")
            cap_tier = "unknown"
            for tier in CAP_TIERS:
                if cap and cap < tier["max_cap"]:
                    cap_tier = tier["name"]
                    break

            with _sweep_board_lock:
                row = _sweep_board.get(sym)
                if row is None:
                    row = {
                        "sym": sym, "bull": 0, "bear": 0, "neutral": 0,
                        "total_value": 0.0, "cap_tier": cap_tier,
                        "name": meta.get("name", ""),
                        "first_ts": ts_str, "last_ts": ts_str,
                    }
                    _sweep_board[sym] = row
                if direction == "bull":
                    row["bull"] += 1
                elif direction == "bear":
                    row["bear"] += 1
                else:
                    row["neutral"] = row.get("neutral", 0) + 1
                # neutral: counts toward value/activity, not bull/bear
                row["total_value"] += value
                row["last_ts"]      = ts_str
            count += 1

        print(f"[sweep-board] loaded {count} sweeps for {len(_sweep_board)} tickers from today's DB")
    except Exception as exc:
        print(f"[sweep-board] ⚠ load today failed: {exc}")


def _sb_save_eod() -> None:
    """Save EOD snapshot to data/sweep_board_YYYY-MM-DD.json then clear the board."""
    try:
        SWEEP_BOARD_DIR.mkdir(exist_ok=True)
        today    = datetime.now(ET).strftime("%Y-%m-%d")
        out_file = SWEEP_BOARD_DIR / f"sweep_board_{today}.json"
        with _sweep_board_lock:
            snapshot = [_sb_row_to_dict(r) for r in _sweep_board.values()]
        snapshot.sort(key=lambda r: r["total_sweeps"], reverse=True)
        out_file.write_text(json.dumps({
            "date":     today,
            "saved_at": datetime.now(ET).isoformat(),
            "rows":     snapshot,
        }, indent=2), encoding="utf-8")
        print(f"[sweep-board] EOD snapshot → {out_file.name} ({len(snapshot)} tickers)")
        with _sweep_board_lock:
            _sweep_board.clear()
        print("[sweep-board] board cleared for next session")
    except Exception as exc:
        print(f"[sweep-board] ⚠ EOD save failed: {exc}")

_prompts: dict = {}
_ni_rules: dict = {}
_anthropic_client = None
_classify_sem = None   # asyncio.Semaphore — set in startup
_ANTHROPIC_OK = False


def _load_ni_prompts() -> None:
    global _prompts
    PROMPTS_DIR.mkdir(exist_ok=True)
    for f in PROMPTS_DIR.glob("*.txt"):
        _prompts[f.stem] = f.read_text(encoding="utf-8")
    print(f"[news-intel] loaded {len(_prompts)} prompts: {list(_prompts.keys())}")


def _load_ni_rules() -> None:
    global _ni_rules
    _default = {
        "noise_keywords": [
            "price target", "reiterates", "maintains rating", "maintains overweight",
            "top gainers", "top losers", "most active", "52-week high", "52-week low",
            "crosses above", "crosses below", "moving average", "stocks to watch"
        ],
        "high_keywords": [
            "fda approves", "fda grants", "accelerated approval", "breakthrough designation",
            "phase 3", "phase iii", "phase 2", "phase ii", "complete response letter",
            "merger", "acquisition", "buyout", "going private", "tender offer",
            "definitive agreement", "bankruptcy", "chapter 11",
            "short seller", "fraud", "sec investigation",
            "ceo resigns", "cfo resigns", "activist investor"
        ],
        "multi_ticker_threshold": 5
    }
    if RULES_FILE.exists():
        try:
            with open(RULES_FILE, encoding="utf-8") as f:
                _ni_rules.update(json.load(f))
        except Exception:
            _ni_rules.update(_default)
    else:
        _ni_rules.update(_default)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(_default, f, indent=2)
    print(f"[news-intel] rules loaded: {len(_ni_rules.get('noise_keywords',[]))} noise, "
          f"{len(_ni_rules.get('high_keywords',[]))} high")


def _init_ni_db() -> None:
    with sqlite3.connect(NEWS_INTEL_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_intel (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                alpaca_id     TEXT    UNIQUE,
                published_at  TEXT,
                sym           TEXT,
                symbols       TEXT,
                headline      TEXT,
                summary       TEXT,
                url           TEXT,
                source        TEXT,
                author        TEXT,
                category      TEXT,
                importance    TEXT,
                classified_by TEXT,
                classified_at TEXT,
                insight_json  TEXT,
                insight_at    TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def _ni_classify_rules(headline: str, symbols: list) -> tuple:
    """Returns (category, importance, classified_by) or (None, None, None)."""
    h = headline.lower()
    threshold = _ni_rules.get("multi_ticker_threshold", 5)
    if len(symbols) >= threshold:
        return "NOISE", "NOISE", "RULE_MULTI_TICKER"
    for kw in _ni_rules.get("noise_keywords", []):
        if kw.lower() in h:
            return "NOISE", "NOISE", f"RULE:{kw}"
    for kw in _ni_rules.get("high_keywords", []):
        if kw.lower() in h:
            cat = _ni_infer_cat(kw)
            return cat, "HIGH", f"RULE:{kw}"
    return None, None, None


def _ni_infer_cat(kw: str) -> str:
    kw = kw.lower()
    if any(x in kw for x in ["fda", "phase", "approval", "breakthrough", "pdufa", "clinical", "crl"]):
        return "REGULATORY_FDA"
    if any(x in kw for x in ["merger", "acquisition", "buyout", "going private", "tender", "strategic review"]):
        return "MERGER_ACQUISITION"
    if any(x in kw for x in ["bankruptcy", "chapter"]):
        return "EARNINGS_PROJECTION"
    if any(x in kw for x in ["short seller", "fraud", "sec investigation", "doj"]):
        return "SHORT_REPORT"
    if any(x in kw for x in ["ceo", "cfo", "activist"]):
        return "MANAGEMENT_CHANGE"
    return "DEAL_PARTNERSHIP"


def _ni_classify_single_sync(alpaca_id: str) -> None:
    """Thread-safe sync classification for one live article via Haiku."""
    prompt_tmpl = _prompts.get("news_classifier", "")
    if not prompt_tmpl or not _ANTHROPIC_OK or _anthropic_client is None:
        return
    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            row = conn.execute(
                "SELECT id, headline, summary FROM news_intel WHERE alpaca_id=?", (str(alpaca_id),)
            ).fetchone()
        if not row:
            return
        row_id, headline, summary = row
        filled = prompt_tmpl.replace("{headline}", headline or "").replace("{summary}", summary or "")
        resp = _anthropic_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=80,
            messages=[{"role": "user", "content": filled}]
        )
        raw = resp.content[0].text.strip()
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            category   = data.get("category",  "UNKNOWN")
            importance = data.get("importance", "LOW")
            now_iso = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(NEWS_INTEL_DB) as conn:
                conn.execute(
                    "UPDATE news_intel SET category=?, importance=?, classified_by=?, classified_at=? WHERE id=?",
                    (category, importance, "API:haiku", now_iso, row_id)
                )
    except Exception as e:
        print(f"[news-intel] live classify error: {e}")


def _ni_save(article: dict, category: str, importance: str, classified_by: str) -> None:
    symbols = article.get("symbols", [])
    sym = symbols[0] if symbols else ""
    now_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(NEWS_INTEL_DB) as conn:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO news_intel
                (alpaca_id,published_at,sym,symbols,headline,summary,url,source,author,
                 category,importance,classified_by,classified_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(article.get("id", "")),
                article.get("created_at", now_iso),
                sym,
                json.dumps(symbols),
                article.get("headline", ""),
                article.get("summary", ""),
                article.get("url", ""),
                article.get("source", ""),
                article.get("author", ""),
                category, importance, classified_by, now_iso
            ))
            # Keep only latest 200
            conn.execute("""
                DELETE FROM news_intel WHERE id NOT IN (
                    SELECT id FROM news_intel ORDER BY published_at DESC LIMIT 200
                )
            """)
            conn.commit()
        except Exception as e:
            print(f"[news-intel] save error: {e}")


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
STOCK_TAGS: dict[str, dict]     = {}      # sym → {market_cap, industry, country, tags:[]}

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


YF_CACHE_FILE       = Path(__file__).parent / "yf_marketcap_cache.json"
FINNHUB_CACHE_FILE  = Path(__file__).parent / "finnhub_marketcap_cache.json"
FINNHUB_API_KEY     = "d7gj0apr01qmqj45hqq0d7gj0apr01qmqj45hqqg"


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


def _enrich_with_finnhub() -> None:
    """
    For every symbol in SYM_META that still has no market cap after yfinance,
    fetch it from Finnhub company_profile2. Returns marketCapitalization in $M
    so we multiply by 1,000,000 before storing.
    Free tier: 60 calls/min — sleep 1.1s per call.
    Cache stored in finnhub_marketcap_cache.json.
    """
    try:
        import finnhub
    except ImportError:
        print("[finnhub] finnhub-python not installed — run: pip install finnhub-python")
        return

    cache: dict[str, float | None] = {}
    if FINNHUB_CACHE_FILE.exists():
        try:
            cache = json.loads(FINNHUB_CACHE_FILE.read_text(encoding="utf-8"))
            print(f"[finnhub] loaded {len(cache):,} cached market caps")
        except Exception as exc:
            print(f"[finnhub] ⚠ cache read failed: {exc}")

    _apply_finnhub_cache(cache)

    missing = [
        sym for sym, meta in SYM_META.items()
        if meta.get("market_cap") is None and sym not in cache
    ]

    if not missing:
        print("[finnhub] no missing market caps — nothing to fetch")
        return

    print(f"[finnhub] fetching market caps for {len(missing):,} symbols…")
    client  = finnhub.Client(api_key=FINNHUB_API_KEY)
    fetched = 0
    errors  = 0

    for sym in missing:
        try:
            profile = client.company_profile2(symbol=sym)
            cap_m   = profile.get("marketCapitalization") if profile else None
            if cap_m and float(cap_m) > 0:
                cache[sym] = float(cap_m) * 1_000_000
                fetched += 1
            else:
                cache[sym] = None
        except Exception as exc:
            print(f"[finnhub] {sym} failed: {exc}")
            cache[sym] = None
            errors += 1
        time.sleep(1.1)

    try:
        FINNHUB_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[finnhub] ⚠ cache write failed: {exc}")

    _apply_finnhub_cache(cache)
    print(f"[finnhub] ✅ enriched {fetched:,} market caps ({errors} failed) "
          f"→ {sum(1 for m in SYM_META.values() if m.get('market_cap'))} total with cap")


def _apply_finnhub_cache(cache: dict) -> None:
    """Write cached Finnhub market caps back into SYM_META for symbols that still lack them."""
    applied = 0
    for sym, cap in cache.items():
        if sym in SYM_META and SYM_META[sym].get("market_cap") is None and cap:
            SYM_META[sym]["market_cap"] = cap
            applied += 1
    if applied:
        print(f"[finnhub] applied {applied:,} cached market caps to SYM_META")


def _sync_stock_tags() -> None:
    """Fetch stock tags from Google Sheet CSV, cache to stock_tags.json. Runs at startup + scheduled."""
    global STOCK_TAGS
    try:
        import urllib.request, csv as _csv, io
        req = urllib.request.Request(GSHEET_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8-sig")
        reader = _csv.DictReader(io.StringIO(raw))
        result = {}
        for row in reader:
            ticker = row.get("ticker", "").strip().upper()
            if not ticker:
                continue
            tags_raw = row.get("tags", "").strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
            result[ticker] = {
                "market_cap": row.get("market cap", "").strip(),
                "industry":   row.get("industry", "").strip(),
                "country":    row.get("country", "").strip(),
                "tags":       tags,
            }
        STOCK_TAGS = result
        STOCK_TAGS_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[tags] ✅ synced {len(result)} stocks from Google Sheet")
    except Exception as exc:
        print(f"[tags] ⚠ sync failed: {exc} — loading from cache")
        if STOCK_TAGS_FILE.exists():
            try:
                STOCK_TAGS = json.loads(STOCK_TAGS_FILE.read_text(encoding="utf-8"))
                print(f"[tags] loaded {len(STOCK_TAGS)} stocks from cache")
            except Exception as e2:
                print(f"[tags] ⚠ cache load failed: {e2}")


async def _tags_scheduler() -> None:
    """Sync tags at startup, then daily at 08:00 and 13:00 ET."""
    await asyncio.to_thread(_sync_stock_tags)
    while True:
        now = datetime.now(ET)
        # Calculate next sync: 08:00 or 13:00 ET
        targets = [now.replace(hour=8, minute=0, second=0, microsecond=0),
                   now.replace(hour=13, minute=0, second=0, microsecond=0)]
        future = [t for t in targets if t > now]
        if not future:
            # Past both today — wait until 08:00 tomorrow
            tomorrow = now + timedelta(days=1)
            next_sync = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            next_sync = min(future)
        wait_secs = (next_sync - now).total_seconds()
        print(f"[tags] next sync at {next_sync.strftime('%H:%M ET')} ({wait_secs/3600:.1f}h)")
        await asyncio.sleep(wait_secs)
        await asyncio.to_thread(_sync_stock_tags)


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

ALERTS_DB          = Path(__file__).parent / "alerts.db"
BREAKING_NEWS_FILE = Path(__file__).parent / "breaking_news.json"
STOCK_TAGS_FILE    = Path(__file__).parent / "stock_tags.json"
USER_TAGS_FILE     = Path(__file__).parent / "user_tags.json"

USER_TAGS: dict[str, list[str]] = {}

def _load_user_tags() -> None:
    global USER_TAGS
    if USER_TAGS_FILE.exists():
        try:
            USER_TAGS = json.loads(USER_TAGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            USER_TAGS = {}

def _save_user_tags() -> None:
    USER_TAGS_FILE.write_text(json.dumps(USER_TAGS, indent=2), encoding="utf-8")
GSHEET_CSV_URL     = "https://docs.google.com/spreadsheets/d/1T5WXga3cO12AWFy-HnADJJKOHopiObxhncvikpDt3iQ/export?format=csv&gid=0"

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
                direction TEXT,
                type      TEXT DEFAULT 'alert'
            )
        """)
        try:
            conn.execute("ALTER TABLE alerts ADD COLUMN type TEXT DEFAULT 'alert'")
        except Exception:
            pass  # column already exists
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


HISTORY_CSV = Path(__file__).parent / "alert_history.csv"
_csv_last_id: int = 0   # highest alert id already written to CSV

_CSV_COLUMNS = ["id", "ts", "sym", "tag", "type", "direction",
                "delta", "value1m", "vwap1m", "vwap2m", "cnt1m"]

def _export_history_sync() -> int:
    """Append any alerts with id > _csv_last_id to HISTORY_CSV. Returns rows written."""
    global _csv_last_id
    with sqlite3.connect(ALERTS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id,ts,sym,tag,type,direction,delta,value1m,vwap1m,vwap2m,cnt1m "
            "FROM alerts WHERE id > ? ORDER BY id",
            (_csv_last_id,)
        ).fetchall()
    if not rows:
        return 0
    write_header = not HISTORY_CSV.exists() or HISTORY_CSV.stat().st_size == 0
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    _csv_last_id = rows[-1]["id"]
    return len(rows)


async def csv_history_exporter() -> None:
    """Background task: append new alert rows to alert_history.csv every hour."""
    # On startup, set _csv_last_id to highest id already in CSV so we don't re-export
    global _csv_last_id
    if HISTORY_CSV.exists() and HISTORY_CSV.stat().st_size > 0:
        try:
            with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
                last = None
                for last in csv.DictReader(f):
                    pass
                if last and last.get("id"):
                    _csv_last_id = int(last["id"])
                    print(f"[csv-export] resuming from id={_csv_last_id}")
        except Exception as exc:
            print(f"[csv-export] could not read existing CSV: {exc}")
    while True:
        await asyncio.sleep(3600)
        try:
            n = await asyncio.to_thread(_export_history_sync)
            if n:
                print(f"[csv-export] ✅ appended {n} rows → {HISTORY_CSV}")
        except Exception as exc:
            print(f"[csv-export] ❌ {exc}")


# ── Auto-trading strategy engine ─────────────────────────────────────────────
# Each entry keyed by sym.  State machine: WATCHING → PENDING_FILL → IN_POSITION
_strategies: dict[str, dict] = {}
_strategy_queues: dict[str, asyncio.Queue] = {}

_STRAT_ENTRY_CANCEL_SECS = 3 * 60   # cancel unfilled limit buy after 3 min


def _strat_log(sym: str, msg: str) -> None:
    entry = _strategies.get(sym)
    if entry is None:
        return
    line = f"{datetime.now(ET).strftime('%H:%M:%S')} {msg}"
    entry["log"].append(line)
    if len(entry["log"]) > 200:
        entry["log"] = entry["log"][-200:]
    print(f"[strategy:{sym}] {msg}")


def _is_regular_hours() -> bool:
    from datetime import time as _t
    n = datetime.now(ET)
    return n.weekday() < 5 and _t(9, 30) <= n.time() < _t(16, 0)


def _is_after_4pm() -> bool:
    """True from 4:00 PM ET onwards (extended hours window)."""
    from datetime import time as _t
    n = datetime.now(ET)
    return n.weekday() < 5 and n.time() >= _t(16, 0)


async def _exit_sell(tc, sym: str, qty: int, ref_price: float, log_fn) -> bool:
    """
    Submit a closing sell that works in ANY session:
      - Regular hours  → Market order (instant fill)
      - Extended hours → Limit order 10% below ref_price with extended_hours=True
        (wide limit acts as pseudo-market; ensures fill at whatever bid exists)
    Returns True if the order was submitted without exception.
    """
    if _is_regular_hours():
        try:
            await asyncio.to_thread(tc.submit_order,
                MarketOrderRequest(symbol=sym, qty=qty,
                                   side=OrderSide.SELL,
                                   time_in_force=TimeInForce.DAY))
            log_fn(f"Market sell {qty}sh submitted")
            return True
        except Exception as exc:
            log_fn(f"Market sell failed: {exc}")
            return False
    else:
        # Extended hours: limit sell at 10% below ref so it fills at market bid
        limit_px = round(max(ref_price * 0.99, 0.01), 4)
        try:
            await asyncio.to_thread(tc.submit_order,
                LimitOrderRequest(symbol=sym, qty=qty,
                                  side=OrderSide.SELL,
                                  time_in_force=TimeInForce.DAY,
                                  limit_price=limit_px,
                                  extended_hours=True))
            log_fn(f"Extended-hours limit sell {qty}sh @ ≥${limit_px:.4f} submitted")
            return True
        except Exception as exc:
            log_fn(f"Extended-hours sell failed: {exc}")
            return False


_EXT_TRAIL = "EXT_TRAIL"   # sentinel: server-side trailing active (extended hours)

async def _place_exit_order(tc, sym: str, qty: int,
                            fill_price: float, stop_pct: float,
                            log_fn) -> str | None:
    """
    Place the 'hold' sell order appropriate for the current session:
      - Regular hours (before 4 PM) → TrailingStopOrderRequest trail_percent=stop_pct
      - Extended hours (after 4 PM)  → No standing order; returns _EXT_TRAIL sentinel
        so the caller activates server-side trailing (poll price every 5s, sell when
        price drops stop_pct% below the session high-watermark).
    Returns order ID string, _EXT_TRAIL, or None on failure.
    """
    if _is_after_4pm():
        log_fn(f"After-4PM: server-side trailing stop active "
               f"({stop_pct}% trail from high) — no standing order")
        return _EXT_TRAIL
    else:
        try:
            o = await asyncio.to_thread(tc.submit_order,
                TrailingStopOrderRequest(symbol=sym, qty=qty,
                                         side=OrderSide.SELL,
                                         time_in_force=TimeInForce.DAY,
                                         trail_percent=stop_pct))
            log_fn(f"Trailing stop placed id={str(o.id)[:8]}… trail={stop_pct}%")
            return str(o.id)
        except Exception as exc:
            log_fn(f"TrailingStopOrder FAILED: {exc} — retrying in 1 min")
            return None


def _ostatus(o) -> str:
    """Safely extract order status string regardless of alpaca-py / Python version."""
    s = o.status
    # str enum in Python 3.11+ may return 'OrderStatus.filled' — use .value to be safe
    return s.value if hasattr(s, 'value') else str(s)


async def _cancel_entry_after(order_id: str, sym: str) -> None:
    await asyncio.sleep(_STRAT_ENTRY_CANCEL_SECS)
    st = _strategies.get(sym)
    if not st or st.get("entry_order_id") != order_id:
        return  # already filled or superseded
    try:
        tc = _get_trading_client()
        await asyncio.to_thread(tc.cancel_order_by_id, order_id)
        _strat_log(sym, f"Entry order {order_id[:8]}… cancelled (3-min timeout)")
    except Exception as exc:
        _strat_log(sym, f"Entry cancel attempt: {exc}")


async def _strategy_worker(sym: str) -> None:
    st   = _strategies[sym]
    q    = _strategy_queues[sym]
    tc   = _get_trading_client()

    consec_bull      = 0
    last_bull_ts     = None     # timestamp of last bull sweep (for 1-min window)
    machine          = "WATCHING"  # WATCHING | PENDING_FILL | IN_POSITION
    entry_order_id   = None
    trail_order_id   = None
    trail_retry_at   = None     # when to retry placing trailing stop (halt recovery)
    trail_retries    = 0        # retry count — market-sell after 5 failed retries
    qty_in           = 0
    entry_fill_price = 0.0
    stop_pct         = 2.0
    trade_entry_ts   = None
    # Extended-hours server-side trailing state
    ext_trail_active = False    # True when _EXT_TRAIL sentinel was returned
    trail_high_px    = 0.0      # high-watermark price seen since entry
    # Phase 1/2 exit state
    exit_phase        = None      # None | "PHASE1" | "PHASE2"
    phase1_order_id   = None      # current active phase1 limit sell order ID
    phase1_order_ts   = None      # datetime when phase1 order was placed
    phase1_sold       = 0         # shares sold via phase1 fills so far
    limit_target_px   = 0.0       # entry_fill_price * (1 + min_sell_margin/100)

    _strat_log(sym, f"Strategy started — notional=${st['notional']} "
               f"n_consec={st['n_consec']} stop_high={st['stop_pct_high']}% "
               f"stop_low={st['stop_pct_low']}%")
    st["state"] = "WATCHING"

    while st["status"] == "running":
        # ── pull next sweep event (5-sec poll so we can check order status) ──
        try:
            event     = await asyncio.wait_for(q.get(), timeout=5.0)
            direction = event.get("direction", "")
            price     = float(event.get("price") or 0)
        except asyncio.TimeoutError:
            event = None; direction = ""; price = 0.0

        # ── PENDING_FILL: poll order until filled or cancelled ─────────────
        if machine == "PENDING_FILL" and entry_order_id:
            try:
                o = await asyncio.to_thread(tc.get_order_by_id, entry_order_id)
                if _ostatus(o) == "filled":
                    qty_in           = int(float(o.filled_qty or 0))
                    entry_fill_price = float(o.filled_avg_price or 0)
                    stop_pct         = st["stop_pct_high"] if entry_fill_price > 3 else st["stop_pct_low"]
                    trade_entry_ts   = datetime.now(ET)
                    entry_order_id   = None
                    _strat_log(sym, f"Entry filled {qty_in}sh @ ${entry_fill_price:.4f} "
                               f"| placing {stop_pct}% trailing stop")
                    await asyncio.sleep(1)
                    # ── Start two-phase exit ──────────────────────────────────────────────
                    limit_target_px = round(entry_fill_price * (1.0 + st["min_sell_margin"] / 100.0), 4)
                    machine = "IN_POSITION"
                    # Check if already above target → go straight to phase 2
                    cur_px_resp = None
                    try:
                        cur_px_resp = await asyncio.to_thread(
                            hist_client.get_stock_latest_trade,
                            StockLatestTradeRequest(symbol_or_symbols=sym))
                        cur_px_init = float(cur_px_resp[sym].price)
                    except Exception:
                        cur_px_init = entry_fill_price
                    if cur_px_init >= limit_target_px and _is_regular_hours():
                        _strat_log(sym, f"Already above target ${limit_target_px:.4f} → Phase2 trailing stop")
                        _oid = await _place_exit_order(tc, sym, qty_in, entry_fill_price, stop_pct, lambda m: _strat_log(sym, m))
                        if _oid == _EXT_TRAIL:
                            exit_phase = "PHASE2"; ext_trail_active = True; trail_high_px = cur_px_init
                            st["state"] = f"IN_POSITION P2 ext-trail high=${trail_high_px:.4f}"
                        elif _oid:
                            exit_phase = "PHASE2"; trail_order_id = _oid
                            st["state"] = "IN_POSITION Phase2 trail"
                        else:
                            exit_phase = "PHASE1"; trail_retry_at = datetime.now(ET) + timedelta(minutes=1)
                            trail_retries = 0; st["state"] = "IN_POSITION P1 (retry)"
                    else:
                        exit_phase = "PHASE1"
                        phase1_sold = 0; phase1_order_id = None; phase1_order_ts = None
                        chunk = min(st["base_qty"], qty_in - phase1_sold)
                        if chunk > 0:
                            try:
                                p1o = await asyncio.to_thread(tc.submit_order,
                                    LimitOrderRequest(symbol=sym, qty=chunk, side=OrderSide.SELL,
                                                      time_in_force=TimeInForce.DAY,
                                                      limit_price=limit_target_px))
                                phase1_order_id = str(p1o.id)
                                phase1_order_ts = datetime.now(ET)
                                _strat_log(sym, f"Phase1: limit sell {chunk}sh @ ${limit_target_px:.4f} "
                                                f"(target={st['min_sell_margin']}% above ${entry_fill_price:.4f}) "
                                                f"id={phase1_order_id[:8]}…")
                            except Exception as exc:
                                _strat_log(sym, f"Phase1 order failed: {exc}")
                        st["state"] = f"IN_POSITION Phase1 sold={phase1_sold}/{qty_in} target=${limit_target_px:.4f}"

                elif _ostatus(o) in ("cancelled", "expired", "done_for_day"):
                    _strat_log(sym, f"Entry order {_ostatus(o)} — resetting")
                    machine = "WATCHING"; st["state"] = "WATCHING"
                    entry_order_id = None; consec_bull = 0
            except Exception as exc:
                _strat_log(sym, f"Order poll error: {exc}")

        # ── IN_POSITION: poll trail stop; retry on halt/cancel ───────────────
        elif machine == "IN_POSITION":
            now_et = datetime.now(ET)

            # ── Fix 1: EOD force-close at 3:55 PM ────────────────────────────
            from datetime import time as _t
            if now_et.time() >= _t(15, 55):
                _strat_log(sym, "3:55 PM — EOD force-close")
                if trail_order_id:
                    try:
                        await asyncio.to_thread(tc.cancel_order_by_id, trail_order_id)
                    except Exception:
                        pass
                    trail_order_id = None
                await _exit_sell(tc, sym, qty_in, entry_fill_price,
                                 lambda m: _strat_log(sym, f"EOD: {m}"))
                machine = "WATCHING"; st["state"] = "WATCHING"
                qty_in = 0; trail_order_id = None; trail_retry_at = None
                trail_retries = 0; consec_bull = 0
                exit_phase = None; phase1_sold = 0; phase1_order_id = None

            # ── Fix 3/4: retry placing trail stop if missing ──────────────────
            elif trail_order_id is None and trail_retry_at is not None:
                if now_et >= trail_retry_at:
                    if trail_retries >= 5:
                        _strat_log(sym, f"Trail stop failed 5 times — force-close")
                        await _exit_sell(tc, sym, qty_in, entry_fill_price,
                                         lambda m: _strat_log(sym, m))
                        machine = "WATCHING"; st["state"] = "WATCHING"
                        qty_in = 0; trail_retry_at = None; trail_retries = 0; consec_bull = 0
                        exit_phase = None; phase1_sold = 0; phase1_order_id = None
                    else:
                        trail_retries += 1
                        _strat_log(sym, f"Retrying exit order (attempt {trail_retries}/5)")
                        _oid = await _place_exit_order(
                            tc, sym, qty_in, entry_fill_price, stop_pct,
                            lambda m: _strat_log(sym, m))
                        if _oid == _EXT_TRAIL:
                            ext_trail_active = True
                            trail_high_px    = entry_fill_price
                            trail_order_id   = None
                            trail_retry_at   = None
                            st["state"]      = f"IN_POSITION ext-trail high=${trail_high_px:.4f}"
                        elif _oid:
                            trail_order_id   = _oid
                            trail_retry_at   = None
                            ext_trail_active = False
                            st["state"]      = "IN_POSITION"
                        else:
                            trail_retry_at = now_et + timedelta(minutes=1)
                else:
                    secs = int((trail_retry_at - now_et).total_seconds())
                    st["state"] = f"IN_POSITION (halt? retry in {secs}s attempt {trail_retries+1}/5)"

            # ── Extended-hours server-side trailing: poll price, sell on drop ──
            elif ext_trail_active:
                try:
                    resp = await asyncio.to_thread(
                        hist_client.get_stock_latest_trade,
                        StockLatestTradeRequest(symbol_or_symbols=sym))
                    cur_px = float(resp[sym].price)
                    # Update high watermark
                    if cur_px > trail_high_px:
                        trail_high_px = cur_px
                    stop_px = round(trail_high_px * (1.0 - stop_pct / 100.0), 4)
                    st["state"] = (f"IN_POSITION ext-trail  "
                                   f"cur=${cur_px:.4f}  high=${trail_high_px:.4f}  "
                                   f"stop=${stop_px:.4f}")
                    if cur_px <= stop_px:
                        _strat_log(sym, f"Ext-trail stop triggered: "
                                        f"cur=${cur_px:.4f} <= stop=${stop_px:.4f} "
                                        f"(high=${trail_high_px:.4f}  trail={stop_pct}%)")
                        sold = await _exit_sell(tc, sym, qty_in, cur_px,
                                                lambda m: _strat_log(sym, m))
                        if sold:
                            pnl      = (cur_px - entry_fill_price) * qty_in
                            dur_secs = int((now_et - trade_entry_ts).total_seconds()) if trade_entry_ts else 0
                            st["trades"].append({
                                "entry_price": entry_fill_price,
                                "exit_price":  cur_px,
                                "qty":         qty_in,
                                "pnl":         round(pnl, 2),
                                "duration_s":  dur_secs,
                                "entry_ts":    trade_entry_ts.isoformat() if trade_entry_ts else "",
                                "exit_ts":     now_et.isoformat(),
                            })
                            _strat_log(sym, f"Ext-trail exit @ ${cur_px:.4f}  PnL=${pnl:+.2f}  ({dur_secs}s)")
                            ext_trail_active = False; trail_high_px = 0.0
                            qty_in = 0; trail_retries = 0
                            machine = "WATCHING"; st["state"] = "WATCHING"; consec_bull = 0
                            exit_phase = None; phase1_sold = 0; phase1_order_id = None
                except Exception as exc:
                    _strat_log(sym, f"Ext-trail poll error: {exc}")

            # ── Phase 1: drip limit sells below target ───────────────────────────
            elif exit_phase == "PHASE1":
                try:
                    cur_resp = await asyncio.to_thread(
                        hist_client.get_stock_latest_trade,
                        StockLatestTradeRequest(symbol_or_symbols=sym))
                    cur_px = float(cur_resp[sym].price)
                except Exception:
                    cur_px = 0.0

                remaining = qty_in - phase1_sold
                # Price crossed above target → switch to Phase 2
                if cur_px >= limit_target_px and cur_px > 0 and _is_regular_hours():
                    _strat_log(sym, f"Phase1→Phase2: price ${cur_px:.4f} >= target ${limit_target_px:.4f} "
                                    f"(sold {phase1_sold}/{qty_in} in P1)")
                    if phase1_order_id:
                        try: await asyncio.to_thread(tc.cancel_order_by_id, phase1_order_id)
                        except Exception: pass
                        phase1_order_id = None
                    remaining = qty_in - phase1_sold
                    if remaining > 0:
                        _oid = await _place_exit_order(tc, sym, remaining, entry_fill_price, stop_pct,
                                                        lambda m: _strat_log(sym, m))
                        if _oid == _EXT_TRAIL:
                            exit_phase = "PHASE2"; ext_trail_active = True; trail_high_px = cur_px
                            st["state"] = f"IN_POSITION P2 ext-trail high=${trail_high_px:.4f}"
                        elif _oid:
                            exit_phase = "PHASE2"; trail_order_id = _oid
                            st["state"] = "IN_POSITION Phase2 trail"
                        else:
                            trail_retry_at = now_et + timedelta(minutes=1); trail_retries = 0
                            st["state"] = "IN_POSITION P2 (trail retry)"
                    else:
                        # all already sold in phase1
                        machine = "WATCHING"; st["state"] = "WATCHING"; exit_phase = None; consec_bull = 0
                elif remaining <= 0:
                    # all sold in phase1
                    _strat_log(sym, f"Phase1 complete: all {qty_in}sh sold")
                    machine = "WATCHING"; st["state"] = "WATCHING"; exit_phase = None
                    qty_in = 0; phase1_order_id = None; consec_bull = 0
                else:
                    # Still in phase1 — manage active order
                    if phase1_order_id:
                        try:
                            p1o = await asyncio.to_thread(tc.get_order_by_id, phase1_order_id)
                            status = _ostatus(p1o)
                            if status == "filled":
                                filled_qty = int(float(p1o.filled_qty or 0))
                                phase1_sold += filled_qty
                                _strat_log(sym, f"Phase1 fill: {filled_qty}sh @ ${float(p1o.filled_avg_price or 0):.4f} "
                                                f"(total sold {phase1_sold}/{qty_in})")
                                phase1_order_id = None
                                # Place next chunk
                                next_chunk = min(st["base_qty"], qty_in - phase1_sold)
                                if next_chunk > 0:
                                    try:
                                        p1o2 = await asyncio.to_thread(tc.submit_order,
                                            LimitOrderRequest(symbol=sym, qty=next_chunk, side=OrderSide.SELL,
                                                              time_in_force=TimeInForce.DAY,
                                                              limit_price=limit_target_px))
                                        phase1_order_id = str(p1o2.id)
                                        phase1_order_ts = now_et
                                        _strat_log(sym, f"Phase1: next chunk {next_chunk}sh @ ${limit_target_px:.4f} "
                                                        f"id={phase1_order_id[:8]}…")
                                    except Exception as exc:
                                        _strat_log(sym, f"Phase1 next chunk failed: {exc}")
                            elif status in ("cancelled", "expired"):
                                _strat_log(sym, f"Phase1 order {status} — re-placing")
                                phase1_order_id = None; phase1_order_ts = None
                            elif phase1_order_ts and (now_et - phase1_order_ts).total_seconds() >= st["sell_order_timeout"] * 60:
                                # Timeout — cancel and re-place
                                _strat_log(sym, f"Phase1 order timeout ({st['sell_order_timeout']}min) — cancel+replace")
                                try: await asyncio.to_thread(tc.cancel_order_by_id, phase1_order_id)
                                except Exception: pass
                                phase1_order_id = None; phase1_order_ts = None
                        except Exception as exc:
                            _strat_log(sym, f"Phase1 poll error: {exc}")

                    if phase1_order_id is None and (qty_in - phase1_sold) > 0:
                        # No active order — place new chunk
                        chunk = min(st["base_qty"], qty_in - phase1_sold)
                        try:
                            p1o = await asyncio.to_thread(tc.submit_order,
                                LimitOrderRequest(symbol=sym, qty=chunk, side=OrderSide.SELL,
                                                  time_in_force=TimeInForce.DAY,
                                                  limit_price=limit_target_px))
                            phase1_order_id = str(p1o.id)
                            phase1_order_ts = now_et
                            _strat_log(sym, f"Phase1: placed {chunk}sh @ ${limit_target_px:.4f} id={phase1_order_id[:8]}…")
                        except Exception as exc:
                            _strat_log(sym, f"Phase1 place failed: {exc}")

                    st["state"] = (f"IN_POSITION Phase1 sold={phase1_sold}/{qty_in} "
                                   f"target=${limit_target_px:.4f} cur=${cur_px:.4f}")

            # ── Normal: poll active trail stop order (regular hours) ──────────
            elif trail_order_id:
                try:
                    o = await asyncio.to_thread(tc.get_order_by_id, trail_order_id)
                    if _ostatus(o) == "filled":
                        exit_price = float(o.filled_avg_price or 0)
                        pnl        = (exit_price - entry_fill_price) * qty_in
                        dur_secs   = int((now_et - trade_entry_ts).total_seconds()) if trade_entry_ts else 0
                        st["trades"].append({
                            "entry_price": entry_fill_price,
                            "exit_price":  exit_price,
                            "qty":         qty_in,
                            "pnl":         round(pnl, 2),
                            "duration_s":  dur_secs,
                            "entry_ts":    trade_entry_ts.isoformat() if trade_entry_ts else "",
                            "exit_ts":     now_et.isoformat(),
                        })
                        _strat_log(sym, f"Trailing stop filled @ ${exit_price:.4f}  PnL=${pnl:+.2f}  ({dur_secs}s)")
                        trail_order_id = None; qty_in = 0; trail_retries = 0
                        machine = "WATCHING"; st["state"] = "WATCHING"; consec_bull = 0
                        exit_phase = None; phase1_sold = 0; phase1_order_id = None

                    elif _ostatus(o) in ("cancelled", "expired"):
                        _strat_log(sym, f"Trail order {_ostatus(o)} — retrying in 1 min (possible halt)")
                        trail_order_id = None
                        trail_retry_at = now_et + timedelta(minutes=1)
                except Exception as exc:
                    _strat_log(sym, f"IN_POSITION poll error: {exc}")

        # ── WATCHING: regular hours only, block entries after 3:45 PM ────────
        if machine == "WATCHING" and direction and _is_regular_hours():
            from datetime import time as _t
            if datetime.now(ET).time() >= _t(15, 45):
                pass  # Fix 2: no new entries in last 15 min of session
            elif direction == "bull":
                now_ts = datetime.now(ET)
                if last_bull_ts and (now_ts - last_bull_ts).total_seconds() > 60:
                    if consec_bull > 0:
                        _strat_log(sym, f"Bull streak expired (>{int((now_ts-last_bull_ts).total_seconds())}s gap) — reset")
                    consec_bull = 0
                consec_bull  += 1
                last_bull_ts  = now_ts
                st["consec_bull"] = consec_bull
                _strat_log(sym, f"Bull sweep {consec_bull}/{st['n_consec']} @ ${price:.4f}")
                if consec_bull >= st["n_consec"] and price > 0:
                    qty = math.floor(st["notional"] / price)
                    if qty < 1:
                        _strat_log(sym, f"Skipping — qty=0 at ${price:.4f}")
                        consec_bull = 0; st["consec_bull"] = 0
                    else:
                        try:
                            o = await asyncio.to_thread(
                                tc.submit_order,
                                MarketOrderRequest(
                                    symbol=sym, qty=qty, side=OrderSide.BUY,
                                    time_in_force=TimeInForce.DAY,
                                ),
                            )
                            entry_order_id = str(o.id)
                            machine        = "PENDING_FILL"
                            st["state"]    = "PENDING_FILL"
                            consec_bull    = 0; st["consec_bull"] = 0
                            _strat_log(sym, f"Entry MKT order: {qty}sh id={entry_order_id[:8]}… (sweep px=${price:.4f})")
                        except Exception as exc:
                            _strat_log(sym, f"Entry order FAILED: {exc}")
                            consec_bull = 0; st["consec_bull"] = 0
            elif direction == "bear":
                consec_bull = 0; last_bull_ts = None; st["consec_bull"] = 0

    # ── Strategy stopped — cancel orders, close any open position ─────────
    for oid in [entry_order_id, trail_order_id, phase1_order_id]:
        if oid:
            try:
                await asyncio.to_thread(tc.cancel_order_by_id, oid)
                _strat_log(sym, f"Cancelled order {oid[:8]}… on stop")
            except Exception:
                pass
    exit_phase = None
    # Fix 5: close position if still open when strategy is stopped
    # Works in regular hours (market order) AND extended hours (limit order)
    if machine == "IN_POSITION" and qty_in > 0:
        ref_px = trail_high_px if ext_trail_active and trail_high_px > 0 else entry_fill_price
        await _exit_sell(tc, sym, qty_in, ref_px,
                         lambda m: _strat_log(sym, f"Stop-close: {m}"))
    ext_trail_active = False; trail_high_px = 0.0
    _strat_log(sym, "Strategy stopped")
    if sym in _strategy_queues:
        del _strategy_queues[sym]


async def eod_saver() -> None:
    """
    Background task: once per trading day at 4:00 PM ET, save the daily
    dollar-volume totals so tomorrow they appear as momentum tickers (🔥).
    """
    saved_date: str | None     = None
    strat_eod_date: str | None = None
    while True:
        await asyncio.sleep(30)
        now_et = datetime.now(ET)
        today  = now_et.strftime("%Y-%m-%d")
        # Save daily volume at 4:00 PM
        if now_et.hour == 16 and now_et.minute == 0 and saved_date != today:
            await asyncio.to_thread(_save_daily_volume_sync)
            saved_date = today
        # Stop all strategies + save sweep board at 8:00 PM (end of extended hours)
        if now_et.hour == 20 and now_et.minute == 0 and strat_eod_date != today:
            for sym, st in list(_strategies.items()):
                if st["status"] == "running":
                    st["status"]    = "eod"
                    st["stopped_at"] = datetime.now(ET).isoformat()
                    _strat_log(sym, "Auto-stopped at 8 PM ET (end of extended hours)")
            # Save and clear sweep board EOD snapshot
            await asyncio.to_thread(_sb_save_eod)
            strat_eod_date = today


# ── Alpaca Trading ────────────────────────────────────────────────────────────
TRADING_KEY    = os.getenv("ALPACA_TRADING_API_KEY", os.getenv("ALPACA_API_KEY", ""))
TRADING_SECRET = os.getenv("ALPACA_TRADING_SECRET_KEY", os.getenv("ALPACA_SECRET_KEY", ""))

_trading_client: "TradingClient | None" = None

def _get_trading_client() -> "TradingClient":
    global _trading_client
    if _trading_client is None:
        if not _TRADING_AVAILABLE:
            raise RuntimeError("alpaca-py trading module not installed")
        _trading_client = TradingClient(TRADING_KEY, TRADING_SECRET, paper=False)
    return _trading_client

# order_id → placed_at epoch seconds (for 5-min auto-cancel watcher)
_order_expiry: dict[str, float] = {}
ORDER_LIFETIME_SECS = 5 * 60  # 5 minutes


async def _order_expiry_watcher() -> None:
    """Background task: cancel orders that are still open after 5 minutes."""
    while True:
        await asyncio.sleep(30)
        if not _order_expiry:
            continue
        now = time.time()
        expired = [oid for oid, placed_at in list(_order_expiry.items())
                   if now - placed_at >= ORDER_LIFETIME_SECS]
        for oid in expired:
            try:
                tc = _get_trading_client()
                await asyncio.to_thread(tc.cancel_order_by_id, oid)
                print(f"[trading] auto-cancelled expired order {oid}")
            except Exception as exc:
                print(f"[trading] auto-cancel {oid} failed: {exc}")
            _order_expiry.pop(oid, None)


def _position_to_dict(p) -> dict:
    return {
        "symbol":         str(p.symbol),
        "qty":            float(p.qty),
        "avg_entry":      float(p.avg_entry_price),
        "market_value":   float(p.market_value or 0),
        "current_price":  float(p.current_price or 0),
        "unrealized_pl":  float(p.unrealized_pl or 0),
        "unrealized_plpc":float(p.unrealized_plpc or 0),
        "side":           str(p.side),
    }


def _order_to_dict(o) -> dict:
    return {
        "id":          str(o.id),
        "symbol":      str(o.symbol),
        "side":        str(o.side),
        "qty":         float(o.qty or 0),
        "filled_qty":  float(o.filled_qty or 0),
        "limit_price": float(o.limit_price or 0),
        "status":      str(o.status),
        "created_at":  o.created_at.isoformat() if o.created_at else "",
    }


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
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Trade routes ──────────────────────────────────────────────────────────────

@app.post("/trade/buy")
async def trade_buy(request: Request) -> JSONResponse:
    body          = await request.json()
    sym           = body.get("sym", "").upper().strip()
    notional      = float(body.get("notional", 100))
    offset_pct    = float(body.get("offset_pct", 1.0))
    market_price  = float(body.get("market_price", 0))

    if not sym or not market_price:
        return JSONResponse({"ok": False, "error": "sym and market_price required"}, status_code=400)

    limit_price = round(market_price * (1 - offset_pct / 100), 2)
    qty = int(notional / limit_price)

    if qty < 1:
        return JSONResponse({"ok": False,
            "error": f"Notional ${notional:.0f} too small for 1 share at ${limit_price:.2f}"})

    try:
        tc = _get_trading_client()
        order = await asyncio.to_thread(
            tc.submit_order,
            LimitOrderRequest(
                symbol=sym, qty=qty, side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY, limit_price=limit_price,
                extended_hours=True,
            )
        )
        oid = str(order.id)
        _order_expiry[oid] = time.time()
        print(f"[trading] BUY {qty} {sym} @ ${limit_price:.2f} (id={oid})")
        return JSONResponse({"ok": True, "order_id": oid,
                             "limit_price": limit_price, "qty": qty, "sym": sym})
    except Exception as exc:
        print(f"[trading] BUY failed: {exc}")
        return JSONResponse({"ok": False, "error": str(exc)})


@app.post("/trade/sell")
async def trade_sell(request: Request) -> JSONResponse:
    body         = await request.json()
    sym          = body.get("sym", "").upper().strip()
    offset_pct   = float(body.get("offset_pct", 1.0))
    market_price = float(body.get("market_price", 0))
    qty          = int(body.get("qty", 0))

    if not sym or not market_price or qty < 1:
        return JSONResponse({"ok": False, "error": "sym, market_price, and qty required"}, status_code=400)

    limit_price = round(market_price * (1 + offset_pct / 100), 2)

    try:
        tc = _get_trading_client()
        order = await asyncio.to_thread(
            tc.submit_order,
            LimitOrderRequest(
                symbol=sym, qty=qty, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY, limit_price=limit_price,
                extended_hours=True,
            )
        )
        oid = str(order.id)
        _order_expiry[oid] = time.time()
        print(f"[trading] SELL {qty} {sym} @ ${limit_price:.2f} (id={oid})")
        return JSONResponse({"ok": True, "order_id": oid,
                             "limit_price": limit_price, "qty": qty, "sym": sym})
    except Exception as exc:
        print(f"[trading] SELL failed: {exc}")
        return JSONResponse({"ok": False, "error": str(exc)})


@app.post("/trade/close/{sym}")
async def trade_close(sym: str) -> JSONResponse:
    sym = sym.upper().strip()
    try:
        tc = _get_trading_client()
        resp = await asyncio.to_thread(tc.close_position, sym)
        print(f"[trading] CLOSE {sym}")
        return JSONResponse({"ok": True, "sym": sym, "order_id": str(resp.id)})
    except Exception as exc:
        print(f"[trading] CLOSE {sym} failed: {exc}")
        return JSONResponse({"ok": False, "error": str(exc)})


@app.post("/trade/cancel/{order_id}")
async def trade_cancel(order_id: str) -> JSONResponse:
    try:
        tc = _get_trading_client()
        await asyncio.to_thread(tc.cancel_order_by_id, order_id)
        _order_expiry.pop(order_id, None)
        print(f"[trading] CANCEL order {order_id}")
        return JSONResponse({"ok": True, "order_id": order_id})
    except Exception as exc:
        print(f"[trading] CANCEL {order_id} failed: {exc}")
        return JSONResponse({"ok": False, "error": str(exc)})


@app.get("/trade/positions")
async def get_positions() -> JSONResponse:
    try:
        tc = _get_trading_client()
        positions = await asyncio.to_thread(tc.get_all_positions)
        return JSONResponse({"positions": [_position_to_dict(p) for p in positions]})
    except Exception as exc:
        return JSONResponse({"positions": [], "error": str(exc)})


@app.get("/trade/orders")
async def get_orders() -> JSONResponse:
    try:
        tc = _get_trading_client()
        orders = await asyncio.to_thread(
            tc.get_orders,
            GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=50)
        )
        now = time.time()
        result = []
        for o in orders:
            d = _order_to_dict(o)
            placed = _order_expiry.get(str(o.id))
            d["expires_in"] = max(0, int(ORDER_LIFETIME_SECS - (now - placed))) if placed else None
            result.append(d)
        return JSONResponse({"orders": result})
    except Exception as exc:
        return JSONResponse({"orders": [], "error": str(exc)})


@app.get("/trade/filled_orders")
async def get_filled_orders() -> JSONResponse:
    try:
        tc = _get_trading_client()
        today_et = datetime.now(ET).replace(hour=0, minute=0, second=0, microsecond=0)
        after_utc = today_et.astimezone(timezone.utc)
        orders = await asyncio.to_thread(
            tc.get_orders,
            GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                after=after_utc,
                limit=200,
            )
        )
        filled = [o for o in orders if _ostatus(o) == "filled"]
        rows = []
        for o in filled:
            rows.append({
                "id":         str(o.id)[:8],
                "sym":        str(o.symbol),
                "side":       o.side.value if hasattr(o.side, "value") else str(o.side),
                "qty":        float(o.filled_qty or 0),
                "price":      float(o.filled_avg_price or 0),
                "total":      float(o.filled_qty or 0) * float(o.filled_avg_price or 0),
                "submitted":  o.submitted_at.isoformat() if o.submitted_at else "",
                "filled_at":  o.filled_at.isoformat() if o.filled_at else "",
                "type":       o.order_type.value if hasattr(o.order_type, "value") else str(o.order_type),
            })
        # Per-symbol PnL: match buys and sells
        from collections import defaultdict
        syms_pnl = defaultdict(lambda: {"buy_val": 0.0, "sell_val": 0.0,
                                          "buy_qty": 0.0, "sell_qty": 0.0})
        for r in rows:
            s = syms_pnl[r["sym"]]
            if r["side"] == "buy":
                s["buy_val"] += r["total"]; s["buy_qty"] += r["qty"]
            else:
                s["sell_val"] += r["total"]; s["sell_qty"] += r["qty"]
        pnl_summary = []
        for sym, s in syms_pnl.items():
            if s["sell_qty"] > 0 and s["buy_qty"] > 0:
                matched = min(s["sell_qty"], s["buy_qty"])
                avg_buy  = s["buy_val"]  / s["buy_qty"]  if s["buy_qty"]  else 0
                avg_sell = s["sell_val"] / s["sell_qty"] if s["sell_qty"] else 0
                pnl = (avg_sell - avg_buy) * matched
                pnl_summary.append({"sym": sym, "pnl": round(pnl, 2),
                                     "avg_buy": round(avg_buy, 4),
                                     "avg_sell": round(avg_sell, 4),
                                     "matched_qty": int(matched)})
        return JSONResponse({"orders": rows, "pnl_summary": pnl_summary})
    except Exception as exc:
        return JSONResponse({"orders": [], "pnl_summary": [], "error": str(exc)})


@app.get("/trade/account")
async def get_account() -> JSONResponse:
    try:
        tc = _get_trading_client()
        acc = await asyncio.to_thread(tc.get_account)
        return JSONResponse({
            "equity":       float(acc.equity or 0),
            "cash":         float(acc.cash or 0),
            "buying_power": float(acc.buying_power or 0),
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)})


# ── Strategy endpoints ────────────────────────────────────────────────────────

@app.post("/strategy/start")
async def strategy_start(request: Request) -> JSONResponse:
    body       = await request.json()
    sym        = body.get("sym", "").upper().strip()
    if not sym:
        return JSONResponse({"ok": False, "error": "sym required"}, status_code=400)
    if sym in _strategies and _strategies[sym]["status"] == "running":
        return JSONResponse({"ok": False, "error": f"{sym} strategy already running"})

    st = {
        "sym":           sym,
        "status":        "running",
        "state":         "WATCHING",
        "started_at":    datetime.now(ET).isoformat(),
        "stopped_at":    None,
        "notional":         float(body.get("notional", 1000)),
        "n_consec":         int(body.get("n_consec", 2)),
        "trail_pct":        float(body.get("trail_pct", 2.0)),   # Phase-2 trailing stop %
        "stop_pct_high":    float(body.get("trail_pct", body.get("stop_pct_high", 2.0))),
        "stop_pct_low":     float(body.get("trail_pct", body.get("stop_pct_low",  2.0))),
        "min_sell_margin":  float(body.get("min_sell_margin", 2.0)),
        "base_qty":         int(body.get("base_qty", 10)),
        "sell_order_timeout": float(body.get("sell_order_timeout", 2.0)),
        "consec_bull":   0,
        "trades":        [],
        "log":           [],
    }
    _strategies[sym]       = st
    _strategy_queues[sym]  = asyncio.Queue()
    asyncio.create_task(_strategy_worker(sym))
    print(f"[strategy] started for {sym}")
    return JSONResponse({"ok": True, "sym": sym})


@app.post("/strategy/stop/{sym}")
async def strategy_stop(sym: str) -> JSONResponse:
    sym = sym.upper().strip()
    st  = _strategies.get(sym)
    if not st:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    st["status"]    = "stopped"
    st["stopped_at"] = datetime.now(ET).isoformat()
    return JSONResponse({"ok": True, "sym": sym})


@app.get("/strategy/list")
async def strategy_list() -> JSONResponse:
    result = []
    for sym, st in _strategies.items():
        trades    = st["trades"]
        total_pnl = sum(t["pnl"] for t in trades)
        wins      = sum(1 for t in trades if t["pnl"] > 0)
        result.append({
            "sym":         sym,
            "status":      st["status"],
            "state":       st["state"],
            "started_at":  st["started_at"],
            "stopped_at":  st["stopped_at"],
            "notional":    st["notional"],
            "n_consec":    st["n_consec"],
            "stop_pct_high": st["stop_pct_high"],
            "stop_pct_low":  st["stop_pct_low"],
            "consec_bull": st["consec_bull"],
            "trades_today": len(trades),
            "wins_today":   wins,
            "total_pnl":   round(total_pnl, 2),
            "log_tail":    st["log"][-30:],
        })
    return JSONResponse({"strategies": result})


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
        "symbol":     data.symbol,
        "price":      float(data.price),
        "size":       int(data.size or 0),
        "time":       ts.strftime("%H:%M:%S.") + f"{ts.microsecond // 1000:03d}",
        "ts_ms":      ms,
        "_ts":        ts,
        "_agg":       (data.symbol, float(data.price), int(data.size or 0), ms),
        "conditions": list(data.conditions) if data.conditions else [],
    }
    try:
        trade_queue.put_nowait(trade)
    except Exception:
        pass


class _ThrottledTradeStream(StockDataStream):
    """StockDataStream with backoff retry and clean exit on connection-limit errors."""
    _connection_limit_hit: bool = False

    async def _run_forever(self) -> None:
        # Mirror the library's own startup gate: wait until a subscription exists
        self._loop = asyncio.get_running_loop()
        while not any(
            v for k, v in self._handlers.items()
            if k not in ("cancelErrors", "corrections")
        ):
            if not self._stop_stream_queue.empty():
                self._stop_stream_queue.get(timeout=1)
                return
            await asyncio.sleep(0)

        self._should_run = True
        self._running    = False
        backoff = 5

        while True:
            try:
                if not self._should_run:
                    return
                if not self._running:
                    await self._start_ws()
                    await self._send_subscribe_msg()
                    self._running = True
                await self._consume()
                backoff = 5
            except ValueError as exc:
                if "connection limit" in str(exc).lower():
                    print("[trade-stream] connection limit — will retry in 60s")
                    self._connection_limit_hit = True
                    await self.close()  # close the leaked socket from the failed auth
                    return          # exit cleanly; asyncio.run() closes loop
                self._running = False
                print(f"[trade-stream] {exc} — retry in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except Exception as exc:
                await self.close()
                self._running = False
                print(f"[trade-stream] {exc} — retry in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                await asyncio.sleep(0)


class _ThrottledNewsStream(NewsDataStream):
    """NewsDataStream with backoff retry and clean exit on connection-limit errors."""
    _connection_limit_hit: bool = False

    async def _run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        while not any(
            v for k, v in self._handlers.items()
            if k not in ("cancelErrors", "corrections")
        ):
            if not self._stop_stream_queue.empty():
                self._stop_stream_queue.get(timeout=1)
                return
            await asyncio.sleep(0)

        self._should_run = True
        self._running    = False
        backoff = 5

        while True:
            try:
                if not self._should_run:
                    return
                if not self._running:
                    await self._start_ws()
                    await self._send_subscribe_msg()
                    self._running = True
                await self._consume()
                backoff = 5
            except ValueError as exc:
                if "connection limit" in str(exc).lower():
                    print("[news-stream] connection limit — will retry in 60s")
                    self._connection_limit_hit = True
                    await self.close()  # close the leaked socket from the failed auth
                    return
                self._running = False
                print(f"[news-stream] {exc} — retry in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except Exception as exc:
                await self.close()
                self._running = False
                print(f"[news-stream] {exc} — retry in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                await asyncio.sleep(0)


def run_trade_stream() -> None:
    while True:
        stream = _ThrottledTradeStream(API_KEY, SECRET_KEY, feed=DataFeed.SIP)
        stream.subscribe_trades(handle_trade, "*")
        stream.run()
        delay = 60 if stream._connection_limit_hit else 10
        print(f"[trade-stream] sleeping {delay}s before reconnect")
        time.sleep(delay)


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
    # ── News Intelligence: classify and persist ───────────────────────────────
    try:
        headline = article.get("headline", "")
        symbols  = article.get("symbols", [])
        category, importance, classified_by = _ni_classify_rules(headline, symbols)
        if category is None:
            # Text rules couldn't classify — save as PENDING, fire Haiku in background thread
            _ni_save(article, "PENDING", "LOW", "PENDING_API")
            if _ANTHROPIC_OK:
                alpaca_id = str(article.get("id", ""))
                threading.Thread(
                    target=_ni_classify_single_sync,
                    args=(alpaca_id,),
                    daemon=True
                ).start()
        else:
            _ni_save(article, category, importance, classified_by)
    except Exception as _ni_exc:
        print(f"[news-intel] live save error: {_ni_exc}")


def run_news_stream() -> None:
    while True:
        stream = _ThrottledNewsStream(API_KEY, SECRET_KEY)
        stream.subscribe_news(handle_news, "*")
        stream.run()
        delay = 60 if stream._connection_limit_hit else 10
        print(f"[news-stream] sleeping {delay}s")
        time.sleep(delay)


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
            for t in batch:
                agg = t.pop("_agg", None)
                if agg:
                    aggregate_tick(*agg)
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


# ── Options data ─────────────────────────────────────────────────────────────
def _fetch_options_sync(sym: str) -> dict:
    """
    Fetch options snapshot data from Alpaca Options API.
    Returns IV rank, P/C ratio, top strikes by OI, and max pain estimate.
    Uses REST directly since alpaca-py OptionHistoricalDataClient may not be
    installed — falls back gracefully if the endpoint is unavailable.
    """
    import statistics

    base = "https://data.alpaca.markets/v1beta1"
    headers = {
        "APCA-API-KEY-ID":     API_KEY,
        "APCA-API-SECRET-KEY": SECRET_KEY,
    }

    # 1. Fetch option chain snapshot — paginate to get up to 500 contracts
    all_snapshots: dict = {}
    page_token = None
    for _ in range(5):  # max 5 pages
        params: dict = {"limit": 100}
        if page_token:
            params["page_token"] = page_token
        try:
            resp = req_lib.get(
                f"{base}/options/snapshots/{sym}",
                headers=headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            if not all_snapshots:
                return {"error": f"Options API error: {exc}"}
            break
        batch = raw.get("snapshots", {}) or {}
        all_snapshots.update(batch)
        page_token = raw.get("next_page_token")
        if not page_token:
            break

    print(f"[options] {sym}: fetched {len(all_snapshots)} contracts")
    if not all_snapshots:
        return {"error": "No options contracts found — check subscription tier"}

    calls, puts = [], []
    for contract_sym, snap in all_snapshots.items():
        greeks  = snap.get("greeks") or {}
        details = snap.get("details") or {}
        day     = snap.get("dailyBar") or {}

        # Alpaca uses "contractType" (not "type")
        option_type = details.get("contractType", "").lower()  # "call" or "put"
        strike      = details.get("strikePrice")
        # OI lives in details, not snap root
        oi     = details.get("openInterest") or 0
        volume = day.get("v") or 0
        iv     = greeks.get("impliedVolatility")

        if not strike or option_type not in ("call", "put"):
            continue

        try:
            strike_f = float(strike)
        except (TypeError, ValueError):
            continue

        entry = {"strike": strike_f, "type": option_type, "oi": int(oi), "volume": int(volume), "iv": iv}
        if option_type == "call":
            calls.append(entry)
        else:
            puts.append(entry)

    print(f"[options] {sym}: {len(calls)} calls, {len(puts)} puts after parse")

    # 2. P/C ratio (by OI)
    total_call_oi = sum(c["oi"] for c in calls)
    total_put_oi  = sum(p["oi"] for p in puts)
    pc_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None

    # 3. Max pain — strike where combined OI loss is minimised
    all_strikes = sorted({e["strike"] for e in calls + puts})
    max_pain = None
    if all_strikes:
        min_pain = float("inf")
        for test_price in all_strikes:
            pain = sum(max(0, test_price - c["strike"]) * c["oi"] for c in calls) + \
                   sum(max(0, p["strike"] - test_price) * p["oi"] for p in puts)
            if pain < min_pain:
                min_pain = pain
                max_pain = test_price

    # 4. IV rank / percentile (rough — across all contracts)
    ivs = [e["iv"] for e in calls + puts if e["iv"] is not None]
    iv_rank = None
    iv_percentile = None
    if ivs:
        iv_min, iv_max = min(ivs), max(ivs)
        avg_iv = statistics.mean(ivs)
        iv_rank       = round((avg_iv - iv_min) / (iv_max - iv_min) * 100, 1) if iv_max > iv_min else 50.0
        iv_percentile = round(sum(1 for v in ivs if v < avg_iv) / len(ivs) * 100, 1)

    # 5. Top strikes by OI (top 8 calls + puts combined)
    combined = sorted(calls + puts, key=lambda x: x["oi"], reverse=True)[:8]
    combined.sort(key=lambda x: (x["strike"], x["type"]))

    if not calls and not puts:
        return {"error": f"Contracts found ({len(all_snapshots)}) but none could be parsed — field mapping issue"}

    return {
        "sym":           sym,
        "iv_rank":       iv_rank,
        "iv_percentile": iv_percentile,
        "pc_ratio":      pc_ratio,
        "max_pain":      max_pain,
        "top_strikes":   combined,
        "call_oi":       total_call_oi,
        "put_oi":        total_put_oi,
        "_debug":        {"total_contracts": len(all_snapshots), "calls": len(calls), "puts": len(puts)},
    }


@app.get("/options/{sym}")
async def get_options(sym: str) -> JSONResponse:
    sym = sym.upper().strip()
    try:
        data = await asyncio.to_thread(_fetch_options_sync, sym)
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"sym": sym, "error": str(exc)})


# ── Alert log (SQLite — permanent storage, no OneDrive locking issues) ────────
_alert_write_lock = threading.Lock()   # serialises concurrent /log/alert POSTs

def _write_alert(body: dict) -> bool:
    """Insert one alert row into SQLite.
    Threading lock + 90-second dedup prevent race conditions when multiple
    browser tabs or rapid requests arrive simultaneously.
    Returns True if the row was inserted, False if it was a duplicate.
    """
    with _alert_write_lock:   # ← serialise: only one thread can check+write at a time
        alert_type = body.get("type", "alert")
        sym        = body.get("sym")

        with sqlite3.connect(ALERTS_DB) as conn:
            # ── Dedup guard ──────────────────────────────────────────────────
            if alert_type in ("sweep", "vol", "alert"):
                from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                cutoff = (_dt.now(_tz.utc) - _td(seconds=90)).strftime("%Y-%m-%dT%H:%M:%S")
                val  = body.get("value1m") or 0
                dlt  = body.get("delta")   or 0
                dirn = body.get("direction", "")
                dup  = conn.execute(
                    "SELECT id FROM alerts "
                    "WHERE type=? AND sym=? AND direction=? "
                    "  AND ABS(COALESCE(value1m,0) - ?) < 500 "
                    "  AND ts >= ? "
                    "LIMIT 1",
                    (alert_type, sym, dirn, val, cutoff),
                ).fetchone()
                if dup:
                    return False   # silent dedup

            conn.execute(
                "INSERT INTO alerts (ts,sym,tag,delta,value1m,vwap1m,vwap2m,cnt1m,direction,type) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    body.get("ts"),
                    sym,
                    body.get("tag", "new"),
                    body.get("delta"),
                    body.get("value1m"),
                    body.get("vwap1m"),
                    body.get("vwap2m"),
                    body.get("cnt1m"),
                    body.get("direction", ""),
                    alert_type,
                ),
            )
            conn.commit()
            return True


@app.post("/log/alert")
async def log_alert(request: Request) -> JSONResponse:
    try:
        body     = await request.json()
        inserted = await asyncio.to_thread(_write_alert, body)
        sym      = (body.get("sym") or "").upper()

        if body.get("type") == "sweep":
            # Fan out to active strategy listener
            if sym in _strategy_queues:
                try:
                    _strategy_queues[sym].put_nowait({
                        "direction": body.get("direction", ""),
                        "price":     float(body.get("vwap1m") or 0),
                    })
                except asyncio.QueueFull:
                    pass

            # Update sweep board (only on genuine insert — skip dedup hits)
            if inserted:
                updated_row = _update_sweep_board(body)
                if updated_row:
                    await broadcast(json.dumps({
                        "type": "sweep_board_update",
                        "row":  updated_row,
                    }))

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
                    "SELECT * FROM alerts ORDER BY id DESC LIMIT 1000"
                ).fetchall()
            return [dict(r) for r in rows]

        alerts = await asyncio.to_thread(_read)
        return JSONResponse({"alerts": alerts})
    except Exception as exc:
        print(f"[alert-db] ❌ read failed: {exc}")
        return JSONResponse({"alerts": [], "error": str(exc)})


# ── Sweep Board endpoints ─────────────────────────────────────────────────────

@app.get("/sweep-board")
async def get_sweep_board() -> JSONResponse:
    """Return current day's sweep tally, filtered by dollar threshold, sorted by sweep count."""
    with _sweep_board_lock:
        rows = list(_sweep_board.values())

    result = []
    for row in rows:
        cap_tier    = row["cap_tier"]
        total_value = row["total_value"]
        # Apply threshold filter
        if total_value < _sb_threshold(cap_tier):
            continue
        result.append(_sb_row_to_dict(row))

    result.sort(key=lambda r: r["total_sweeps"], reverse=True)
    return JSONResponse({
        "ok":            True,
        "rows":          result,
        "total_tickers": len(result),
        "as_of":         datetime.now(ET).isoformat(),
    })


@app.post("/sweep-board/reset")
async def reset_sweep_board() -> JSONResponse:
    """Manually save EOD snapshot and clear the board (admin use)."""
    await asyncio.to_thread(_sb_save_eod)
    return JSONResponse({"ok": True, "msg": "Board saved and cleared"})


@app.get("/sweep-board/history/{date}")
async def get_sweep_board_history(date: str) -> JSONResponse:
    """Return a saved daily snapshot (date format: YYYY-MM-DD)."""
    try:
        f = SWEEP_BOARD_DIR / f"sweep_board_{date}.json"
        if not f.exists():
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        data = json.loads(f.read_text(encoding="utf-8"))
        return JSONResponse({"ok": True, **data})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


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
    """Re-fetch missing market caps from Yahoo Finance then Finnhub."""
    missing_before = sum(1 for m in SYM_META.values() if not m.get("market_cap"))
    def _enrich_all():
        _enrich_with_yfinance()
        _enrich_with_finnhub()
    threading.Thread(target=_enrich_all, daemon=True).start()
    return JSONResponse({"ok": True, "missing_before": missing_before})


@app.get("/breaking-news")
async def get_breaking_news() -> JSONResponse:
    """Return breaking news headlines from breaking_news.json (reloaded live — no restart needed)."""
    try:
        if BREAKING_NEWS_FILE.exists():
            items = json.loads(BREAKING_NEWS_FILE.read_text(encoding="utf-8"))
            if isinstance(items, list):
                return JSONResponse({"items": [str(s).strip() for s in items if str(s).strip()]})
        return JSONResponse({"items": []})
    except Exception as exc:
        return JSONResponse({"items": [], "error": str(exc)})


@app.get("/tags")
async def get_tags() -> JSONResponse:
    """Return all stock tags (Google Sheet + user-added merged)."""
    merged: dict = {}
    for sym, data in STOCK_TAGS.items():
        entry = dict(data)
        if sym in USER_TAGS and USER_TAGS[sym]:
            gs = set(data.get("tags", []))
            entry["tags"] = data.get("tags", []) + [t for t in USER_TAGS[sym] if t not in gs]
        merged[sym] = entry
    for sym, utags in USER_TAGS.items():
        if sym not in merged and utags:
            merged[sym] = {"tags": utags}
    return JSONResponse({"tags": merged})


@app.get("/tags/user")
async def get_user_tags() -> JSONResponse:
    """Return user-added tags only."""
    return JSONResponse({"user_tags": USER_TAGS})


@app.post("/tags/user/add")
async def add_user_tag(request: Request) -> JSONResponse:
    body = await request.json()
    sym  = body.get("sym", "").upper().strip()
    tag  = body.get("tag", "").strip().lower()
    if not sym or not tag:
        return JSONResponse({"ok": False, "error": "sym and tag required"}, status_code=400)
    if sym not in USER_TAGS:
        USER_TAGS[sym] = []
    if tag not in USER_TAGS[sym]:
        USER_TAGS[sym].append(tag)
        await asyncio.to_thread(_save_user_tags)
    return JSONResponse({"ok": True, "sym": sym, "tags": USER_TAGS[sym]})


@app.post("/tags/user/remove")
async def remove_user_tag(request: Request) -> JSONResponse:
    body = await request.json()
    sym  = body.get("sym", "").upper().strip()
    tag  = body.get("tag", "").strip().lower()
    if sym in USER_TAGS and tag in USER_TAGS[sym]:
        USER_TAGS[sym].remove(tag)
        if not USER_TAGS[sym]:
            del USER_TAGS[sym]
        await asyncio.to_thread(_save_user_tags)
    return JSONResponse({"ok": True, "sym": sym, "tags": USER_TAGS.get(sym, [])})


@app.get("/tags/{sym}")
async def get_tag(sym: str) -> JSONResponse:
    """Return tags for a specific symbol."""
    sym = sym.upper().strip()
    return JSONResponse({"sym": sym, "data": STOCK_TAGS.get(sym, {})})


@app.post("/tags/refresh")
async def refresh_tags() -> JSONResponse:
    """Manually trigger a Google Sheet sync."""
    await asyncio.to_thread(_sync_stock_tags)
    return JSONResponse({"ok": True, "count": len(STOCK_TAGS)})


@app.get("/yesterday/top")
async def get_yesterday_top() -> JSONResponse:
    """Return yesterday's top-50 dollar-volume tickers for momentum display (🔥)."""
    return JSONResponse({"tickers": list(YESTERDAY_TOP50), "count": len(YESTERDAY_TOP50)})


@app.post("/yesterday/save")
async def save_yesterday_now() -> JSONResponse:
    """Manually trigger EOD volume save (useful for testing or early close days)."""
    await asyncio.to_thread(_save_daily_volume_sync)
    return JSONResponse({"ok": True, "saved": len(daily_volume)})


# ── News Intelligence API ─────────────────────────────────────────────────────

@app.get("/news-intel/articles")
async def ni_get_articles() -> JSONResponse:
    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM news_intel
                ORDER BY published_at DESC
                LIMIT 200
            """).fetchall()
        articles = [dict(r) for r in rows]
        for a in articles:
            try:
                a["symbols"] = json.loads(a.get("symbols") or "[]")
            except Exception:
                a["symbols"] = []
        return JSONResponse({"articles": articles, "total": len(articles)})
    except Exception as e:
        return JSONResponse({"articles": [], "error": str(e)})


@app.post("/news-intel/classify/{article_id}")
async def ni_classify(article_id: int) -> JSONResponse:
    """Re-classify a single article via Haiku API."""
    if not _ANTHROPIC_OK:
        return JSONResponse({"error": "Anthropic API not available. Set ANTHROPIC_API_KEY in .env"})
    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM news_intel WHERE id=?", (article_id,)).fetchone()
        if not row:
            return JSONResponse({"error": "Article not found"})
        row = dict(row)

        prompt = _prompts.get("news_classifier", "")
        if not prompt:
            return JSONResponse({"error": "news_classifier.txt prompt not found in prompts/"})

        filled = prompt.replace("{headline}", row.get("headline", "")).replace(
            "{summary}", row.get("summary", "") or "")

        async with _classify_sem:
            resp = await asyncio.to_thread(
                _anthropic_client.messages.create,
                model="claude-haiku-4-5",
                max_tokens=80,
                messages=[{"role": "user", "content": filled}]
            )
        raw = resp.content[0].text.strip()
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        if not m:
            return JSONResponse({"error": f"Invalid JSON from model: {raw[:100]}"})
        data = json.loads(m.group())
        category   = data.get("category", "UNKNOWN")
        importance = data.get("importance", "LOW")
        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            conn.execute("""
                UPDATE news_intel SET category=?, importance=?, classified_by=?, classified_at=?
                WHERE id=?
            """, (category, importance, "API:haiku", now_iso, article_id))
            conn.commit()

        return JSONResponse({"ok": True, "category": category, "importance": importance,
                             "classified_by": "API:haiku"})
    except Exception as e:
        return JSONResponse({"error": str(e)})


def _scrape_article(url: str) -> str:
    """Fetch and extract plain text from a news article URL."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")
        # Remove boilerplate
        for tag in soup(["script","style","nav","footer","header","aside",
                          "iframe","noscript","form","button","figure"]):
            tag.decompose()
        # Try article-specific containers first
        content = ""
        for sel in ["article", "main", ".article-body", ".article-content",
                    ".post-content", "#article-body", ".entry-content",
                    ".story-body", ".article__body", ".caas-body",
                    "[data-module='ArticleBody']"]:
            el = soup.select_one(sel)
            if el:
                content = el.get_text(separator="\n", strip=True)
                break
        if not content:
            # Fall back to all paragraphs ≥ 40 chars
            paras = soup.find_all("p")
            content = "\n".join(
                p.get_text(strip=True) for p in paras
                if len(p.get_text(strip=True)) >= 40
            )
        # Cap at 12 000 chars (~3 000 tokens) to keep costs reasonable
        return content[:12_000] if content else ""
    except Exception as e:
        return ""


@app.get("/news-intel/fetch-content/{article_id}")
async def ni_fetch_content(article_id: int) -> JSONResponse:
    """Scrape full article text so Deep Insight can read the real content."""
    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            row = conn.execute(
                "SELECT url, headline FROM news_intel WHERE id=?", (article_id,)
            ).fetchone()
        if not row or not row[0]:
            return JSONResponse({"ok": False, "error": "No URL stored for this article"})
        url = row[0]
        content = await asyncio.to_thread(_scrape_article, url)
        if not content:
            return JSONResponse({"ok": False, "error": "Could not extract article text (paywall or empty page)"})
        return JSONResponse({"ok": True, "content": content, "chars": len(content), "url": url})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/news-intel/insight/{article_id}")
async def ni_deep_insight(article_id: int, request: Request) -> JSONResponse:
    """Generate deep insight for an article — called on user click."""
    if not _ANTHROPIC_OK:
        return JSONResponse({"error": "Anthropic API not available. Set ANTHROPIC_API_KEY in .env"})
    try:
        body = await request.json()
        ctx = body.get("context", {})

        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM news_intel WHERE id=?", (article_id,)).fetchone()
        if not row:
            return JSONResponse({"error": "Article not found"})
        row = dict(row)

        cat = (row.get("category") or "").upper()
        prompt_map = {
            "REGULATORY_FDA":     "fda_deep_insight",
            "MERGER_ACQUISITION": "ma_deep_insight",
            "DEAL_PARTNERSHIP":   "deal_deep_insight",
            "EARNINGS_PROJECTION":"earnings_deep_insight",
            "MANAGEMENT_CHANGE":  "general_deep_insight",
            "SHORT_REPORT":       "general_deep_insight",
            "ANALYST_ACTION":     "general_deep_insight",
            "MACRO":              "general_deep_insight",
            "UNKNOWN":            "general_deep_insight",
        }
        prompt_key = prompt_map.get(cat, "general_deep_insight")
        prompt = _prompts.get(prompt_key, _prompts.get("general_deep_insight", _prompts.get("fda_deep_insight", "")))
        if not prompt:
            return JSONResponse({"error": f"Prompt {prompt_key}.txt not found"})

        # Fetch full article content if not already provided in context
        full_content = ctx.get("full_content", "")
        if not full_content and row.get("url"):
            full_content = await asyncio.to_thread(_scrape_article, row["url"])

        filled = prompt
        fields = {
            "{headline}":        row.get("headline", ""),
            "{summary}":         row.get("summary", "") or "",
            "{full_content}":    full_content or "(full article text not available — analysis based on headline/summary only)",
            "{source}":          row.get("source", ""),
            "{published_at}":    row.get("published_at", ""),
            "{sym}":             row.get("sym", ""),
            "{cap_tier}":        ctx.get("cap_tier", "UNKNOWN"),
            "{current_price}":   str(ctx.get("current_price", "—")),
            "{price_at_publish}":str(ctx.get("price_at_publish", "—")),
            "{move_since_news}": str(ctx.get("move_since_news", "—")),
            "{day_change_pct}":  str(ctx.get("day_change_pct", "—")),
            "{day_low}":         str(ctx.get("day_low", "—")),
            "{day_high}":        str(ctx.get("day_high", "—")),
            "{vol_ratio}":       str(ctx.get("vol_ratio", "—")),
            "{dark_pool_pct}":   str(ctx.get("dark_pool_pct", "—")),
            "{sweep_count}":     str(ctx.get("sweep_count", "0")),
            "{sweep_direction}": ctx.get("sweep_direction", "—"),
            "{sweep_dollar_val}":str(ctx.get("sweep_dollar_val", "0")),
        }
        for k, v in fields.items():
            filled = filled.replace(k, v)

        # Use Sonnet for full article content (needs bigger context), Haiku for summary-only
        model = "claude-sonnet-4-5" if len(full_content) > 500 else "claude-haiku-4-5"
        max_tok = 2500 if len(full_content) > 500 else 1500

        resp = await asyncio.to_thread(
            _anthropic_client.messages.create,
            model=model,
            max_tokens=max_tok,
            messages=[{"role": "user", "content": filled}]
        )
        raw = resp.content[0].text.strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return JSONResponse({"error": "Could not parse model JSON response", "raw": raw[:300]})
        insight = json.loads(m.group())
        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            conn.execute("""
                UPDATE news_intel SET insight_json=?, insight_at=? WHERE id=?
            """, (json.dumps(insight), now_iso, article_id))
            conn.commit()

        return JSONResponse({"ok": True, "insight": insight})
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/news-intel/rules")
async def ni_get_rules() -> JSONResponse:
    return JSONResponse(_ni_rules)


@app.post("/news-intel/rules")
async def ni_save_rules(request: Request) -> JSONResponse:
    global _ni_rules
    try:
        body = await request.json()
        _ni_rules = body
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(_ni_rules, f, indent=2)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/news-intel/prompts")
async def ni_list_prompts() -> JSONResponse:
    return JSONResponse({"prompts": list(_prompts.keys())})


@app.get("/news-intel/prompts/{name}")
async def ni_get_prompt(name: str) -> JSONResponse:
    if name not in _prompts:
        return JSONResponse({"error": "Prompt not found"}, status_code=404)
    return JSONResponse({"name": name, "content": _prompts[name]})


@app.put("/news-intel/prompts/{name}")
async def ni_update_prompt(name: str, request: Request) -> JSONResponse:
    global _prompts
    try:
        body = await request.json()
        content = body.get("content", "")
        path = PROMPTS_DIR / f"{name}.txt"
        path.write_text(content, encoding="utf-8")
        _prompts[name] = content
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/news-intel/snapshot/{sym}")
async def ni_snapshot(sym: str) -> JSONResponse:
    """Real-time snapshot for News Intel right panel: cap tier, today vol, sweeps."""
    sym = sym.upper().strip()

    # Cap tier from SYM_META
    meta     = SYM_META.get(sym, {})
    cap      = meta.get("market_cap")
    cap_tier = "unknown"
    for tier in CAP_TIERS:
        if cap and cap < tier["max_cap"]:
            cap_tier = tier["name"]
            break

    # Today's running dollar volume (tracked from live trades)
    today_vol_usd = daily_volume.get(sym, 0)

    # Sweeps + vol-spike alerts today from SQLite
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    sweep_count  = 0
    sweep_dir    = "—"
    sweep_val    = 0
    try:
        with sqlite3.connect(ALERTS_DB) as conn:
            rows = conn.execute(
                "SELECT direction, value1m FROM alerts WHERE sym=? AND ts >= ?",
                (sym, today_start)
            ).fetchall()
            sweep_count = len(rows)
            if rows:
                bull = sum(1 for r in rows if (r[0] or '') == 'bull')
                bear = sum(1 for r in rows if (r[0] or '') == 'bear')
                sweep_dir = "bull" if bull > bear else ("bear" if bear > bull else "mixed")
                sweep_val = int(sum(r[1] or 0 for r in rows))
    except Exception:
        pass

    return JSONResponse({
        "sym":            sym,
        "cap_tier":       cap_tier,
        "sector":         meta.get("sector", ""),
        "name":           meta.get("name", ""),
        "today_vol_usd":  today_vol_usd,
        "sweep_count":    sweep_count,
        "sweep_direction":sweep_dir,
        "sweep_dollar_val":sweep_val,
    })


# ── AI Assessment ─────────────────────────────────────────────────────────────
AI_ASSESSMENT_FILE = Path(__file__).parent / "ai_assessments.json"
_ai_assessments: dict[str, dict] = {}   # sym → {tags, markdown, snapshot, updated_at}
_ai_assess_lock  = threading.Lock()

_MASSIVE_HEADERS = {"X-API-KEY": MASSIVE_API_KEY, "Accept": "application/json"}

_AI_ASSESS_PROMPT = """You are a senior equity analyst specializing in news-driven tape reading.
Analyze {sym} based ONLY on the news and snapshot data provided.

SNAPSHOT ({date}):
{snapshot_block}

NEWS — last 14 days (sources: Alpaca/Benzinga + Massive):
{news_block}

Output EXACTLY this structure — no intro, no extra text:

### TAGS
[4-6 comma-separated tags: cap tier, sector niche, catalyst type, order-flow label, risk label]

### NEWS IMPORTANCE
| Date | Source | Headline | Importance | Sentiment |
|------|--------|----------|------------|-----------|
[One row per item. Importance: HIGH / MED / LOW. Sentiment: BULL / BEAR / NEUTRAL]

### KEY THESIS
[2-3 sentences: what is the primary news-driven narrative right now and what order-flow it implies]

### WATCH
- Catalyst: [next specific upcoming event or price level to watch]
- Risk: [primary downside risk or red flag from recent news]"""


def _load_ai_assessments() -> None:
    global _ai_assessments
    if AI_ASSESSMENT_FILE.exists():
        try:
            _ai_assessments = json.loads(AI_ASSESSMENT_FILE.read_text(encoding="utf-8"))
            print(f"[ai-assess] loaded {len(_ai_assessments)} cached assessments")
        except Exception as exc:
            print(f"[ai-assess] load failed: {exc}")


def _save_ai_assessments() -> None:
    try:
        with _ai_assess_lock:
            AI_ASSESSMENT_FILE.write_text(
                json.dumps(_ai_assessments, indent=2), encoding="utf-8"
            )
    except Exception as exc:
        print(f"[ai-assess] save failed: {exc}")


def _massive_get_snapshot_sync(sym: str) -> dict | None:
    """Fetch current stock snapshot from Massive API (price, mktcap, float, etc.)."""
    try:
        r = req_lib.get(
            f"{MASSIVE_BASE_URL}/stocks/snapshot",
            headers=_MASSIVE_HEADERS,
            params={"symbol": sym},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else None
    except Exception as exc:
        print(f"[massive] snapshot {sym}: {exc}")
        return None


def _massive_get_news_sync(sym: str) -> list[dict]:
    """Fetch last 14 days of news from Massive API for a ticker."""
    try:
        from_date = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        r = req_lib.get(
            f"{MASSIVE_BASE_URL}/news",
            headers=_MASSIVE_HEADERS,
            params={"symbol": sym, "from": from_date, "limit": 25},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        return items if isinstance(items, list) else []
    except Exception as exc:
        print(f"[massive] news {sym}: {exc}")
        return []


def _format_snapshot_block(snap: dict | None, sym: str) -> str:
    """Format snapshot dict into a prompt-friendly string."""
    if not snap:
        meta = SYM_META.get(sym, {})
        cap  = meta.get("market_cap")
        cap_str = f"~${cap/1e6:.0f}M" if cap else "unknown"
        return f"Symbol: {sym} | Mkt Cap: {cap_str} | (no live snapshot available)"
    def _g(keys, default="—"):
        for k in keys:
            v = snap.get(k)
            if v is not None:
                return v
        return default
    price     = _g(["price", "lastPrice", "last", "close"])
    change    = _g(["changePercent", "change_pct", "changesPercentage"])
    mktcap    = _g(["marketCap", "market_cap", "mktCap"])
    float_sh  = _g(["float", "floatShares", "float_shares"])
    short_pct = _g(["shortPercent", "short_float_percent", "shortPercentOfFloat"])
    volume    = _g(["volume", "vol"])
    day_high  = _g(["dayHigh", "high", "h"])
    day_low   = _g(["dayLow",  "low",  "l"])

    def _fmt_num(v, prefix="", suffix="", div=1):
        try:
            n = float(v) / div
            if n >= 1e9:  return f"{prefix}{n/1e9:.2f}B{suffix}"
            if n >= 1e6:  return f"{prefix}{n/1e6:.1f}M{suffix}"
            if n >= 1e3:  return f"{prefix}{n/1e3:.1f}K{suffix}"
            return f"{prefix}{n:.2f}{suffix}"
        except Exception:
            return str(v)

    parts = [f"Symbol: {sym}"]
    if price != "—":
        chg_str = f" ({_fmt_num(change, suffix='%')})" if change != "—" else ""
        parts.append(f"Price: ${float(price):.4f}{chg_str}")
    if day_high != "—" and day_low != "—":
        parts.append(f"Day Range: ${float(day_low):.2f}–${float(day_high):.2f}")
    if mktcap  != "—": parts.append(f"Mkt Cap: {_fmt_num(mktcap, prefix='$')}")
    if float_sh!= "—": parts.append(f"Float: {_fmt_num(float_sh)}")
    if short_pct!= "—": parts.append(f"Short%: {short_pct}")
    if volume  != "—": parts.append(f"Volume: {_fmt_num(volume)}")
    return " | ".join(parts)


def _alpaca_get_news_sync(sym: str) -> list[tuple[str, str, str]]:
    """
    Fetch last 14 days of news from Alpaca REST API for a ticker.
    Returns list of (date, source, headline) tuples.
    """
    items: list[tuple[str, str, str]] = []
    try:
        start_dt = datetime.now(timezone.utc) - timedelta(days=14)
        req  = NewsRequest(symbols=sym, start=start_dt, limit=50)
        resp = news_client.get_news(req)
        raw  = resp.data.get("news", []) if hasattr(resp, "data") else []
        for a in raw:
            d = article_to_dict(a)
            h = d.get("headline", "")
            if not h:
                continue
            ts   = d.get("created_at", "")
            date = (ts or "")[:10]
            src  = d.get("source", "Alpaca")
            items.append((date, src, h))
    except Exception as exc:
        print(f"[alpaca-news] {sym}: {exc}")
    # Also merge from live in-memory stream cache
    try:
        with _news_lock:
            live = list(news_store.get(sym, deque()))
        for ln in live:
            h = ln.get("headline", "")
            if h:
                ts   = ln.get("created_at", "")
                date = (ts or "")[:10]
                items.append((date, ln.get("source", "Alpaca"), h))
    except Exception:
        pass
    return items


def _get_combined_news_for_sym(sym: str, massive_news: list[dict]) -> str:
    """
    Merge news from three sources, newest first, deduplicated.
    1. Alpaca REST API (last 14d — always fresh, same as the news panel)
    2. news_intel.db local cache (classified articles from live stream)
    3. Massive API news
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    items: list[tuple[str, str, str]] = []  # (date, source_label, headline)

    # — Alpaca REST + live stream cache —
    items.extend(_alpaca_get_news_sync(sym))

    # — news_intel.db (backup / classified articles) —
    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            rows = conn.execute(
                "SELECT headline, published_at, source FROM news_intel "
                "WHERE (sym=? OR symbols LIKE ?) AND published_at >= ? "
                "AND (importance IS NULL OR importance != 'NOISE') "
                "ORDER BY published_at DESC LIMIT 15",
                (sym, f'%"{sym}"%', cutoff)
            ).fetchall()
        for h, ts, src in rows:
            date = (ts or "")[:10]
            items.append((date, src if src else "Benzinga", h))
    except Exception:
        pass

    # — Massive news —
    for art in massive_news:
        headline = art.get("headline", art.get("title", art.get("text", "")))
        if not headline:
            continue
        ts   = art.get("published_at", art.get("publishedAt", art.get("date", "")))
        date = (ts or "")[:10]
        src  = art.get("source", "Massive")
        items.append((date, src, headline))

    if not items:
        return "(no news found in the last 14 days)"

    # Deduplicate by headline prefix (first 70 chars), sort newest first
    seen:   set[str]  = set()
    unique: list[tuple[str, str, str]] = []
    for date, src, h in sorted(items, key=lambda x: x[0], reverse=True):
        key = h[:70].lower()
        if key not in seen:
            seen.add(key)
            unique.append((date, src, h))

    lines = [f"- [{d}] [{s}] {h}" for d, s, h in unique[:25]]
    return "\n".join(lines)


async def _generate_ai_assessment(sym: str) -> dict:
    """Call Claude Sonnet to generate news-focused assessment."""
    if not _ANTHROPIC_OK or _anthropic_client is None:
        raise RuntimeError("Anthropic API not available")

    # Fetch Massive snapshot + news concurrently in threads
    snap, massive_news = await asyncio.gather(
        asyncio.to_thread(_massive_get_snapshot_sync, sym),
        asyncio.to_thread(_massive_get_news_sync, sym),
    )

    snapshot_block = _format_snapshot_block(snap, sym)
    news_block     = _get_combined_news_for_sym(sym, massive_news)
    today_str      = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")

    prompt = (
        _AI_ASSESS_PROMPT
        .replace("{sym}", sym)
        .replace("{date}", today_str)
        .replace("{snapshot_block}", snapshot_block)
        .replace("{news_block}", news_block)
    )

    resp = await asyncio.to_thread(
        _anthropic_client.messages.create,
        model="claude-sonnet-4-6",
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text.strip()

    # Extract tags for badge display (first non-header line after ### TAGS)
    tags: list[str] = []
    in_tags = False
    for line in raw.splitlines():
        if line.startswith("### TAGS"):
            in_tags = True
            continue
        if in_tags and line.strip() and not line.startswith("#"):
            tags = [t.strip() for t in line.split(",") if t.strip()]
            break

    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {
        "sym":        sym,
        "tags":       tags,
        "markdown":   raw,
        "snapshot":   {
            "block": snapshot_block,
            "raw":   snap or {},
        },
        "updated_at": now_iso,
    }
    with _ai_assess_lock:
        _ai_assessments[sym] = entry
    await asyncio.to_thread(_save_ai_assessments)
    return entry


@app.get("/ai-assessment/{sym}")
async def get_ai_assessment(sym: str) -> JSONResponse:
    sym = sym.upper().strip()
    with _ai_assess_lock:
        entry = _ai_assessments.get(sym)
    if entry:
        return JSONResponse({"ok": True, "cached": True, **entry})
    return JSONResponse({"ok": False, "cached": False, "sym": sym})


@app.post("/ai-assessment/{sym}")
async def create_ai_assessment(sym: str) -> JSONResponse:
    sym = sym.upper().strip()
    if not _ANTHROPIC_OK:
        return JSONResponse({"ok": False, "error": "ANTHROPIC_API_KEY not set"}, status_code=503)
    try:
        entry = await _generate_ai_assessment(sym)
        return JSONResponse({"ok": True, "cached": False, **entry})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/news-intel/status")
async def ni_status() -> JSONResponse:
    """Check Anthropic API connection and loaded prompts/rules."""
    pending_count = 0
    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            row = conn.execute("SELECT COUNT(*) FROM news_intel WHERE category='PENDING'").fetchone()
            pending_count = row[0] if row else 0
    except Exception:
        pass
    return JSONResponse({
        "anthropic_ok": _ANTHROPIC_OK,
        "prompts_loaded": list(_prompts.keys()),
        "rules": {
            "noise": len(_ni_rules.get("noise_keywords", [])),
            "high":  len(_ni_rules.get("high_keywords", []))
        },
        "pending_classification": pending_count
    })


@app.post("/news-intel/classify-pending")
async def ni_classify_pending() -> JSONResponse:
    """Immediately classify all PENDING articles via Haiku — returns progress."""
    if not _ANTHROPIC_OK:
        return JSONResponse({"ok": False, "error": "Anthropic API not available. Set ANTHROPIC_API_KEY in .env"})
    prompt_tmpl = _prompts.get("news_classifier", "")
    if not prompt_tmpl:
        return JSONResponse({"ok": False, "error": "news_classifier.txt not found in prompts/"})

    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            rows = conn.execute(
                "SELECT id, headline, summary FROM news_intel WHERE category='PENDING' OR category='PENDING_API' LIMIT 100"
            ).fetchall()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"DB read error: {e}"})

    if not rows:
        return JSONResponse({"ok": True, "classified": 0, "message": "No PENDING articles found"})

    classified = 0
    errors = []
    for row_id, headline, summary in rows:
        try:
            filled = prompt_tmpl.replace("{headline}", headline or "").replace(
                "{summary}", summary or "")
            async with _classify_sem:
                resp = await asyncio.to_thread(
                    _anthropic_client.messages.create,
                    model="claude-haiku-4-5",
                    max_tokens=80,
                    messages=[{"role": "user", "content": filled}]
                )
            raw = resp.content[0].text.strip()
            m = re.search(r'\{.*?\}', raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                category   = data.get("category",   "UNKNOWN")
                importance = data.get("importance",  "LOW")
                now_iso = datetime.now(timezone.utc).isoformat()
                with sqlite3.connect(NEWS_INTEL_DB) as conn:
                    conn.execute(
                        "UPDATE news_intel SET category=?, importance=?, classified_by=?, classified_at=? WHERE id=?",
                        (category, importance, "API:haiku", now_iso, row_id)
                    )
                classified += 1
            else:
                errors.append(f"id={row_id}: bad JSON: {raw[:60]}")
        except Exception as e:
            errors.append(f"id={row_id}: {str(e)[:80]}")

    print(f"[news-intel] classify-pending: {classified}/{len(rows)} done, {len(errors)} errors")
    if errors:
        for err in errors[:5]:
            print(f"  [news-intel] error: {err}")

    return JSONResponse({
        "ok": True,
        "classified": classified,
        "total": len(rows),
        "errors": errors[:5]
    })


async def _ni_batch_classify_bg() -> None:
    """Background task: classify all PENDING articles via Haiku API."""
    if not _ANTHROPIC_OK:
        return
    prompt_tmpl = _prompts.get("news_classifier", "")
    if not prompt_tmpl:
        return
    try:
        with sqlite3.connect(NEWS_INTEL_DB) as conn:
            rows = conn.execute(
                "SELECT id, headline, summary FROM news_intel WHERE category='PENDING' LIMIT 100"
            ).fetchall()
    except Exception as e:
        print(f"[news-intel] batch classify DB read error: {e}")
        return

    print(f"[news-intel] batch classify: {len(rows)} PENDING articles")
    for row_id, headline, summary in rows:
        try:
            filled = prompt_tmpl.replace("{headline}", headline or "").replace(
                "{summary}", summary or "")
            async with _classify_sem:
                resp = await asyncio.to_thread(
                    _anthropic_client.messages.create,
                    model="claude-haiku-4-5",
                    max_tokens=80,
                    messages=[{"role": "user", "content": filled}]
                )
            raw = resp.content[0].text.strip()
            m = re.search(r'\{.*?\}', raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                category   = data.get("category",   "UNKNOWN")
                importance = data.get("importance",  "LOW")
                now_iso = datetime.now(timezone.utc).isoformat()
                with sqlite3.connect(NEWS_INTEL_DB) as conn:
                    conn.execute(
                        "UPDATE news_intel SET category=?, importance=?, classified_by=?, classified_at=? WHERE id=?",
                        (category, importance, "API:haiku", now_iso, row_id)
                    )
        except Exception as e:
            print(f"[news-intel] batch classify error id={row_id}: {e}")
    print("[news-intel] batch classify complete")


@app.post("/news-intel/load-initial")
async def ni_load_initial() -> JSONResponse:
    """Load last 200 news articles from Alpaca REST API and classify them."""
    try:
        start_dt = datetime.now(timezone.utc) - timedelta(hours=24)
        req = NewsRequest(start=start_dt, limit=200, sort="desc")
        resp = await asyncio.to_thread(news_client.get_news, req)
        raw_articles = resp.data.get("news", []) if hasattr(resp, "data") else []
        articles = [article_to_dict(a) for a in raw_articles]

        loaded = 0
        api_needed = []
        for article in articles:
            symbols  = article.get("symbols", [])
            headline = article.get("headline", "")
            category, importance, classified_by = _ni_classify_rules(headline, symbols)
            if category is None:
                api_needed.append(article)
                _ni_save(article, "PENDING", "LOW", "PENDING_API")
            else:
                _ni_save(article, category, importance, classified_by)
            loaded += 1

        # Fire background Haiku classification for articles that need it
        if api_needed and _ANTHROPIC_OK:
            asyncio.create_task(_ni_batch_classify_bg())

        return JSONResponse({
            "ok": True,
            "loaded": loaded,
            "rule_classified": loaded - len(api_needed),
            "pending_api": len(api_needed),
            "api_classification": "started" if (api_needed and _ANTHROPIC_OK) else ("no_key" if not _ANTHROPIC_OK else "none_needed")
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    global _classify_sem, _anthropic_client, _ANTHROPIC_OK
    # ── News Intelligence init ────────────────────────────────────────────────
    _load_ni_prompts()
    _load_ni_rules()
    _init_ni_db()
    _classify_sem = asyncio.Semaphore(3)
    if ANTHROPIC_KEY and _ANTHROPIC_IMPORT_OK:
        try:
            _anthropic_client = _anthropic_lib.Anthropic(api_key=ANTHROPIC_KEY)
            _ANTHROPIC_OK = True
            print("[news-intel] Anthropic client ready")
        except Exception as _anth_exc:
            print(f"[news-intel] Anthropic client init failed: {_anth_exc}")
    elif not _ANTHROPIC_IMPORT_OK:
        print("[news-intel] anthropic package not installed — run: pip install anthropic")
    else:
        print("[news-intel] ANTHROPIC_API_KEY not set — AI classification disabled")
    # ── Core init ─────────────────────────────────────────────────────────────
    _init_db()
    _load_user_tags()
    load_universe()
    load_yesterday_volume()
    SWEEP_BOARD_DIR.mkdir(exist_ok=True)
    _sb_load_today()          # pre-populate sweep board from today's DB on restart
    _load_ai_assessments()    # load cached AI assessments
    asyncio.create_task(queue_processor())
    asyncio.create_task(eod_saver())
    asyncio.create_task(_order_expiry_watcher())
    asyncio.create_task(csv_history_exporter())
    asyncio.create_task(_refresh_etf_exclude())   # fetch live ETF list in background
    asyncio.create_task(_tags_scheduler())         # sync stock tags from Google Sheet
    threading.Thread(target=run_trade_stream,    daemon=True).start()
    threading.Thread(target=run_news_stream,     daemon=True).start()
    def _enrich_all_caps():
        _enrich_with_yfinance()
        _enrich_with_finnhub()
    threading.Thread(target=_enrich_all_caps, daemon=True).start()  # fill missing market caps
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
                msg = await asyncio.wait_for(ws.receive(), timeout=30)
                if msg.get("type") == "websocket.disconnect":
                    break
            except asyncio.TimeoutError:
                ok = await safe_send(ws, '{"type":"ping"}')
                if not ok:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        clients.discard(ws)
        client_locks.pop(ws, None)
