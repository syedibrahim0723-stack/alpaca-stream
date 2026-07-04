"""
RSI Backtester — FastAPI app

BUY:   RSI recovers from below rsi_buy → add $1 000.  Window: 9:30 AM – exit_time.

TRAILING STOP activates (whichever comes first):
  A. RSI  >= rsi_trail_trigger  (default 60)   — early trail arm
  B. RSI  >= rsi_sell           (default 70)   — overbought arms trail (not instant sell)
  C. price >= avg_entry × (1 + trail_activate_pct%)   (default 3 %)
  D. time  >= exit_time  (default 13:00 ET)    — force-arms trail at exit time

Once active trail peak is tracked; fires when close <= peak × (1 – trail_pct%).
  — BEFORE exit_time : trail fires ONLY if close > avg_entry  (no loss exits pre-exit)
  — AT/AFTER exit_time: trail fires regardless (willing to accept a small loss to exit)

INSTANT SELL (only one — checked before trailing):
  1. Profit target : close >= avg_entry × (1 + profit_target_pct%)

EOD: any open position closed at last bar price.
"""

from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

API_KEY    = "AKHYBEIWDAYHQZCY6VRJA74PPP"
SECRET_KEY = "CpcKZEwtv8tMCDiHGnnp57fmVkpipSKoCM4W19SX1Lw"
DATA_BASE  = "https://data.alpaca.markets"
NY         = ZoneInfo("America/New_York")

app = FastAPI(title="RSI Backtester")

# ── Alpaca data fetch ─────────────────────────────────────────────────────────

async def fetch_bars(symbol: str, day: date):
    start  = datetime(day.year, day.month, day.day,  4, 0, tzinfo=NY)
    end    = datetime(day.year, day.month, day.day, 20, 0, tzinfo=NY)
    url    = f"{DATA_BASE}/v2/stocks/{symbol}/bars"
    params = {
        "timeframe":  "1Min",
        "start":      start.isoformat(),
        "end":        end.isoformat(),
        "limit":      10000,
        "feed":       "iex",
        "adjustment": "raw",
    }
    headers = {
        "APCA-API-KEY-ID":     API_KEY,
        "APCA-API-SECRET-KEY": SECRET_KEY,
    }
    bars = []
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        while True:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200:
                raise HTTPException(r.status_code, f"Alpaca error: {r.text}")
            data = r.json()
            bars.extend(data.get("bars") or [])
            token = data.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
    return bars

# ── RSI (Wilder smoothing) ────────────────────────────────────────────────────

def compute_rsi(closes: list, period: int = 12) -> list:
    rsi = [None] * len(closes)
    if len(closes) < period + 1:
        return rsi
    diffs    = [closes[i] - closes[i-1] for i in range(1, period + 1)]
    avg_gain = sum(max(d, 0) for d in diffs) / period
    avg_loss = sum(max(-d, 0) for d in diffs) / period
    for i in range(period, len(closes)):
        if i > period:
            d        = closes[i] - closes[i-1]
            avg_gain = (avg_gain * (period - 1) + max(d, 0))  / period
            avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period
        rsi[i] = 100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
    return rsi

# ── Strategy ──────────────────────────────────────────────────────────────────

def _make_dt(day: date, hhmm: str, tz) -> datetime:
    """Parse 'HH:MM' string into an aware datetime on trade_day."""
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=tz)

def run_backtest(
    bars:                 list,
    trade_day:            date,
    rsi_period:           int   = 12,
    rsi_buy:              float = 30.0,
    rsi_sell:             float = 70.0,
    profit_target_pct:    float = 10.0,
    # ── trailing stop ─────────────────────────────────────────────────────
    trail_pct:            float = 3.0,
    trail_activate_pct:   float = 3.0,
    rsi_trail_trigger:    float = 60.0,
    # ── time windows ──────────────────────────────────────────────────────
    start_time_str:       str   = "09:30",  # buys open
    exit_time_str:        str   = "13:00",  # close profitable pos; force-arm trail on negative
    final_exit_time_str:  str   = "15:30",  # hard-close ALL remaining positions
    # ── sizing ────────────────────────────────────────────────────────────
    buy_amount:           float = 1000.0,   # $ per RSI-dip buy
):
    """
    BUY windows:
      • New entry  (no position):        start_time  ≤ ts < exit_time
      • DCA        (negative position):  start_time  ≤ ts < final_exit_time

    SELL events (checked in priority order each bar):
      1. final_exit_time reached          → close ALL regardless of P&L
      2. Profit target hit                → close all
      3. exit_time reached + profitable   → close all  (locks in winners)
      4. Trailing stop fires              → close all
         • No-loss guard: trail won't fire at a loss before final_exit_time
         • Trail arms at exit_time even for negative positions (gives time to recover)
    """
    if not bars:
        return [], [], []

    closes   = [b["c"] for b in bars]
    times    = [datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                for b in bars]
    rsi_vals = compute_rsi(closes, period=rsi_period)

    BUY_START      = _make_dt(trade_day, start_time_str,      NY)
    EXIT_DT        = _make_dt(trade_day, exit_time_str,       NY)
    FINAL_EXIT_DT  = _make_dt(trade_day, final_exit_time_str, NY)

    total_shares  = 0
    total_cost    = 0.0
    below_seen    = False
    trail_active  = False
    trail_peak    = 0.0
    trail_reason  = None
    blocked_count = 0

    buys   = []
    trades = []
    chart  = []

    for ts, close, rsi in zip(times, closes, rsi_vals):
        signal      = None
        exit_reason = None

        if rsi is None:
            chart.append({"t": ts.isoformat(), "close": close, "rsi": None,
                          "signal": None, "trail_stop": None, "avg_entry": None})
            continue

        avg_entry  = (total_cost / total_shares) if total_shares > 0 else 0.0
        trail_stop = round(trail_peak * (1 - trail_pct / 100), 4) if trail_active else None

        # ── SELL LOGIC ────────────────────────────────────────────────────
        if total_shares > 0:
            past_exit       = ts >= EXIT_DT
            past_final_exit = ts >= FINAL_EXIT_DT

            # Priority 1 — hard deadline: close everything
            if past_final_exit:
                exit_reason = "final_exit"

            # Priority 2 — instant profit target
            elif profit_target_pct > 0 and close >= avg_entry * (1 + profit_target_pct / 100):
                exit_reason = "target"

            # Priority 3 — exit_time reached and position is profitable → lock in winner
            elif past_exit and close > avg_entry:
                exit_reason = "exit_profit"

            else:
                # Arm trailing stop (4 conditions)
                if not trail_active:
                    if rsi >= rsi_sell:
                        trail_active = True; trail_peak = close
                        trail_reason = f"rsi{int(rsi_sell)}"
                    elif rsi >= rsi_trail_trigger:
                        trail_active = True; trail_peak = close
                        trail_reason = f"rsi{int(rsi_trail_trigger)}"
                    elif close >= avg_entry * (1 + trail_activate_pct / 100):
                        trail_active = True; trail_peak = close
                        trail_reason = f"price+{trail_activate_pct}%"
                    elif past_exit:                        # force-arm at exit_time (negative pos)
                        trail_active = True; trail_peak = close
                        trail_reason = "exit_time"

                # Fire trailing stop
                if trail_active:
                    if close > trail_peak:
                        trail_peak = close
                    trail_stop  = round(trail_peak * (1 - trail_pct / 100), 4)
                    trail_fires = close <= trail_stop
                    # No-loss guard: blocked before final_exit_time if would exit at a loss
                    if trail_fires and not past_final_exit and close <= avg_entry:
                        trail_fires   = False
                        blocked_count += 1
                    if trail_fires:
                        exit_reason = "trail"

            # Execute exit
            if exit_reason:
                pnl = round(close * total_shares - total_cost, 2)
                trades.append({
                    "avg_entry":    round(avg_entry, 4),
                    "total_shares": total_shares,
                    "total_cost":   round(total_cost, 2),
                    "exit_price":   round(close, 4),
                    "exit_time":    ts.isoformat(),
                    "pnl":          pnl,
                    "open":         False,
                    "reason":       exit_reason,
                    "trail_reason": trail_reason,
                    "buys":         list(buys),
                })
                signal        = "sell"
                total_shares  = 0;  total_cost   = 0.0
                trail_active  = False; trail_peak = 0.0; trail_reason = None
                buys          = [];  below_seen   = False
                avg_entry     = 0.0; trail_stop   = None; blocked_count = 0

        # ── BUY LOGIC ─────────────────────────────────────────────────────
        if exit_reason is None:
            if rsi < rsi_buy:
                below_seen = True

            if total_shares == 0:
                # New entry: only before exit_time
                in_window = BUY_START <= ts < EXIT_DT
            else:
                # DCA on negative position: allowed until final_exit_time
                in_window = close < avg_entry and BUY_START <= ts < FINAL_EXIT_DT

            can_buy = below_seen and rsi >= rsi_buy and in_window and close > 0
            if can_buy:
                new_shares = int(buy_amount / close)
                if new_shares > 0:
                    total_shares += new_shares
                    total_cost   += new_shares * close
                    below_seen    = False
                    signal        = "buy"
                    buys.append({
                        "time":   ts.isoformat(),
                        "price":  round(close, 4),
                        "shares": new_shares,
                        "spend":  round(new_shares * close, 2),
                    })
                    # Disarm trail if new avg makes it premature
                    if trail_active:
                        new_avg = total_cost / total_shares
                        if trail_peak < new_avg * (1 + trail_activate_pct / 100):
                            trail_active = False; trail_peak = 0.0; trail_reason = None

        # Recompute trail_stop for chart
        if total_shares > 0 and trail_active:
            trail_stop = round(trail_peak * (1 - trail_pct / 100), 4)
        else:
            trail_stop = None

        chart.append({
            "t":            ts.isoformat(),
            "close":        close,
            "rsi":          rsi,
            "signal":       signal,
            "trail_stop":   trail_stop,
            "trail_active": trail_active and total_shares > 0,
            "avg_entry":    round(avg_entry, 4) if total_shares > 0 else None,
            "blocked":      (trail_active and total_shares > 0
                             and close <= round(trail_peak * (1 - trail_pct / 100), 4)
                             and close <= avg_entry
                             and ts < FINAL_EXIT_DT),
        })

    # EOD: still holding after final_exit_time (shouldn't happen, but safety net)
    if total_shares > 0:
        avg_entry  = total_cost / total_shares
        last_close = closes[-1]
        pnl        = round(last_close * total_shares - total_cost, 2)
        trades.append({
            "avg_entry":    round(avg_entry, 4),
            "total_shares": total_shares,
            "total_cost":   round(total_cost, 2),
            "exit_price":   round(last_close, 4),
            "exit_time":    times[-1].isoformat(),
            "pnl":          pnl,
            "open":         True,
            "reason":       "eod",
            "trail_reason": trail_reason,
            "buys":         list(buys),
        })

    return buys, trades, chart

# ── Shared param validation + single-symbol runner ───────────────────────────

def _validate_time(t: str, name: str):
    try:
        h, m = map(int, t.split(":"))
        assert 9 <= h <= 20 and 0 <= m < 60
    except Exception:
        raise HTTPException(400, f"{name} must be HH:MM (09:00–20:00)")

def _validate_params(start_time_str: str, exit_time_str: str, final_exit_time_str: str):
    _validate_time(start_time_str,      "start_time_str")
    _validate_time(exit_time_str,       "exit_time_str")
    _validate_time(final_exit_time_str, "final_exit_time_str")
    sh, sm = map(int, start_time_str.split(":"))
    eh, em = map(int, exit_time_str.split(":"))
    fh, fm = map(int, final_exit_time_str.split(":"))
    if (sh * 60 + sm) >= (eh * 60 + em):
        raise HTTPException(400, "start_time must be before exit_time")
    if (eh * 60 + em) >= (fh * 60 + fm):
        raise HTTPException(400, "exit_time must be before final_exit_time")

async def _run_one(
    symbol: str, day: date,
    rsi_period, rsi_buy, rsi_sell,
    profit_target_pct, trail_pct, trail_activate_pct,
    rsi_trail_trigger,
    start_time_str="09:30", exit_time_str="13:00", final_exit_time_str="15:30",
    buy_amount=1000.0,
) -> dict:
    bars = await fetch_bars(symbol, day)
    if not bars:
        return {"symbol": symbol, "error": f"No bars found for {symbol}"}
    _, trades, chart = run_backtest(
        bars, day,
        rsi_period=rsi_period, rsi_buy=rsi_buy, rsi_sell=rsi_sell,
        profit_target_pct=profit_target_pct, trail_pct=trail_pct,
        trail_activate_pct=trail_activate_pct, rsi_trail_trigger=rsi_trail_trigger,
        start_time_str=start_time_str, exit_time_str=exit_time_str,
        final_exit_time_str=final_exit_time_str, buy_amount=buy_amount,
    )
    net_pnl       = round(sum(t["pnl"] for t in trades), 2)
    blocked_count = sum(1 for c in chart if c.get("blocked"))
    return {
        "symbol":        symbol,
        "bars":          len(bars),
        "trades":        trades,
        "chart":         chart,
        "net_pnl":       net_pnl,
        "blocked_count": blocked_count,
    }

# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/backtest")
async def backtest(
    symbol:               str,
    date_str:             str,
    rsi_period:           int   = 12,
    rsi_buy:              float = 30.0,
    rsi_sell:             float = 70.0,
    profit_target_pct:    float = 10.0,
    trail_pct:            float = 3.0,
    trail_activate_pct:   float = 3.0,
    rsi_trail_trigger:    float = 60.0,
    start_time_str:       str   = "09:30",
    exit_time_str:        str   = "13:00",
    final_exit_time_str:  str   = "15:30",
    buy_amount:           float = 1000.0,
):
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(400, "date_str must be YYYY-MM-DD")
    _validate_params(start_time_str, exit_time_str, final_exit_time_str)

    result = await _run_one(
        symbol.upper(), day,
        rsi_period, rsi_buy, rsi_sell,
        profit_target_pct, trail_pct, trail_activate_pct, rsi_trail_trigger,
        start_time_str, exit_time_str, final_exit_time_str, buy_amount,
    )
    if "error" in result:
        raise HTTPException(404, result["error"])
    return {**result, "date": date_str,
            "start_time_str": start_time_str, "exit_time_str": exit_time_str,
            "final_exit_time_str": final_exit_time_str, "buy_amount": buy_amount}


@app.get("/api/backtest/multi")
async def backtest_multi(
    symbols:              str,
    date_str:             str,
    rsi_period:           int   = 12,
    rsi_buy:              float = 30.0,
    rsi_sell:             float = 70.0,
    profit_target_pct:    float = 10.0,
    trail_pct:            float = 3.0,
    trail_activate_pct:   float = 3.0,
    rsi_trail_trigger:    float = 60.0,
    start_time_str:       str   = "09:30",
    exit_time_str:        str   = "13:00",
    final_exit_time_str:  str   = "15:30",
    buy_amount:           float = 1000.0,
):
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(400, "date_str must be YYYY-MM-DD")
    _validate_params(start_time_str, exit_time_str, final_exit_time_str)

    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(400, "Provide at least one symbol")

    import asyncio as _asyncio
    tasks   = [_run_one(s, day, rsi_period, rsi_buy, rsi_sell,
                        profit_target_pct, trail_pct, trail_activate_pct, rsi_trail_trigger,
                        start_time_str, exit_time_str, final_exit_time_str, buy_amount)
               for s in sym_list]
    results = await _asyncio.gather(*tasks)
    return {
        "date": date_str, "symbols": sym_list, "results": list(results),
        "total_pnl": round(sum(r.get("net_pnl", 0) for r in results), 2),
    }


@app.get("/api/batch")
async def batch_backtest(
    rsi_period:           int   = 12,
    rsi_buy:              float = 30.0,
    rsi_sell:             float = 65.0,
    profit_target_pct:    float = 10.0,
    trail_pct:            float = 3.0,
    trail_activate_pct:   float = 3.0,
    rsi_trail_trigger:    float = 60.0,
    start_time_str:       str   = "09:30",
    exit_time_str:        str   = "13:00",
    final_exit_time_str:  str   = "15:30",
    buy_amount:           float = 1000.0,
    concurrency:          int   = 8,
):
    """
    Read premarket_top5_by_sweeps.csv, run backtest for every (date, symbol, rank) row.
    Returns per-day and per-rank-group summaries plus every individual result.
    """
    import asyncio as _asyncio
    import csv as _csv

    CSV_PATH = r"C:\Users\ibrah\OneDrive\Documents\The100xTrade\cluade\alpaca-stream\premarket_top5_by_sweeps.csv"
    _validate_params(start_time_str, exit_time_str, final_exit_time_str)

    # ── Load CSV ──
    rows = []
    try:
        with open(CSV_PATH, newline="") as f:
            for r in _csv.DictReader(f):
                rows.append({"date": r["date"], "rank": int(r["rank"]),
                             "symbol": r["symbol"].strip().upper(),
                             "sweep_count": int(r["sweep_count"])})
    except FileNotFoundError:
        raise HTTPException(404, f"CSV not found: {CSV_PATH}")

    # ── Run all with semaphore to avoid rate-limits ──
    sem = _asyncio.Semaphore(concurrency)

    async def _guarded(row):
        async with sem:
            day = date.fromisoformat(row["date"])
            res = await _run_one(row["symbol"], day, rsi_period, rsi_buy, rsi_sell,
                                 profit_target_pct, trail_pct, trail_activate_pct,
                                 rsi_trail_trigger, start_time_str, exit_time_str,
                                 final_exit_time_str, buy_amount)
            return {**res, "date": row["date"], "rank": row["rank"],
                    "sweep_count": row["sweep_count"]}

    all_results = await _asyncio.gather(*[_guarded(r) for r in rows])

    # ── Per-day summary ──
    from collections import defaultdict as _dd
    day_map = _dd(lambda: {"date": "", "symbols": [], "total_pnl": 0.0,
                            "total_trades": 0, "ranks": {}})
    for r in all_results:
        d  = r["date"]
        rk = r["rank"]
        day_map[d]["date"]         = d
        day_map[d]["total_pnl"]    = round(day_map[d]["total_pnl"] + r.get("net_pnl", 0), 2)
        day_map[d]["total_trades"] += len(r.get("trades", []))
        day_map[d]["symbols"].append(r["symbol"])
        day_map[d]["ranks"][rk]    = {
            "symbol":      r["symbol"],
            "sweep_count": r["sweep_count"],
            "net_pnl":     r.get("net_pnl", 0),
            "trades":      len(r.get("trades", [])),
            "error":       r.get("error"),
        }

    # ── Rank-group summary (1-2 vs 3 vs 4-5) ──
    groups = {"1-2": [], "3": [], "4-5": []}
    for r in all_results:
        rk  = r["rank"]
        pnl = r.get("net_pnl", 0)
        if rk in (1, 2):   groups["1-2"].append(pnl)
        elif rk == 3:       groups["3"].append(pnl)
        else:               groups["4-5"].append(pnl)

    def _grp_stats(vals):
        if not vals: return {"count": 0, "total": 0, "avg": 0, "wins": 0, "win_rate": 0}
        wins = sum(1 for v in vals if v > 0)
        return {"count": len(vals), "total": round(sum(vals), 2),
                "avg": round(sum(vals) / len(vals), 2),
                "wins": wins, "win_rate": round(wins / len(vals) * 100, 1)}

    rank_groups = {k: _grp_stats(v) for k, v in groups.items()}

    return {
        "params": {"rsi_period": rsi_period, "rsi_buy": rsi_buy, "rsi_sell": rsi_sell,
                   "profit_target_pct": profit_target_pct, "trail_pct": trail_pct,
                   "trail_activate_pct": trail_activate_pct, "rsi_trail_trigger": rsi_trail_trigger,
                   "start_time_str": start_time_str, "exit_time_str": exit_time_str,
                   "final_exit_time_str": final_exit_time_str, "buy_amount": buy_amount},
        "total_rows":   len(rows),
        "total_pnl":    round(sum(r.get("net_pnl", 0) for r in all_results), 2),
        "daily":        [day_map[k] for k in sorted(day_map)],
        "rank_groups":  rank_groups,
        "rows":         all_results,    # full detail (chart omitted for speed — can add)
    }


# ── UI ────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSI Backtester — 100xTrade</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}
header{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
header h1{font-size:1.08rem;font-weight:700;color:#58a6ff;white-space:nowrap}
.pill{background:#21262d;border:1px solid #30363d;border-radius:20px;padding:2px 9px;font-size:.70rem;color:#8b949e}
.pill b{color:#e6edf3}
.container{max-width:1380px;margin:0 auto;padding:14px 14px}
.controls{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px 16px;margin-bottom:14px}
.ctrl-row{display:flex;gap:9px;flex-wrap:wrap;align-items:flex-end}
.ctrl-group{display:flex;flex-direction:column;padding:8px 11px;background:#0d1117;border:1px solid #21262d;border-radius:7px}
.ctrl-group-label{font-size:.62rem;color:#484f58;text-transform:uppercase;letter-spacing:.08em;margin-bottom:5px;white-space:nowrap}
.ctrl-fields{display:flex;gap:7px;flex-wrap:wrap;align-items:flex-end}
.field{display:flex;flex-direction:column;gap:3px}
label{font-size:.67rem;color:#8b949e;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
label .hint{font-size:.59rem;color:#484f58;text-transform:none;letter-spacing:0}
input[type=text],input[type=date],input[type=number],input[type=time]{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:5px 8px;border-radius:5px;font-size:.87rem;outline:none;transition:border-color .15s}
input:focus{border-color:#58a6ff}
input[type=text]{width:90px;text-transform:uppercase}
input[type=date]{width:145px}
input[type=number]{width:68px}
input[type=time]{width:95px;color-scheme:dark}
.ticker-wrap{display:flex;flex-direction:column;gap:4px;min-width:260px}
.ticker-input-row{display:flex;gap:6px;align-items:center}
#symInput{width:100px;text-transform:uppercase}
.btn-add{background:#21262d;border:1px solid #30363d;color:#58a6ff;border-radius:5px;padding:5px 10px;font-size:.82rem;cursor:pointer;transition:background .15s;white-space:nowrap}
.btn-add:hover{background:#2d333b}
.chips{display:flex;gap:5px;flex-wrap:wrap;min-height:26px;margin-top:3px}
.chip{display:inline-flex;align-items:center;gap:4px;background:#1f3a5f;border:1px solid #1f6feb;color:#58a6ff;border-radius:14px;padding:2px 10px;font-size:.78rem;font-weight:600}
.chip .rm{cursor:pointer;color:#8b949e;font-size:.9rem;line-height:1;margin-left:2px}
.chip .rm:hover{color:#f85149}
.btn-run{background:linear-gradient(135deg,#1f6feb,#388bfd);color:#fff;border:none;border-radius:6px;padding:8px 22px;font-size:.92rem;font-weight:700;cursor:pointer;transition:opacity .15s;white-space:nowrap}
.btn-run:hover{opacity:.85}
.btn-run:disabled{background:#21262d;color:#484f58;cursor:not-allowed}
#status{font-size:.78rem;color:#8b949e;min-height:16px;margin-top:6px}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.card{background:#161b22;border:1px solid #30363d;border-radius:7px;padding:10px 13px;flex:1;min-width:115px}
.card-label{font-size:.64rem;color:#8b949e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px}
.card-value{font-size:1.25rem;font-weight:700}
.green{color:#3fb950}.red{color:#f85149}.blue{color:#58a6ff}
.yellow{color:#d29922}.purple{color:#bc8cff}.orange{color:#f0883e}
.tab-bar{display:flex;gap:0;border-bottom:1px solid #30363d;margin-bottom:12px;flex-wrap:wrap}
.tab{padding:7px 16px;font-size:.82rem;cursor:pointer;color:#8b949e;border-bottom:2px solid transparent;transition:color .15s,border-color .15s;white-space:nowrap;user-select:none}
.tab:hover{color:#e6edf3}
.tab.active{color:#58a6ff;border-bottom-color:#58a6ff;font-weight:600}
.tab.err{color:#f85149}
.tab-panel{display:none}
.tab-panel.active{display:block}
.sym-bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;padding:8px 12px;background:#161b22;border:1px solid #30363d;border-radius:7px}
.sym-bar .sym-name{font-size:1rem;font-weight:700;color:#58a6ff;margin-right:6px}
.sym-stat{font-size:.78rem;color:#8b949e}
.sym-stat b{color:#e6edf3}
.charts{display:grid;grid-template-rows:300px 175px;gap:9px;margin-bottom:14px}
.chart-box{background:#161b22;border:1px solid #30363d;border-radius:7px;padding:8px 12px}
.section-title{font-size:.88rem;font-weight:600;color:#e6edf3;margin-bottom:7px;display:flex;align-items:center;gap:8px}
.tag{background:#21262d;border-radius:4px;padding:2px 7px;font-size:.68rem;color:#8b949e;font-weight:400}
.tbl-wrap{overflow-x:auto;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:.81rem}
th{background:#21262d;color:#8b949e;padding:6px 10px;text-align:left;font-weight:500;border-bottom:1px solid #30363d;white-space:nowrap}
td{padding:6px 10px;border-bottom:1px solid #21262d;white-space:nowrap}
tr:hover td{background:#1c2128}
.badge{display:inline-block;border-radius:4px;padding:2px 6px;font-size:.67rem;font-weight:700}
.badge-target{background:#1a3a2a;color:#3fb950}
.badge-trail{background:#3a1f00;color:#f0883e}
.badge-eod{background:#0f2a3f;color:#58a6ff}
.sub-row td{background:#0d1117!important;padding:4px 10px 4px 24px;font-size:.77rem;color:#8b949e;border-bottom:1px solid #161b22}
.toggle-btn{cursor:pointer;background:none;border:none;color:#58a6ff;font-size:.73rem;padding:0 3px}
</style>
</head>
<body>
<header>
  <h1>&#9889; RSI Backtester</h1>
  <span class="pill">Buy on <b>RSI dip recovery</b> &#183; +$1k/dip</span>
  <span class="pill">Instant exit: <b>profit target</b></span>
  <span class="pill">Trail: <b>RSI trigger</b> &#183; <b>RSI OB</b> &#183; <b>price+%</b> &#183; <b>exit time</b></span>
  <span class="pill">No-loss guard <b>before exit time</b></span>
  <div style="margin-left:auto;display:flex;gap:8px">
    <a href="/batch" style="background:#21262d;border:1px solid #30363d;color:#58a6ff;border-radius:5px;padding:5px 12px;font-size:.8rem;text-decoration:none">&#128202; Batch</a>
    <a href="/multiday" style="background:#21262d;border:1px solid #30363d;color:#34d399;border-radius:5px;padding:5px 12px;font-size:.8rem;text-decoration:none">&#128197; Multi-Day</a>
    <a href="/momentum" style="background:#21262d;border:1px solid #30363d;color:#fbbf24;border-radius:5px;padding:5px 12px;font-size:.8rem;text-decoration:none">&#9889; Momentum</a>
    <a href="/spike" style="background:#21262d;border:1px solid #30363d;color:#a5b4fc;border-radius:5px;padding:5px 12px;font-size:.8rem;text-decoration:none">&#128200; Spike</a>
    <a href="/grid" style="background:#21262d;border:1px solid #30363d;color:#34d399;border-radius:5px;padding:5px 12px;font-size:.8rem;text-decoration:none">&#9783; Grid</a>
    <a href="/alerts" style="background:#21262d;border:1px solid #30363d;color:#fbbf24;border-radius:5px;padding:5px 12px;font-size:.8rem;text-decoration:none">&#128276; Alerts</a>
  </div>
</header>

<div class="container">

<div class="controls">
  <div class="ctrl-row">

    <div class="ctrl-group">
      <div class="ctrl-group-label">Tickers &amp; Date</div>
      <div class="ctrl-fields">
        <div class="field ticker-wrap">
          <label>Add symbols <span class="hint">Enter or click +</span></label>
          <div class="ticker-input-row">
            <input type="text" id="symInput" placeholder="ASTC" onkeydown="if(event.key==='Enter'){event.preventDefault();addTicker()}">
            <button class="btn-add" onclick="addTicker()">+ Add</button>
          </div>
          <div class="chips" id="chips"></div>
        </div>
        <div class="field">
          <label>Date</label>
          <input type="date" id="dt" value="2026-05-28">
        </div>
      </div>
    </div>

    <div class="ctrl-group">
      <div class="ctrl-group-label">RSI Settings</div>
      <div class="ctrl-fields">
        <div class="field"><label>Period</label><input type="number" id="rsiPeriod" value="12" min="2" max="50"></div>
        <div class="field"><label>Buy &#8595;</label><input type="number" id="rsiBuy" value="30" min="1" max="49"></div>
        <div class="field"><label>OB &#8594; Trail <span class="hint">arms trail</span></label><input type="number" id="rsiSell" value="65" min="51" max="99"></div>
      </div>
    </div>

    <div class="ctrl-group">
      <div class="ctrl-group-label">Instant Exit</div>
      <div class="ctrl-fields">
        <div class="field"><label>Profit Target % <span class="hint">0=off</span></label><input type="number" id="profitTarget" value="10" min="0" max="500" step="0.5"></div>
      </div>
    </div>

    <div class="ctrl-group">
      <div class="ctrl-group-label">Trailing Stop &#8212; arms on ANY &#8595;</div>
      <div class="ctrl-fields">
        <div class="field"><label>RSI trigger <span class="hint">early arm</span></label><input type="number" id="rsiTrailTrigger" value="60" min="30" max="99"></div>
        <div class="field"><label>Price +% <span class="hint">above avg</span></label><input type="number" id="trailActivate" value="3" min="0.1" max="50" step="0.5"></div>
        <div class="field"><label>Exit Time <span class="hint">ET</span></label><input type="time" id="exitTime" value="13:00"></div>
        <div class="field"><label>Trail % <span class="hint">from peak</span></label><input type="number" id="trailDist" value="3" min="0.1" max="30" step="0.5"></div>
      </div>
    </div>

    <button class="btn-run" id="runBtn" onclick="runBacktest()">&#9654; Run</button>
  </div>
  <div id="status"></div>
</div>

<div class="cards" id="cards" style="display:none">
  <div class="card"><div class="card-label">Total Net PNL</div><div class="card-value" id="cPnl">&#8212;</div></div>
  <div class="card"><div class="card-label">Tickers</div><div class="card-value blue" id="cSyms">&#8212;</div></div>
  <div class="card"><div class="card-label">Total Exits</div><div class="card-value blue" id="cTrades">&#8212;</div></div>
  <div class="card"><div class="card-label">Total Legs</div><div class="card-value purple" id="cBuys">&#8212;</div></div>
  <div class="card"><div class="card-label">Total Invested</div><div class="card-value yellow" id="cInvested">&#8212;</div></div>
  <div class="card"><div class="card-label">Win Rate</div><div class="card-value yellow" id="cWin">&#8212;</div></div>
  <div class="card"><div class="card-label">&#10003; Target</div><div class="card-value green" id="cTarget">&#8212;</div></div>
  <div class="card"><div class="card-label">&#8600; Trail</div><div class="card-value orange" id="cTrail">&#8212;</div></div>
  <div class="card"><div class="card-label">&#128737; Blocked</div><div class="card-value yellow" id="cBlocked">&#8212;</div></div>
</div>

<div id="tabSection" style="display:none">
  <div class="tab-bar" id="tabBar"></div>
  <div id="tabPanels"></div>
</div>

<div id="allTradesSection" style="display:none">
  <div class="section-title">All Trades <span class="tag" id="allTradeTag"></span></div>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th></th><th>Symbol</th><th>#</th><th>Legs</th>
          <th>Avg Entry</th><th>Shares</th><th>Invested</th>
          <th>Exit Time</th><th>Exit $</th><th>PNL $</th><th>PNL %</th>
          <th>Exit Reason</th><th>Trail Armed By</th>
        </tr>
      </thead>
      <tbody id="allTradeBody"></tbody>
    </table>
  </div>
</div>

</div>

<script>
let tickers = [];
const chartRegistry = {};

['ASTC','SPRC'].forEach(t => addTickerVal(t));

function addTicker() {
  const inp = document.getElementById('symInput');
  const v   = inp.value.trim().toUpperCase();
  if (v) { addTickerVal(v); inp.value = ''; }
  inp.focus();
}
function addTickerVal(sym) {
  if (!sym || tickers.includes(sym)) return;
  tickers.push(sym);
  renderChips();
}
function removeTicker(sym) {
  tickers = tickers.filter(t => t !== sym);
  renderChips();
}
function renderChips() {
  document.getElementById('chips').innerHTML = tickers.map(t =>
    '<span class="chip">' + t + '<span class="rm" onclick="removeTicker(\'' + t + '\')">&#x2715;</span></span>'
  ).join('');
}

function destroyChart(id) {
  if (chartRegistry[id]) { chartRegistry[id].destroy(); delete chartRegistry[id]; }
}

const fmt = ts => new Date(ts).toLocaleTimeString('en-US',
  {hour:'2-digit',minute:'2-digit',timeZone:'America/New_York'});
const fmtFull = ts => new Date(ts).toLocaleString('en-US',
  {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',
   timeZone:'America/New_York'});

const REASON_COLOR = {target:'#3fb950',trail:'#f0883e',eod:'#58a6ff'};
const BADGES = {
  target:'<span class="badge badge-target">&#10003; Target</span>',
  trail: '<span class="badge badge-trail">&#8600; Trail</span>',
  eod:   '<span class="badge badge-eod">&#9201; EOD</span>',
};
function trailByLabel(key) {
  if (!key) return '&#8212;';
  if (key.startsWith('rsi'))   return 'RSI >= ' + key.slice(3);
  if (key.startsWith('price')) return 'Price ' + key.slice(5);
  if (key === 'exit_time')     return 'Exit time';
  return key;
}

async function runBacktest() {
  if (!tickers.length) { document.getElementById('status').textContent = 'Add at least one ticker.'; return; }
  const dt    = document.getElementById('dt').value.trim();
  const period= +document.getElementById('rsiPeriod').value    || 12;
  const buy   = +document.getElementById('rsiBuy').value       || 30;
  const sell  = +document.getElementById('rsiSell').value      || 70;
  const target= +document.getElementById('profitTarget').value;
  const rsiTT = +document.getElementById('rsiTrailTrigger').value || 60;
  const tAct  = +document.getElementById('trailActivate').value   || 3;
  const exitT = document.getElementById('exitTime').value         || '13:00';
  const tDist = +document.getElementById('trailDist').value       || 3;
  const btn   = document.getElementById('runBtn');
  const status= document.getElementById('status');

  if (!dt) { status.textContent = 'Select a date.'; return; }
  btn.disabled = true;
  status.textContent = 'Fetching ' + tickers.length + ' ticker(s)...';
  ['cards','tabSection','allTradesSection'].forEach(id =>
    document.getElementById(id).style.display = 'none');

  const qs = new URLSearchParams({
    symbols: tickers.join(','), date_str: dt,
    rsi_period: period, rsi_buy: buy, rsi_sell: sell,
    profit_target_pct: target,
    trail_pct: tDist, trail_activate_pct: tAct,
    rsi_trail_trigger: rsiTT, exit_time_str: exitT,
  });

  try {
    const res  = await fetch('/api/backtest/multi?' + qs);
    if (!res.ok) { const e = await res.json(); status.textContent = 'Error: ' + (e.detail || res.statusText); return; }
    const data = await res.json();
    status.textContent = tickers.length + ' ticker(s) done | RSI(' + data.rsi_period + ') buy<' + data.rsi_buy +
      ' | target ' + data.profit_target_pct + '% | trail dist ' + data.trail_pct + '%';
    render(data);
  } catch(e) {
    status.textContent = 'Network error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

function render(data) {
  const { results, total_pnl, rsi_buy, rsi_sell, rsi_period,
          rsi_trail_trigger, trail_pct, trail_activate_pct, exit_time_str } = data;

  const allTrades   = results.flatMap(r => (r.trades||[]).map(t => Object.assign({}, t, {symbol: r.symbol})));
  const closed      = allTrades.filter(t => !t.open);
  const wins        = closed.filter(t => t.pnl > 0).length;
  const winRate     = closed.length ? Math.round(wins / closed.length * 100) : 0;
  const totalBuys   = allTrades.reduce((s,t) => s + (t.buys||[]).length, 0);
  const totalInvest = allTrades.reduce((s,t) => s + (t.total_cost||0), 0);
  const byR = r     => allTrades.filter(t => t.reason === r).length;
  const totalBlocked= results.reduce((s,r) => s + (r.blocked_count||0), 0);

  const pEl = document.getElementById('cPnl');
  pEl.textContent = '$' + total_pnl.toFixed(2);
  pEl.className   = 'card-value ' + (total_pnl >= 0 ? 'green' : 'red');
  document.getElementById('cSyms').textContent     = results.length;
  document.getElementById('cTrades').textContent   = allTrades.length;
  document.getElementById('cBuys').textContent     = totalBuys;
  document.getElementById('cInvested').textContent = '$' + totalInvest.toFixed(0);
  document.getElementById('cWin').textContent      = winRate + '% (' + wins + '/' + closed.length + ')';
  document.getElementById('cTarget').textContent   = byR('target');
  document.getElementById('cTrail').textContent    = byR('trail');
  document.getElementById('cBlocked').textContent  = totalBlocked;
  document.getElementById('cards').style.display   = 'flex';

  const tabBar    = document.getElementById('tabBar');
  const tabPanels = document.getElementById('tabPanels');
  tabBar.innerHTML    = '';
  tabPanels.innerHTML = '';
  Object.keys(chartRegistry).forEach(k => { chartRegistry[k].destroy(); delete chartRegistry[k]; });

  results.forEach((r, idx) => {
    const sym    = r.symbol;
    const hasErr = !!r.error;
    const panelId= 'panel-' + sym;

    const tab = document.createElement('div');
    tab.className = 'tab' + (hasErr ? ' err' : '') + (idx === 0 ? ' active' : '');
    const symPnl = r.net_pnl != null ? ' ($' + (r.net_pnl >= 0 ? '+' : '') + r.net_pnl.toFixed(2) + ')' : '';
    tab.textContent = sym + symPnl;
    tab.onclick = () => switchTab(sym);
    tab.dataset.sym = sym;
    tabBar.appendChild(tab);

    const panel = document.createElement('div');
    panel.className = 'tab-panel' + (idx === 0 ? ' active' : '');
    panel.id = panelId;

    if (hasErr) {
      panel.innerHTML = '<div style="padding:20px;color:#f85149">' + r.error + '</div>';
    } else {
      const trades   = r.trades || [];
      const chart    = r.chart  || [];
      const netPnl   = r.net_pnl || 0;
      const pnlClass = netPnl >= 0 ? 'green' : 'red';
      const legs     = trades.reduce((s,t) => s + (t.buys||[]).length, 0);
      const invested = trades.reduce((s,t) => s + (t.total_cost||0), 0);
      const pChId    = 'pc-' + sym;
      const rChId    = 'rc-' + sym;

      panel.innerHTML =
        '<div class="sym-bar">' +
          '<span class="sym-name">' + sym + '</span>' +
          '<span class="sym-stat">Bars: <b>' + r.bars + '</b></span>' +
          '<span class="sym-stat">Exits: <b>' + trades.length + '</b></span>' +
          '<span class="sym-stat">Legs: <b>' + legs + '</b></span>' +
          '<span class="sym-stat">Invested: <b>$' + invested.toFixed(0) + '</b></span>' +
          '<span class="sym-stat">Blocked: <b>' + (r.blocked_count||0) + '</b></span>' +
          '<span class="sym-stat">Net PNL: <b class="' + pnlClass + '">$' + netPnl.toFixed(2) + '</b></span>' +
        '</div>' +
        '<div class="charts">' +
          '<div class="chart-box"><canvas id="' + pChId + '"></canvas></div>' +
          '<div class="chart-box"><canvas id="' + rChId + '"></canvas></div>' +
        '</div>';

      tabPanels.appendChild(panel);
      (function(s, ch, tr, pId, rId) {
        requestAnimationFrame(function() {
          drawCharts(s, ch, tr, rsi_buy, rsi_sell, rsi_period,
                     rsi_trail_trigger, trail_pct, exit_time_str, pId, rId);
        });
      })(sym, chart, trades, pChId, rChId);
    }

    if (!tabPanels.contains(panel)) tabPanels.appendChild(panel);
  });

  document.getElementById('tabSection').style.display = 'block';
  renderAllTrades(allTrades);
}

function switchTab(sym) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.sym === sym));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + sym));
}

function drawCharts(sym, chart, trades, rsi_buy, rsi_sell, rsi_period,
                    rsi_trail_trigger, trail_pct, exit_time_str, pChId, rChId) {
  const labels      = chart.map(c => fmt(c.t));
  const closes      = chart.map(c => c.close);
  const rsiVals     = chart.map(c => c.rsi);
  const trailSeries = chart.map(c => c.trail_stop != null ? c.trail_stop : null);

  const annotations = {};

  const exitIdx = chart.findIndex(c => {
    const t = new Date(c.t).toLocaleTimeString('en-US',
      {hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/New_York'});
    return t >= exit_time_str;
  });
  if (exitIdx >= 0) {
    annotations['exitTime'] = {
      type:'line', xMin:exitIdx, xMax:exitIdx,
      borderColor:'#484f58', borderWidth:1, borderDash:[2,4],
      label:{content:'Exit ' + exit_time_str, enabled:true, position:'start',
             color:'#8b949e', backgroundColor:'rgba(0,0,0,.5)', font:{size:8}}
    };
  }

  chart.forEach(function(c, idx) {
    if (c.signal === 'buy') {
      annotations['b' + idx] = {
        type:'line', xMin:idx, xMax:idx,
        borderColor:'#3fb950', borderWidth:1.5, borderDash:[3,3],
        label:{content:'B $' + c.close, enabled:true, position:'start',
               color:'#3fb950', backgroundColor:'rgba(0,0,0,.6)', font:{size:8}}
      };
    }
    if (c.signal === 'sell') {
      const mt  = trades.slice().reverse().find(t => new Date(t.exit_time) <= new Date(c.t));
      const rsn = mt ? mt.reason : 'trail';
      const col = REASON_COLOR[rsn] || '#e6edf3';
      const lbl = rsn === 'target' ? 'TARGET $' + c.close : rsn === 'trail' ? 'TRAIL $' + c.close : 'EOD $' + c.close;
      annotations['s' + idx] = {
        type:'line', xMin:idx, xMax:idx,
        borderColor:col, borderWidth:2, borderDash:[3,3],
        label:{content:lbl, enabled:true, position:'end',
               color:col, backgroundColor:'rgba(0,0,0,.6)', font:{size:8}}
      };
    }
  });

  trades.forEach(function(t, i) {
    if (!t.buys || !t.buys.length) return;
    const xS = chart.findIndex(c => new Date(c.t) >= new Date(t.buys[0].time));
    const xE = chart.findIndex(c => new Date(c.t) >= new Date(t.exit_time));
    if (xS >= 0 && xE > xS) {
      annotations['avg' + i] = {
        type:'line', yMin:t.avg_entry, yMax:t.avg_entry, xMin:xS, xMax:xE,
        borderColor:'rgba(188,140,255,.5)', borderWidth:1, borderDash:[2,5],
        label:{content:'avg $' + t.avg_entry, enabled:true, position:'center',
               color:'#bc8cff', backgroundColor:'rgba(0,0,0,.4)', font:{size:7}}
      };
    }
  });

  destroyChart(pChId);
  chartRegistry[pChId] = new Chart(document.getElementById(pChId).getContext('2d'), {
    type:'line',
    data:{labels:labels, datasets:[
      {label:sym, data:closes, borderColor:'#58a6ff', borderWidth:1.5,
       pointRadius:0, tension:0.1, fill:false, order:1},
      {label:'Trail Stop (' + trail_pct + '%)', data:trailSeries,
       borderColor:'#f0883e', borderWidth:1.1, borderDash:[4,3],
       pointRadius:0, tension:0, fill:false, spanGaps:false, order:2},
    ]},
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{
        legend:{labels:{color:'#8b949e', boxWidth:11, font:{size:10}}},
        annotation:{annotations:annotations}
      },
      scales:{
        x:{ticks:{color:'#8b949e', maxTicksLimit:12}, grid:{color:'#21262d'}},
        y:{ticks:{color:'#8b949e'}, grid:{color:'#21262d'}}
      }
    }
  });

  const rsiAnno = {
    lineBuy:{type:'line', yMin:rsi_buy, yMax:rsi_buy, borderColor:'#3fb950', borderWidth:1, borderDash:[4,4],
             label:{content:'Buy ' + rsi_buy, enabled:true, position:'end', color:'#3fb950', font:{size:8}, backgroundColor:'transparent'}},
    lineTrail:{type:'line', yMin:rsi_trail_trigger, yMax:rsi_trail_trigger, borderColor:'#f0883e', borderWidth:1, borderDash:[3,3],
              label:{content:'Trail ' + rsi_trail_trigger, enabled:true, position:'end', color:'#f0883e', font:{size:8}, backgroundColor:'transparent'}},
    lineSell:{type:'line', yMin:rsi_sell, yMax:rsi_sell, borderColor:'#bc8cff', borderWidth:1.5, borderDash:[4,4],
              label:{content:'TrailOB ' + rsi_sell, enabled:true, position:'end', color:'#bc8cff', font:{size:8}, backgroundColor:'transparent'}},
  };

  destroyChart(rChId);
  chartRegistry[rChId] = new Chart(document.getElementById(rChId).getContext('2d'), {
    type:'line',
    data:{labels:labels, datasets:[{
      label:'RSI(' + rsi_period + ')', data:rsiVals,
      borderColor:'#d29922', borderWidth:1.5,
      pointRadius:0, tension:0.1, fill:false, spanGaps:true,
    }]},
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{
        legend:{labels:{color:'#8b949e'}},
        annotation:{annotations:rsiAnno}
      },
      scales:{
        x:{ticks:{color:'#8b949e', maxTicksLimit:12}, grid:{color:'#21262d'}},
        y:{min:0, max:100, ticks:{color:'#8b949e', stepSize:10}, grid:{color:'#21262d'}}
      }
    }
  });
}

function renderAllTrades(allTrades) {
  document.getElementById('allTradeTag').textContent = allTrades.length + ' total across all symbols';
  const tbody = document.getElementById('allTradeBody');
  tbody.innerHTML = '';

  if (!allTrades.length) {
    tbody.innerHTML = '<tr><td colspan="13" style="text-align:center;color:#8b949e;padding:20px">No trades triggered</td></tr>';
    document.getElementById('allTradesSection').style.display = 'block';
    return;
  }

  const sorted = allTrades.slice().sort(function(a, b) {
    const aT = a.buys && a.buys.length ? a.buys[0].time : a.exit_time;
    const bT = b.buys && b.buys.length ? b.buys[0].time : b.exit_time;
    return new Date(aT) - new Date(bT);
  });

  sorted.forEach(function(t, i) {
    const tradeIdx = i + 1;
    const pnlPct   = t.total_cost > 0 ? (t.pnl / t.total_cost * 100).toFixed(2) : '—';
    const pClass   = t.pnl >= 0 ? 'green' : 'red';
    const rowId    = 'all-sub-' + tradeIdx;
    tbody.innerHTML +=
      '<tr>' +
        '<td><button class="toggle-btn" onclick="toggleSub(event,\'' + rowId + '\')">&#9658;</button></td>' +
        '<td style="font-weight:700;color:#58a6ff">' + t.symbol + '</td>' +
        '<td>' + tradeIdx + '</td>' +
        '<td>' + (t.buys||[]).length + '</td>' +
        '<td>$' + t.avg_entry + '</td>' +
        '<td>' + t.total_shares + '</td>' +
        '<td>$' + t.total_cost.toFixed(2) + '</td>' +
        '<td>' + fmtFull(t.exit_time) + '</td>' +
        '<td>$' + t.exit_price + '</td>' +
        '<td class="' + pClass + '" style="font-weight:700">$' + t.pnl.toFixed(2) + '</td>' +
        '<td class="' + pClass + '">' + pnlPct + '%</td>' +
        '<td>' + (BADGES[t.reason] || t.reason) + '</td>' +
        '<td style="color:#8b949e;font-size:.72rem">' + trailByLabel(t.trail_reason) + '</td>' +
      '</tr>';
    (t.buys||[]).forEach(function(b, bi) {
      tbody.innerHTML +=
        '<tr class="sub-row" id="' + rowId + '-' + bi + '" style="display:none">' +
          '<td></td>' +
          '<td style="color:#484f58">' + t.symbol + '</td>' +
          '<td style="color:#484f58">' + tradeIdx + '.' + (bi+1) + '</td>' +
          '<td><span style="color:#3fb950">&#9650; BUY</span></td>' +
          '<td colspan="2">$' + b.price + ' x ' + b.shares + ' sh = $' + b.spend.toFixed(2) + '</td>' +
          '<td colspan="7" style="color:#8b949e">' + fmtFull(b.time) + '</td>' +
        '</tr>';
    });
  });

  document.getElementById('allTradesSection').style.display = 'block';
}

function toggleSub(e, rowId) {
  var i = 0;
  while(true) {
    var el = document.getElementById(rowId + '-' + i);
    if (!el) break;
    el.style.display = el.style.display === 'none' ? '' : 'none';
    i++;
  }
  e.target.textContent = e.target.textContent === '▶' ? '▼' : '▶';
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && document.activeElement.id !== 'symInput') runBacktest();
});
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(HTML)


from batch_page import BATCH_HTML

@app.get("/batch", response_class=HTMLResponse)
async def batch_page_route():
    return HTMLResponse(BATCH_HTML)


# ── Multi-day: fetch full date-range bars in one paginated call ───────────────

async def fetch_bars_range(symbol: str, s_date: date, e_date: date):
    """Fetch 1-min extended-hours bars (4 AM – 8 PM ET) for a date range."""
    start_dt = datetime(s_date.year, s_date.month, s_date.day,  4, 0, tzinfo=NY)
    end_dt   = datetime(e_date.year, e_date.month, e_date.day,  20, 0, tzinfo=NY)
    url      = f"{DATA_BASE}/v2/stocks/{symbol}/bars"
    params   = {
        "timeframe":  "1Min",
        "start":      start_dt.isoformat(),
        "end":        end_dt.isoformat(),
        "limit":      10000,
        "feed":       "iex",
        "adjustment": "raw",
    }
    headers  = {
        "APCA-API-KEY-ID":     API_KEY,
        "APCA-API-SECRET-KEY": SECRET_KEY,
    }
    bars = []
    async with httpx.AsyncClient(timeout=120, verify=False) as client:
        while True:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200:
                raise HTTPException(r.status_code, f"Alpaca error: {r.text}")
            data = r.json()
            bars.extend(data.get("bars") or [])
            token = data.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
    return bars


# ── Continuous multi-day strategy engine ─────────────────────────────────────

def run_backtest_continuous(
    bars:               list,
    rsi_period:         int   = 12,
    rsi_buy:            float = 30.0,
    rsi_sell:           float = 65.0,
    profit_target_pct:  float = 10.0,
    trail_pct:          float = 3.0,
    trail_activate_pct: float = 3.0,
    rsi_trail_trigger:  float = 60.0,
):
    """
    Overnight / continuous strategy:
      - Positions CARRY OVERNIGHT — no forced EOD close
      - Buys allowed only in regular hours: 09:30–16:00 ET each day
      - Trailing stop ONLY fires when close > avg_entry  (no-loss guard is ALWAYS on)
      - Trail arms on: RSI >= rsi_sell, RSI >= rsi_trail_trigger, price >= avg*(1+trail_activate_pct%)
        (no time-based forcing)
      - End-of-range: any open position is marked as 'open' (still holding)
    """
    if not bars:
        return [], [], []

    closes   = [b["c"] for b in bars]
    times    = [datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                for b in bars]
    rsi_vals = compute_rsi(closes, period=rsi_period)

    total_shares  = 0
    total_cost    = 0.0
    below_seen    = False
    trail_active  = False
    trail_peak    = 0.0
    trail_reason  = None

    buys   = []
    trades = []
    chart  = []

    for ts, close, rsi in zip(times, closes, rsi_vals):
        signal      = None
        exit_reason = None

        if rsi is None:
            chart.append({"t": ts.isoformat(), "close": close, "rsi": None,
                          "signal": None, "trail_stop": None, "avg_entry": None})
            continue

        avg_entry  = (total_cost / total_shares) if total_shares > 0 else 0.0
        trail_stop = round(trail_peak * (1 - trail_pct / 100), 4) if trail_active else None

        # ── SELL LOGIC ──────────────────────────────────────────────────────
        if total_shares > 0:
            # 1. Instant: profit target
            if profit_target_pct > 0 and close >= avg_entry * (1 + profit_target_pct / 100):
                exit_reason = "target"
            else:
                # Arm trailing stop (3 conditions — NO time-based forcing)
                if not trail_active:
                    if rsi >= rsi_sell:
                        trail_active = True; trail_peak = close
                        trail_reason = f"rsi{int(rsi_sell)}"
                    elif rsi >= rsi_trail_trigger:
                        trail_active = True; trail_peak = close
                        trail_reason = f"rsi{int(rsi_trail_trigger)}"
                    elif close >= avg_entry * (1 + trail_activate_pct / 100):
                        trail_active = True; trail_peak = close
                        trail_reason = f"price+{trail_activate_pct}%"

                # Fire trailing stop — ONLY if close > avg_entry (always protected)
                if trail_active:
                    if close > trail_peak:
                        trail_peak = close
                    trail_stop  = round(trail_peak * (1 - trail_pct / 100), 4)
                    # No-loss guard: trail never fires below avg cost
                    if close <= trail_stop and close > avg_entry:
                        exit_reason = "trail"

            # Execute exit
            if exit_reason:
                pnl = round(close * total_shares - total_cost, 2)
                trades.append({
                    "avg_entry":    round(avg_entry, 4),
                    "total_shares": total_shares,
                    "total_cost":   round(total_cost, 2),
                    "exit_price":   round(close, 4),
                    "exit_time":    ts.isoformat(),
                    "exit_date":    ts.date().isoformat(),
                    "pnl":          pnl,
                    "open":         False,
                    "reason":       exit_reason,
                    "trail_reason": trail_reason,
                    "buys":         list(buys),
                })
                signal       = "sell"
                total_shares = 0;  total_cost  = 0.0
                trail_active = False; trail_peak = 0.0; trail_reason = None
                buys = [];  below_seen = False
                avg_entry = 0.0;  trail_stop = None

        # ── BUY LOGIC — regular hours only: 09:30–16:00 ET ─────────────────
        is_regular = (ts.hour, ts.minute) >= (9, 30) and (ts.hour, ts.minute) < (16, 0)
        if exit_reason is None and is_regular:
            if rsi < rsi_buy:
                below_seen = True
            if below_seen and rsi >= rsi_buy and close > 0:
                new_shares = int(1000 / close)
                if new_shares > 0:
                    total_shares += new_shares
                    total_cost   += new_shares * close
                    below_seen    = False
                    signal        = "buy"
                    buys.append({
                        "time":   ts.isoformat(),
                        "price":  round(close, 4),
                        "shares": new_shares,
                        "spend":  round(new_shares * close, 2),
                    })
                    # New buy raises avg — if trail_peak now below new arm threshold, disarm
                    if trail_active:
                        new_avg = total_cost / total_shares
                        if trail_peak < new_avg * (1 + trail_activate_pct / 100):
                            trail_active = False; trail_peak = 0.0; trail_reason = None

        # Update trail_stop for chart
        if total_shares > 0 and trail_active:
            trail_stop = round(trail_peak * (1 - trail_pct / 100), 4)
        else:
            trail_stop = None

        chart.append({
            "t":            ts.isoformat(),
            "close":        close,
            "rsi":          rsi,
            "signal":       signal,
            "trail_stop":   trail_stop,
            "trail_active": trail_active and total_shares > 0,
            "avg_entry":    round(avg_entry, 4) if total_shares > 0 else None,
        })

    # End of range: still holding → mark as open (not closed)
    if total_shares > 0:
        avg_entry  = total_cost / total_shares
        last_close = closes[-1]
        pnl        = round(last_close * total_shares - total_cost, 2)
        trades.append({
            "avg_entry":    round(avg_entry, 4),
            "total_shares": total_shares,
            "total_cost":   round(total_cost, 2),
            "exit_price":   round(last_close, 4),
            "exit_time":    times[-1].isoformat(),
            "exit_date":    times[-1].date().isoformat(),
            "pnl":          pnl,
            "open":         True,
            "reason":       "open",
            "trail_reason": trail_reason,
            "buys":         list(buys),
        })

    return buys, trades, chart


# ── Multi-day backtest API ────────────────────────────────────────────────────

@app.get("/api/multiday")
async def multiday_backtest(
    symbols:             str,
    start_date:          str,
    end_date:            str,
    rsi_period:          int   = 12,
    rsi_buy:             float = 30.0,
    rsi_sell:            float = 65.0,
    profit_target_pct:   float = 10.0,
    trail_pct:           float = 3.0,
    trail_activate_pct:  float = 3.0,
    rsi_trail_trigger:   float = 60.0,
    concurrency:         int   = 6,
):
    """
    Continuous overnight RSI backtest across a date range.
    Positions carry overnight — NO EOD close.
    Trail only fires when close > avg_entry (no-loss guard always active).
    """
    import asyncio as _asyncio
    from collections import defaultdict as _dd

    try:
        s_date = date.fromisoformat(start_date)
        e_date = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "start_date/end_date must be YYYY-MM-DD")
    if s_date > e_date:
        raise HTTPException(400, "start_date must be <= end_date")
    if (e_date - s_date).days > 180:
        raise HTTPException(400, "Date range too large (max 6 months)")

    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(400, "Provide at least one symbol")

    sem = _asyncio.Semaphore(concurrency)

    async def _run_sym(sym: str):
        async with sem:
            try:
                bars = await fetch_bars_range(sym, s_date, e_date)
                if not bars:
                    return {"symbol": sym, "error": "No data", "net_pnl": 0,
                            "trades": [], "bars": 0}
                _, trades, chart = run_backtest_continuous(
                    bars,
                    rsi_period=rsi_period, rsi_buy=rsi_buy, rsi_sell=rsi_sell,
                    profit_target_pct=profit_target_pct, trail_pct=trail_pct,
                    trail_activate_pct=trail_activate_pct,
                    rsi_trail_trigger=rsi_trail_trigger,
                )
                net_pnl = round(sum(t["pnl"] for t in trades), 2)
                return {
                    "symbol":   sym,
                    "bars":     len(bars),
                    "trades":   trades,
                    "net_pnl":  net_pnl,
                    # chart omitted by default — large; available via separate endpoint if needed
                }
            except Exception as exc:
                return {"symbol": sym, "error": str(exc), "net_pnl": 0,
                        "trades": [], "bars": 0}

    sym_results = await _asyncio.gather(*[_run_sym(s) for s in sym_list])

    # ── Build daily PNL breakdown ─────────────────────────────────────────────
    # Attribute each closed trade to its exit_date; open trades to end_date
    day_map = _dd(lambda: {"date": "", "net_pnl": 0.0, "trades": 0, "symbols": {}})

    by_symbol = {}
    for r in sym_results:
        sym       = r["symbol"]
        all_pnl   = 0.0
        win_trades = 0
        total_trades = 0

        for t in r.get("trades", []):
            exit_d = t.get("exit_date") or end_date
            pnl    = t["pnl"]
            all_pnl += pnl
            total_trades += 1
            if pnl > 0:
                win_trades += 1

            day_map[exit_d]["date"]    = exit_d
            day_map[exit_d]["net_pnl"] = round(day_map[exit_d]["net_pnl"] + pnl, 2)
            day_map[exit_d]["trades"] += 1
            prev = day_map[exit_d]["symbols"].get(sym, {"pnl": 0.0, "trades": 0})
            day_map[exit_d]["symbols"][sym] = {
                "pnl":    round(prev["pnl"] + pnl, 2),
                "trades": prev["trades"] + 1,
            }

        by_symbol[sym] = {
            "symbol":       sym,
            "bars":         r.get("bars", 0),
            "net_pnl":      round(all_pnl, 2),
            "trades":       total_trades,
            "win_trades":   win_trades,
            "win_rate":     round(win_trades / total_trades * 100, 1) if total_trades else 0,
            "open_position": any(t.get("open") for t in r.get("trades", [])),
            "error":         r.get("error"),
        }

    daily_sorted = [day_map[k] for k in sorted(day_map)]

    return {
        "symbols":      sym_list,
        "start_date":   start_date,
        "end_date":     end_date,
        "trading_days": len(daily_sorted),
        "total_pnl":    round(sum(r["net_pnl"] for r in sym_results), 2),
        "by_symbol":    by_symbol,
        "daily":        daily_sorted,
        "rows":         sym_results,   # full trade list per symbol
    }


from multiday_page import MULTIDAY_HTML

@app.get("/multiday", response_class=HTMLResponse)
async def multiday_page_route():
    return HTMLResponse(MULTIDAY_HTML)


# ── Momentum strategy helpers ─────────────────────────────────────────────────

def compute_vwap_session(bars: list, times: list, market_open: datetime) -> list:
    """VWAP anchored to 09:30 market open (ignores pre-market bars)."""
    cum_vol = 0.0; cum_tpv = 0.0
    result = []
    for b, ts in zip(bars, times):
        if ts < market_open:
            result.append(None); continue
        tp = (b['h'] + b['l'] + b['c']) / 3.0
        cum_vol += b['v']; cum_tpv += tp * b['v']
        result.append(round(cum_tpv / cum_vol, 4) if cum_vol > 0 else None)
    return result


def compute_atr_wilder(bars: list, period: int = 14) -> list:
    """Wilder-smoothed ATR."""
    trs = [bars[0]['h'] - bars[0]['l']]
    for i in range(1, len(bars)):
        pc = bars[i-1]['c']
        trs.append(max(bars[i]['h'] - bars[i]['l'],
                       abs(bars[i]['h'] - pc), abs(bars[i]['l'] - pc)))
    atr = [None] * len(bars)
    if len(bars) >= period:
        atr[period - 1] = sum(trs[:period]) / period
        for i in range(period, len(bars)):
            atr[i] = (atr[i-1] * (period - 1) + trs[i]) / period
    return atr


def run_momentum_backtest(
    bars:               list,
    trade_day:          date,
    # Gates
    flush_pct:          float = 5.0,    # Gate 1: highest close in lookback is this % above current close
    flush_lookback:     int   = 10,     # Gate 1: bars to look back
    base_candles:       int   = 5,      # Gate 2: base window size
    base_range_pct:     float = 2.0,    # Gate 2: max high-low range %
    trigger_atr_mult:   float = 1.5,    # Gate 3: body >= N × ATR
    trigger_vol_mult:   float = 2.0,    # Gate 3: vol >= N × base avg vol
    atr_period:         int   = 14,
    # Entry / sizing
    max_risk:           float = 200.0,  # $ max risk per trade
    stop_buffer:        float = 0.10,   # dollar buffer below base low for stop
    t1_r:               float = 1.0,    # T1 = entry + t1_r × R
    t2_r:               float = 2.0,    # T2 = entry + t2_r × R
    # Exits
    t1_scale_pct:       float = 40.0,   # % of position to sell at T1
    t2_scale_pct:       float = 40.0,   # % of position to sell at T2
    trail_pct:          float = 3.0,    # trailing stop % from peak on remainder
    time_exit_bars:     int   = 10,     # bars with no T1 progress → time exit
    watch_end_str:      str   = "11:00",# stop entering (and force-exit open pos) at this time
):
    """
    Flush-and-base momentum strategy.

    STATES: WATCHING → IN_POSITION → (WATCHING again after exit)

    GATES (all three must pass on same bar, any fail → WATCHING):
      1. Flush: max close in last flush_lookback bars is >= flush_pct% above current close
      2. Base:  last base_candles bars (before trigger) have range <= base_range_pct%
                AND volume declining (2nd half < 1st half)
      3. Trigger candle: green, body >= trigger_atr_mult×ATR, close > base_high,
                         vol >= trigger_vol_mult × base_avg_vol

    VWAP FILTER (after Gate 3): close >= VWAP, else skip

    ENTRY:
      entry = close of trigger bar
      stop  = base_low - stop_buffer
      R     = entry - stop
      T1/T2 = entry + t1_r/t2_r × R
      shares = floor(max_risk / R)

    EXITS:
      Stop hit    → close all remaining shares
      T1 hit      → sell t1_scale_pct%, move stop to entry (breakeven)
      T2 hit      → sell t2_scale_pct%, activate trail on remainder
      Trail fires → close remainder
      Time exit   → 10 bars with no T1 hit, OR watch_end reached → close all
    """
    if not bars:
        return [], []

    times    = [datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                for b in bars]
    mkt_open  = _make_dt(trade_day, "09:30", NY)
    watch_end = _make_dt(trade_day, watch_end_str, NY)

    vwap_vals = compute_vwap_session(bars, times, mkt_open)
    atr_vals  = compute_atr_wilder(bars, period=atr_period)

    trades     = []
    chart_data = []
    state      = "WATCHING"
    pos        = None          # position dict when IN_POSITION
    min_i      = max(flush_lookback, atr_period, base_candles + 1)

    for i, (ts, b) in enumerate(zip(times, bars)):
        close = b['c']; high = b['h']; low = b['l']
        cd = {
            "t": ts.isoformat(),
            "o": b['o'], "h": high, "l": low, "c": close, "v": b['v'],
            "vwap": vwap_vals[i], "atr": atr_vals[i],
            "signal": None, "state": state,
            "g1": None, "g2": None, "g3": None, "vwap_ok": None,
            "stop": None, "stop_orig": None,
            "t1": None, "t2": None, "trail_stop": None, "entry": None,
        }

        # ── IN_POSITION ──────────────────────────────────────────────────────
        if state == "IN_POSITION":
            cd.update({
                "stop": pos['stop'], "stop_orig": pos['stop_orig'],
                "t1": pos['t1'],   "t2": pos['t2'], "entry": pos['entry'],
            })
            if pos['trail_active']:
                cd['trail_stop'] = round(pos['peak'] * (1 - trail_pct / 100), 4)

            exit_reason = None; exit_price = None
            bars_held   = i - pos['entry_bar']

            # Update peak
            if high > pos['peak']:
                pos['peak'] = high

            # ── Stop hit (priority 1) ──
            if low <= pos['stop']:
                exit_reason = "stop"; exit_price = pos['stop']

            else:
                # ── T1 hit ──
                if not pos['t1_hit'] and high >= pos['t1']:
                    pos['t1_hit'] = True
                    n = min(max(1, int(pos['orig_shares'] * t1_scale_pct / 100)), pos['shares'])
                    pos['shares'] -= n
                    pos['exit_parts'].append({
                        "time": ts.isoformat(), "price": round(pos['t1'], 4),
                        "shares": n, "reason": "T1",
                        "pnl": round((pos['t1'] - pos['entry']) * n, 2),
                    })
                    pos['stop'] = pos['entry']    # breakeven
                    cd['stop']  = pos['stop']
                    cd['signal'] = 'T1'

                # ── T2 hit ──
                if pos['t1_hit'] and not pos['t2_hit'] and high >= pos['t2']:
                    pos['t2_hit'] = True
                    n = min(max(1, int(pos['orig_shares'] * t2_scale_pct / 100)), pos['shares'])
                    pos['shares'] -= n
                    pos['exit_parts'].append({
                        "time": ts.isoformat(), "price": round(pos['t2'], 4),
                        "shares": n, "reason": "T2",
                        "pnl": round((pos['t2'] - pos['entry']) * n, 2),
                    })
                    pos['trail_active'] = True; pos['peak'] = high
                    cd['signal'] = 'T2' if cd['signal'] != 'T1' else 'T1T2'

                # ── Trail fire ──
                if pos['trail_active'] and pos['shares'] > 0:
                    if high > pos['peak']: pos['peak'] = high
                    ts_val = round(pos['peak'] * (1 - trail_pct / 100), 4)
                    cd['trail_stop'] = ts_val
                    if low <= ts_val:
                        exit_reason = "trail"; exit_price = ts_val

                # ── Time exit: 10 bars flat (no T1) OR watch_end reached ──
                if exit_reason is None:
                    time_limit = (not pos['t1_hit'] and bars_held >= time_exit_bars)
                    end_hit    = ts >= watch_end and not pos['t1_hit']
                    if time_limit or end_hit:
                        exit_reason = "time"; exit_price = close

            # ── Execute exit ──
            if exit_reason and pos['shares'] > 0:
                pnl_rem = round((exit_price - pos['entry']) * pos['shares'], 2)
                pos['exit_parts'].append({
                    "time": ts.isoformat(), "price": round(exit_price, 4),
                    "shares": pos['shares'], "reason": exit_reason, "pnl": pnl_rem,
                })
                total_pnl = round(sum(p['pnl'] for p in pos['exit_parts']), 2)
                trades.append({
                    "entry_time":  pos['entry_time'],
                    "entry_price": round(pos['entry'], 4),
                    "stop_orig":   round(pos['stop_orig'], 4),
                    "t1":          round(pos['t1'], 4),
                    "t2":          round(pos['t2'], 4),
                    "R":           round(pos['R'], 4),
                    "orig_shares": pos['orig_shares'],
                    "exit_reason": exit_reason,
                    "exit_time":   ts.isoformat(),
                    "exit_price":  round(exit_price, 4),
                    "pnl":         total_pnl,
                    "parts":       pos['exit_parts'],
                    "base_high":   round(pos['base_high'], 4),
                    "base_low":    round(pos['base_low'], 4),
                })
                if cd['signal'] not in ('T1', 'T2', 'T1T2'):
                    cd['signal'] = 'exit_' + exit_reason
                state = "WATCHING"; pos = None

        # ── WATCHING ─────────────────────────────────────────────────────────
        else:
            in_window = mkt_open <= ts < watch_end
            atr_ready = atr_vals[i] is not None
            if in_window and atr_ready and i >= min_i:

                # Gate 1: highest close in last flush_lookback bars is flush_pct% above current close
                w0 = max(0, i - flush_lookback + 1)
                roll_close_high = max(bars[j]['c'] for j in range(w0, i + 1))
                g1 = (roll_close_high - close) / roll_close_high >= flush_pct / 100.0
                cd['g1'] = g1

                if g1:
                    # Gate 2: last base_candles bars BEFORE current form tight base
                    bw = bars[i - base_candles: i]
                    if len(bw) == base_candles:
                        base_high = max(x['h'] for x in bw)
                        base_low  = min(x['l'] for x in bw)
                        rng       = (base_high - base_low) / base_low if base_low > 0 else 999
                        vols      = [x['v'] for x in bw]
                        half      = len(vols) // 2
                        vol_decl  = (sum(vols[half:]) < sum(vols[:half])) if half > 0 else True
                        g2        = rng <= base_range_pct / 100.0 and vol_decl
                        cd['g2']  = g2

                        if g2:
                            avg_base_vol = sum(vols) / len(vols)
                            # Gate 3: trigger candle
                            body = close - b['o']          # positive only for green
                            g3   = (
                                body >= trigger_atr_mult * atr_vals[i]   # green + body size
                                and close > base_high                     # breaks above base
                                and b['v'] >= trigger_vol_mult * avg_base_vol  # vol surge
                            )
                            cd['g3'] = g3

                            if g3:
                                # VWAP filter
                                vwap_ok   = vwap_vals[i] is not None and close >= vwap_vals[i]
                                cd['vwap_ok'] = vwap_ok

                                if not vwap_ok:
                                    cd['signal'] = 'skip_vwap'
                                else:
                                    # ── ENTER ──
                                    entry  = close
                                    stop   = round(base_low - stop_buffer, 4)
                                    R      = entry - stop
                                    if R > 0.01:
                                        t1     = round(entry + t1_r * R, 4)
                                        t2     = round(entry + t2_r * R, 4)
                                        shares = max(1, int(max_risk / R))
                                        pos = {
                                            "entry":        entry,
                                            "stop":         stop, "stop_orig": stop,
                                            "t1":           t1,   "t2":        t2,
                                            "R":            R,    "shares":    shares,
                                            "orig_shares":  shares,
                                            "t1_hit":       False, "t2_hit":   False,
                                            "trail_active": False, "peak":     entry,
                                            "entry_bar":    i,
                                            "entry_time":   ts.isoformat(),
                                            "base_high":    base_high,
                                            "base_low":     base_low,
                                            "exit_parts":   [],
                                        }
                                        state = "IN_POSITION"
                                        cd.update({
                                            "signal": "buy", "stop": stop,
                                            "stop_orig": stop, "t1": t1,
                                            "t2": t2, "entry": entry,
                                        })

        cd['state'] = state
        chart_data.append(cd)

    # EOD: still in position → mark as open
    if state == "IN_POSITION" and pos and pos['shares'] > 0:
        lc = bars[-1]['c']
        pos['exit_parts'].append({
            "time": times[-1].isoformat(), "price": lc,
            "shares": pos['shares'], "reason": "eod",
            "pnl": round((lc - pos['entry']) * pos['shares'], 2),
        })
        trades.append({
            "entry_time":  pos['entry_time'],
            "entry_price": round(pos['entry'], 4),
            "stop_orig":   round(pos['stop_orig'], 4),
            "t1":          round(pos['t1'], 4),
            "t2":          round(pos['t2'], 4),
            "R":           round(pos['R'], 4),
            "orig_shares": pos['orig_shares'],
            "exit_reason": "eod",
            "exit_time":   times[-1].isoformat(),
            "exit_price":  round(lc, 4),
            "pnl":         round(sum(p['pnl'] for p in pos['exit_parts']), 2),
            "parts":       pos['exit_parts'],
            "base_high":   round(pos['base_high'], 4),
            "base_low":    round(pos['base_low'], 4),
        })

    return trades, chart_data


# ── Momentum API ──────────────────────────────────────────────────────────────

@app.get("/api/momentum")
async def momentum_single(
    symbol:            str,
    date_str:          str,
    flush_pct:         float = 5.0,
    flush_lookback:    int   = 10,
    base_candles:      int   = 5,
    base_range_pct:    float = 2.0,
    trigger_atr_mult:  float = 1.5,
    trigger_vol_mult:  float = 2.0,
    atr_period:        int   = 14,
    max_risk:          float = 200.0,
    stop_buffer:       float = 0.10,
    t1_r:              float = 1.0,
    t2_r:              float = 2.0,
    t1_scale_pct:      float = 40.0,
    t2_scale_pct:      float = 40.0,
    trail_pct:         float = 3.0,
    time_exit_bars:    int   = 10,
    watch_end_str:     str   = "11:00",
):
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(400, "date_str must be YYYY-MM-DD")

    bars = await fetch_bars(symbol.upper(), day)
    if not bars:
        raise HTTPException(404, f"No data for {symbol} on {date_str}")

    trades, chart = run_momentum_backtest(
        bars, day,
        flush_pct=flush_pct, flush_lookback=flush_lookback,
        base_candles=base_candles, base_range_pct=base_range_pct,
        trigger_atr_mult=trigger_atr_mult, trigger_vol_mult=trigger_vol_mult,
        atr_period=atr_period, max_risk=max_risk, stop_buffer=stop_buffer,
        t1_r=t1_r, t2_r=t2_r,
        t1_scale_pct=t1_scale_pct, t2_scale_pct=t2_scale_pct,
        trail_pct=trail_pct, time_exit_bars=time_exit_bars,
        watch_end_str=watch_end_str,
    )
    return {
        "symbol":  symbol.upper(), "date": date_str, "bars": len(bars),
        "trades":  trades,
        "net_pnl": round(sum(t['pnl'] for t in trades), 2),
        "chart":   chart,
    }


@app.get("/api/momentum/range")
async def momentum_range(
    symbol:            str,
    start_date:        str,
    end_date:          str,
    flush_pct:         float = 5.0,
    flush_lookback:    int   = 10,
    base_candles:      int   = 5,
    base_range_pct:    float = 2.0,
    trigger_atr_mult:  float = 1.5,
    trigger_vol_mult:  float = 2.0,
    atr_period:        int   = 14,
    max_risk:          float = 200.0,
    stop_buffer:       float = 0.10,
    t1_r:              float = 1.0,
    t2_r:              float = 2.0,
    t1_scale_pct:      float = 40.0,
    t2_scale_pct:      float = 40.0,
    trail_pct:         float = 3.0,
    time_exit_bars:    int   = 10,
    watch_end_str:     str   = "11:00",
    concurrency:       int   = 6,
):
    """Run momentum strategy across a date range for one symbol. No chart data returned."""
    import asyncio as _asyncio
    from datetime import timedelta

    try:
        s_date = date.fromisoformat(start_date)
        e_date = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")
    if (e_date - s_date).days > 180:
        raise HTTPException(400, "Max range 6 months")

    days = []
    cur = s_date
    while cur <= e_date:
        if cur.weekday() < 5: days.append(cur)
        cur += timedelta(days=1)

    sem = _asyncio.Semaphore(concurrency)
    sym = symbol.upper()

    async def _run_day(d):
        async with sem:
            try:
                bars = await fetch_bars(sym, d)
                if not bars: return {"date": d.isoformat(), "bars": 0, "trades": [], "net_pnl": 0}
                trades, _ = run_momentum_backtest(
                    bars, d,
                    flush_pct=flush_pct, flush_lookback=flush_lookback,
                    base_candles=base_candles, base_range_pct=base_range_pct,
                    trigger_atr_mult=trigger_atr_mult, trigger_vol_mult=trigger_vol_mult,
                    atr_period=atr_period, max_risk=max_risk, stop_buffer=stop_buffer,
                    t1_r=t1_r, t2_r=t2_r,
                    t1_scale_pct=t1_scale_pct, t2_scale_pct=t2_scale_pct,
                    trail_pct=trail_pct, time_exit_bars=time_exit_bars,
                    watch_end_str=watch_end_str,
                )
                return {"date": d.isoformat(), "bars": len(bars),
                        "trades": trades, "net_pnl": round(sum(t['pnl'] for t in trades), 2)}
            except Exception as e:
                return {"date": d.isoformat(), "bars": 0, "trades": [], "net_pnl": 0, "error": str(e)}

    results   = await _asyncio.gather(*[_run_day(d) for d in days])
    valid     = [r for r in results if r.get("bars", 0) > 0]
    all_trades= [t for r in valid for t in r.get("trades", [])]
    wins      = sum(1 for t in all_trades if t['pnl'] > 0)
    return {
        "symbol": sym, "start_date": start_date, "end_date": end_date,
        "days_tested":  len(valid),
        "total_trades": len(all_trades),
        "wins":         wins,
        "losses":       len(all_trades) - wins,
        "win_rate":     round(wins / len(all_trades) * 100, 1) if all_trades else 0,
        "net_pnl":      round(sum(t['pnl'] for t in all_trades), 2),
        "avg_trade":    round(sum(t['pnl'] for t in all_trades) / len(all_trades), 2) if all_trades else 0,
        "best_trade":   max((t['pnl'] for t in all_trades), default=0),
        "worst_trade":  min((t['pnl'] for t in all_trades), default=0),
        "days":         results,
    }


from momentum_page import MOMENTUM_HTML

@app.get("/momentum", response_class=HTMLResponse)
async def momentum_page_route():
    return HTMLResponse(MOMENTUM_HTML)


# ── Spike momentum strategy ───────────────────────────────────────────────────

def run_spike_momentum(
    bars,
    trade_day:          date,
    spike_type:         str   = "prev_bar",   # "prev_bar" | "day_open"
    # Auto-classification price thresholds
    nano_max_price:     float = 5.0,
    small_max_price:    float = 20.0,
    # Nano-cap params
    nano_spike_pct:     float = 10.0,
    nano_min_vol:       int   = 50_000,
    nano_rsi_profit:    float = 60.0,
    nano_buy_amount:    float = 500.0,
    # Small-cap params
    small_spike_pct:    float = 5.0,
    small_min_vol:      int   = 200_000,
    small_rsi_profit:   float = 65.0,
    small_buy_amount:   float = 1000.0,
    # Timing
    entry_start_str:    str   = "09:30",
    entry_end_str:      str   = "11:00",
    time_exit_str:      str   = "15:30",
    # RSI
    rsi_period:         int   = 14,
):
    """
    Spike Momentum Strategy
    ───────────────────────
    ENTRY  : price spike % + volume surge in entry window
             spike_type="prev_bar"  → (close - prev_bar_close) / prev_bar_close
             spike_type="day_open"  → (close - day_open_price) / day_open_price
             Auto-classifies as nano (<nano_max_price) or small (<small_max_price)
             — stocks above small_max_price are skipped

    EXIT   (priority order):
      1. time_exit reached          → market close
      2. RSI >= rsi_profit          → market close  (momentum captured)
      3. bar.low <= avg_entry       → limit sell at avg_entry  (breakeven stop)
      4. EOD last bar               → market close

    RE-ENTRY: allowed after any exit — resets and watches for next spike
    """
    if not bars:
        return [], []

    times    = [datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                for b in bars]
    closes   = [b["c"] for b in bars]
    rsi_vals = compute_rsi(closes, period=rsi_period)

    ENTRY_START = _make_dt(trade_day, entry_start_str, NY)
    ENTRY_END   = _make_dt(trade_day, entry_end_str,   NY)
    TIME_EXIT   = _make_dt(trade_day, time_exit_str,   NY)

    # Day open = first bar's open at/after ENTRY_START (for "day_open" spike type)
    day_open = next((b['o'] for b, ts in zip(bars, times) if ts >= ENTRY_START), None)

    trades     = []
    chart_data = []

    # Position state
    pos_shares   = 0
    pos_avg      = 0.0
    pos_class    = None     # "nano" | "small"
    pos_rsi_prof = 60.0
    pos_entry_i  = None

    for i, (ts, b) in enumerate(zip(times, bars)):
        close = b['c']
        rsi   = rsi_vals[i]

        cd = {
            "t": ts.isoformat(),
            "o": b['o'], "h": b['h'], "l": b['l'], "c": close, "v": b['v'],
            "rsi": rsi,
            "signal":     None,
            "avg_entry":  round(pos_avg, 4) if pos_shares > 0 else None,
            "rsi_profit": pos_rsi_prof if pos_shares > 0 else None,
        }

        if rsi is None:
            chart_data.append(cd)
            continue

        exit_reason = None
        exit_price  = close

        # ── EXIT ──────────────────────────────────────────────────────────
        if pos_shares > 0:
            if ts >= TIME_EXIT:                          # 1. hard time exit
                exit_reason = "time_exit"
            elif rsi >= pos_rsi_prof:                   # 2. RSI profit
                exit_reason = "rsi_profit"
            elif b['l'] <= pos_avg:                     # 3. limit stop at avg_entry
                exit_reason = "stop_limit"
                exit_price  = pos_avg                   # limit fills at avg_entry

            if exit_reason:
                pnl = round((exit_price - pos_avg) * pos_shares, 2)
                trades.append({
                    "date":         trade_day.isoformat(),
                    "entry_time":   times[pos_entry_i].isoformat(),
                    "entry_price":  round(pos_avg, 4),
                    "exit_time":    ts.isoformat(),
                    "exit_price":   round(exit_price, 4),
                    "shares":       pos_shares,
                    "pnl":          pnl,
                    "reason":       exit_reason,
                    "cap_class":    pos_class,
                    "rsi_at_entry": rsi_vals[pos_entry_i],
                    "rsi_at_exit":  rsi,
                    "rsi_profit":   pos_rsi_prof,
                })
                cd['signal']    = "sell"
                cd['avg_entry'] = round(pos_avg, 4)
                pos_shares = 0;  pos_avg = 0.0
                pos_class  = None; pos_entry_i = None

        # ── ENTRY (no re-entry on same bar as exit) ────────────────────────
        if pos_shares == 0 and exit_reason is None and i > 0:
            if ENTRY_START <= ts < ENTRY_END:
                # Auto-classify by current price
                if close < nano_max_price:
                    cap_cls  = "nano"
                    spk_pct  = nano_spike_pct
                    min_vol  = nano_min_vol
                    rsi_prof = nano_rsi_profit
                    buy_amt  = nano_buy_amount
                elif close < small_max_price:
                    cap_cls  = "small"
                    spk_pct  = small_spike_pct
                    min_vol  = small_min_vol
                    rsi_prof = small_rsi_profit
                    buy_amt  = small_buy_amount
                else:
                    cap_cls = None

                if cap_cls:
                    ref = bars[i-1]['c'] if spike_type == "prev_bar" else day_open
                    if ref and ref > 0:
                        actual_spike = (close - ref) / ref * 100
                        if actual_spike >= spk_pct and b['v'] >= min_vol:
                            n            = max(1, int(buy_amt / close))
                            pos_shares   = n
                            pos_avg      = close
                            pos_class    = cap_cls
                            pos_rsi_prof = rsi_prof
                            pos_entry_i  = i
                            cd['signal']     = "buy"
                            cd['avg_entry']  = round(close, 4)
                            cd['rsi_profit'] = rsi_prof
                            cd['spike_pct']  = round(actual_spike, 2)
                            cd['cap_class']  = cap_cls

        # Refresh avg_entry in chart point after any buy
        if pos_shares > 0:
            cd['avg_entry'] = round(pos_avg, 4)
        chart_data.append(cd)

    # EOD: still holding
    if pos_shares > 0 and pos_entry_i is not None:
        lc  = closes[-1]
        pnl = round((lc - pos_avg) * pos_shares, 2)
        trades.append({
            "date":         trade_day.isoformat(),
            "entry_time":   times[pos_entry_i].isoformat(),
            "entry_price":  round(pos_avg, 4),
            "exit_time":    times[-1].isoformat(),
            "exit_price":   round(lc, 4),
            "shares":       pos_shares,
            "pnl":          pnl,
            "reason":       "eod",
            "cap_class":    pos_class,
            "rsi_at_entry": rsi_vals[pos_entry_i],
            "rsi_at_exit":  rsi_vals[-1],
            "rsi_profit":   pos_rsi_prof,
        })

    return trades, chart_data


# ── Spike API ─────────────────────────────────────────────────────────────────

def _spike_kwargs(req) -> dict:
    """Unpack all spike strategy params from a FastAPI request namespace."""
    return dict(
        spike_type=req.spike_type,
        nano_max_price=req.nano_max_price, small_max_price=req.small_max_price,
        nano_spike_pct=req.nano_spike_pct, nano_min_vol=req.nano_min_vol,
        nano_rsi_profit=req.nano_rsi_profit, nano_buy_amount=req.nano_buy_amount,
        small_spike_pct=req.small_spike_pct, small_min_vol=req.small_min_vol,
        small_rsi_profit=req.small_rsi_profit, small_buy_amount=req.small_buy_amount,
        entry_start_str=req.entry_start_str, entry_end_str=req.entry_end_str,
        time_exit_str=req.time_exit_str, rsi_period=req.rsi_period,
    )


@app.get("/api/spike")
async def spike_single(
    symbol:           str,
    date_str:         str,
    spike_type:       str   = "prev_bar",
    nano_max_price:   float = 5.0,
    small_max_price:  float = 20.0,
    nano_spike_pct:   float = 10.0,
    nano_min_vol:     int   = 50_000,
    nano_rsi_profit:  float = 60.0,
    nano_buy_amount:  float = 500.0,
    small_spike_pct:  float = 5.0,
    small_min_vol:    int   = 200_000,
    small_rsi_profit: float = 65.0,
    small_buy_amount: float = 1000.0,
    entry_start_str:  str   = "09:30",
    entry_end_str:    str   = "11:00",
    time_exit_str:    str   = "15:30",
    rsi_period:       int   = 14,
):
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(400, "date_str must be YYYY-MM-DD")

    bars = await fetch_bars(symbol.upper(), day)
    if not bars:
        raise HTTPException(404, f"No data for {symbol} on {date_str}")

    trades, chart = run_spike_momentum(
        bars, day, spike_type=spike_type,
        nano_max_price=nano_max_price, small_max_price=small_max_price,
        nano_spike_pct=nano_spike_pct, nano_min_vol=nano_min_vol,
        nano_rsi_profit=nano_rsi_profit, nano_buy_amount=nano_buy_amount,
        small_spike_pct=small_spike_pct, small_min_vol=small_min_vol,
        small_rsi_profit=small_rsi_profit, small_buy_amount=small_buy_amount,
        entry_start_str=entry_start_str, entry_end_str=entry_end_str,
        time_exit_str=time_exit_str, rsi_period=rsi_period,
    )
    return {
        "symbol": symbol.upper(), "date": date_str, "bars": len(bars),
        "trades": trades, "chart": chart,
        "net_pnl": round(sum(t["pnl"] for t in trades), 2),
    }


@app.get("/api/spike/batch")
async def spike_batch(
    spike_type:       str   = "prev_bar",
    nano_max_price:   float = 5.0,
    small_max_price:  float = 20.0,
    nano_spike_pct:   float = 10.0,
    nano_min_vol:     int   = 50_000,
    nano_rsi_profit:  float = 60.0,
    nano_buy_amount:  float = 500.0,
    small_spike_pct:  float = 5.0,
    small_min_vol:    int   = 200_000,
    small_rsi_profit: float = 65.0,
    small_buy_amount: float = 1000.0,
    entry_start_str:  str   = "09:30",
    entry_end_str:    str   = "11:00",
    time_exit_str:    str   = "15:30",
    rsi_period:       int   = 14,
    concurrency:      int   = 8,
):
    """Run spike strategy across all rows in premarket_top5_by_sweeps.csv."""
    import asyncio as _asyncio
    import csv     as _csv
    from collections import defaultdict as _dd

    CSV_PATH = r"C:\Users\ibrah\OneDrive\Documents\The100xTrade\cluade\alpaca-stream\premarket_top5_by_sweeps.csv"
    rows = []
    try:
        with open(CSV_PATH, newline="") as f:
            for r in _csv.DictReader(f):
                rows.append({"date": r["date"], "rank": int(r["rank"]),
                             "symbol": r["symbol"].strip().upper(),
                             "sweep_count": int(r["sweep_count"])})
    except FileNotFoundError:
        raise HTTPException(404, f"CSV not found: {CSV_PATH}")

    kw = dict(
        spike_type=spike_type,
        nano_max_price=nano_max_price, small_max_price=small_max_price,
        nano_spike_pct=nano_spike_pct, nano_min_vol=nano_min_vol,
        nano_rsi_profit=nano_rsi_profit, nano_buy_amount=nano_buy_amount,
        small_spike_pct=small_spike_pct, small_min_vol=small_min_vol,
        small_rsi_profit=small_rsi_profit, small_buy_amount=small_buy_amount,
        entry_start_str=entry_start_str, entry_end_str=entry_end_str,
        time_exit_str=time_exit_str, rsi_period=rsi_period,
    )
    sem = _asyncio.Semaphore(concurrency)

    async def _run(row):
        async with sem:
            try:
                d    = date.fromisoformat(row["date"])
                bars = await fetch_bars(row["symbol"], d)
                if not bars:
                    return {**row, "trades": [], "net_pnl": 0, "bars": 0, "skipped": True}
                trades, _ = run_spike_momentum(bars, d, **kw)
                return {**row, "trades": trades,
                        "net_pnl": round(sum(t["pnl"] for t in trades), 2),
                        "bars": len(bars), "skipped": False}
            except Exception as e:
                return {**row, "trades": [], "net_pnl": 0, "bars": 0,
                        "error": str(e), "skipped": True}

    all_rows = await _asyncio.gather(*[_run(r) for r in rows])
    valid    = [r for r in all_rows if not r.get("skipped")]
    all_trades = [t for r in valid for t in r["trades"]]

    # Per-class summary
    def _cls_stats(cls):
        t = [x for x in all_trades if x["cap_class"] == cls]
        wins = sum(1 for x in t if x["pnl"] > 0)
        return {
            "trades": len(t), "wins": wins,
            "losses": len(t) - wins,
            "win_rate": round(wins / len(t) * 100, 1) if t else 0,
            "net_pnl":  round(sum(x["pnl"] for x in t), 2),
            "avg_pnl":  round(sum(x["pnl"] for x in t) / len(t), 2) if t else 0,
        }

    # Per-day summary
    day_map = _dd(lambda: {"date": "", "net_pnl": 0.0, "trades": 0, "symbols": {}})
    for r in valid:
        d = r["date"]
        day_map[d]["date"]    = d
        day_map[d]["net_pnl"] = round(day_map[d]["net_pnl"] + r["net_pnl"], 2)
        day_map[d]["trades"] += len(r["trades"])
        day_map[d]["symbols"][r["symbol"]] = {
            "rank": r["rank"], "pnl": r["net_pnl"], "trades": len(r["trades"])
        }

    return {
        "total_rows":   len(rows),
        "total_pnl":    round(sum(t["pnl"] for t in all_trades), 2),
        "total_trades": len(all_trades),
        "nano":         _cls_stats("nano"),
        "small":        _cls_stats("small"),
        "daily":        [day_map[k] for k in sorted(day_map)],
        "rows":         all_rows,
    }


@app.get("/api/spike/range")
async def spike_range(
    symbols:          str,
    start_date:       str,
    end_date:         str,
    spike_type:       str   = "prev_bar",
    nano_max_price:   float = 5.0,
    small_max_price:  float = 20.0,
    nano_spike_pct:   float = 10.0,
    nano_min_vol:     int   = 50_000,
    nano_rsi_profit:  float = 60.0,
    nano_buy_amount:  float = 500.0,
    small_spike_pct:  float = 5.0,
    small_min_vol:    int   = 200_000,
    small_rsi_profit: float = 65.0,
    small_buy_amount: float = 1000.0,
    entry_start_str:  str   = "09:30",
    entry_end_str:    str   = "11:00",
    time_exit_str:    str   = "15:30",
    rsi_period:       int   = 14,
    concurrency:      int   = 8,
):
    import asyncio  as _asyncio
    from datetime   import timedelta
    from collections import defaultdict as _dd

    try:
        s_d = date.fromisoformat(start_date)
        e_d = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")
    if (e_d - s_d).days > 180:
        raise HTTPException(400, "Max range 6 months")

    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    days = []
    cur  = s_d
    while cur <= e_d:
        if cur.weekday() < 5: days.append(cur)
        cur += timedelta(days=1)

    kw = dict(
        spike_type=spike_type,
        nano_max_price=nano_max_price, small_max_price=small_max_price,
        nano_spike_pct=nano_spike_pct, nano_min_vol=nano_min_vol,
        nano_rsi_profit=nano_rsi_profit, nano_buy_amount=nano_buy_amount,
        small_spike_pct=small_spike_pct, small_min_vol=small_min_vol,
        small_rsi_profit=small_rsi_profit, small_buy_amount=small_buy_amount,
        entry_start_str=entry_start_str, entry_end_str=entry_end_str,
        time_exit_str=time_exit_str, rsi_period=rsi_period,
    )
    sem = _asyncio.Semaphore(concurrency)

    async def _run(sym, d):
        async with sem:
            try:
                bars = await fetch_bars(sym, d)
                if not bars:
                    return {"symbol": sym, "date": d.isoformat(), "trades": [],
                            "net_pnl": 0, "bars": 0}
                trades, chart = run_spike_momentum(bars, d, **kw)
                return {"symbol": sym, "date": d.isoformat(), "bars": len(bars),
                        "trades": trades, "chart": chart,
                        "net_pnl": round(sum(t["pnl"] for t in trades), 2)}
            except Exception as e:
                return {"symbol": sym, "date": d.isoformat(), "trades": [],
                        "net_pnl": 0, "bars": 0, "error": str(e)}

    results    = await _asyncio.gather(*[_run(s, d) for s in sym_list for d in days])
    all_trades = [t for r in results for t in r.get("trades", [])]

    def _cls_stats(cls):
        t = [x for x in all_trades if x["cap_class"] == cls]
        wins = sum(1 for x in t if x["pnl"] > 0)
        return {"trades": len(t), "wins": wins, "losses": len(t) - wins,
                "win_rate": round(wins/len(t)*100,1) if t else 0,
                "net_pnl": round(sum(x["pnl"] for x in t), 2),
                "avg_pnl": round(sum(x["pnl"] for x in t)/len(t), 2) if t else 0}

    return {
        "symbols": sym_list, "start_date": start_date, "end_date": end_date,
        "total_pnl":    round(sum(t["pnl"] for t in all_trades), 2),
        "total_trades": len(all_trades),
        "nano":         _cls_stats("nano"),
        "small":        _cls_stats("small"),
        "rows":         results,
    }


from spike_page import SPIKE_HTML

@app.get("/spike", response_class=HTMLResponse)
async def spike_page_route():
    return HTMLResponse(SPIKE_HTML)


# ── RSI Grid strategy ─────────────────────────────────────────────────────────

def run_rsi_grid(
    bars:              list,
    base_qty:          int   = 1,
    buy_drop_pct:      float = 0.5,
    sell_rise_pct:     float = 0.5,
    rsi_period:        int   = 14,
    rsi_low:           float = 30.0,
    rsi_high:          float = 60.0,
    max_order_days:    int   = 7,
    trade_start_date   = None,   # date — bars before this are RSI warmup only, no orders recorded
):
    """
    RSI-tiered GTC limit-order grid — runs on ALL hours (including extended).

    ORDER LIFECYCLE
    ───────────────
    One buy limit  and one sell limit are always active (sell only when position > 0).
    Each order persists until:
      a) It fills (bar.low ≤ buy_price  OR  bar.high ≥ sell_price)
      b) max_order_days unique trading dates pass without fill → cancel + replace at current price

    When an order fills or is cancelled, a fresh replacement is placed immediately
    at the current bar's close ± the configured %, with qty determined by current RSI.

    RSI TIERS (set at placement time)
    ───────────────────────────────────
      RSI < rsi_low            → buy 2× base_qty,  sell 1× base_qty
      rsi_low ≤ RSI ≤ rsi_high → buy 1× base_qty,  sell 1× base_qty
      RSI > rsi_high           → buy 1× base_qty,  sell 2× base_qty

    PnL = cash_received − cash_spent + (final_position × last_bar_close)
    """
    if not bars:
        return [], [], {}

    times    = [datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                for b in bars]
    closes   = [b["c"] for b in bars]
    rsi_vals = compute_rsi(closes, period=rsi_period)

    position       = 0
    total_spent    = 0.0
    total_received = 0.0
    trades         = []
    day_data       = {}
    seen_dates     = []     # unique calendar dates in encounter order (for GTC age tracking)
    total_cancels  = 0

    # GTC orders — each is a dict or None
    buy_order  = None   # {"price", "qty", "rsi", "date_idx"}
    sell_order = None   # {"price", "qty", "rsi", "date_idx"}

    def _qty(rsi):
        """Return (buy_qty, sell_qty) for the current RSI level."""
        if rsi < rsi_low:
            return 2 * base_qty, 1 * base_qty
        elif rsi <= rsi_high:
            return 1 * base_qty, 1 * base_qty
        else:
            return 1 * base_qty, 2 * base_qty

    def _new_buy(close, rsi):
        bq, _ = _qty(rsi)
        return {"price": round(close * (1 - buy_drop_pct  / 100), 4),
                "qty":   bq,
                "rsi":   round(rsi, 1),
                "date_idx": len(seen_dates) - 1}   # index of placement date

    def _new_sell(close, rsi):
        _, sq = _qty(rsi)
        return {"price": round(close * (1 + sell_rise_pct / 100), 4),
                "qty":   sq,
                "rsi":   round(rsi, 1),
                "date_idx": len(seen_dates) - 1}

    def _age(order):
        """Trading dates elapsed since order placement (O(1))."""
        return len(seen_dates) - 1 - order["date_idx"]

    for i, (ts, b) in enumerate(zip(times, bars)):
        close = b['c']
        rsi   = rsi_vals[i]
        d_str = ts.date().isoformat()

        if rsi is None or close <= 0:
            continue

        # ── RSI warmup pass: bars before trade_start_date are used only for
        #    RSI initialisation — no orders are placed or recorded ───────────
        if trade_start_date and ts.date() < trade_start_date:
            continue

        # ── Track unique dates ────────────────────────────────────────────
        if d_str not in seen_dates:
            seen_dates.append(d_str)
            day_data.setdefault(d_str, {"date": d_str,
                                         "buys": 0, "sells": 0, "cancels": 0,
                                         "spent": 0.0, "received": 0.0,
                                         "bars": 0})

        day_data[d_str]["bars"] += 1

        bq, sq = _qty(rsi)
        cur_di = len(seen_dates) - 1   # current date index

        # ── STEP 1: Maintain buy order (place if none, refresh if expired) ──
        if buy_order is None:
            buy_order = _new_buy(close, rsi)
        elif _age(buy_order) >= max_order_days:
            day_data[d_str]["cancels"] += 1
            total_cancels += 1
            buy_order = _new_buy(close, rsi)

        # ── STEP 2: Try to fill buy order ──────────────────────────────────
        if b['l'] <= buy_order["price"]:
            cost         = round(buy_order["qty"] * buy_order["price"], 2)
            position    += buy_order["qty"]
            total_spent += cost
            day_data[d_str]["buys"]  += 1
            day_data[d_str]["spent"] = round(day_data[d_str]["spent"] + cost, 2)
            trades.append({
                "ts": ts.isoformat(), "date": d_str, "type": "buy",
                "qty": buy_order["qty"], "price": buy_order["price"],
                "value": cost, "rsi": buy_order["rsi"],
                "position": position, "order_age": _age(buy_order),
            })
            buy_order = _new_buy(close, rsi)   # immediately place fresh order

        # ── STEP 3: Maintain sell order (always active — position can go negative / short) ──
        if sell_order is None:
            sell_order = _new_sell(close, rsi)
        elif _age(sell_order) >= max_order_days:
            day_data[d_str]["cancels"] += 1
            total_cancels += 1
            sell_order = _new_sell(close, rsi)

        # ── STEP 4: Try to fill sell order ─────────────────────────────────
        if sell_order is not None and b['h'] >= sell_order["price"]:
            qty_sold        = sell_order["qty"]
            proceeds        = round(qty_sold * sell_order["price"], 2)
            position       -= qty_sold
            total_received += proceeds
            day_data[d_str]["sells"]    += 1
            day_data[d_str]["received"] = round(day_data[d_str]["received"] + proceeds, 2)
            trades.append({
                "ts": ts.isoformat(), "date": d_str, "type": "sell",
                "qty": qty_sold, "price": sell_order["price"],
                "value": proceeds, "rsi": sell_order["rsi"],
                "position": position, "order_age": _age(sell_order),
            })
            sell_order = _new_sell(close, rsi)

    # Mark-to-market at last bar close
    last_price = closes[-1] if closes else 0.0
    pos_value  = round(position * last_price, 2)

    daily_list = []
    cum = 0.0
    for d in sorted(day_data):
        row      = day_data[d]
        net_cash = round(row["received"] - row["spent"], 2)
        cum      = round(cum + net_cash, 2)
        daily_list.append({
            "date":     d,
            "bars":     row.get("bars", 0),
            "buys":     row["buys"],   "sells":    row["sells"],
            "cancels":  row["cancels"],
            "spent":    round(row["spent"], 2),
            "received": round(row["received"], 2),
            "net_cash": net_cash, "cum_cash": cum,
        })

    total_buys  = sum(1 for t in trades if t["type"] == "buy")
    total_sells = sum(1 for t in trades if t["type"] == "sell")

    stats = {
        "position":        position,
        "last_price":      round(last_price, 4),
        "position_value":  pos_value,
        "total_spent":     round(total_spent, 2),
        "total_received":  round(total_received, 2),
        "realized_pnl":    round(total_received - total_spent, 2),
        "net_pnl":         round(total_received - total_spent + pos_value, 2),
        "total_buys":      total_buys,
        "total_sells":     total_sells,
        "total_cancels":   total_cancels,
        "trading_days":    len(daily_list),
        "active_buy_order":  buy_order,
        "active_sell_order": sell_order,
    }

    return trades[-1000:], daily_list, stats


@app.get("/api/grid")
async def grid_backtest(
    symbols:         str,
    start_date:      str,
    base_qty:        int   = 1,
    buy_drop_pct:    float = 0.5,
    sell_rise_pct:   float = 0.5,
    rsi_period:      int   = 14,
    rsi_low:         float = 30.0,
    rsi_high:        float = 60.0,
    max_order_days:  int   = 7,
    concurrency:     int   = 4,
):
    import asyncio as _asyncio

    try:
        s_date = date.fromisoformat(start_date)
    except ValueError:
        raise HTTPException(400, "start_date must be YYYY-MM-DD")

    from datetime import timedelta as _td

    e_date   = date.today()
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(400, "Provide at least one symbol")
    if (e_date - s_date).days > 365:
        raise HTTPException(400, "Max range 1 year")

    # Fetch extra history so RSI is warm before the first trade date.
    # rsi_period bars = ~rsi_period minutes; add generous calendar buffer for weekends/holidays.
    warmup_start = s_date - _td(days=max(30, rsi_period * 3))

    sem = _asyncio.Semaphore(concurrency)

    async def _run(sym):
        async with sem:
            try:
                bars = await fetch_bars_range(sym, warmup_start, e_date)
                if not bars:
                    return {"symbol": sym, "error": "No data", "stats": {},
                            "trades": [], "daily": []}
                trades, daily, stats = run_rsi_grid(
                    bars,
                    base_qty=base_qty, buy_drop_pct=buy_drop_pct,
                    sell_rise_pct=sell_rise_pct, rsi_period=rsi_period,
                    rsi_low=rsi_low, rsi_high=rsi_high,
                    max_order_days=max_order_days,
                    trade_start_date=s_date,   # orders only from user's start date
                )
                return {"symbol": sym, "bars": len(bars),
                        "stats": stats, "trades": trades, "daily": daily}
            except Exception as e:
                return {"symbol": sym, "error": str(e), "stats": {},
                        "trades": [], "daily": []}

    results   = await _asyncio.gather(*[_run(s) for s in sym_list])
    total_pnl = round(sum(r.get("stats", {}).get("net_pnl", 0) for r in results), 2)

    return {
        "symbols":        sym_list,
        "start_date":     start_date,
        "end_date":       e_date.isoformat(),
        "max_order_days": max_order_days,
        "total_pnl":      total_pnl,
        "results":        list(results),
    }


from grid_page import GRID_HTML

@app.get("/grid", response_class=HTMLResponse)
async def grid_page_route():
    return HTMLResponse(GRID_HTML)


# ══════════════════════════════════════════════════════════════════════════
# Alert-Driven Backtest  (alert_history.csv)
#
# Browses the live-stream alert log, optionally requires a prior ISO-sweep
# alert in the same direction within a lookback window, then simulates a
# buy-on-alert / TP%-SL% bracket exit using real Alpaca 1-min bars.
# ══════════════════════════════════════════════════════════════════════════
import csv as _alerts_csv
import os as _alerts_os
import bisect as _alerts_bisect
from collections import defaultdict as _alerts_dd
from datetime import timedelta as _alerts_timedelta

ALERT_CSV_PATH = r"C:\Users\ibrah\OneDrive\Documents\The100xTrade\cluade\alpaca-stream\alert_history.csv"

_alert_cache = {"mtime": None, "rows": [], "sweeps_by_sym": {}}


def _load_alert_history():
    """Load + cache alert_history.csv. Re-parses only when the file's mtime changes."""
    try:
        mtime = _alerts_os.path.getmtime(ALERT_CSV_PATH)
    except OSError:
        return [], {}

    if _alert_cache["mtime"] == mtime:
        return _alert_cache["rows"], _alert_cache["sweeps_by_sym"]

    rows = []
    with open(ALERT_CSV_PATH, newline="", encoding="utf-8") as f:
        for r in _alerts_csv.DictReader(f):
            try:
                ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            except (KeyError, ValueError, AttributeError):
                continue

            def _f(key):
                try:
                    return float(r.get(key) or 0)
                except ValueError:
                    return 0.0

            rows.append({
                "id":        r.get("id", ""),
                "ts":        ts,
                "sym":       (r.get("sym") or "").upper(),
                "tag":       r.get("tag") or "",
                "type":      r.get("type") or "",
                "direction": r.get("direction") or "",
                "delta":     _f("delta"),
                "value1m":   _f("value1m"),
                "vwap1m":    _f("vwap1m"),
                "vwap2m":    _f("vwap2m"),
                "cnt1m":     _f("cnt1m"),
            })

    rows.sort(key=lambda r: r["ts"])

    sweeps_by_sym = _alerts_dd(list)
    for r in rows:
        if r["tag"].startswith("sweep") and r["direction"] in ("bull", "bear", "neutral"):
            sweeps_by_sym[r["sym"]].append(r)

    _alert_cache["mtime"]         = mtime
    _alert_cache["rows"]          = rows
    _alert_cache["sweeps_by_sym"] = dict(sweeps_by_sym)
    return rows, _alert_cache["sweeps_by_sym"]


def _find_prior_sweep(sweeps_by_sym, sym, alert_ts, lookback_min, min_value, min_score,
                       direction, match_direction):
    """Most recent qualifying sweep for `sym` within `lookback_min` minutes before
    `alert_ts`, or None. Each sweeps_by_sym[sym] list is sorted by ts ascending."""
    sweeps = sweeps_by_sym.get(sym)
    if not sweeps:
        return None

    window_start = alert_ts - _alerts_timedelta(minutes=lookback_min)
    times = [s["ts"] for s in sweeps]
    lo = _alerts_bisect.bisect_left(times, window_start)
    hi = _alerts_bisect.bisect_left(times, alert_ts)

    best = None
    for s in sweeps[lo:hi]:
        if s["value1m"] < min_value:
            continue
        if s["delta"] < min_score:
            continue
        if match_direction and direction in ("bull", "bear") and s["direction"] != direction:
            continue
        best = s  # slice is ascending, so last kept = latest
    return best


def _filter_alerts(
    rows, sweeps_by_sym,
    start_date, end_date,
    tags, direction,
    min_delta, max_delta,
    min_value, max_price, min_price,
    min_cnt, symbols,
    require_sweep, sweep_lookback_min, sweep_min_value, sweep_min_score, sweep_match_direction,
):
    s_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, tzinfo=NY)
    e_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=NY)
    sym_set = set(symbols) if symbols else None

    out = []
    for r in rows:
        if r["tag"] not in tags:
            continue
        ts_ny = r["ts"].astimezone(NY)
        if ts_ny < s_dt or ts_ny > e_dt:
            continue
        if direction != "any" and r["direction"] != direction:
            continue
        if not (min_delta <= r["delta"] <= max_delta):
            continue
        if r["value1m"] < min_value:
            continue
        if not (min_price <= r["vwap1m"] <= max_price):
            continue
        if r["cnt1m"] < min_cnt:
            continue
        if sym_set and r["sym"] not in sym_set:
            continue

        sweep = _find_prior_sweep(
            sweeps_by_sym, r["sym"], r["ts"], sweep_lookback_min,
            sweep_min_value, sweep_min_score, r["direction"], sweep_match_direction,
        )
        if require_sweep and sweep is None:
            continue

        item = dict(r)
        item["ts_ny"]       = ts_ny.isoformat()
        item["had_sweep"]   = sweep is not None
        item["sweep_ts"]    = sweep["ts"].astimezone(NY).isoformat() if sweep else None
        item["sweep_score"] = sweep["delta"]     if sweep else None
        item["sweep_value"] = sweep["value1m"]   if sweep else None
        item["sweep_dir"]   = sweep["direction"] if sweep else None
        out.append(item)
    return out


@app.get("/api/alerts/meta")
async def alerts_meta():
    rows, _ = _load_alert_history()
    if not rows:
        return {"min_date": None, "max_date": None, "total_rows": 0, "unique_symbols": 0}
    syms = set(r["sym"] for r in rows)
    return {
        "min_date":       rows[0]["ts"].astimezone(NY).date().isoformat(),
        "max_date":       rows[-1]["ts"].astimezone(NY).date().isoformat(),
        "total_rows":     len(rows),
        "unique_symbols": len(syms),
    }


@app.get("/api/alerts/query")
async def alerts_query(
    start_date:            str,
    end_date:              str,
    tags:                  str   = "new,escalation",
    direction:              str   = "bull",
    min_delta:              float = 0.0,
    max_delta:              float = 1000.0,
    min_value:              float = 0.0,
    max_price:              float = 5.0,
    min_price:              float = 0.0,
    min_cnt:                float = 0.0,
    symbols:                str   = "",
    require_sweep:          bool  = False,
    sweep_lookback_min:     float = 15.0,
    sweep_min_value:        float = 0.0,
    sweep_min_score:        float = 0.0,
    sweep_match_direction:  bool  = False,
    limit:                  int   = 500,
):
    try:
        s_date = date.fromisoformat(start_date)
        e_date = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "start_date/end_date must be YYYY-MM-DD")

    tag_set  = set(t.strip() for t in tags.split(",") if t.strip())
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    rows, sweeps_by_sym = _load_alert_history()
    matched = _filter_alerts(
        rows, sweeps_by_sym, s_date, e_date, tag_set, direction,
        min_delta, max_delta, min_value, max_price, min_price, min_cnt, sym_list,
        require_sweep, sweep_lookback_min, sweep_min_value, sweep_min_score, sweep_match_direction,
    )

    alerts_out = []
    for r in matched[:limit]:
        alerts_out.append({
            "ts":          r["ts_ny"],
            "sym":         r["sym"],
            "tag":         r["tag"],
            "direction":   r["direction"],
            "delta":       round(r["delta"], 2),
            "value1m":     round(r["value1m"], 0),
            "price":       round(r["vwap1m"], 4),
            "cnt1m":       r["cnt1m"],
            "had_sweep":   r["had_sweep"],
            "sweep_ts":    r["sweep_ts"],
            "sweep_score": r["sweep_score"],
            "sweep_value": r["sweep_value"],
        })

    return {
        "total_matched": len(matched),
        "returned":      len(alerts_out),
        "alerts":        alerts_out,
    }


@app.get("/api/alerts/backtest")
async def alerts_backtest(
    start_date:             str,
    end_date:               str,
    tags:                   str   = "new,escalation",
    direction:               str   = "bull",
    min_delta:               float = 10.0,
    max_delta:               float = 1000.0,
    min_value:                float = 100_000.0,
    max_price:                float = 5.0,
    min_price:                float = 0.0,
    min_cnt:                  float = 0.0,
    symbols:                  str   = "",
    require_sweep:            bool  = False,
    sweep_lookback_min:       float = 15.0,
    sweep_min_value:          float = 0.0,
    sweep_min_score:          float = 0.0,
    sweep_match_direction:    bool  = False,
    buy_amount:               float = 500.0,
    tp_pct:                   float = 20.0,
    sl_pct:                   float = 5.0,
    max_hold_min:             float = 60.0,
    entry_mode:               str   = "next_open",
    same_bar_rule:            str   = "sl_first",
    max_alerts:               int   = 300,
    concurrency:              int   = 8,
):
    """Simulate buy-on-alert / TP%-SL% bracket exits using real Alpaca 1-min bars,
    and split results into with-prior-sweep vs without-prior-sweep cohorts."""
    import asyncio as _asyncio
    from collections import defaultdict as _dd2

    try:
        s_date = date.fromisoformat(start_date)
        e_date = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "start_date/end_date must be YYYY-MM-DD")

    tag_set  = set(t.strip() for t in tags.split(",") if t.strip())
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    rows, sweeps_by_sym = _load_alert_history()
    matched = _filter_alerts(
        rows, sweeps_by_sym, s_date, e_date, tag_set, direction,
        min_delta, max_delta, min_value, max_price, min_price, min_cnt, sym_list,
        require_sweep, sweep_lookback_min, sweep_min_value, sweep_min_score, sweep_match_direction,
    )
    total_matched = len(matched)
    matched = matched[:max_alerts]

    # group by (symbol, NY trading day) so each day's bars are fetched once
    groups = _dd2(list)
    for r in matched:
        ts_ny = r["ts"].astimezone(NY)
        groups[(r["sym"], ts_ny.date())].append(r)

    sem        = _asyncio.Semaphore(concurrency)
    bars_cache = {}

    async def _fetch(sym, day):
        async with sem:
            try:
                bars_cache[(sym, day)] = await fetch_bars(sym, day)
            except HTTPException:
                bars_cache[(sym, day)] = []

    await _asyncio.gather(*[_fetch(sym, day) for (sym, day) in groups.keys()])

    trades  = []
    skipped = 0

    for (sym, day), alerts in groups.items():
        bars = bars_cache.get((sym, day)) or []
        if not bars:
            skipped += len(alerts)
            continue

        bar_times = [datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                     for b in bars]

        for r in alerts:
            alert_ts = r["ts"].astimezone(NY)

            signal_idx = None
            for i, bt in enumerate(bar_times):
                if bt <= alert_ts:
                    signal_idx = i
                else:
                    break
            if signal_idx is None:
                skipped += 1
                continue

            if entry_mode == "next_open":
                entry_idx = signal_idx + 1
                if entry_idx >= len(bars):
                    skipped += 1
                    continue
                entry_price = bars[entry_idx]["o"]
            else:
                entry_idx = signal_idx
                entry_price = bars[entry_idx]["c"]

            if entry_price <= 0:
                skipped += 1
                continue

            tp_price = entry_price * (1 + tp_pct / 100.0)
            sl_price = entry_price * (1 - sl_pct / 100.0)
            entry_ts = bar_times[entry_idx]

            exit_price  = None
            exit_reason = None
            exit_idx    = entry_idx

            for j in range(entry_idx, len(bars)):
                bt = bar_times[j]
                if max_hold_min and (bt - entry_ts).total_seconds() / 60.0 > max_hold_min:
                    break
                exit_idx = j
                b = bars[j]
                hit_tp = b["h"] >= tp_price
                hit_sl = b["l"] <= sl_price
                if hit_tp and hit_sl:
                    if same_bar_rule == "tp_first":
                        exit_price, exit_reason = tp_price, "tp"
                    else:
                        exit_price, exit_reason = sl_price, "sl"
                    break
                elif hit_tp:
                    exit_price, exit_reason = tp_price, "tp"
                    break
                elif hit_sl:
                    exit_price, exit_reason = sl_price, "sl"
                    break

            if exit_price is None:
                exit_price  = bars[exit_idx]["c"]
                exit_reason = "time" if max_hold_min else "eod"

            shares     = buy_amount / entry_price
            pnl_dollar = shares * (exit_price - entry_price)
            pnl_pct    = (exit_price / entry_price - 1.0) * 100.0
            hold_min   = (bar_times[exit_idx] - entry_ts).total_seconds() / 60.0

            trades.append({
                "sym":         sym,
                "alert_ts":    alert_ts.isoformat(),
                "tag":         r["tag"],
                "direction":   r["direction"],
                "delta":       round(r["delta"], 2),
                "had_sweep":   r["had_sweep"],
                "sweep_score": r["sweep_score"],
                "entry_ts":    entry_ts.isoformat(),
                "entry_price": round(entry_price, 4),
                "exit_ts":     bar_times[exit_idx].isoformat(),
                "exit_price":  round(exit_price, 4),
                "exit_reason": exit_reason,
                "hold_min":    round(hold_min, 1),
                "pnl_pct":     round(pnl_pct, 2),
                "pnl_dollar":  round(pnl_dollar, 2),
            })

    trades.sort(key=lambda t: t["entry_ts"])

    def _stats(group):
        n = len(group)
        if n == 0:
            return {"n": 0, "win_rate": 0, "avg_pnl_pct": 0, "total_pnl": 0,
                     "tp_hits": 0, "sl_hits": 0, "time_exits": 0, "avg_hold_min": 0}
        wins = sum(1 for t in group if t["pnl_dollar"] > 0)
        return {
            "n":            n,
            "win_rate":     round(100.0 * wins / n, 1),
            "avg_pnl_pct":  round(sum(t["pnl_pct"] for t in group) / n, 2),
            "total_pnl":    round(sum(t["pnl_dollar"] for t in group), 2),
            "tp_hits":      sum(1 for t in group if t["exit_reason"] == "tp"),
            "sl_hits":      sum(1 for t in group if t["exit_reason"] == "sl"),
            "time_exits":   sum(1 for t in group if t["exit_reason"] in ("time", "eod")),
            "avg_hold_min": round(sum(t["hold_min"] for t in group) / n, 1),
        }

    with_sweep    = [t for t in trades if t["had_sweep"]]
    without_sweep = [t for t in trades if not t["had_sweep"]]

    cum = 0.0
    equity_curve = []
    for t in trades:
        cum += t["pnl_dollar"]
        equity_curve.append({"i": len(equity_curve) + 1, "entry_ts": t["entry_ts"], "cum_pnl": round(cum, 2)})

    return {
        "total_matched":     total_matched,
        "alerts_considered": len(matched),
        "trades_executed":   len(trades),
        "skipped":           skipped,
        "overall":           _stats(trades),
        "with_sweep":        _stats(with_sweep),
        "without_sweep":     _stats(without_sweep),
        "equity_curve":      equity_curve,
        "trades":            trades,
    }


from alerts_backtest_page import ALERTS_HTML

@app.get("/alerts", response_class=HTMLResponse)
async def alerts_page_route():
    return HTMLResponse(ALERTS_HTML)


# ══════════════════════════════════════════════════════════════════════════
# Low-Float Spike Backtest  (alerts.db → yfinance float → Alpaca 1-min bars)
#
# Hypothesis: a low-float stock (< N million shares) that pops ≥ X% intraday
# tends to sustain / extend the move. Scan a day's alerted symbols, rank by
# dollar flow, filter by float + spike, then simulate an entry at
# baseline × (1 + spike% + delta%) with $-sized bracket exits, and report
# how far the runners actually go (max run-up distribution).
# ══════════════════════════════════════════════════════════════════════════
import json as _lf_json
import sqlite3 as _lf_sql
import asyncio as _lf_aio
import statistics as _lf_stat
from datetime import timedelta as _lf_td
from pathlib import Path as _lf_Path

LF_DB_PATH     = _lf_Path(__file__).resolve().parent.parent / "alerts.db"
LF_FLOAT_CACHE = _lf_Path(__file__).resolve().parent / "float_cache.json"
_LF_UTC        = ZoneInfo("UTC")


def _lf_day_activity(day: date):
    """Per-symbol alert activity for one NY calendar day, ranked by $ flow."""
    start = datetime(day.year, day.month, day.day, tzinfo=NY).astimezone(_LF_UTC)
    end   = start + _lf_td(days=1)
    fmt   = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S")
    con = _lf_sql.connect(str(LF_DB_PATH))
    try:
        rows = con.execute(
            """
            SELECT sym,
                   COUNT(*),
                   SUM(CASE WHEN type='sweep' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN type='vol'   THEN 1 ELSE 0 END),
                   SUM(COALESCE(value1m, 0)),
                   MIN(ts),
                   AVG(CASE WHEN vwap1m > 0 THEN vwap1m END)
            FROM alerts
            WHERE ts >= ? AND ts < ? AND sym != ''
            GROUP BY sym
            ORDER BY 5 DESC
            """,
            (fmt(start), fmt(end)),
        ).fetchall()
    finally:
        con.close()

    out = []
    for sym, n, sweeps, vols, dollar, first_ts, avg_px in rows:
        try:
            first_ny = datetime.fromisoformat(first_ts.replace("Z", "+00:00")).astimezone(NY)
            first_str = first_ny.strftime("%H:%M")
        except (ValueError, AttributeError):
            first_str = ""
        out.append({
            "sym":         sym,
            "alerts":      n,
            "sweeps":      sweeps or 0,
            "vol_spikes":  vols or 0,
            "dollar_flow": round(dollar or 0.0, 0),
            "first_alert": first_str,
            "avg_price":   round(avg_px, 4) if avg_px else None,
        })
    return out


def _lf_read_float_cache() -> dict:
    try:
        return _lf_json.loads(LF_FLOAT_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _lf_fetch_floats_sync(symbols: list) -> dict:
    """Sequential yfinance lookups sharing ONE session — parallel sessions trip
    Yahoo's 'Invalid Crumb' auth, so do not parallelize this."""
    out = {}
    try:
        import yfinance as yf
        # corporate SSL interception on this machine — same reason the Alpaca
        # client runs verify=False
        from curl_cffi import requests as _curl_requests
        sess = _curl_requests.Session(impersonate="chrome", verify=False)
    except Exception:
        return {s: {"float": None, "shares_out": None, "mcap": None, "name": ""}
                for s in symbols}
    for sym in symbols:
        try:
            info = yf.Ticker(sym, session=sess).get_info() or {}
            out[sym] = {
                "float":      info.get("floatShares"),
                "shares_out": info.get("sharesOutstanding"),
                "mcap":       info.get("marketCap"),
                "name":       info.get("shortName") or "",
            }
        except Exception:
            out[sym] = {"float": None, "shares_out": None, "mcap": None, "name": ""}
    return out


_LF_FLOAT_LOCK = _lf_aio.Lock()


async def _lf_get_floats(symbols: list) -> dict:
    """Float shares per symbol via yfinance, disk-cached. Successful lookups are
    kept 30 days; failed/null lookups are retried after 1 day."""
    cache = _lf_read_float_cache()
    now   = datetime.now(_LF_UTC)
    out, missing = {}, []

    for s in symbols:
        c = cache.get(s)
        if c:
            try:
                age_days = (now - datetime.fromisoformat(c["fetched_at"])).days
            except (KeyError, ValueError):
                age_days = 9999
            if (c.get("float") is not None and age_days < 30) or \
               (c.get("float") is None and age_days < 1):
                out[s] = c
                continue
        missing.append(s)

    if missing:
        async with _LF_FLOAT_LOCK:          # one yfinance batch at a time
            fetched = await _lf_aio.to_thread(_lf_fetch_floats_sync, missing)
        for s, r in fetched.items():
            r["fetched_at"] = now.isoformat()
            out[s] = r
        cache.update({s: out[s] for s in missing})
        try:
            LF_FLOAT_CACHE.write_text(_lf_json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
    return out


async def _lf_daily_bars(symbols: list, day: date) -> dict:
    """Daily bars (lookback ~10 days through `day`) for many symbols in one call.
    Returns {sym: {"prev_close": .., "day_open": .., "day_high": .., "day_low": ..,
    "day_close": .., "day_volume": ..}} — day_* fields None if no bar for `day`."""
    start  = datetime(day.year, day.month, day.day, tzinfo=NY) - _lf_td(days=12)
    end    = datetime(day.year, day.month, day.day, 23, 59, tzinfo=NY)
    params = {
        "symbols":    ",".join(symbols),
        "timeframe":  "1Day",
        "start":      start.isoformat(),
        "end":        end.isoformat(),
        "limit":      10000,
        "feed":       "iex",
        "adjustment": "raw",
    }
    headers = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": SECRET_KEY}
    url     = f"{DATA_BASE}/v2/stocks/bars"
    merged  = {}
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        while True:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200:
                raise HTTPException(r.status_code, f"Alpaca error: {r.text}")
            data = r.json()
            for sym, blist in (data.get("bars") or {}).items():
                merged.setdefault(sym, []).extend(blist)
            token = data.get("next_page_token")
            if not token:
                break
            params["page_token"] = token

    out = {}
    for sym in symbols:
        day_bar, prev_close = None, None
        for b in merged.get(sym, []):
            b_day = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY).date()
            if b_day == day:
                day_bar = b
            elif b_day < day:
                prev_close = b["c"]
        out[sym] = {
            "prev_close": prev_close,
            "day_open":   day_bar["o"] if day_bar else None,
            "day_high":   day_bar["h"] if day_bar else None,
            "day_low":    day_bar["l"] if day_bar else None,
            "day_close":  day_bar["c"] if day_bar else None,
            "day_volume": day_bar["v"] if day_bar else None,
        }
    return out


@app.get("/api/lowfloat/meta")
async def lowfloat_meta():
    con = _lf_sql.connect(str(LF_DB_PATH))
    try:
        mn, mx, n = con.execute("SELECT MIN(ts), MAX(ts), COUNT(*) FROM alerts").fetchone()
    finally:
        con.close()
    def _d(ts):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(NY).date().isoformat()
        except (ValueError, AttributeError):
            return None
    return {"min_date": _d(mn), "max_date": _d(mx), "total_rows": n}


@app.get("/api/lowfloat/candidates")
async def lowfloat_candidates(
    day:           str,
    max_float_m:   float = 3.0,    # float threshold, millions of shares
    min_spike_pct: float = 10.0,   # day high vs prev close
    top_n:         int   = 60,     # how many top-$-flow symbols to scan
    max_price:     float = 0.0,    # 0 = no price filter (avg alert price)
):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "day must be YYYY-MM-DD")

    acts = _lf_day_activity(d)
    if not acts:
        return {"date": day, "total_active": 0, "scanned": 0, "candidates": []}
    if max_price > 0:
        acts = [a for a in acts if a["avg_price"] and a["avg_price"] <= max_price]

    scanned = acts[:max(1, min(top_n, 200))]
    syms    = [a["sym"] for a in scanned]

    floats, daily = await _lf_aio.gather(_lf_get_floats(syms), _lf_daily_bars(syms, d))

    candidates = []
    for a in scanned:
        f  = floats.get(a["sym"], {})
        db = daily.get(a["sym"], {})
        flt        = f.get("float")
        float_m    = round(flt / 1e6, 3) if flt else None
        prev_close = db.get("prev_close")
        day_high   = db.get("day_high")
        spike_pct  = round((day_high / prev_close - 1) * 100, 2) if (prev_close and day_high) else None
        close_pct  = (round((db["day_close"] / prev_close - 1) * 100, 2)
                      if (prev_close and db.get("day_close")) else None)
        gap_pct    = (round((db["day_open"] / prev_close - 1) * 100, 2)
                      if (prev_close and db.get("day_open")) else None)
        candidates.append({
            **a,
            "name":         f.get("name") or "",
            "float_m":      float_m,
            "shares_out_m": round(f["shares_out"] / 1e6, 3) if f.get("shares_out") else None,
            "prev_close":   prev_close,
            "day_open":     db.get("day_open"),
            "day_high":     day_high,
            "day_close":    db.get("day_close"),
            "day_volume":   db.get("day_volume"),
            "spike_pct":    spike_pct,
            "close_pct":    close_pct,
            "gap_pct":      gap_pct,
            "passes_float": float_m is not None and float_m <= max_float_m,
            "passes_spike": spike_pct is not None and spike_pct >= min_spike_pct,
        })

    candidates.sort(key=lambda c: (not (c["passes_float"] and c["passes_spike"]),
                                   -(c["dollar_flow"] or 0)))
    return {
        "date":          day,
        "total_active":  len(acts),
        "scanned":       len(scanned),
        "passing":       sum(1 for c in candidates if c["passes_float"] and c["passes_spike"]),
        "candidates":    candidates,
    }


def _lf_simulate(sym, bars, bar_times, baseline_px, spike_pct, entry_delta_pct,
                 amount, sl_pct, trail_pct, entry_start_dt, entry_end_dt, exit_dt):
    """Walk 1-min bars: trigger when high ≥ baseline×(1+spike%), enter at
    baseline×(1+spike%+delta%) (or bar open if it gapped through). Exit on a
    trailing stop: hard stop at entry×(1−sl%), ratcheted up to peak×(1−trail%)
    as the stock makes new highs (peak updates AFTER the stop check each bar,
    so a same-bar spike-and-dump can't trail itself out — conservative).
    Also measures how far the move ran after the trigger (MFE)."""
    trigger_level = baseline_px * (1 + spike_pct / 100.0)
    entry_level   = baseline_px * (1 + (spike_pct + entry_delta_pct) / 100.0)

    trigger_idx = entry_idx = None
    entry_px = None
    for i, (b, bt) in enumerate(zip(bars, bar_times)):
        if bt < entry_start_dt:
            continue
        if bt > entry_end_dt:
            break
        if trigger_idx is None and b["h"] >= trigger_level:
            trigger_idx = i
        if trigger_idx is not None and b["h"] >= entry_level:
            entry_idx = i
            entry_px  = b["o"] if b["o"] >= entry_level else entry_level
            break

    # day-wide reference stats (independent of the trade)
    sess = [(b, bt) for b, bt in zip(bars, bar_times) if bt >= entry_start_dt]
    day_high = max((b["h"] for b, _ in sess), default=None)
    day_high_ts = None
    if day_high is not None:
        for b, bt in sess:
            if b["h"] >= day_high:
                day_high_ts = bt
                break
    day_max_vs_baseline = (day_high / baseline_px - 1) * 100 if day_high else None

    result = {
        "sym":                 sym,
        "baseline":            round(baseline_px, 4),
        "trigger_level":       round(trigger_level, 4),
        "entry_level":         round(entry_level, 4),
        "triggered":           trigger_idx is not None,
        "trigger_ts":          bar_times[trigger_idx].isoformat() if trigger_idx is not None else None,
        "entered":             entry_idx is not None,
        "day_high":            day_high,
        "day_high_ts":         day_high_ts.isoformat() if day_high_ts else None,
        "day_max_vs_baseline": round(day_max_vs_baseline, 2) if day_max_vs_baseline is not None else None,
    }
    if trigger_idx is not None:
        post = [b["h"] for b, bt in zip(bars, bar_times)
                if bt >= bar_times[trigger_idx] and bt >= entry_start_dt]
        peak = max(post, default=trigger_level)
        result["runup_after_trigger"] = round((peak / trigger_level - 1) * 100, 2)
    else:
        result["runup_after_trigger"] = None

    if entry_idx is None:
        return result

    sl_px      = entry_px * (1 - sl_pct / 100.0)
    trail_frac = (1 - trail_pct / 100.0) if trail_pct > 0 else None
    shares   = amount / entry_px
    entry_ts = bar_times[entry_idx]

    exit_px = exit_reason = None
    exit_idx = entry_idx
    mfe_px, mae_px, mfe_ts = entry_px, entry_px, entry_ts
    peak = entry_px                       # post-entry high the trail ratchets on
    trail_curve = []                      # per-bar stop level, for the chart

    for j in range(entry_idx, len(bars)):
        b, bt = bars[j], bar_times[j]
        if bt >= exit_dt:
            exit_px, exit_reason, exit_idx = b["o"], "time", j
            break
        exit_idx = j
        if b["h"] > mfe_px:
            mfe_px, mfe_ts = b["h"], bt
        mae_px = min(mae_px, b["l"])
        if j == entry_idx:
            # entry bar: only the hard stop below the fill can realistically hit
            trail_curve.append([bt.isoformat(), round(sl_px, 4)])
            if b["l"] <= sl_px:
                exit_px, exit_reason = sl_px, "sl"
                break
            continue
        stop_level = sl_px
        if trail_frac is not None:
            stop_level = max(sl_px, peak * trail_frac)
        trail_curve.append([bt.isoformat(), round(stop_level, 4)])
        if b["l"] <= stop_level:
            exit_px     = b["o"] if b["o"] < stop_level else stop_level
            exit_reason = "trail" if stop_level > sl_px else "sl"
            break
        if b["h"] > peak:                 # ratchet AFTER the stop check
            peak = b["h"]

    if exit_px is None:
        exit_px, exit_reason = bars[exit_idx]["c"], "eod"

    pnl_pct = (exit_px / entry_px - 1) * 100
    result.update({
        "entry_ts":     entry_ts.isoformat(),
        "entry_price":  round(entry_px, 4),
        "shares":       round(shares, 2),
        "sl_price":     round(sl_px, 4),
        "trail_curve":  trail_curve,
        "exit_ts":      bar_times[exit_idx].isoformat(),
        "exit_price":   round(exit_px, 4),
        "exit_reason":  exit_reason,
        "hold_min":     round((bar_times[exit_idx] - entry_ts).total_seconds() / 60, 1),
        "pnl_pct":      round(pnl_pct, 2),
        "pnl_dollar":   round(shares * (exit_px - entry_px), 2),
        "mfe_pct":      round((mfe_px / entry_px - 1) * 100, 2),
        "mae_pct":      round((mae_px / entry_px - 1) * 100, 2),
        "mfe_ts":       mfe_ts.isoformat(),
    })
    return result


@app.get("/api/lowfloat/backtest")
async def lowfloat_backtest(
    day:             str,
    symbols:         str,
    spike_pct:       float = 10.0,     # trigger: % above baseline
    entry_delta_pct: float = 1.0,      # fill delta above the trigger
    amount:          float = 1000.0,   # $ per trade
    sl_pct:          float = 10.0,     # hard initial stop below entry
    trail_pct:       float = 10.0,     # trailing stop off post-entry high; 0 = off
    baseline:        str   = "prev_close",   # prev_close | day_open
    entry_start:     str   = "09:30",
    entry_end:       str   = "15:30",
    exit_time:       str   = "15:55",
    include_bars:    bool  = True,
):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "day must be YYYY-MM-DD")
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        raise HTTPException(400, "symbols required")
    if len(syms) > 20:
        raise HTTPException(400, "max 20 symbols per run")

    entry_start_dt = _make_dt(d, entry_start, NY)
    entry_end_dt   = _make_dt(d, entry_end, NY)
    exit_dt        = _make_dt(d, exit_time, NY)

    daily = await _lf_daily_bars(syms, d)

    sem = _lf_aio.Semaphore(6)
    bars_by_sym = {}

    async def _fetch(sym):
        async with sem:
            try:
                bars_by_sym[sym] = await fetch_bars(sym, d)
            except HTTPException:
                bars_by_sym[sym] = []

    await _lf_aio.gather(*[_fetch(s) for s in syms])

    results, series = [], {}
    for sym in syms:
        bars = bars_by_sym.get(sym) or []
        if not bars:
            results.append({"sym": sym, "error": "no 1-min bars for this day"})
            continue
        db = daily.get(sym, {})
        baseline_px = db.get("prev_close") if baseline == "prev_close" else db.get("day_open")
        used_baseline = baseline
        if not baseline_px:                          # IPO / missing daily bar fallback
            baseline_px = db.get("day_open") or bars[0]["o"]
            used_baseline = "day_open(fallback)"
        if not baseline_px or baseline_px <= 0:
            results.append({"sym": sym, "error": "no baseline price"})
            continue

        bar_times = [datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                     for b in bars]
        r = _lf_simulate(sym, bars, bar_times, baseline_px, spike_pct, entry_delta_pct,
                         amount, sl_pct, trail_pct, entry_start_dt, entry_end_dt, exit_dt)
        r["baseline_mode"] = used_baseline
        r["prev_close"]    = db.get("prev_close")
        results.append(r)

        if include_bars:
            series[sym] = {
                "t": [bt.isoformat() for bt in bar_times],
                "c": [b["c"] for b in bars],
                "h": [b["h"] for b in bars],
                "l": [b["l"] for b in bars],
                "v": [b["v"] for b in bars],
            }

    trades = [r for r in results if r.get("entered")]
    triggered = [r for r in results if r.get("triggered")]

    def _agg(rows):
        n = len(rows)
        if n == 0:
            return {"n": 0}
        wins = sum(1 for t in rows if t["pnl_dollar"] > 0)
        mfes = [t["mfe_pct"] for t in rows]
        return {
            "n":            n,
            "wins":         wins,
            "win_rate":     round(100 * wins / n, 1),
            "avg_pnl_pct":  round(sum(t["pnl_pct"] for t in rows) / n, 2),
            "total_pnl":    round(sum(t["pnl_dollar"] for t in rows), 2),
            "invested":     round(n * amount, 2),
            "trail_hits":   sum(1 for t in rows if t["exit_reason"] == "trail"),
            "sl_hits":      sum(1 for t in rows if t["exit_reason"] == "sl"),
            "time_exits":   sum(1 for t in rows if t["exit_reason"] in ("time", "eod")),
            "avg_hold_min": round(sum(t["hold_min"] for t in rows) / n, 1),
            "avg_mfe_pct":  round(sum(mfes) / n, 2),
            "med_mfe_pct":  round(_lf_stat.median(mfes), 2),
            "max_mfe_pct":  round(max(mfes), 2),
        }

    runups = [r["runup_after_trigger"] for r in triggered
              if r.get("runup_after_trigger") is not None]
    buckets = [10, 25, 50, 100, 200]
    runup_dist = [{"gte": b, "count": sum(1 for x in runups if x >= b)} for b in buckets]

    return {
        "date":        day,
        "params": {
            "spike_pct": spike_pct, "entry_delta_pct": entry_delta_pct, "amount": amount,
            "sl_pct": sl_pct, "trail_pct": trail_pct, "baseline": baseline,
            "entry_start": entry_start, "entry_end": entry_end, "exit_time": exit_time,
        },
        "n_symbols":   len(syms),
        "n_triggered": len(triggered),
        "n_trades":    len(trades),
        "stats":       _agg(trades),
        "avg_runup_after_trigger": round(sum(runups) / len(runups), 2) if runups else None,
        "med_runup_after_trigger": round(_lf_stat.median(runups), 2) if runups else None,
        "runup_distribution":      runup_dist,
        "results":     results,
        "series":      series,
    }


from lowfloat_page import LOWFLOAT_HTML

@app.get("/lowfloat", response_class=HTMLResponse)
async def lowfloat_page_route():
    return HTMLResponse(LOWFLOAT_HTML)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backtest_app:app", host="0.0.0.0", port=2222, reload=False)
