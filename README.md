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

## Database (`alerts.db`)

A single SQLite file next to `main.py`, created and migrated automatically on
startup (`_init_db()`). It is gitignored — it is runtime data, not source.
Journal mode is **WAL** so the dashboard can poll history while alerts are
being written; every connection is opened with a 30 s busy timeout and closed
when its request finishes.

### `alerts` — one row per fired alert

| Column      | Type      | Notes                                                  |
|-------------|-----------|--------------------------------------------------------|
| `id`        | INTEGER   | PK, autoincrement — also the newest-first sort key      |
| `ts`        | TEXT      | ISO-8601, **normalised to UTC** server-side             |
| `sym`       | TEXT      | Uppercased, validated against `^[A-Z][A-Z0-9.\-]{0,9}$` |
| `tag`       | TEXT      | `new`, or the re-alert tag (max 32 chars)               |
| `delta`     | REAL      | VWAP 1m vs 2m change, %                                 |
| `value1m`   | REAL      | 1-minute dollar volume                                  |
| `vwap1m`    | REAL      | 1-minute VWAP                                           |
| `vwap2m`    | REAL      | 2-minute VWAP (baseline)                                |
| `cnt1m`     | INTEGER   | Trade count in the last minute                          |
| `direction` | TEXT      | `bull` / `bear` — derived from `delta` if not supplied  |

Indexes: `idx_alerts_sym_id (sym, id DESC)` for per-ticker history,
`idx_alerts_ts (ts)` for date-range reads.

### `suppressed` — tickers muted by the user

| Column       | Type    | Notes                                                    |
|--------------|---------|----------------------------------------------------------|
| `sym`        | TEXT    | PRIMARY KEY — re-suppressing a ticker replaces the row    |
| `reason`     | TEXT    | Free text, max 200 chars                                  |
| `expires_at` | TEXT    | `NULL` = forever; otherwise UTC ISO-8601                  |
| `added_at`   | TEXT    | UTC ISO-8601                                              |

Expired rows are purged on every `GET /suppressed`, so a suppression lapses
even if the browser tab is stale. Index: `idx_supp_expires (expires_at)`.

### Endpoints

| Method   | Path                             | Behaviour                                                        |
|----------|----------------------------------|------------------------------------------------------------------|
| `POST`   | `/log/alert`                     | Insert one alert. Validates/coerces every field; `400` on bad input |
| `GET`    | `/log/alerts?limit=&sym=`        | Newest-first history. `limit` 1–5000 (default 500), optional ticker filter. Returns `{alerts, total, limit}` |
| `GET`    | `/suppressed`                    | Active suppressions only (purges expired)                        |
| `POST`   | `/suppressed/{sym}`              | Body `{reason?, expires_at?}`; omit `expires_at` to mute forever |
| `DELETE` | `/suppressed/{sym}`              | Un-suppress; reports `removed` count                             |

All payloads come from the browser, so tickers, numbers and timestamps are
validated server-side — NaN/∞ are stored as `NULL`, unparseable timestamps fall
back to the server clock, and a malformed ticker is rejected rather than
written.

**Suppression is enforced on write, not just in the UI.** `POST /log/alert`
checks the `suppressed` table before inserting, so a browser tab holding a
stale suppression list can't log alerts for a muted ticker. A skipped alert
still returns `200` — `{"ok": true, "suppressed": true, "written": false}` —
so the caller can tell it was muted rather than failed.

### Retention

`alerts` keeps everything by default. Set `ALERT_RETENTION_DAYS` in `.env` to
opt into pruning:

```
ALERT_RETENTION_DAYS=90     # 0 or unset = keep forever
```

A background task prunes at startup and once every 24 h, then `VACUUM`s to
actually give the disk space back. Rows with a `NULL` ts are never pruned —
their age is unknown, so they're left alone.

**Schema migrations:** `_init_db()` adds any columns an older `alerts.db` is
missing (`ALTER TABLE … ADD COLUMN`) and creates missing indexes, so upgrading
in place preserves existing rows. Backing up is just copying `alerts.db`
(plus `alerts.db-wal` if the app is running).

---

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
