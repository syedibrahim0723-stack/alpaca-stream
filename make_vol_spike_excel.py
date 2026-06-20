"""
Build vol_spike_example.xlsx  — 4 sheets:
  1. Vol Spike   — how vol spike is detected
  2. Move Logic  — how bull/bear move alerts fire
  3. Sweep Logic — sweep confidence model + strategy trigger
  4. Raw Data    — real rows from alerts.db
"""
import sqlite3
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

wb = Workbook()

# ─────────────────────────────────────────────────────────────────────────────
# STYLE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def cell(ws, row, col, val="", bold=False, italic=False,
         align="left", color=None, bg=None, fmt=None):
    c = ws.cell(row=row, column=col, value=val)
    c.font = Font(bold=bold, italic=italic, name="Calibri", size=10,
                  color=color or "000000")
    c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=False)
    if bg:
        c.fill = PatternFill("solid", fgColor=bg)
    if fmt:
        c.number_format = fmt
    return c

def hdr(ws, row, col, val):
    cell(ws, row, col, val, bold=True, align="center", bg="D9E1F2")

def title_row(ws, row, text, ncols=11):
    cell(ws, row, 1, text, bold=True, italic=True, color="1F4E79")
    ws.merge_cells(start_row=row, start_column=1,
                   end_row=row,   end_column=ncols)

def col_w(ws, widths: dict):
    for c, w in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = w

PASS_COLOR = "006400"   # dark green text
FAIL_COLOR = "C00000"   # red text
GREEN_BG   = "E2EFDA"
RED_BG     = "FCE4D6"
BLUE_BG    = "DDEEFF"
GREY_BG    = "F2F2F2"

# ─────────────────────────────────────────────────────────────────────────────
# SHARED: calc_section  (reused across Vol Spike & Move Logic sheets)
# ─────────────────────────────────────────────────────────────────────────────
def calc_block(ws, start_row, col_start, header, thresholds,
               baseline_rows, current_rows, checks, fired):
    """
    Generic right-side calculation block.
    thresholds : list of (label, value_str)
    baseline_rows : list of (label, value, fmt)
    current_rows  : list of (label, value, fmt)
    checks        : list of (description, passed:bool)
    """
    r = start_row
    bg_hdr = "375623" if fired else "833C00"
    cell(ws, r, col_start,   header, bold=True, color="FFFFFF", bg=bg_hdr)
    cell(ws, r, col_start+1, "",     bold=True, color="FFFFFF", bg=bg_hdr)
    cell(ws, r, col_start+2, "",     bold=True, color="FFFFFF", bg=bg_hdr)
    r += 1

    cell(ws, r, col_start, "THRESHOLDS", bold=True, italic=True, color="404040"); r += 1
    for lbl, val in thresholds:
        cell(ws, r, col_start, "  " + lbl)
        cell(ws, r, col_start+1, val, bold=True, align="right"); r += 1

    r += 1
    cell(ws, r, col_start, "BASELINE WINDOW", bold=True); r += 1
    for lbl, val, fmt in baseline_rows:
        cell(ws, r, col_start, "  " + lbl)
        c = ws.cell(row=r, column=col_start+1, value=val)
        c.number_format = fmt; c.font = Font(bold=True, name="Calibri", size=10)
        c.alignment = Alignment(horizontal="right"); r += 1

    r += 1
    cell(ws, r, col_start, "CURRENT 1-MIN WINDOW", bold=True); r += 1
    for lbl, val, fmt in current_rows:
        cell(ws, r, col_start, "  " + lbl)
        c = ws.cell(row=r, column=col_start+1, value=val)
        c.number_format = fmt; c.font = Font(bold=True, name="Calibri", size=10)
        c.alignment = Alignment(horizontal="right"); r += 1

    r += 1
    cell(ws, r, col_start, "CHECKS", bold=True, italic=True, color="404040"); r += 1
    for desc, passed in checks:
        tick = "YES  ✓" if passed else "NO   ✗"
        cell(ws, r, col_start, "  " + desc)
        cell(ws, r, col_start+1, tick, bold=True, align="right",
             color=PASS_COLOR if passed else FAIL_COLOR); r += 1

    r += 1
    result = "✅  FIRES" if fired else "❌  NO FIRE"
    res_bg = "C6EFCE" if fired else "FFCCCC"
    res_fg = "375623" if fired else "9C0006"
    cell(ws, r, col_start,   "RESULT:  " + result, bold=True, color=res_fg, bg=res_bg)
    cell(ws, r, col_start+1, "", bg=res_bg)
    cell(ws, r, col_start+2, "", bg=res_bg)
    return r + 2


# ═════════════════════════════════════════════════════════════════════════════
# SHEET 1: VOL SPIKE
# ═════════════════════════════════════════════════════════════════════════════
ws1 = wb.active
ws1.title = "Vol Spike"
col_w(ws1, {1:4, 2:10, 3:7, 4:9, 5:9, 6:13, 7:11, 8:2, 9:32, 10:16, 11:12})

title_row(ws1, 1,
    "Vol Spike Detection  |  "
    "spike = dollar_vol_last_1min  ÷  (dollar_vol_prior_4min ÷ 4)   →  fire if spike ≥ threshold  AND  vol ≥ min  AND  price delta ≥ min%")

for c, lbl in enumerate(["#","Time","Ticker","Price","Shares","Dollar Vol","Window"],1):
    hdr(ws1, 3, c, lbl)

# --- raw data helper ---
def write_ticks(ws, ticks, row_start, row_offset=0, sym_prefix=""):
    for i, (t, price, shares, window) in enumerate(ticks):
        r = row_start + i
        bg = GREEN_BG if window == "1-MIN" else None
        dv = round(price * shares, 2)
        for c, v in enumerate([i+1+row_offset, t, sym_prefix, price, shares, dv, window], 1):
            fmt = None
            if c == 4: fmt = '"$"#,##0.00'
            if c == 5: fmt = "#,##0"
            if c == 6: fmt = '"$"#,##0.00'
            cell(ws, r, c, v, bg=bg if c in (1,2,3,7) else None,
                 fmt=fmt, align="center" if c in (1,2,3,7) else "right",
                 bold=(window == "1-MIN" and c == 7))

# ── Case 1: XYZ SPIKE ─────────────────────────────────────────────────────
ticks1 = [
    ("09:30:10", 2.00, 500,   "BASELINE"),
    ("09:30:45", 2.01, 400,   "BASELINE"),
    ("09:31:20", 2.00, 300,   "BASELINE"),
    ("09:32:05", 1.99, 500,   "BASELINE"),
    ("09:32:50", 2.00, 400,   "BASELINE"),
    ("09:33:15", 2.01, 350,   "BASELINE"),
    ("09:33:55", 2.00, 300,   "BASELINE"),
    ("09:34:10", 2.00, 5_000, "1-MIN"),
    ("09:34:35", 2.15, 4_500, "1-MIN"),
    ("09:34:52", 2.22, 4_000, "1-MIN"),
]
write_ticks(ws1, ticks1, 4, row_offset=0, sym_prefix="XYZ")

# ── Case 2: ABC NO SPIKE ──────────────────────────────────────────────────
ticks2 = [
    ("09:30:08", 5.00, 2_000, "BASELINE"),
    ("09:30:50", 5.01, 1_800, "BASELINE"),
    ("09:31:25", 5.00, 2_200, "BASELINE"),
    ("09:32:10", 4.99, 1_900, "BASELINE"),
    ("09:32:45", 5.00, 2_100, "BASELINE"),
    ("09:33:20", 5.01, 1_800, "BASELINE"),
    ("09:33:55", 5.00, 2_000, "BASELINE"),
    ("09:34:15", 5.02, 2_500, "1-MIN"),
    ("09:34:40", 5.03, 2_200, "1-MIN"),
    ("09:34:58", 5.02, 2_000, "1-MIN"),
]
write_ticks(ws1, ticks2, 15, row_offset=10, sym_prefix="ABC")

# ── Calc blocks ───────────────────────────────────────────────────────────
def spike_calc(ticks):
    bvs  = [p*s for _,p,s,w in ticks if w=="BASELINE"]
    cvs  = [p*s for _,p,s,w in ticks if w=="1-MIN"]
    pxs  = [p   for _,p,s,w in ticks if w=="1-MIN"]
    bvol = sum(bvs); bpm = bvol/4
    cvol = sum(cvs)
    dlt  = (pxs[-1]-pxs[0])/pxs[0]*100
    spk  = cvol/bpm
    return bvol, bpm, cvol, dlt, spk

b1,bpm1,cv1,d1,spk1 = spike_calc(ticks1)
b2,bpm2,cv2,d2,spk2 = spike_calc(ticks2)

calc_block(ws1, 3, 9,
    "=== CASE 1: XYZ  (NANO CAP) — SPIKE FIRES ===",
    thresholds=[("Spike multiplier >=","10×"),("Min dollar vol >=","$10,000"),("Price delta >=","8%")],
    baseline_rows=[
        ("Total dollar vol — 7 ticks",  round(b1,2),   '"$"#,##0.00'),
        ("Per-min baseline  (÷ 4)",      round(bpm1,2),  '"$"#,##0.00'),
    ],
    current_rows=[
        ("Total dollar vol — 3 ticks",  round(cv1,2),   '"$"#,##0.00'),
        ("Price delta  (first→last)",   round(d1,2),    '0.00"%"'),
        ("Spike ratio  (1min ÷ base/min)", round(spk1,2),'0.00"×"'),
    ],
    checks=[
        (f"vol1m ${cv1:,.0f} >= $10,000?",       cv1 >= 10_000),
        (f"delta {d1:.2f}% >= 8%?",              d1  >= 8),
        (f"spike {spk1:.1f}x >= 10×?",           spk1>= 10),
    ],
    fired=True,
)

calc_block(ws1, 15, 9,
    "=== CASE 2: ABC  (NANO CAP) — NO SPIKE ===",
    thresholds=[("Spike multiplier >=","10×"),("Min dollar vol >=","$10,000"),("Price delta >=","8%")],
    baseline_rows=[
        ("Total dollar vol — 7 ticks",  round(b2,2),   '"$"#,##0.00'),
        ("Per-min baseline  (÷ 4)",      round(bpm2,2),  '"$"#,##0.00'),
    ],
    current_rows=[
        ("Total dollar vol — 3 ticks",  round(cv2,2),   '"$"#,##0.00'),
        ("Price delta  (first→last)",   round(d2,2),    '0.00"%"'),
        ("Spike ratio  (1min ÷ base/min)", round(spk2,2),'0.00"×"'),
    ],
    checks=[
        (f"vol1m ${cv2:,.0f} >= $10,000?",       cv2 >= 10_000),
        (f"delta {d2:.2f}% >= 8%?",              d2  >= 8),
        (f"spike {spk2:.1f}x >= 10×?",           spk2>= 10),
    ],
    fired=False,
)


# ═════════════════════════════════════════════════════════════════════════════
# SHEET 2: MOVE LOGIC  (Bull/Bear VWAP-delta alerts)
# ═════════════════════════════════════════════════════════════════════════════
ws2 = wb.create_sheet("Move Logic")
col_w(ws2, {1:4, 2:10, 3:7, 4:9, 5:9, 6:13, 7:13, 8:2, 9:34, 10:16, 11:12})

title_row(ws2, 1,
    "Move Logic (Bull/Bear Alert)  |  "
    "delta% = (VWAP_last_1min − VWAP_prior_1min) ÷ VWAP_prior_1min × 100   →  fire if |delta| ≥ thresh AND vol ≥ min AND trades ≥ min")

for c, lbl in enumerate(["#","Time","Ticker","Price","Shares","Dollar Vol","Window"],1):
    hdr(ws2, 3, c, lbl)

# helper: VWAP from ticks list
def vwap(ticks_filtered):
    sv = sum(p*s for _,p,s,_ in ticks_filtered)
    ss = sum(s   for _,p,s,_ in ticks_filtered)
    return sv/ss if ss else 0

# ── Case 1: PQR  BULL fires ────────────────────────────────────────────────
# 2-MIN = ticks from 1-2 min ago; 1-MIN = ticks from last minute
m_ticks1 = [
    # (time,   price,  shares,  window)
    ("09:32:05", 3.00, 400,  "2-MIN"),
    ("09:32:25", 3.01, 350,  "2-MIN"),
    ("09:32:45", 3.00, 500,  "2-MIN"),
    ("09:33:10", 3.01, 400,  "2-MIN"),
    ("09:33:30", 3.00, 300,  "2-MIN"),
    ("09:33:50", 3.02, 350,  "2-MIN"),
    ("09:33:58", 3.01, 400,  "2-MIN"),
    ("09:34:08", 3.10, 1_800, "1-MIN"),
    ("09:34:28", 3.16, 2_200, "1-MIN"),
    ("09:34:50", 3.20, 1_500, "1-MIN"),
]
write_ticks(ws2, m_ticks1, 4, row_offset=0, sym_prefix="PQR")

# ── Case 2: DEF  BULL delta too small — NO FIRE ────────────────────────────
m_ticks2 = [
    ("09:32:05", 8.00, 1_000, "2-MIN"),
    ("09:32:30", 8.01,   900, "2-MIN"),
    ("09:32:55", 8.00, 1_100, "2-MIN"),
    ("09:33:15", 7.99,   950, "2-MIN"),
    ("09:33:35", 8.00, 1_000, "2-MIN"),
    ("09:33:55", 8.01,   950, "2-MIN"),
    ("09:33:58", 8.00,   900, "2-MIN"),
    ("09:34:10", 8.02, 1_200, "1-MIN"),
    ("09:34:35", 8.03, 1_100, "1-MIN"),
    ("09:34:55", 8.02, 1_000, "1-MIN"),
]
write_ticks(ws2, m_ticks2, 15, row_offset=10, sym_prefix="DEF")

# ── Calc blocks ───────────────────────────────────────────────────────────
def move_calc(ticks):
    w2 = [(t,p,s,w) for t,p,s,w in ticks if w=="2-MIN"]
    w1 = [(t,p,s,w) for t,p,s,w in ticks if w=="1-MIN"]
    v2 = vwap(w2); v1 = vwap(w1)
    vol1m = sum(p*s for t,p,s,w in w1)
    cnt1m = len(w1)
    delta = (v1 - v2) / v2 * 100
    return v2, v1, vol1m, cnt1m, delta

v2_1,v1_1,vol1_1,cnt1_1,dlt1 = move_calc(m_ticks1)
v2_2,v1_2,vol1_2,cnt1_2,dlt2 = move_calc(m_ticks2)

calc_block(ws2, 3, 9,
    "=== CASE 1: PQR  (NANO CAP) — BULL ALERT FIRES ===",
    thresholds=[
        ("Bull delta >= ","4%  (NANO tier)"),
        ("Min dollar vol >= ","$20,000"),
        ("Min trade count >= ","1"),
    ],
    baseline_rows=[
        ("VWAP — prior 1-min (2-MIN window)", round(v2_1,4), '"$"#,##0.0000'),
        ("Trade count",                        len([t for t in m_ticks1 if t[3]=="2-MIN"]), "0"),
    ],
    current_rows=[
        ("VWAP — last 1-min (1-MIN window)", round(v1_1,4), '"$"#,##0.0000'),
        ("Dollar vol in last 1-min",         round(vol1_1,2), '"$"#,##0.00'),
        ("Trade count",                       cnt1_1, "0"),
        ("delta% = (v1−v2)/v2 × 100",        round(dlt1,2),  '0.00"%"'),
    ],
    checks=[
        (f"|delta| {dlt1:.2f}% >= 4%?",           abs(dlt1) >= 4),
        (f"vol1m ${vol1_1:,.0f} >= $20,000?",      vol1_1 >= 20_000),
        (f"trades {cnt1_1} >= 1?",                 cnt1_1 >= 1),
    ],
    fired=True,
)

calc_block(ws2, 15, 9,
    "=== CASE 2: DEF  (NANO CAP) — NO ALERT ===",
    thresholds=[
        ("Bull delta >= ","4%  (NANO tier)"),
        ("Min dollar vol >= ","$20,000"),
        ("Min trade count >= ","1"),
    ],
    baseline_rows=[
        ("VWAP — prior 1-min (2-MIN window)", round(v2_2,4), '"$"#,##0.0000'),
        ("Trade count",                        len([t for t in m_ticks2 if t[3]=="2-MIN"]), "0"),
    ],
    current_rows=[
        ("VWAP — last 1-min (1-MIN window)", round(v1_2,4), '"$"#,##0.0000'),
        ("Dollar vol in last 1-min",         round(vol1_2,2), '"$"#,##0.00'),
        ("Trade count",                       cnt1_2, "0"),
        ("delta% = (v1−v2)/v2 × 100",        round(dlt2,2),  '0.00"%"'),
    ],
    checks=[
        (f"|delta| {dlt2:.2f}% >= 4%?",           abs(dlt2) >= 4),
        (f"vol1m ${vol1_2:,.0f} >= $20,000?",      vol1_2 >= 20_000),
        (f"trades {cnt1_2} >= 1?",                 cnt1_2 >= 1),
    ],
    fired=False,
)

# ═════════════════════════════════════════════════════════════════════════════
# SHEET 3: SWEEP LOGIC
# ═════════════════════════════════════════════════════════════════════════════
ws3 = wb.create_sheet("Sweep Logic")
col_w(ws3, {1:6, 2:10, 3:7, 4:11, 5:13, 6:10, 7:11, 8:2,
            9:28, 10:18, 11:14})

title_row(ws3, 1,
    "Sweep Logic  |  Sweeps arrive from external source with confidence (delta%).  "
    "App shows ▲ bull / ▼ bear / <> neutral.  Strategy fires after N consecutive bull sweeps within 60s.", 11)

for c, lbl in enumerate(
        ["#","Time","Ticker","Confidence%","Dollar Vol","VWAP Price","Direction"],1):
    hdr(ws3, 3, c, lbl)

# 10 sweep events — mix of directions
sweeps = [
    # (time,    ticker, conf,  value,    vwap,  direction)
    ("09:05:50","WOK",   99,   101_400,  1.23, "bull"),
    ("09:05:50","WOK",   94,    21_400,  1.18, "bull"),
    ("09:05:53","WOK",   99,    40_700,  1.25, "bull"),
    ("09:06:08","WOK",   27,    23_900,  1.28, "neutral"),
    ("09:10:23","WOK",   27,    23_400,  1.21, "neutral"),
    ("09:17:27","WOK",   27,    23_900,  1.28, "neutral"),
    ("09:18:44","WOK",   99,    21_000,  1.24, "bear"),
    ("09:19:33","WOK",   27,    21_200,  1.20, "neutral"),
    ("09:32:02","AEHL",  97,    24_488,  5.32, "bull"),
    ("09:31:06","AEHL",  27,    26_250,  5.25, "neutral"),
]

dir_icon = {"bull": "▲  BULL", "bear": "▼  BEAR", "neutral": "<>  NEUTRAL"}
dir_bg   = {"bull": GREEN_BG, "bear": RED_BG, "neutral": GREY_BG}

for i, (t, ticker, conf, value, vwap_px, dirn) in enumerate(sweeps):
    r = 4 + i
    bg = dir_bg.get(dirn)
    cell(ws3, r, 1, i+1,   align="center")
    cell(ws3, r, 2, t,     align="center")
    cell(ws3, r, 3, ticker, align="center")
    c4 = ws3.cell(row=r, column=4, value=conf)
    c4.number_format = '0"%"'
    c4.alignment = Alignment(horizontal="right")
    c5 = ws3.cell(row=r, column=5, value=value)
    c5.number_format = '"$"#,##0'
    c5.alignment = Alignment(horizontal="right")
    c6 = ws3.cell(row=r, column=6, value=vwap_px)
    c6.number_format = '"$"#,##0.00'
    c6.alignment = Alignment(horizontal="right")
    cell(ws3, r, 7, dir_icon.get(dirn, dirn), bg=bg,
         bold=(dirn in ("bull","bear")), align="center",
         color=PASS_COLOR if dirn=="bull" else FAIL_COLOR if dirn=="bear" else "555555")

# ── Right-side: confidence rules + strategy condition ─────────────────────
r = 3
cell(ws3, r, 9, "=== SWEEP DISPLAY RULES ===", bold=True, color="FFFFFF", bg="1F4E79")
cell(ws3, r, 10, "", bold=True, bg="1F4E79"); cell(ws3, r, 11, "", bold=True, bg="1F4E79"); r += 1

for lbl, val in [
    ("direction == 'bull'",    "▲  Green color"),
    ("direction == 'bear'",    "▼  Red color"),
    ("direction == 'neutral'", "<>  Green if conf>10%, Red if conf<-10%, Grey if near 0"),
    ("conf (delta field)",     "Confidence score sent by sweep source (0–100%)"),
]:
    cell(ws3, r, 9, "  " + lbl); cell(ws3, r, 10, val, italic=True); r += 1

r += 1
cell(ws3, r, 9, "=== STRATEGY TRIGGER (strategy worker) ===", bold=True, color="FFFFFF", bg="375623")
cell(ws3, r, 10, "", bold=True, bg="375623"); cell(ws3, r, 11, "", bold=True, bg="375623"); r += 1

strategy_rules = [
    ("Sweep type",            "Must be type='sweep'  direction='bull'"),
    ("Consecutive count",     "n_consec_bull must reach threshold (default 2)"),
    ("Time window",           "All bull sweeps must land within 60 seconds of each other"),
    ("Market hours only",     "9:30 AM – 3:45 PM ET  (no extended hours)"),
    ("No open position",      "machine state must be WATCHING (not IN_POSITION)"),
    ("Result if all pass",    "→ Submit Market Buy order → then place TrailingStop sell"),
]
for lbl, val in strategy_rules:
    cell(ws3, r, 9, "  " + lbl); cell(ws3, r, 10, val, italic=True); r += 1

r += 1
cell(ws3, r, 9, "=== WOK EXAMPLE TRACE (rows 1-3) ===", bold=True, color="FFFFFF", bg="833C00")
cell(ws3, r, 10, "", bold=True, bg="833C00"); cell(ws3, r, 11, "", bold=True, bg="833C00"); r += 1

trace = [
    ("09:05:50  sweep #1  bull  99%",  "consec_bull = 1  last_bull_ts = 09:05:50"),
    ("09:05:50  sweep #2  bull  94%",  "consec_bull = 2  ← threshold hit!  → BUY ORDER"),
    ("09:05:53  sweep #3  bull  99%",  "already IN_POSITION — ignored"),
    ("09:18:44  sweep #7  bear  99%",  "direction=bear — resets consec_bull = 0"),
    ("gap > 60s between sweeps",       "streak expires → consec_bull resets to 0"),
]
for lbl, val in trace:
    cell(ws3, r, 9, "  " + lbl); cell(ws3, r, 10, val, italic=True, color="555555"); r += 1


# ═════════════════════════════════════════════════════════════════════════════
# SHEET 4: RAW DATA  (actual rows from alerts.db)
# ═════════════════════════════════════════════════════════════════════════════
ws4 = wb.create_sheet("Raw Data")
col_w(ws4, {1:5, 2:26, 3:7, 4:14, 5:9, 6:13, 7:11, 8:11, 9:8, 10:10, 11:9})

title_row(ws4, 1,
    "Raw Data — Actual rows from alerts.db  "
    "(type: alert=move alert, sweep=options sweep, vol=volume spike)", 11)

db_headers = ["id","ts","sym","tag","delta","value1m","vwap1m","vwap2m","cnt1m","direction","type"]
for c, lbl in enumerate(db_headers, 1):
    hdr(ws4, 3, c, lbl)

try:
    with sqlite3.connect("alerts.db") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id,ts,sym,tag,delta,value1m,vwap1m,vwap2m,cnt1m,direction,type "
            "FROM alerts ORDER BY id DESC LIMIT 20"
        ).fetchall()

    type_bg = {"alert": BLUE_BG, "sweep": GREEN_BG, "vol": "FFF2CC"}

    for i, row in enumerate(rows):
        r = 4 + i
        d = dict(row)
        bg = type_bg.get(d.get("type",""), None)
        for c, key in enumerate(db_headers, 1):
            v = d.get(key)
            fmt = None
            if key in ("value1m","vwap1m","vwap2m") and v is not None:
                fmt = '"$"#,##0.00'
            if key == "delta" and v is not None:
                fmt = '0.00"%"'
            aln = "right" if key in ("id","delta","value1m","vwap1m","vwap2m","cnt1m") else "left"
            cell(ws4, r, c, v, align=aln, bg=bg if c in (11,3) else None, fmt=fmt)

except Exception as e:
    cell(ws4, 4, 1, f"Could not read alerts.db: {e}")

# legend
r = 26
cell(ws4, r, 1, "COLOR KEY:", bold=True)
cell(ws4, r+1, 1, "  Blue  = type:alert  (move alert — VWAP delta)",  bg=BLUE_BG)
cell(ws4, r+2, 1, "  Green = type:sweep  (options sweep — bull/bear/neutral)", bg=GREEN_BG)
cell(ws4, r+3, 1, "  Yellow= type:vol    (volume spike / new activity)",  bg="FFF2CC")


# ─────────────────────────────────────────────────────────────────────────────
out = "vol_spike_example.xlsx"
wb.save(out)
print(f"OK  Saved  {out}")
print("   Sheet 1: Vol Spike")
print("   Sheet 2: Move Logic")
print("   Sheet 3: Sweep Logic")
print("   Sheet 4: Raw Data  (last 20 rows from alerts.db)")
