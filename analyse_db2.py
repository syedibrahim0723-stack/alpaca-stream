import sqlite3

conn = sqlite3.connect('alerts.db')
cur = conn.cursor()

# Delta distribution
cur.execute("SELECT delta FROM alerts ORDER BY delta")
rows = [x[0] for x in cur.fetchall()]
n = len(rows)
print(f"DELTA stats: min={rows[0]:.2f}, max={rows[-1]:.2f}, avg={sum(rows)/n:.2f}")
print(f"  p25={rows[n//4]:.2f}, p50={rows[n//2]:.2f}, p75={rows[3*n//4]:.2f}, p90={rows[int(n*0.9)]:.2f}, p95={rows[int(n*0.95)]:.2f}")

# Top tickers by alert count
cur.execute("SELECT sym, COUNT(*) as cnt FROM alerts GROUP BY sym ORDER BY cnt DESC LIMIT 20")
print("\nTOP 20 TICKERS by alert count:")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

# Nano cap tickers (vwap1m < 5)
cur.execute("SELECT sym, COUNT(*), AVG(vwap1m), AVG(value1m) FROM alerts WHERE vwap1m < 5 GROUP BY sym ORDER BY 2 DESC LIMIT 20")
print("\nTOP 20 NANO-CAP TICKERS (vwap1m < $5):")
for r in cur.fetchall(): print(f"  {r[0]}: cnt={r[1]}, avg_price=${r[2]:.3f}, avg_val1m=${r[3]:,.0f}")

# Sample nano with high value1m
cur.execute("""
    SELECT ts, sym, tag, delta, value1m, vwap1m, direction
    FROM alerts
    WHERE vwap1m < 5 AND value1m > 100000
    ORDER BY value1m DESC
    LIMIT 20
""")
print("\nNANO HIGH VALUE1M (>$100k) SAMPLES:")
for r in cur.fetchall():
    print(f"  {r[0][:16]} {r[1]:6s} tag={r[2]:10s} delta={r[3]:+6.1f}% val=${r[4]:,.0f} price=${r[5]:.3f} {r[6]}")

# Vol spike + sweep combo within 5 min (nano)
cur.execute("""
    SELECT a.sym, a.ts, a.tag as tag_a, a.value1m as val_a,
           b.tag as tag_b, b.value1m as val_b, b.ts as ts_b,
           a.vwap1m, a.direction, b.direction as dir_b
    FROM alerts a
    JOIN alerts b ON a.sym = b.sym
        AND b.ts > a.ts
        AND b.ts <= datetime(a.ts, '+5 minutes')
        AND a.tag != b.tag
    WHERE a.vwap1m < 5 AND a.value1m > 50000 AND b.value1m > 50000
    ORDER BY a.value1m DESC
    LIMIT 30
""")
print("\nNANO: Multi-alert clusters within 5 min (val>50k each):")
for r in cur.fetchall():
    print(f"  {r[0]:6s} {r[1][:16]} {r[2]}->{r[4]} val1=${r[3]:,.0f} val2=${r[5]:,.0f} price=${r[7]:.3f} dir={r[8]}/{r[9]}")

# How many distinct tickers per day nano
cur.execute("""
    SELECT substr(ts,1,10) as day, COUNT(DISTINCT sym) as syms, COUNT(*) as alerts
    FROM alerts WHERE vwap1m < 5
    GROUP BY day ORDER BY day
""")
print("\nNANO alerts per day:")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]} symbols, {r[2]} alerts")

# Sweep nano bull with value > 200k
cur.execute("""
    SELECT ts, sym, delta, value1m, vwap1m, direction, cnt1m
    FROM alerts
    WHERE tag='sweep:nano' AND value1m > 200000
    ORDER BY value1m DESC LIMIT 20
""")
print("\nSWEEP:NANO with value1m > 200k:")
for r in cur.fetchall():
    print(f"  {r[0][:16]} {r[1]:6s} delta={r[2]:+.1f}% val=${r[3]:,.0f} price=${r[4]:.3f} {r[5]} cnt={r[6]}")

# vol_spike stats for nano
cur.execute("""
    SELECT ts, sym, delta, value1m, vwap1m, cnt1m
    FROM alerts
    WHERE tag='vol_spike' AND vwap1m < 5
    ORDER BY value1m DESC LIMIT 20
""")
print("\nVOL_SPIKE NANO (top by value):")
for r in cur.fetchall():
    print(f"  {r[0][:16]} {r[1]:6s} delta={r[2]:+.1f}% val=${r[3]:,.0f} price=${r[4]:.3f} cnt={r[5]}")

conn.close()
print("\nDONE")
