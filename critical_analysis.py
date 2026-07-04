import sqlite3
from collections import defaultdict

conn = sqlite3.connect('alerts.db')
cur = conn.cursor()

print("="*65)
print("CRITICAL ANALYSIS — SIGNAL QUALITY & STRATEGY VIABILITY")
print("="*65)

# ── 1. ASTC contaminating sweep:nano ──────────────────────────────
print("\n[1] ASTC PRICE AT TIME OF SWEEP:NANO ALERTS (should be <$5?)")
cur.execute("""
    SELECT substr(ts,1,10), MIN(vwap1m), MAX(vwap1m), COUNT(*)
    FROM alerts WHERE sym='ASTC' AND tag='sweep:nano'
    GROUP BY substr(ts,1,10) ORDER BY 1
""")
for r in cur.fetchall():
    print(f"  {r[0]}: price range ${r[1]:.2f}-${r[2]:.2f}, alerts={r[3]}")

# ── 2. Vol spike + sweep combo — how rare? ────────────────────────
print("\n[2] VOL_SPIKE then SWEEP within 5min (nano, vol>50k) — actual count:")
cur.execute("""
    SELECT COUNT(*) FROM alerts a
    JOIN alerts b ON a.sym=b.sym
        AND b.ts>a.ts AND b.ts<=datetime(a.ts,'+5 minutes')
        AND b.tag IN ('sweep:nano','sweep:small')
    WHERE a.tag='vol_spike' AND a.vwap1m<5 AND a.value1m>50000
""")
print(f"  Count: {cur.fetchone()[0]}")

cur.execute("""
    SELECT COUNT(*) FROM alerts a
    JOIN alerts b ON a.sym=b.sym
        AND b.ts>a.ts AND b.ts<=datetime(a.ts,'+5 minutes')
        AND b.tag IN ('sweep:nano','sweep:small')
    WHERE a.tag='vol_spike' AND a.vwap1m<10 AND a.value1m>50000
""")
print(f"  Count (price<$10): {cur.fetchone()[0]}")

# ── 3. Time of day distribution ───────────────────────────────────
print("\n[3] WHEN DO HIGH-VALUE NANO SWEEPS HAPPEN? (value1m>100k, price<5)")
cur.execute("""
    SELECT substr(ts,12,2) as hour, COUNT(*), ROUND(AVG(value1m),0), ROUND(AVG(delta),1)
    FROM alerts
    WHERE vwap1m<5 AND value1m>100000 AND tag IN ('sweep:nano','sweep:small')
    GROUP BY hour ORDER BY hour
""")
for r in cur.fetchall():
    bar = '#' * (r[1] // 5)
    print(f"  {r[0]}h: {r[1]:4d} alerts  avg_val=${int(r[2]):,}  avg_delta={r[3]}  {bar}")

# ── 4. Delta quality — does high delta predict direction? ─────────
print("\n[4] DELTA BREAKDOWN for sweep:nano (direction field vs delta value)")
cur.execute("""
    SELECT direction,
        SUM(CASE WHEN delta>70 THEN 1 ELSE 0 END) as hi_delta,
        SUM(CASE WHEN delta BETWEEN 40 AND 70 THEN 1 ELSE 0 END) as mid_delta,
        SUM(CASE WHEN delta<40 THEN 1 ELSE 0 END) as lo_delta,
        COUNT(*) as total
    FROM alerts WHERE tag='sweep:nano' AND delta IS NOT NULL
    GROUP BY direction ORDER BY total DESC
""")
for r in cur.fetchall():
    print(f"  dir={r[0]:8s}: hi_delta(>70)={r[1]:5d}, mid={r[2]:5d}, lo(<40)={r[3]:5d}, total={r[4]}")

# ── 5. Consecutive sweeps same ticker ─────────────────────────────
print("\n[5] CONSECUTIVE BULL SWEEPS — same ticker, 2+ within 10min (nano, val>50k):")
cur.execute("""
    SELECT a.sym, a.ts, a.value1m, b.ts as ts2, b.value1m as val2, a.vwap1m, a.delta
    FROM alerts a
    JOIN alerts b ON a.sym=b.sym
        AND b.ts>a.ts AND b.ts<=datetime(a.ts,'+10 minutes')
        AND b.tag=a.tag AND b.direction='bull'
    WHERE a.tag IN ('sweep:nano','sweep:small') AND a.direction='bull'
        AND a.vwap1m<5 AND a.value1m>50000 AND b.value1m>50000
        AND a.delta>60 AND b.delta>60
    ORDER BY a.value1m DESC LIMIT 20
""")
rows = cur.fetchall()
print(f"  Total occurrences: {len(rows)}")
for r in rows[:15]:
    print(f"  {r[0]:6s} {r[1][:16]} val1=${int(r[2]):,} -> val2=${int(r[4]):,} price=${r[5]:.3f} delta={r[6]}")

# ── 6. VWAP acceleration signal ───────────────────────────────────
print("\n[6] VWAP ACCELERATION (vwap1m > vwap2m by >0.5%) with high value:")
cur.execute("""
    SELECT ts, sym, tag, value1m, vwap1m, vwap2m,
        ROUND((vwap1m/vwap2m - 1)*100, 2) as accel_pct,
        direction, delta
    FROM alerts
    WHERE vwap1m > vwap2m * 1.005
        AND value1m > 100000
        AND vwap1m < 5
        AND direction = 'bull'
    ORDER BY accel_pct DESC LIMIT 20
""")
for r in cur.fetchall():
    print(f"  {r[0][:16]} {r[1]:6s} {r[2]:12s} val=${int(r[3]):,} accel=+{r[6]}% price=${r[4]:.3f} delta={r[8]}")

# ── 7. After-hours vs market-hours signal count ───────────────────
print("\n[7] MARKET HOURS vs AFTER HOURS signal distribution (all nano sweeps):")
cur.execute("""
    SELECT
        CASE
            WHEN substr(ts,12,5)>='09:30' AND substr(ts,12,5)<'16:00' THEN 'market'
            WHEN substr(ts,12,5)>='16:00' THEN 'after_hours'
            ELSE 'pre_market'
        END as session,
        COUNT(*) as cnt,
        ROUND(AVG(value1m),0) as avg_val
    FROM alerts WHERE tag IN ('sweep:nano','sweep:small') AND vwap1m<10
    GROUP BY session ORDER BY cnt DESC
""")
for r in cur.fetchall():
    print(f"  {r[0]:15s}: {r[1]:6d} alerts, avg_val=${int(r[2]):,}")

# ── 8. new + escalation chain ─────────────────────────────────────
print("\n[8] NEW -> ESCALATION chain within 3min (nano, val>50k each):")
cur.execute("""
    SELECT a.sym, a.ts, a.value1m, b.ts, b.value1m, a.vwap1m, a.direction, a.delta
    FROM alerts a
    JOIN alerts b ON a.sym=b.sym
        AND b.ts>a.ts AND b.ts<=datetime(a.ts,'+3 minutes')
        AND b.tag='escalation'
    WHERE a.tag IN ('new','new_activity')
        AND a.value1m>50000 AND b.value1m>50000
        AND a.vwap1m<10
    ORDER BY a.value1m+b.value1m DESC LIMIT 20
""")
rows2 = cur.fetchall()
print(f"  Total: {len(rows2)}")
for r in rows2[:15]:
    print(f"  {r[0]:6s} {r[1][:16]} new=${int(r[2]):,} esc=${int(r[4]):,} price=${r[5]:.3f} {r[6]} delta={r[7]}")

# ── 9. Realistic slippage concern — how fast do alerts cluster? ───
print("\n[9] ALERT BURST SPEED — how many alerts fire in same minute for hot tickers:")
cur.execute("""
    SELECT sym, substr(ts,1,16) as minute, COUNT(*) as burst_cnt, SUM(value1m) as total_val, MIN(vwap1m) as price
    FROM alerts
    WHERE vwap1m<5 AND value1m>10000
    GROUP BY sym, minute HAVING burst_cnt >= 3
    ORDER BY burst_cnt DESC LIMIT 20
""")
for r in cur.fetchall():
    print(f"  {r[0]:6s} {r[1]} burst={r[2]} total_val=${int(r[3]):,} price=${r[4]:.3f}")

# ── 10. Bear sweeps on nano — short opportunity? ──────────────────
print("\n[10] BEAR SWEEPS NANO (delta<30, direction=bear, val>100k):")
cur.execute("""
    SELECT ts, sym, delta, value1m, vwap1m, cnt1m
    FROM alerts
    WHERE tag IN ('sweep:nano','sweep:small') AND direction='bear'
        AND value1m>100000 AND vwap1m<5
    ORDER BY value1m DESC LIMIT 15
""")
for r in cur.fetchall():
    print(f"  {r[0][:16]} {r[1]:6s} delta={r[2]} val=${int(r[3]):,} price=${r[4]:.3f}")

conn.close()
print("\nDONE")
