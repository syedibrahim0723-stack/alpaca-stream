import sqlite3, json
from collections import Counter

conn = sqlite3.connect('alerts.db')
cur = conn.cursor()

print("="*60)
print("ALERTS TABLE DEEP ANALYSIS")
print("="*60)

# Date range
cur.execute("SELECT MIN(ts), MAX(ts) FROM alerts")
print("\nDate range:", cur.fetchone())

# Tags
cur.execute("SELECT tag, COUNT(*) as cnt FROM alerts GROUP BY tag ORDER BY cnt DESC")
print("\nTAGS:")
for r in cur.fetchall(): print(" ", r)

# Directions
cur.execute("SELECT direction, COUNT(*) FROM alerts GROUP BY direction ORDER BY 2 DESC")
print("\nDIRECTIONS:")
for r in cur.fetchall(): print(" ", r)

# Types
cur.execute("SELECT type, COUNT(*) FROM alerts GROUP BY type ORDER BY 2 DESC")
print("\nTYPES:")
for r in cur.fetchall(): print(" ", r)

# Tag + direction combo
cur.execute("SELECT tag, direction, COUNT(*) FROM alerts GROUP BY tag, direction ORDER BY 3 DESC LIMIT 20")
print("\nTAG+DIRECTION combos (top 20):")
for r in cur.fetchall(): print(" ", r)

# Price range of vwap1m (proxy for stock price)
cur.execute("""
    SELECT
        SUM(CASE WHEN vwap1m < 5 THEN 1 ELSE 0 END) as nano,
        SUM(CASE WHEN vwap1m >= 5 AND vwap1m < 20 THEN 1 ELSE 0 END) as small,
        SUM(CASE WHEN vwap1m >= 20 THEN 1 ELSE 0 END) as large,
        COUNT(*) as total
    FROM alerts
""")
r = cur.fetchone()
print(f"\nPRICE BUCKETS (by vwap1m): nano(<$5)={r[0]}, small($5-20)={r[1]}, large(>$20)={r[2]}, total={r[3]}")

# Value1m distribution
cur.execute("""
    SELECT
        SUM(CASE WHEN value1m < 10000 THEN 1 ELSE 0 END) as lt10k,
        SUM(CASE WHEN value1m >= 10000 AND value1m < 50000 THEN 1 ELSE 0 END) as lt50k,
        SUM(CASE WHEN value1m >= 50000 AND value1m < 100000 THEN 1 ELSE 0 END) as lt100k,
        SUM(CASE WHEN value1m >= 100000 AND value1m < 200000 THEN 1 ELSE 0 END) as lt200k,
        SUM(CASE WHEN value1m >= 200000 THEN 1 ELSE 0 END) as gt200k
    FROM alerts
""")
r = cur.fetchone()
print(f"\nVALUE1M BUCKETS: <10k={r[0]}, 10-50k={r[1]}, 50-100k={r[2]}, 100-200k={r[3]}, >200k={r[4]}")

# Delta distribution
cur.execute("""
    SELECT
        MIN(delta), MAX(delta), AVG(delta),
        PERCENTILE_CONT(0.25) WITHIN GROUP(ORDER BY delta),
        PERCENTILE_CONT(0.50) WITHIN GROUP(ORDER BY delta),
        PERCENTILE_CONT(0.75) WITHIN GROUP(ORDER BY delta)
    FROM alerts
""")
try:
    r = cur.fetchone()
    print(f"\nDELTA stats: min={r[0]:.2f}, max={r[1]:.2f}, avg={r[2]:.2f}")
except:
    cur.execute("SELECT MIN(delta), MAX(delta), AVG(delta) FROM alerts")
    r = cur.fetchone()
    print(f"\nDELTA stats: min={r[0]:.2f}, max={r[1]:.2f}, avg={r[2]:.2f}")
    cur.execute("SELECT delta FROM alerts ORDER BY delta")
    rows = [x[0] for x in cur.fetchall()]
    n = len(rows)
    print(f"  p25={rows[n//4]:.2f}, p50={rows[n//2]:.2f}, p75={rows[3*n//4]:.2f}, p90={rows[int(n*0.9)]:.2f}, p95={rows[int(n*0.95)]:.2f}")

# Top tickers by alert count
cur.execute("SELECT sym, COUNT(*) as cnt FROM alerts GROUP BY sym ORDER BY cnt DESC LIMIT 20")
print("\nTOP 20 TICKERS by alert count:")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

# Top tickers nano cap only (vwap1m < 5)
cur.execute("SELECT sym, COUNT(*), AVG(vwap1m), AVG(value1m) FROM alerts WHERE vwap1m < 5 GROUP BY sym ORDER BY 2 DESC LIMIT 20")
print("\nTOP 20 NANO-CAP TICKERS (vwap1m < $5):")
for r in cur.fetchall(): print(f"  {r[0]}: cnt={r[1]}, avg_price=${r[2]:.3f}, avg_value1m=${r[3]:,.0f}")

# Sample nano with high value1m
cur.execute("""
    SELECT ts, sym, tag, delta, value1m, vwap1m, direction
    FROM alerts
    WHERE vwap1m < 5 AND value1m > 100000
    ORDER BY value1m DESC
    LIMIT 20
""")
print("\nNANO CAP HIGH VALUE1M (>$100k) SAMPLE:")
for r in cur.fetchall():
    print(f"  {r[0][:16]} {r[1]:6s} tag={r[2]:6s} delta={r[3]:+.1f}% val=${r[4]:,.0f} price=${r[5]:.3f} {r[6]}")

# How often tags appear together for same sym within 5 min
cur.execute("""
    SELECT a.sym, a.ts, a.tag, a.value1m, a.vwap1m, a.direction,
           b.tag as b_tag, b.value1m as b_val, b.ts as b_ts
    FROM alerts a
    JOIN alerts b ON a.sym = b.sym
        AND b.ts > a.ts
        AND b.ts <= datetime(a.ts, '+5 minutes')
        AND a.tag != b.tag
    WHERE a.vwap1m < 5 AND a.value1m > 50000
    LIMIT 30
""")
print("\nNANO: Cross-tag combos within 5 min (sample):")
for r in cur.fetchall():
    print(f"  {r[0]:6s} {r[1][:16]} {r[2]}->{r[6]} val1=${r[3]:,.0f} val2=${r[7]:,.0f} dir={r[5]}")

conn.close()
print("\nDONE")
