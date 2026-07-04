"""
Build documentation Excel for The100xTrade Live Dashboard logic.
Tabs: Raw Stream · Filter · Vol Spike · Sweep · Move % · Control Panel
"""

from openpyxl import Workbook
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter

# ── Colour palette ────────────────────────────────────────────────────────────
BG_DARK    = "0D1117"
BG_CARD    = "161B22"
BG_CARD2   = "1C2128"
BG_GREEN   = "1A3A1A"
BG_RED     = "3A1A1A"
BG_BLUE    = "1A2A3A"
BG_YELLOW  = "3A3A1A"
BG_PURPLE  = "2A1A3A"
BG_HEADER  = "21262D"

C_GREEN    = "3FB950"
C_RED      = "F85149"
C_BLUE     = "58A6FF"
C_YELLOW   = "E3B341"
C_PURPLE   = "BC8CFF"
C_TEAL     = "39D353"
C_DIM      = "8B949E"
C_TEXT     = "E6EDF3"
C_WHITE    = "FFFFFF"
C_ORANGE   = "E8A060"
C_NANO     = "E86060"
C_SMALL    = "E8A060"
C_MID      = "60A0E8"
C_BIG      = "A060E8"

def fill(hex_col):
    return PatternFill("solid", fgColor=hex_col)

def font(hex_col=C_TEXT, bold=False, size=10, italic=False):
    return Font(color=hex_col, bold=bold, size=size, italic=italic,
                name="Consolas")

def center():
    return Alignment(horizontal="center", vertical="center", wrap_text=True)

def left():
    return Alignment(horizontal="left", vertical="center", wrap_text=True)

def thin_border():
    s = Side(style="thin", color="30363D")
    return Border(left=s, right=s, top=s, bottom=s)

def header_border():
    b = Side(style="medium", color="58A6FF")
    s = Side(style="thin",   color="30363D")
    return Border(left=s, right=s, top=b, bottom=b)


def style_cell(ws, row, col, value,
               bg=BG_CARD, fg=C_TEXT, bold=False, size=10,
               align="left", italic=False, border=True, num_fmt=None):
    c = ws.cell(row=row, column=col, value=value)
    c.fill      = fill(bg)
    c.font      = font(fg, bold, size, italic)
    c.alignment = center() if align == "center" else left()
    if border:
        c.border = thin_border()
    if num_fmt:
        c.number_format = num_fmt
    return c


def write_header_row(ws, row, headers, bgs=None, fgs=None, col_start=1):
    for i, h in enumerate(headers):
        bg  = (bgs[i]  if bgs  else BG_HEADER)
        fg  = (fgs[i]  if fgs  else C_BLUE)
        c   = ws.cell(row=row, column=col_start + i, value=h)
        c.fill      = fill(bg)
        c.font      = font(fg, bold=True, size=10)
        c.alignment = center()
        c.border    = header_border()


def section_title(ws, row, col, text, span=1, bg=BG_HEADER, fg=C_BLUE):
    c = ws.cell(row=row, column=col, value=text)
    c.fill      = fill(bg)
    c.font      = font(fg, bold=True, size=11)
    c.alignment = center()
    c.border    = header_border()
    if span > 1:
        ws.merge_cells(start_row=row, start_column=col,
                       end_row=row, end_column=col + span - 1)


def blank_row(ws, row, cols, bg=BG_DARK):
    for col in range(1, cols + 1):
        c = ws.cell(row=row, column=col, value="")
        c.fill = fill(bg)
        c.border = thin_border()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — RAW STREAM  (120 tagged records)
# ══════════════════════════════════════════════════════════════════════════════
# TAG values and their meaning
# "PASSED -> symbolData"        — normal tick stored in rolling window
# "PASSED -> sweepAcc [ISO]"    — F-condition, accumulated in sweep batch
# "DROPPED: stale >5min"        — tick ts_ms older than now-5min AT TIME OF PROCESSING
#                                  In live feed ticks arrive in <200ms so this never fires.
#                                  Fires on WS reconnect when server replays buffered ticks.
# "DROPPED: large-cap"          — symbol on LARGE_CAP_EXCLUDE list
# "DROPPED: cond [M]"           — MOC auction print
# "DROPPED: cond [Q]"           — official close print
# "EXCH D: dark pool / late"    — FINRA ADF print, passed today but stale risk
#
# Columns: Timestamp | Symbol | Exchange | Price | Size | Conditions | $ Val | TAG
#
# Exchange codes used:
#   N=NYSE  Q=NASDAQ  P=NYSE Arca  Z=Cboe BZX  K=Cboe EDGX
#   C=NYSE American  V=IEX  D=FINRA ADF (dark pool)  U=MEMX

_TAG_PASSED    = "PASSED -> symbolData"
_TAG_ISO       = "PASSED -> sweepAcc [ISO]"
_TAG_STALE     = "DROPPED: stale >5min (reconnect replay)"
_TAG_LARGECAP  = "DROPPED: large-cap"
_TAG_COND_M    = "DROPPED: cond [M]"
_TAG_COND_Q    = "DROPPED: cond [Q]"
_TAG_DARK      = "EXCH D: dark pool / late"

def _tag_color(tag):
    if tag == _TAG_PASSED:   return C_GREEN,  BG_CARD
    if tag == _TAG_ISO:      return C_YELLOW, BG_YELLOW
    if tag == _TAG_STALE:    return C_DIM,    BG_CARD2
    if tag == _TAG_LARGECAP: return C_RED,    BG_RED
    if tag == _TAG_COND_M:   return C_RED,    BG_RED
    if tag == _TAG_COND_Q:   return C_RED,    BG_RED
    if tag == _TAG_DARK:     return C_ORANGE, "3A2A0A"
    return C_TEXT, BG_CARD

# fmt: (timestamp, symbol, exchange, price, size, conditions, tag)
_RAW_RECORDS = [
    # ── Stale ticks — RECONNECT SCENARIO ────────────────────────────────────
    # WS disconnected at 09:31:00 and reconnected at 09:36:10.
    # Server replayed buffered ticks from the gap. These ticks have real
    # timestamps (09:31) but are received at 09:36 — ts_ms < now-5min → DROPPED.
    # In a normal uninterrupted session these rows do NOT exist.
    ("09:31:02.115", "ABCD", "N", 14.05,   500,  "[]",    _TAG_STALE),
    ("09:31:04.330", "EFGH", "Q", 42.10,   300,  "[]",    _TAG_STALE),
    ("09:31:06.880", "MNOP", "P", 28.15,   800,  "[]",    _TAG_STALE),
    ("09:31:09.002", "ABCD", "Z", 14.08,  1000,  "[]",    _TAG_STALE),
    ("09:31:12.445", "LMNO", "N", 36.18,   400,  "[]",    _TAG_STALE),
    ("09:31:15.770", "QRST", "Q", 85.10,   600,  "[]",    _TAG_STALE),
    ("09:31:19.330", "EFGH", "P", 42.22,   700,  "[]",    _TAG_STALE),
    ("09:31:22.005", "ABCD", "N", 14.12,   900,  "[]",    _TAG_STALE),

    # ── Large-cap drops ──────────────────────────────────────────────────────
    ("09:31:00.211", "AAPL", "Q",175.22, 2000,   "[]",    _TAG_LARGECAP),
    ("09:31:00.450", "SPY",  "P",485.60, 5000,   "[]",    _TAG_LARGECAP),
    ("09:31:01.003", "MSFT", "Q",420.10,  300,   "[]",    _TAG_LARGECAP),
    ("09:31:01.204", "NVDA", "Q",875.40,  800,   "[]",    _TAG_LARGECAP),
    ("09:31:02.010", "TSLA", "N",178.30, 1500,   "[]",    _TAG_LARGECAP),
    ("09:31:02.355", "QQQ",  "Q",432.80, 3000,   "[]",    _TAG_LARGECAP),
    ("09:31:03.100", "AAPL", "N",175.25, 1000,   "['F']", _TAG_LARGECAP),

    # ── Bad condition drops ──────────────────────────────────────────────────
    ("09:31:03.500", "UVWX", "N",  7.22,   200,  "['M']", _TAG_COND_M),
    ("09:31:03.600", "UVWX", "N",  7.22,   150,  "['Q']", _TAG_COND_Q),
    ("09:31:04.010", "LMNO", "Q", 36.20,   100,  "['M']", _TAG_COND_M),
    ("09:31:10.200", "EFGH", "P", 42.10,   500,  "['Q']", _TAG_COND_Q),

    # ── Normal ticks — ABCD (Nano cap, building vol) ─────────────────────────
    ("09:31:05.112", "ABCD", "N", 14.10,   300,  "[]",    _TAG_PASSED),
    ("09:31:05.450", "ABCD", "Q", 14.11,   500,  "[]",    _TAG_PASSED),
    ("09:31:06.003", "ABCD", "P", 14.12,   200,  "[]",    _TAG_PASSED),
    ("09:31:06.780", "ABCD", "Z", 14.11,   800,  "[]",    _TAG_PASSED),
    ("09:31:07.122", "ABCD", "N", 14.13,  1200,  "[]",    _TAG_PASSED),
    ("09:31:08.005", "ABCD", "K", 14.14,   400,  "[]",    _TAG_PASSED),
    ("09:31:09.330", "ABCD", "Q", 14.15,   600,  "[]",    _TAG_PASSED),
    ("09:31:10.001", "ABCD", "P", 14.16,   900,  "[]",    _TAG_PASSED),
    ("09:31:10.445", "ABCD", "N", 14.17,  1100,  "[]",    _TAG_PASSED),
    ("09:31:11.200", "ABCD", "Z", 14.18,   700,  "[]",    _TAG_PASSED),

    # ── Normal ticks — EFGH (Small cap) ─────────────────────────────────────
    ("09:31:05.220", "EFGH", "Q", 42.10,   300,  "[]",    _TAG_PASSED),
    ("09:31:06.445", "EFGH", "N", 42.12,   500,  "[]",    _TAG_PASSED),
    ("09:31:07.780", "EFGH", "P", 42.08,   200,  "[]",    _TAG_PASSED),
    ("09:31:09.005", "EFGH", "V", 42.14,   400,  "[]",    _TAG_PASSED),
    ("09:31:11.330", "EFGH", "Z", 42.18,   600,  "[]",    _TAG_PASSED),
    ("09:31:13.002", "EFGH", "Q", 42.20,   800,  "[]",    _TAG_PASSED),
    ("09:31:15.110", "EFGH", "N", 42.22,   300,  "[]",    _TAG_PASSED),
    ("09:31:17.440", "EFGH", "K", 42.25,   500,  "[]",    _TAG_PASSED),

    # ── Exchange D (FINRA ADF dark pool) — currently PASSED but flag ─────────
    ("09:31:08.120", "ABCD", "D",  14.10,  2000, "[]",    _TAG_DARK),
    ("09:31:12.330", "EFGH", "D",  42.15,  1500, "[]",    _TAG_DARK),
    ("09:31:18.005", "MNOP", "D",  28.40,  3000, "[]",    _TAG_DARK),
    ("09:31:25.441", "LMNO", "D",  36.25,  2500, "[]",    _TAG_DARK),
    ("09:32:04.770", "QRST", "D",  85.80,  1000, "[]",    _TAG_DARK),
    ("09:32:44.110", "ABCD", "D",  14.28,  4000, "[]",    _TAG_DARK),
    ("09:33:15.220", "UVWX", "D",   7.38,  5000, "[]",    _TAG_DARK),

    # ── MNOP ISO sweep sequence (Small cap, $28 range) ───────────────────────
    # Pre-sweep normal ticks (these set the prePrice reference)
    ("09:31:20.001", "MNOP", "Q", 28.20,   400,  "[]",    _TAG_PASSED),
    ("09:31:20.220", "MNOP", "N", 28.22,   600,  "[]",    _TAG_PASSED),
    ("09:31:20.440", "MNOP", "P", 28.21,   300,  "[]",    _TAG_PASSED),
    # ISO sweep starts — same batch window
    ("09:31:20.885", "MNOP", "Q", 28.30,  2000,  "['F']", _TAG_ISO),
    ("09:31:20.886", "MNOP", "N", 28.32,  3500,  "['F']", _TAG_ISO),
    ("09:31:20.887", "MNOP", "Z", 28.34,  2800,  "['F']", _TAG_ISO),
    ("09:31:20.888", "MNOP", "P", 28.35,  4000,  "['F']", _TAG_ISO),
    ("09:31:20.889", "MNOP", "K", 28.36,  3200,  "['F']", _TAG_ISO),
    ("09:31:20.890", "MNOP", "Q", 28.38,  2500,  "['F']", _TAG_ISO),
    ("09:31:20.891", "MNOP", "N", 28.40,  1800,  "['F']", _TAG_ISO),
    # Post-sweep normal ticks
    ("09:31:21.110", "MNOP", "Q", 28.42,   500,  "[]",    _TAG_PASSED),
    ("09:31:21.330", "MNOP", "N", 28.44,   700,  "[]",    _TAG_PASSED),

    # ── QRST normal ticks (Mid cap, $85-88) ─────────────────────────────────
    ("09:31:22.001", "QRST", "Q", 85.20,   200,  "[]",    _TAG_PASSED),
    ("09:31:23.440", "QRST", "N", 85.25,   300,  "[]",    _TAG_PASSED),
    ("09:31:25.003", "QRST", "P", 85.30,   400,  "[]",    _TAG_PASSED),
    ("09:31:27.220", "QRST", "V", 85.28,   500,  "[]",    _TAG_PASSED),
    ("09:31:29.115", "QRST", "Z", 85.35,   600,  "[]",    _TAG_PASSED),
    ("09:31:31.002", "QRST", "Q", 85.40,   800,  "[]",    _TAG_PASSED),

    # ── UVWX normal ticks (Nano cap, $6-8) ──────────────────────────────────
    ("09:31:15.005", "UVWX", "Q",  7.20,   500,  "[]",    _TAG_PASSED),
    ("09:31:16.110", "UVWX", "N",  7.21,   800,  "[]",    _TAG_PASSED),
    ("09:31:17.330", "UVWX", "P",  7.22,   600,  "[]",    _TAG_PASSED),
    ("09:31:19.002", "UVWX", "Z",  7.23,  1000,  "[]",    _TAG_PASSED),
    ("09:31:21.440", "UVWX", "K",  7.24,   700,  "[]",    _TAG_PASSED),

    # ── ABCD vol spike building (9:32 — high volume minute) ─────────────────
    ("09:32:00.110", "ABCD", "N", 14.20,  1500,  "[]",    _TAG_PASSED),
    ("09:32:00.330", "ABCD", "Q", 14.22,  2000,  "[]",    _TAG_PASSED),
    ("09:32:00.560", "ABCD", "P", 14.24,  3000,  "[]",    _TAG_PASSED),
    ("09:32:00.780", "ABCD", "Z", 14.25,  2500,  "[]",    _TAG_PASSED),
    ("09:32:01.002", "ABCD", "N", 14.26,  4000,  "[]",    _TAG_PASSED),
    ("09:32:01.220", "ABCD", "K", 14.27,  3500,  "[]",    _TAG_PASSED),
    ("09:32:01.440", "ABCD", "Q", 14.28,  2800,  "[]",    _TAG_PASSED),
    ("09:32:01.660", "ABCD", "P", 14.30,  4500,  "[]",    _TAG_PASSED),
    ("09:32:01.880", "ABCD", "V", 14.31,  3200,  "[]",    _TAG_PASSED),
    ("09:32:02.100", "ABCD", "N", 14.32,  2000,  "[]",    _TAG_PASSED),
    ("09:32:02.320", "ABCD", "Z", 14.33,  5000,  "[]",    _TAG_PASSED),
    ("09:32:02.540", "ABCD", "Q", 14.35,  4200,  "[]",    _TAG_PASSED),
    ("09:32:02.760", "ABCD", "K", 14.36,  3800,  "[]",    _TAG_PASSED),
    ("09:32:02.980", "ABCD", "N", 14.37,  2600,  "[]",    _TAG_PASSED),
    ("09:32:03.200", "ABCD", "P", 14.38,  4800,  "[]",    _TAG_PASSED),
    # Note: after this batch, vol_1m ABCD >> 10x basePerMin -> VOL SPIKE fires

    # ── LMNO bear move building ──────────────────────────────────────────────
    ("09:32:05.001", "LMNO", "N", 36.20,   400,  "[]",    _TAG_PASSED),
    ("09:32:06.330", "LMNO", "Q", 36.10,   600,  "[]",    _TAG_PASSED),
    ("09:32:07.550", "LMNO", "P", 35.95,   900,  "[]",    _TAG_PASSED),
    ("09:32:08.770", "LMNO", "Z", 35.80,  1200,  "[]",    _TAG_PASSED),
    ("09:32:09.990", "LMNO", "N", 35.65,  1500,  "[]",    _TAG_PASSED),
    ("09:32:11.110", "LMNO", "Q", 35.50,  2000,  "[]",    _TAG_PASSED),
    ("09:32:12.330", "LMNO", "K", 35.38,  1800,  "[]",    _TAG_PASSED),
    ("09:32:13.550", "LMNO", "V", 35.25,  2500,  "[]",    _TAG_PASSED),
    # Note: LMNO dropped -2.6% from open $36.20 with $50K+ val -> BEAR ALERT fires

    # ── QRST ISO sweep (Mid cap — large dollar value) ────────────────────────
    ("09:32:15.001", "QRST", "Q", 85.50,  1000,  "[]",    _TAG_PASSED),
    ("09:32:15.220", "QRST", "N", 85.52,   800,  "[]",    _TAG_PASSED),
    ("09:32:15.440", "QRST", "Q", 85.60,  5000,  "['F']", _TAG_ISO),
    ("09:32:15.441", "QRST", "N", 85.65, 8000,   "['F']", _TAG_ISO),
    ("09:32:15.442", "QRST", "P", 85.68, 6000,   "['F']", _TAG_ISO),
    ("09:32:15.443", "QRST", "Z", 85.70, 7500,   "['F']", _TAG_ISO),
    ("09:32:15.444", "QRST", "K", 85.72, 4000,   "['F']", _TAG_ISO),
    ("09:32:15.640", "QRST", "Q", 85.74,  800,   "[]",    _TAG_PASSED),

    # ── EFGH ISO sweep (Small cap) ───────────────────────────────────────────
    ("09:33:01.001", "EFGH", "Q", 42.80,   300,  "[]",    _TAG_PASSED),
    ("09:33:01.220", "EFGH", "N", 42.82,   400,  "[]",    _TAG_PASSED),
    ("09:33:01.440", "EFGH", "Q", 42.90,  2500,  "['F']", _TAG_ISO),
    ("09:33:01.441", "EFGH", "P", 42.92,  3800,  "['F']", _TAG_ISO),
    ("09:33:01.442", "EFGH", "Z", 42.94,  2200,  "['F']", _TAG_ISO),
    ("09:33:01.443", "EFGH", "N", 42.95,  4000,  "['F']", _TAG_ISO),
    ("09:33:01.660", "EFGH", "Q", 42.97,   500,  "[]",    _TAG_PASSED),
    ("09:33:02.001", "EFGH", "K", 42.99,   700,  "[]",    _TAG_PASSED),

    # ── Mix of tickers continuing normal flow ────────────────────────────────
    ("09:33:10.001", "ABCD", "N", 14.40,  2000,  "[]",    _TAG_PASSED),
    ("09:33:10.330", "MNOP", "Q", 28.50,   600,  "[]",    _TAG_PASSED),
    ("09:33:10.660", "UVWX", "P",  7.30,   800,  "[]",    _TAG_PASSED),
    ("09:33:11.001", "QRST", "N", 85.80,   400,  "[]",    _TAG_PASSED),
    ("09:33:11.330", "LMNO", "Z", 35.20,  1000,  "[]",    _TAG_PASSED),
    ("09:33:12.001", "EFGH", "Q", 43.05,   600,  "[]",    _TAG_PASSED),
    ("09:33:12.440", "ABCD", "K", 14.42,  1500,  "[]",    _TAG_PASSED),
    ("09:33:13.001", "MNOP", "V", 28.55,   900,  "[]",    _TAG_PASSED),
    ("09:33:14.330", "QRST", "P", 85.85,   500,  "[]",    _TAG_PASSED),
    ("09:33:15.001", "UVWX", "N",  7.32,  1200,  "[]",    _TAG_PASSED),

    # ── More bad conditions scattered ────────────────────────────────────────
    ("09:33:20.001", "ABCD", "N", 14.42,   300,  "['M']", _TAG_COND_M),
    ("09:33:21.330", "EFGH", "Q", 43.05,   200,  "['M']", _TAG_COND_M),
    ("09:33:22.001", "MNOP", "P", 28.55,   100,  "['Q']", _TAG_COND_Q),

    # ── Large-cap sneak through mid-stream ───────────────────────────────────
    ("09:33:25.001", "AMZN", "Q",185.40, 2000,   "[]",    _TAG_LARGECAP),
    ("09:33:26.440", "META", "N",490.20, 1000,   "[]",    _TAG_LARGECAP),

    # ── Final normal cluster ─────────────────────────────────────────────────
    ("09:34:00.001", "ABCD", "N", 14.45,  1800,  "[]",    _TAG_PASSED),
    ("09:34:00.220", "EFGH", "Q", 43.10,   700,  "[]",    _TAG_PASSED),
    ("09:34:00.440", "MNOP", "P", 28.60,  1100,  "[]",    _TAG_PASSED),
    ("09:34:00.660", "QRST", "Z", 85.90,   600,  "[]",    _TAG_PASSED),
    ("09:34:00.880", "LMNO", "N", 35.15,  2200,  "[]",    _TAG_PASSED),
    ("09:34:01.001", "UVWX", "K",  7.35,  1500,  "[]",    _TAG_PASSED),
    ("09:34:01.220", "ABCD", "Q", 14.46,  2400,  "[]",    _TAG_PASSED),
    ("09:34:01.440", "EFGH", "V", 43.14,   900,  "[]",    _TAG_PASSED),
    ("09:34:01.660", "MNOP", "N", 28.62,  1300,  "[]",    _TAG_PASSED),
    ("09:34:02.001", "QRST", "Q", 85.95,   800,  "[]",    _TAG_PASSED),
]


def build_raw_stream(wb):
    ws = wb.create_sheet("1 · Raw Stream")
    ws.sheet_properties.tabColor = "58A6FF"

    NCOLS = 8
    ws.column_dimensions["A"].width = 15   # Timestamp
    ws.column_dimensions["B"].width = 7    # Symbol
    ws.column_dimensions["C"].width = 8    # Exchange
    ws.column_dimensions["D"].width = 9    # Price
    ws.column_dimensions["E"].width = 10   # Size
    ws.column_dimensions["F"].width = 10   # Conditions
    ws.column_dimensions["G"].width = 11   # $ Val
    ws.column_dimensions["H"].width = 32   # TAG

    # ── Title ────────────────────────────────────────────────────────────────
    section_title(ws, 1, 1,
        "RAW FEED — Alpaca SIP Feed  (120 sample records with tags)",
        span=NCOLS, fg=C_TEAL)

    # ── Legend row ───────────────────────────────────────────────────────────
    ws.row_dimensions[2].height = 14
    blank_row(ws, 2, NCOLS, bg=BG_DARK)

    legend = [
        (_TAG_PASSED,   _tag_color(_TAG_PASSED)),
        (_TAG_ISO,      _tag_color(_TAG_ISO)),
        (_TAG_STALE,    _tag_color(_TAG_STALE)),
        (_TAG_LARGECAP, _tag_color(_TAG_LARGECAP)),
        (_TAG_COND_M,   _tag_color(_TAG_COND_M)),
        (_TAG_DARK,     _tag_color(_TAG_DARK)),
    ]
    section_title(ws, 3, 1, "LEGEND:", span=1, bg=BG_HEADER, fg=C_BLUE)
    # Write legend inline
    lg_row = 3
    # put them in 2 rows of 3
    for idx, (tag, (fg, bg)) in enumerate(legend):
        col_offset = (idx % 3) * 2 + 2   # cols 2,4,6 then 2,4,6
        row_offset = idx // 3
        c = ws.cell(row=lg_row + row_offset, column=col_offset, value=tag)
        c.fill = fill(bg); c.font = font(fg, bold=True, size=9)
        c.alignment = center(); c.border = thin_border()
        ws.merge_cells(start_row=lg_row+row_offset, start_column=col_offset,
                       end_row=lg_row+row_offset, end_column=col_offset+1)

    # Exchange note
    blank_row(ws, 5, NCOLS, bg=BG_DARK)
    ws.row_dimensions[5].height = 8
    style_cell(ws, 6, 1,
        "Exchange D = FINRA ADF (dark pool / off-exchange). "
        "These prints are PASSED today but arrive LATE — actual fill may be minutes old. "
        "Should be filtered to prevent stale vol/price data skewing detection.",
        bg="3A2A0A", fg=C_ORANGE)
    ws.merge_cells(start_row=6, start_column=1, end_row=6, end_column=NCOLS)
    ws.row_dimensions[6].height = 30

    blank_row(ws, 7, NCOLS, bg=BG_DARK)
    ws.row_dimensions[7].height = 6

    # ── Exchange reference ────────────────────────────────────────────────────
    section_title(ws, 8, 1, "EXCHANGE CODES", span=NCOLS, fg=C_BLUE)
    exch_ref = [
        ("N","NYSE"),("Q","NASDAQ"),("P","NYSE Arca"),("Z","Cboe BZX"),
        ("K","Cboe EDGX"),("C","NYSE American"),("V","IEX"),("U","MEMX"),
    ]
    exch_dark = [("D","FINRA ADF — dark pool / off-exchange")]
    for idx, (code, name) in enumerate(exch_ref):
        col = (idx % 4) * 2 + 1
        row = 9 + idx // 4
        style_cell(ws, row, col, code, bg=BG_CARD2, fg=C_TEAL, bold=True, align="center")
        style_cell(ws, row, col+1, name, bg=BG_CARD2, fg=C_DIM)
    style_cell(ws, 11, 1, "D", bg="3A2A0A", fg=C_ORANGE, bold=True, align="center")
    style_cell(ws, 11, 2, "FINRA ADF — dark pool / off-exchange (stale risk)", bg="3A2A0A", fg=C_ORANGE)
    ws.merge_cells(start_row=11, start_column=2, end_row=11, end_column=NCOLS)

    blank_row(ws, 12, NCOLS, bg=BG_DARK)
    ws.row_dimensions[12].height = 6

    # ── Column headers ────────────────────────────────────────────────────────
    HEADER_ROW = 13
    headers = ["Timestamp (ET)", "Sym", "Exch", "Price ($)", "Size", "Conditions", "$ Val", "TAG"]
    write_header_row(ws, HEADER_ROW, headers)

    # ── Data rows ─────────────────────────────────────────────────────────────
    for i, (ts, sym, exch, price, size, conds, tag) in enumerate(_RAW_RECORDS):
        r  = HEADER_ROW + 1 + i
        fg_tag, bg_row = _tag_color(tag)
        dv = price * size

        # Format dollar value
        if dv >= 1_000_000:
            dv_str = f"${dv/1_000_000:.2f}M"
        elif dv >= 1_000:
            dv_str = f"${dv/1_000:.1f}K"
        else:
            dv_str = f"${dv:.0f}"

        exch_fg = C_ORANGE if exch == "D" else C_DIM
        cond_fg = C_YELLOW if "F" in conds else (C_RED if "M" in conds or "Q" in conds else C_DIM)

        style_cell(ws, r, 1, ts,      bg=bg_row, fg=C_DIM)
        style_cell(ws, r, 2, sym,     bg=bg_row, fg=C_BLUE, bold=True)
        style_cell(ws, r, 3, exch,    bg=bg_row, fg=exch_fg, bold=(exch=="D"), align="center")
        style_cell(ws, r, 4, f"${price:.2f}", bg=bg_row, fg=C_TEXT)
        style_cell(ws, r, 5, str(size), bg=bg_row, fg=C_TEXT)
        style_cell(ws, r, 6, conds,   bg=bg_row, fg=cond_fg)
        style_cell(ws, r, 7, dv_str,  bg=bg_row, fg=C_TEXT)
        style_cell(ws, r, 8, tag,     bg=bg_row, fg=fg_tag, bold=True)
        ws.row_dimensions[r].height = 16

    # fix header + top rows heights
    ws.row_dimensions[1].height  = 22
    ws.row_dimensions[3].height  = 18
    ws.row_dimensions[4].height  = 18
    ws.row_dimensions[8].height  = 18
    ws.row_dimensions[9].height  = 18
    ws.row_dimensions[10].height = 18
    ws.row_dimensions[13].height = 20


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — FILTER
# ══════════════════════════════════════════════════════════════════════════════
def build_filter(wb):
    ws = wb.create_sheet("2 · Filter")
    ws.sheet_properties.tabColor = "F85149"

    for col, w in zip("ABCDEFGH", [18,18,18,18,24,24,12,12]):
        ws.column_dimensions[get_column_letter(ord(col)-64)].width = w

    section_title(ws, 1, 1, "DATA FILTER — What gets dropped before any detection runs", span=6, fg=C_RED)
    blank_row(ws, 2, 8)

    # Filter table
    section_title(ws, 3, 1, "FILTER STAGE", span=2, fg=C_BLUE)
    section_title(ws, 3, 3, "RULE", span=2, fg=C_BLUE)
    section_title(ws, 3, 5, "REASON", span=2, fg=C_BLUE)
    section_title(ws, 3, 7, "WHERE", span=2, fg=C_DIM)

    filters = [
        ("1 · Stale tick",       "tick.ts_ms < now − 5 min",
         "Safety net for WS reconnect replays — live ticks arrive in <200ms so this rarely fires in normal flow", "processBatch()"),
        ("2 · Large-cap exclude","symbol ∈ LARGE_CAP_EXCLUDE",
         "AAPL/MSFT/SPY/QQQ etc — too liquid, distort signals", "processBatch()"),
        ("3 · Bad condition M",  "conditions[].includes('M')",
         "MOC auction print — single print distorts volume",     "processBatch()"),
        ("4 · Bad condition Q",  "conditions[].includes('Q')",
         "Official close print — same distortion risk",          "processBatch()"),
        ("5 · Suppressed sym",   "symbol ∈ suppressedSyms",
         "User manually silenced ticker (with optional expiry)", "computeVolumeSummary()"),
        ("6 · Min dollar vol",   "vol_1m < tier.minVolK × 1000",
         "Too little activity for the tier — noise filter",      "computeVolumeSummary()"),
        ("7 · Min price delta",  "|Δ%| < tier.vol.deltaP",
         "Flat price = not a real spike, just illiquid print",   "computeVolumeSummary()"),
    ]
    bgs2 = [BG_CARD, BG_CARD2] * 10
    for i, (stage, rule, reason, where) in enumerate(filters):
        bg = bgs2[i]
        style_cell(ws, 4+i, 1, stage,  bg=bg, fg=C_YELLOW, bold=True)
        style_cell(ws, 4+i, 2, "",     bg=bg)
        ws.merge_cells(start_row=4+i, start_column=1, end_row=4+i, end_column=2)
        style_cell(ws, 4+i, 3, rule,   bg=bg, fg=C_TEAL)
        style_cell(ws, 4+i, 4, "",     bg=bg)
        ws.merge_cells(start_row=4+i, start_column=3, end_row=4+i, end_column=4)
        style_cell(ws, 4+i, 5, reason, bg=bg, fg=C_DIM)
        style_cell(ws, 4+i, 6, "",     bg=bg)
        ws.merge_cells(start_row=4+i, start_column=5, end_row=4+i, end_column=6)
        style_cell(ws, 4+i, 7, where,  bg=bg, fg=C_BLUE)
        style_cell(ws, 4+i, 8, "",     bg=bg)
        ws.merge_cells(start_row=4+i, start_column=7, end_row=4+i, end_column=8)

    blank_row(ws, 11, 8)

    # Flow diagram as text
    section_title(ws, 12, 1, "DATA FLOW (simplified)", span=8, fg=C_TEAL)
    flow = [
        ("Alpaca SIP WebSocket",     "All US equity trades — ~thousands/sec",       C_BLUE,   BG_BLUE),
        ("↓  Bad conditions drop",   "M and Q conditions removed",                  C_RED,    BG_RED),
        ("↓  Large-cap drop",        "Mega caps / ETFs filtered out server + client",C_RED,    BG_RED),
        ("↓  Age cutoff",            "> 5 min old dropped from rolling window",      C_DIM,    BG_CARD2),
        ("↓  Store in symbolData",   "sym → [{x:ts, y:price, sz:size}]  per symbol", C_TEAL,   BG_CARD),
        ("↓  ISO ('F') branching",   "F-condition prints go to sweepAcc, rest normal",C_YELLOW,BG_YELLOW),
        ("     ├─ sweepAcc{}",       "Batch accumulator for ISO prints",             C_YELLOW, BG_YELLOW),
        ("     └─ symbolData[]",     "All passing ticks stored for vol/move calc",   C_TEAL,   BG_CARD),
    ]
    for i, (step, desc, fg, bg) in enumerate(flow):
        style_cell(ws, 13+i, 1, step, bg=bg, fg=fg, bold=True)
        ws.merge_cells(start_row=13+i, start_column=1, end_row=13+i, end_column=3)
        style_cell(ws, 13+i, 4, desc, bg=bg, fg=C_DIM)
        ws.merge_cells(start_row=13+i, start_column=4, end_row=13+i, end_column=8)

    for r in range(1, 25):
        ws.row_dimensions[r].height = 20


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — VOL SPIKE
# ══════════════════════════════════════════════════════════════════════════════
def build_vol_spike(wb):
    ws = wb.create_sheet("3 · Vol Spike")
    ws.sheet_properties.tabColor = "E86060"

    for col, w in zip("ABCDEFGHIJ", [12,10,12,12,12,12,12,12,18,20]):
        ws.column_dimensions[get_column_letter(ord(col)-64)].width = w

    section_title(ws, 1, 1, "VOL SPIKE DETECTION — computeVolumeSummary() · runs every bar update", span=10, fg=C_NANO)
    blank_row(ws, 2, 10)

    # Algorithm steps
    section_title(ws, 3, 1, "ALGORITHM", span=10, fg=C_BLUE)
    algo = [
        ("Step 1", "Window split",  "1-min window = last 60s ticks   |   4-min baseline = 60–300s ago"),
        ("Step 2", "Min vol check", "vol_1m = Σ(price × size) for last 1 min. If < tier.minVolK × 1000 → skip"),
        ("Step 3", "Delta % check", "If |last_price − first_price_1m| / first_price < tier.deltaP% → skip"),
        ("Step 4", "Baseline calc", "basePerMin = vol_4m / 4  (avg $/min over prior 4 mins)"),
        ("Step 5a","Spike detect",  "If basePerMin > 0:  spike_ratio = vol_1m / basePerMin. If ≥ tier.spike → SPIKE"),
        ("Step 5b","New Activity",  "If basePerMin = 0 (no prior data):  → NEW ACTIVITY (spike ratio shown as ∞)"),
        ("Step 6", "TTL cache",     "First detection → stored in volSpikeCache with firstTs. Expires after 5 min"),
        ("Step 7", "Stale rows",    "After TTL expires from active, still shown as dimmed 'stale' until 5-min hard cap"),
    ]
    bgs3 = [BG_CARD, BG_CARD2] * 6
    for i, (step, label, desc) in enumerate(algo):
        bg = bgs3[i]
        style_cell(ws, 4+i, 1, step,  bg=bg, fg=C_YELLOW, bold=True, align="center")
        style_cell(ws, 4+i, 2, label, bg=bg, fg=C_TEAL, bold=True)
        ws.merge_cells(start_row=4+i, start_column=2, end_row=4+i, end_column=2)
        style_cell(ws, 4+i, 3, desc,  bg=bg, fg=C_TEXT)
        ws.merge_cells(start_row=4+i, start_column=3, end_row=4+i, end_column=10)

    blank_row(ws, 12, 10)

    # Tier thresholds table
    section_title(ws, 13, 1, "TIER THRESHOLDS (default values — all editable in Control Panel)", span=10, fg=C_BLUE)
    hdrs = ["Tier", "Market Cap", "Spike ×", "Min $/min", "Min Delta%", "Flash $/min", "Color"]
    write_header_row(ws, 14, hdrs)
    tiers = [
        ("Nano",  "< $50M",   "10×", "$10K",  "8%",  "$100K",  "🔴", C_NANO,   BG_CARD),
        ("Small", "< $300M",  "8×",  "$40K",  "5%",  "$1.0M",  "🟠", C_SMALL,  BG_CARD2),
        ("Mid",   "< $2B",    "5×",  "$100K", "3%",  "$2.0M",  "🔵", C_MID,    BG_CARD),
        ("Big",   "< $100B",  "7×",  "$1M",   "2%",  "$10.0M", "🟣", C_BIG,    BG_CARD2),
        ("Other", "Unknown",  "10×", "$10K",  "3%",  "$1.0M",  "⚫", C_DIM,    BG_CARD),
    ]
    for i, (name, cap, spike, minv, delt, flash, col, fg, bg) in enumerate(tiers):
        vals = [name, cap, spike, minv, delt, flash, col]
        fgs2 = [fg, C_TEXT, C_YELLOW, C_TEXT, C_TEXT, C_GREEN, fg]
        for j, (v, f) in enumerate(zip(vals, fgs2)):
            style_cell(ws, 15+i, 1+j, v, bg=bg, fg=f, bold=(j==0))

    blank_row(ws, 20, 10)

    # Sample calculation
    section_title(ws, 21, 1, "SAMPLE CALCULATION — ABCD (Small tier, $200M cap)", span=10, fg=C_SMALL)
    hdrs2 = ["Parameter", "Value", "Calc / Note"]
    write_header_row(ws, 22, hdrs2[:3])
    for j in range(3, 11):
        style_cell(ws, 22, 1+j, "", bg=BG_HEADER)

    calc = [
        ("Tier",               "Small",       "Market cap $200M → < $300M boundary"),
        ("Spike threshold",    "8×",          "tier.vol.spike = 8"),
        ("Min vol",            "$40,000/min", "tier.vol.minVolK = 40 → 40 × 1000"),
        ("Min delta %",        "5%",          "tier.vol.deltaP = 5"),
        ("vol_1m",             "$320,000",    "Last 60s: 8000 trades × avg $40 price × avg 100 shares → example"),
        ("vol_4m (prior)",     "$160,000",    "60–300s ago: lower activity"),
        ("basePerMin",         "$40,000",     "160,000 / 4 = $40,000 / min"),
        ("spike_ratio",        "8.0×",        "320,000 / 40,000 = 8.0"),
        ("≥ threshold?",       "YES (8× ≥ 8×)","→ SPIKE DETECTED"),
        ("Delta % check",      "+6.2%",       "Price moved 6.2% in 1 min → ≥ 5% threshold ✓"),
    ]
    calc_bgs = [BG_CARD, BG_CARD2] * 8
    for i, (param, val, note) in enumerate(calc):
        bg = calc_bgs[i]
        is_result = i == 8
        style_cell(ws, 23+i, 1, param, bg=bg, fg=C_DIM)
        style_cell(ws, 23+i, 2, val,   bg=bg, fg=(C_TEAL if is_result else C_TEXT), bold=is_result)
        style_cell(ws, 23+i, 3, note,  bg=bg, fg=(C_GREEN if is_result else C_DIM))
        ws.merge_cells(start_row=23+i, start_column=3, end_row=23+i, end_column=10)

    for r in range(1, 35):
        ws.row_dimensions[r].height = 20


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SWEEP
# ══════════════════════════════════════════════════════════════════════════════
def build_sweep(wb):
    ws = wb.create_sheet("4 · Sweep")
    ws.sheet_properties.tabColor = "E3B341"

    for col, w in zip("ABCDEFGHIJ", [14,12,14,14,12,12,12,14,18,20]):
        ws.column_dimensions[get_column_letter(ord(col)-64)].width = w

    section_title(ws, 1, 1, "SWEEP DETECTION — ISO condition 'F' (Intermarket Sweep Order)", span=10, fg=C_YELLOW)
    blank_row(ws, 2, 10)

    # What is a sweep
    section_title(ws, 3, 1, "WHAT IS AN ISO SWEEP?", span=10, fg=C_BLUE)
    style_cell(ws, 4, 1,
        "An Intermarket Sweep Order (condition code 'F') is a special order type that allows a market participant to "
        "simultaneously hit multiple price levels across multiple exchanges without waiting for NBBO protection. "
        "It signals institutional urgency — someone is willing to pay up or sell down to fill a large position fast.",
        bg=BG_CARD2, fg=C_DIM)
    ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=10)
    ws.row_dimensions[4].height = 40

    blank_row(ws, 5, 10)

    # Detection algorithm
    section_title(ws, 6, 1, "DETECTION ALGORITHM", span=10, fg=C_BLUE)
    algo = [
        ("Step 1", "Tick arrives",    "processBatch() checks if 'F' ∈ conditions[]"),
        ("Step 2", "Non-F track",     "Every non-ISO tick updates lastNonFPrice[sym] = price (clean reference)"),
        ("Step 3", "F-tick: accum",   "ISO tick → sweepAcc[sym].val += price × size  |  prices[] and sizes[] appended"),
        ("Step 4", "Batch ends",      "After all ticks in batch processed → sweepDirection() called per sym"),
        ("Step 5", "Threshold check", "dollar_val compared to tier threshold (direct / voice)  → if below direct → dropped"),
        ("Step 6", "Panel + history", "Passes → pushed to sweepAlerts[] panel  AND  logged to history via /log/alert"),
    ]
    for i, (step, label, desc) in enumerate(algo):
        bg = [BG_CARD, BG_CARD2][i % 2]
        style_cell(ws, 7+i, 1, step,  bg=bg, fg=C_YELLOW, bold=True, align="center")
        style_cell(ws, 7+i, 2, label, bg=bg, fg=C_TEAL, bold=True)
        style_cell(ws, 7+i, 3, desc,  bg=bg, fg=C_TEXT)
        ws.merge_cells(start_row=7+i, start_column=3, end_row=7+i, end_column=10)

    blank_row(ws, 13, 10)

    # Confidence scoring
    section_title(ws, 14, 1, "CONFIDENCE SCORING — sweepDirection(acc)", span=10, fg=C_YELLOW)
    style_cell(ws, 15, 1,
        "3 signals voted together with weights → direction (bull/bear/neutral).  "
        "4 components score → confidence 0–99.",
        bg=BG_CARD2, fg=C_DIM)
    ws.merge_cells(start_row=15, start_column=1, end_row=15, end_column=10)

    blank_row(ws, 16, 10)
    section_title(ws, 17, 1, "SIGNAL", span=2, fg=C_BLUE)
    section_title(ws, 17, 3, "HOW CALCULATED", span=4, fg=C_BLUE)
    section_title(ws, 17, 7, "WEIGHT", span=2, fg=C_BLUE)
    section_title(ws, 17, 9, "BULL CONDITION", span=2, fg=C_GREEN)

    sigs = [
        ("Signal 1\n(Primary)",
         "Intra-sweep price trend",
         "intraMove = (lastPrice − firstPrice) / firstPrice\nBull if > +0.05%  |  Bear if < −0.05%",
         "45%",
         "Price went UP during the sweep"),
        ("Signal 2\n(Secondary)",
         "Sweep VWAP vs pre-sweep price",
         "vwap = Σ(price×size)/Σ(size)\nvsRef = (vwap − prePrice) / prePrice\nBull if > +0.1%  |  Bear if < −0.1%",
         "35%",
         "Sweep avg price ABOVE last clean price"),
        ("Signal 3\n(Tertiary)",
         "Tick-by-tick consistency",
         "Count upTicks (price[i] > price[i-1]) vs downTicks\nBull if upTicks > downTicks",
         "20%",
         "More ticks moving UP than DOWN"),
    ]
    for i, (sig, name, calc, wt, bull_cond) in enumerate(sigs):
        bg = [BG_CARD, BG_CARD2][i % 2]
        style_cell(ws, 18+i, 1, sig,       bg=bg, fg=C_YELLOW, bold=True, align="center")
        ws.merge_cells(start_row=18+i, start_column=1, end_row=18+i, end_column=2)
        style_cell(ws, 18+i, 3, name,      bg=bg, fg=C_TEAL, bold=True)
        style_cell(ws, 18+i, 4, calc,      bg=bg, fg=C_DIM)
        ws.merge_cells(start_row=18+i, start_column=3, end_row=18+i, end_column=6)
        style_cell(ws, 18+i, 7, wt,        bg=bg, fg=C_ORANGE, bold=True, align="center")
        ws.merge_cells(start_row=18+i, start_column=7, end_row=18+i, end_column=8)
        style_cell(ws, 18+i, 9, bull_cond, bg=bg, fg=C_GREEN)
        ws.merge_cells(start_row=18+i, start_column=9, end_row=18+i, end_column=10)
        ws.row_dimensions[18+i].height = 36

    blank_row(ws, 21, 10)

    # Vote + direction
    section_title(ws, 22, 1, "DIRECTION VOTE (weighted sum of signals)", span=5, fg=C_BLUE)
    section_title(ws, 22, 6, "RESULT", span=5, fg=C_BLUE)
    votes = [
        ("vote = sig1×0.45 + sig2×0.35 + sig3×0.20", "vote > +0.10  →  BULL  🟢", C_GREEN),
        ("Range: −1.0 to +1.0  (all signals aligned = max)", "vote < −0.10  →  BEAR  🔴", C_RED),
        ("Neutral zone: −0.10 to +0.10", "otherwise   →  NEUTRAL  ⚪", C_DIM),
    ]
    for i, (formula, result, fg) in enumerate(votes):
        bg = [BG_CARD, BG_CARD2][i % 2]
        style_cell(ws, 23+i, 1, formula, bg=bg, fg=C_TEXT)
        ws.merge_cells(start_row=23+i, start_column=1, end_row=23+i, end_column=5)
        style_cell(ws, 23+i, 6, result, bg=bg, fg=fg, bold=True)
        ws.merge_cells(start_row=23+i, start_column=6, end_row=23+i, end_column=10)

    blank_row(ws, 26, 10)

    # Confidence components
    section_title(ws, 27, 1, "CONFIDENCE COMPONENTS (0–99 total)", span=10, fg=C_YELLOW)
    section_title(ws, 28, 1, "Component", span=2, fg=C_BLUE)
    section_title(ws, 28, 3, "Formula", span=5, fg=C_BLUE)
    section_title(ws, 28, 8, "Max Pts", span=1, fg=C_BLUE)
    section_title(ws, 28, 9, "What drives it", span=2, fg=C_BLUE)
    comps = [
        ("A · Move strength",
         "min(|intraMove| / 0.003, 1) × 35",
         "35",
         "0.3% price move during sweep fills bucket"),
        ("B · Signal agreement",
         "|vote| × 30",
         "30",
         "All 3 signals pointing same direction = full 30"),
        ("C · Tick count",
         "min(n / 5, 1) × 20",
         "20",
         "≥ 5 ISO prints in sweep = full 20"),
        ("D · Tick consistency",
         "max(upTicks, downTicks) / moveTicks × 14",
         "14",
         "All ticks moving same way = full 14"),
        ("TOTAL", "A + B + C + D  (capped at 99)", "99", ""),
    ]
    for i, (comp, formula, pts, note) in enumerate(comps):
        bg = BG_CARD if i % 2 == 0 else BG_CARD2
        is_total = i == 4
        style_cell(ws, 29+i, 1, comp, bg=bg, fg=(C_TEAL if not is_total else C_YELLOW), bold=is_total)
        ws.merge_cells(start_row=29+i, start_column=1, end_row=29+i, end_column=2)
        style_cell(ws, 29+i, 3, formula, bg=bg, fg=C_TEXT)
        ws.merge_cells(start_row=29+i, start_column=3, end_row=29+i, end_column=7)
        style_cell(ws, 29+i, 8, pts, bg=bg, fg=C_ORANGE, bold=True, align="center")
        style_cell(ws, 29+i, 9, note, bg=bg, fg=C_DIM)
        ws.merge_cells(start_row=29+i, start_column=9, end_row=29+i, end_column=10)

    blank_row(ws, 34, 10)

    # Confidence colour coding
    section_title(ws, 35, 1, "CONFIDENCE COLOUR CODING (dashboard display)", span=10, fg=C_BLUE)
    cc = [
        ("> 70%  BULL",  "Dollar value shown in GREEN",  C_GREEN,  BG_GREEN),
        ("> 70%  BEAR",  "Dollar value shown in RED",    C_RED,    BG_RED),
        ("≤ 70%",        "Dollar value shown in GREY",   C_DIM,    BG_CARD2),
    ]
    for i, (cond, what, fg, bg) in enumerate(cc):
        style_cell(ws, 36+i, 1, cond, bg=bg, fg=fg, bold=True)
        ws.merge_cells(start_row=36+i, start_column=1, end_row=36+i, end_column=3)
        style_cell(ws, 36+i, 4, what, bg=bg, fg=fg)
        ws.merge_cells(start_row=36+i, start_column=4, end_row=36+i, end_column=10)

    blank_row(ws, 39, 10)

    # Sweep tier thresholds
    section_title(ws, 40, 1, "SWEEP THRESHOLDS (default — editable in Control Panel)", span=10, fg=C_BLUE)
    write_header_row(ws, 41, ["Tier", "Direct ($K)", "Voice ($K)", "Notes"])
    thresh = [
        ("Nano",    "$10K",  "$50K",  "ISO print ≥ $10K logged to history. ≥ $50K triggers voice alert"),
        ("Small",   "$25K",  "$100K", ""),
        ("Mid",     "$75K",  "$250K", ""),
        ("Big",     "$150K", "$500K", ""),
        ("Unknown", "$10K",  "$50K",  "Same as Nano — plays it safe"),
    ]
    for i, (tier, direct, voice, note) in enumerate(thresh):
        bg = [BG_CARD, BG_CARD2][i % 2]
        style_cell(ws, 42+i, 1, tier,   bg=bg, fg=C_YELLOW, bold=True)
        style_cell(ws, 42+i, 2, direct, bg=bg, fg=C_GREEN)
        style_cell(ws, 42+i, 3, voice,  bg=bg, fg=C_TEAL)
        style_cell(ws, 42+i, 4, note,   bg=bg, fg=C_DIM)
        ws.merge_cells(start_row=42+i, start_column=4, end_row=42+i, end_column=10)

    # Blackout times
    blank_row(ws, 47, 10)
    section_title(ws, 48, 1, "BLACKOUT TIMES (sweeps suppressed — open/close noise)", span=10, fg=C_RED)
    style_cell(ws, 49, 1,
        "9:30 · 9:31 · 9:32  (market open — first 3 min)    |    15:58 · 15:59 · 16:00  (market close — last 2 min)",
        bg=BG_RED, fg=C_RED, bold=True)
    ws.merge_cells(start_row=49, start_column=1, end_row=49, end_column=10)

    for r in range(1, 55):
        ws.row_dimensions[r].height = 20
    ws.row_dimensions[4].height = 42
    for r in [18, 19, 20]:
        ws.row_dimensions[r].height = 38


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — MOVE %
# ══════════════════════════════════════════════════════════════════════════════
def build_move_pct(wb):
    ws = wb.create_sheet("5 · Move %")
    ws.sheet_properties.tabColor = "3FB950"

    for col, w in zip("ABCDEFGHIJ", [14,12,14,14,12,14,12,12,16,18]):
        ws.column_dimensions[get_column_letter(ord(col)-64)].width = w

    section_title(ws, 1, 1, "MOVE % DETECTION — Bull & Bear Alerts · renderSummary()", span=10, fg=C_GREEN)
    blank_row(ws, 2, 10)

    # Algorithm
    section_title(ws, 3, 1, "ALGORITHM", span=10, fg=C_BLUE)
    algo = [
        ("Step 1", "Input",            "rows[] from server — each row is the latest 1-min aggregate for a symbol"),
        ("Step 2", "Qualify",          "Filter rows by 3 per-tier thresholds: delta%, valK, trades (see table below)"),
        ("Step 3", "Suppression",      "Skip symbols in suppressedSyms (user-muted)"),
        ("Step 4", "alertHistory",     "Qualified rows stored in alertHistory Map: sym → {row, firstTs, lastTs}"),
        ("Step 5", "First alert",      "New entry: auto-select chart if nothing pinned. Log to /log/alert with tag='new'"),
        ("Step 6", "Escalation",       "Existing: re-log if newDelta ≥ 1.5× prevDelta AND ≥ 2× tier.delta threshold"),
        ("Step 7", "5-min hard TTL",   "Entries expire exactly 5 min after FIRST appearance (not last update)"),
        ("Step 8", "Stale display",    "Entries ≥ 4 min old shown with reduced opacity ('stale' class)"),
        ("Step 9", "Sort & display",   "Split into bulls/bears. Sort by |Δ%| descending. Unified panel: bulls then bears"),
    ]
    for i, (step, label, desc) in enumerate(algo):
        bg = [BG_CARD, BG_CARD2][i % 2]
        style_cell(ws, 4+i, 1, step,  bg=bg, fg=C_YELLOW, bold=True, align="center")
        style_cell(ws, 4+i, 2, label, bg=bg, fg=C_TEAL, bold=True)
        style_cell(ws, 4+i, 3, desc,  bg=bg, fg=C_TEXT)
        ws.merge_cells(start_row=4+i, start_column=3, end_row=4+i, end_column=10)

    blank_row(ws, 13, 10)

    # Qualification thresholds per tier
    section_title(ws, 14, 1, "QUALIFICATION THRESHOLDS — must pass ALL 3 per direction", span=10, fg=C_BLUE)
    hdrs = ["Tier", "Direction", "Min Δ%", "Min $ Val", "Min Trades", "Flash at $", "Notes"]
    write_header_row(ws, 15, hdrs)
    trows = [
        ("Nano",  "Bull", "4%",  "$20K",  "1",  "$50K",   C_GREEN, BG_CARD,  C_NANO),
        ("Nano",  "Bear", "6%",  "$20K",  "2",  "$50K",   C_RED,   BG_CARD2, C_NANO),
        ("Small", "Bull", "3%",  "$50K",  "1",  "$500K",  C_GREEN, BG_CARD,  C_SMALL),
        ("Small", "Bear", "4%",  "$50K",  "3",  "$100K",  C_RED,   BG_CARD2, C_SMALL),
        ("Mid",   "Bull", "2%",  "$1M",   "1",  "$1.0M",  C_GREEN, BG_CARD,  C_MID),
        ("Mid",   "Bear", "3%",  "$100K", "3",  "$250K",  C_RED,   BG_CARD2, C_MID),
        ("Big",   "Bull", "1%",  "$2M",   "1",  "$500K",  C_GREEN, BG_CARD,  C_BIG),
        ("Big",   "Bear", "2%",  "$1M",   "5",  "$500K",  C_RED,   BG_CARD2, C_BIG),
        ("Other", "Both", "3%",  "$100K", "3",  "$200K",  C_DIM,   BG_CARD,  C_DIM),
    ]
    for i, row in enumerate(trows):
        tier, direc, delt, val, tr, flash, dir_fg, bg, tier_fg = row
        note = "Bear harder to qualify intentionally (bearish moves noisier)"
        style_cell(ws, 16+i, 1, tier,  bg=bg, fg=tier_fg, bold=True)
        style_cell(ws, 16+i, 2, direc, bg=bg, fg=dir_fg,  bold=True)
        style_cell(ws, 16+i, 3, delt,  bg=bg, fg=C_YELLOW)
        style_cell(ws, 16+i, 4, val,   bg=bg, fg=C_TEXT)
        style_cell(ws, 16+i, 5, tr,    bg=bg, fg=C_TEXT)
        style_cell(ws, 16+i, 6, flash, bg=bg, fg=C_TEAL)
        style_cell(ws, 16+i, 7, "⚡ gold highlight if met" if direc != "Both" else "—",
                   bg=bg, fg=C_YELLOW)
        ws.merge_cells(start_row=16+i, start_column=7, end_row=16+i, end_column=10)

    blank_row(ws, 25, 10)

    # Display fields
    section_title(ws, 26, 1, "WHAT'S SHOWN IN THE MOVES PANEL", span=10, fg=C_BLUE)
    fields = [
        ("Symbol",       "Ticker — click to filter all columns"),
        ("Δ%",           "Delta from 1-min open to latest price"),
        ("$ Val",        "Dollar value of last 1-min window (price × shares)"),
        ("VWAP 1m",      "Volume-weighted avg price of the last 1 minute"),
        ("vs VWAP 2m",   "Comparison to 2-min VWAP — shows momentum direction"),
        ("Trade count",  "Number of individual prints in the last 1 min"),
        ("Age",          "Time since first alert for this ticker (up to 5 min)"),
        ("Color",        "Green row = bull  |  Red row = bear  |  Dimmed = stale (≥ 4 min)"),
        ("⚡ Flash",      "Gold highlight when dollar value exceeds tier flashM threshold"),
        ("🔥 Badge",     "Symbol was in yesterday's top 50 by dollar volume"),
    ]
    for i, (f, desc) in enumerate(fields):
        bg = [BG_CARD, BG_CARD2][i % 2]
        style_cell(ws, 27+i, 1, f,    bg=bg, fg=C_TEAL, bold=True)
        ws.merge_cells(start_row=27+i, start_column=1, end_row=27+i, end_column=2)
        style_cell(ws, 27+i, 3, desc, bg=bg, fg=C_DIM)
        ws.merge_cells(start_row=27+i, start_column=3, end_row=27+i, end_column=10)

    for r in range(1, 40):
        ws.row_dimensions[r].height = 20


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — CONTROL PANEL
# ══════════════════════════════════════════════════════════════════════════════
def build_control_panel(wb):
    ws = wb.create_sheet("6 · Control Panel")
    ws.sheet_properties.tabColor = "BC8CFF"

    for col, w in zip("ABCDEFGHIJKL", [16,12,12,12,12,12,12,12,12,12,12,18]):
        ws.column_dimensions[get_column_letter(ord(col)-64)].width = w

    section_title(ws, 1, 1, "CONTROL PANEL — All user-tunable parameters (stored in localStorage)", span=12, fg=C_PURPLE)
    blank_row(ws, 2, 12)

    # Stock classification boundaries
    section_title(ws, 3, 1, "STOCK CLASSIFICATION BOUNDARIES — tierConfig.maxCapM", span=12, fg=C_BLUE)
    style_cell(ws, 4, 1,
        "Market cap in $M. Each tier matches stocks UP TO its maxCapM. "
        "Stock with no market cap data → 'Other'. Large caps excluded entirely.",
        bg=BG_CARD2, fg=C_DIM)
    ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=12)

    write_header_row(ws, 5, ["Tier", "Label", "Default Max Cap", "Color", "Used in all 3 detectors"])
    bounds = [
        ("nano",  "Nano",  "< $50M",    "🔴 Red",    "Yes — lowest threshold sensitivity", C_NANO,  BG_CARD),
        ("small", "Small", "< $300M",   "🟠 Orange",  "Yes",                                C_SMALL, BG_CARD2),
        ("mid",   "Mid",   "< $2,000M", "🔵 Blue",    "Yes",                                C_MID,   BG_CARD),
        ("big",   "Big",   "< $100,000M","🟣 Purple", "Yes",                                C_BIG,   BG_CARD2),
        ("other", "Other", "No cap data","⚫ Grey",   "Yes — fallback for unknown caps",     C_DIM,   BG_CARD),
    ]
    for i, (key, label, cap, color, note, fg, bg) in enumerate(bounds):
        style_cell(ws, 6+i, 1, key,   bg=bg, fg=fg, bold=True)
        style_cell(ws, 6+i, 2, label, bg=bg, fg=fg)
        style_cell(ws, 6+i, 3, cap,   bg=bg, fg=C_YELLOW)
        style_cell(ws, 6+i, 4, color, bg=bg, fg=fg)
        style_cell(ws, 6+i, 5, note,  bg=bg, fg=C_DIM)
        ws.merge_cells(start_row=6+i, start_column=5, end_row=6+i, end_column=12)

    blank_row(ws, 11, 12)

    # Vol spike controls
    section_title(ws, 12, 1, "VOL SPIKE CONTROLS — tierConfig[tier].vol", span=12, fg=C_NANO)
    write_header_row(ws, 13, ["Tier", "spike ×", "minVolK ($K)", "deltaP (%)", "flashM ($M)", "", "", "", "", "", "", "What it does"])
    vc = [
        ("nano",  "10×", "$10K", "8%",  "$0.10M", BG_CARD,  C_NANO),
        ("small", "8×",  "$40K", "5%",  "$1.0M",  BG_CARD2, C_SMALL),
        ("mid",   "5×",  "$100K","3%",  "$2.0M",  BG_CARD,  C_MID),
        ("big",   "7×",  "$1M",  "2%",  "$10.0M", BG_CARD2, C_BIG),
        ("other", "10×", "$10K", "3%",  "$1.0M",  BG_CARD,  C_DIM),
    ]
    descs = [
        "spike= how many × baseline to qualify  |  minVolK= min $/min (noise filter)  |  deltaP= min price move %  |  flashM= gold ⚡ threshold",
        "", "", "", ""
    ]
    for i, (tier, spike, minv, delt, flash, bg, fg) in enumerate(vc):
        style_cell(ws, 14+i, 1,  tier,  bg=bg, fg=fg, bold=True)
        style_cell(ws, 14+i, 2,  spike, bg=bg, fg=C_YELLOW)
        style_cell(ws, 14+i, 3,  minv,  bg=bg, fg=C_TEXT)
        style_cell(ws, 14+i, 4,  delt,  bg=bg, fg=C_TEXT)
        style_cell(ws, 14+i, 5,  flash, bg=bg, fg=C_TEAL)
        style_cell(ws, 14+i, 12, descs[i] if i == 0 else "", bg=bg, fg=C_DIM)
        for col in range(6, 12):
            style_cell(ws, 14+i, col, "", bg=bg)
        ws.merge_cells(start_row=14+i, start_column=12, end_row=14+i, end_column=12)

    blank_row(ws, 19, 12)

    # Bull move controls
    section_title(ws, 20, 1, "BULL MOVE CONTROLS — tierConfig[tier].bull", span=12, fg=C_GREEN)
    write_header_row(ws, 21, ["Tier", "delta (%)", "valK ($K)", "trades", "flashM ($M)", "", "", "", "", "", "", "Notes"])
    bmc = [
        ("nano",  "4%", "$20K",  "1", "$0.05M", BG_CARD,  C_NANO),
        ("small", "3%", "$50K",  "1", "$0.5M",  BG_CARD2, C_SMALL),
        ("mid",   "2%", "$1M",   "1", "$1.0M",  BG_CARD,  C_MID),
        ("big",   "1%", "$2M",   "1", "$0.5M",  BG_CARD2, C_BIG),
        ("other", "3%", "$100K", "3", "$0.2M",  BG_CARD,  C_DIM),
    ]
    for i, (tier, delt, val, tr, flash, bg, fg) in enumerate(bmc):
        style_cell(ws, 22+i, 1,  tier,  bg=bg, fg=fg, bold=True)
        style_cell(ws, 22+i, 2,  delt,  bg=bg, fg=C_GREEN)
        style_cell(ws, 22+i, 3,  val,   bg=bg, fg=C_TEXT)
        style_cell(ws, 22+i, 4,  tr,    bg=bg, fg=C_TEXT)
        style_cell(ws, 22+i, 5,  flash, bg=bg, fg=C_TEAL)
        note = "Big caps need only 1% move but $2M+ val — high quality filter" if tier == "big" else ""
        style_cell(ws, 22+i, 12, note, bg=bg, fg=C_DIM)
        for col in range(6, 12):
            style_cell(ws, 22+i, col, "", bg=bg)

    blank_row(ws, 27, 12)

    # Bear move controls
    section_title(ws, 28, 1, "BEAR MOVE CONTROLS — tierConfig[tier].bear", span=12, fg=C_RED)
    write_header_row(ws, 29, ["Tier", "delta (%)", "valK ($K)", "trades", "flashM ($M)", "", "", "", "", "", "", "Notes"])
    bemc = [
        ("nano",  "6%", "$20K",  "2", "$0.05M", BG_CARD,  C_NANO,  "Bear harder — 6% vs 4% bull (prevents noise)"),
        ("small", "4%", "$50K",  "3", "$0.1M",  BG_CARD2, C_SMALL, "min 3 trades filter — bearish can be one big print"),
        ("mid",   "3%", "$100K", "3", "$0.25M", BG_CARD,  C_MID,   ""),
        ("big",   "2%", "$1M",   "5", "$0.5M",  BG_CARD2, C_BIG,   "5 trades required — big caps rarely drop on 1 print"),
        ("other", "3%", "$10K",  "3", "$0.2M",  BG_CARD,  C_DIM,   ""),
    ]
    for i, (tier, delt, val, tr, flash, bg, fg, note) in enumerate(bemc):
        style_cell(ws, 30+i, 1,  tier,  bg=bg, fg=fg, bold=True)
        style_cell(ws, 30+i, 2,  delt,  bg=bg, fg=C_RED)
        style_cell(ws, 30+i, 3,  val,   bg=bg, fg=C_TEXT)
        style_cell(ws, 30+i, 4,  tr,    bg=bg, fg=C_TEXT)
        style_cell(ws, 30+i, 5,  flash, bg=bg, fg=C_TEAL)
        style_cell(ws, 30+i, 12, note,  bg=bg, fg=C_DIM)
        for col in range(6, 12):
            style_cell(ws, 30+i, col, "", bg=bg)

    blank_row(ws, 35, 12)

    # Sweep controls
    section_title(ws, 36, 1, "SWEEP CONTROLS — sweepConfig", span=12, fg=C_YELLOW)
    write_header_row(ws, 37, ["Tier", "Direct ($K)", "Voice ($K)", "", "", "", "", "", "", "", "", "Notes"])
    sc = [
        ("nano",    "$10K",  "$50K",  BG_CARD,  C_NANO,  "ISO ≥ $10K → logged to history. ≥ $50K → voice announced"),
        ("small",   "$25K",  "$100K", BG_CARD2, C_SMALL, ""),
        ("mid",     "$75K",  "$250K", BG_CARD,  C_MID,   ""),
        ("big",     "$150K", "$500K", BG_CARD2, C_BIG,   ""),
        ("unknown", "$10K",  "$50K",  BG_CARD,  C_DIM,   "Fallback — same as nano"),
    ]
    for i, (tier, direct, voice, bg, fg, note) in enumerate(sc):
        style_cell(ws, 38+i, 1,  tier,   bg=bg, fg=fg, bold=True)
        style_cell(ws, 38+i, 2,  direct, bg=bg, fg=C_GREEN)
        style_cell(ws, 38+i, 3,  voice,  bg=bg, fg=C_TEAL)
        style_cell(ws, 38+i, 12, note,   bg=bg, fg=C_DIM)
        for col in range(4, 12):
            style_cell(ws, 38+i, col, "", bg=bg)

    blank_row(ws, 43, 12)

    # Persistence & other
    section_title(ws, 44, 1, "PERSISTENCE & OTHER SETTINGS", span=12, fg=C_BLUE)
    other = [
        ("Storage",        "localStorage  (browser)  —  survives page refresh, lost on browser clear"),
        ("Key: tierConfig2", "All tier classification + bull/bear/vol thresholds"),
        ("Key: sweepConfig", "Sweep enabled, voice, blackout times, per-tier $ thresholds"),
        ("Reset button",   "Restores DEFAULT_TIER_CONFIG and DEFAULT_SWEEP_CONFIG, clears localStorage"),
        ("Speak cooldown", "Minimum 120s between voice alerts for same ticker (SPEAK_COOLDOWN)"),
        ("ALERT_TTL",      "5 minutes — hard cap on alertHistory and volSpikeCache entries"),
        ("WIN_1M",         "60s — rolling window for vol spike and move % detection"),
        ("WIN_5M",         "300s — rolling window for symbolData tick storage"),
    ]
    for i, (key, val) in enumerate(other):
        bg = [BG_CARD, BG_CARD2][i % 2]
        style_cell(ws, 45+i, 1, key, bg=bg, fg=C_TEAL, bold=True)
        ws.merge_cells(start_row=45+i, start_column=1, end_row=45+i, end_column=3)
        style_cell(ws, 45+i, 4, val, bg=bg, fg=C_DIM)
        ws.merge_cells(start_row=45+i, start_column=4, end_row=45+i, end_column=12)

    for r in range(1, 56):
        ws.row_dimensions[r].height = 20
    ws.row_dimensions[4].height = 30


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    wb = Workbook()
    wb.remove(wb.active)   # remove default sheet

    build_raw_stream(wb)
    build_filter(wb)
    build_vol_spike(wb)
    build_sweep(wb)
    build_move_pct(wb)
    build_control_panel(wb)

    out = r"C:\Users\ibrah\OneDrive\Documents\The100xTrade\cluade\alpaca-stream\dashboard_logic_docs.xlsx"
    wb.save(out)
    print(f"Saved: {out}")

if __name__ == "__main__":
    main()
