import sqlite3
conn = sqlite3.connect('alerts.db')
cur = conn.cursor()

print('TOP 20 TICKERS by alert count:')
cur.execute('SELECT sym, COUNT(*) as cnt FROM alerts GROUP BY sym ORDER BY cnt DESC LIMIT 20')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]}')

print('\nTOP 20 NANO-CAP (vwap1m < 5):')
cur.execute('SELECT sym, COUNT(*), ROUND(AVG(vwap1m),3), ROUND(AVG(value1m),0) FROM alerts WHERE vwap1m < 5 GROUP BY sym ORDER BY 2 DESC LIMIT 20')
for r in cur.fetchall(): print(f'  {r[0]}: cnt={r[1]}, avg_price={r[2]}, avg_val1m={int(r[3]):,}')

print('\nSWEEP:NANO value1m > 200k:')
cur.execute('SELECT ts, sym, delta, value1m, vwap1m, direction, cnt1m FROM alerts WHERE tag=? AND value1m > 200000 ORDER BY value1m DESC LIMIT 20', ('sweep:nano',))
for r in cur.fetchall(): print(f'  {r[0][:16]} {r[1]:6s} delta={r[2]} val={int(r[3]):,} price={r[4]:.3f} {r[5]} cnt={r[6]}')

print('\nVOL_SPIKE NANO top by value:')
cur.execute('SELECT ts, sym, delta, value1m, vwap1m, cnt1m FROM alerts WHERE tag=? AND vwap1m < 5 ORDER BY value1m DESC LIMIT 20', ('vol_spike',))
for r in cur.fetchall(): print(f'  {r[0][:16]} {r[1]:6s} delta={r[2]} val={int(r[3]):,} price={r[4]:.3f} cnt={r[5]}')

print('\nNANO alerts per day:')
cur.execute('SELECT substr(ts,1,10) as day, COUNT(DISTINCT sym) as syms, COUNT(*) as alerts FROM alerts WHERE vwap1m < 5 GROUP BY day ORDER BY day')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]} symbols, {r[2]} alerts')

print('\nMULTI-ALERT NANO clusters within 5min (both val>50k):')
sql = '''
SELECT a.sym, a.ts, a.tag, a.value1m, b.tag as b_tag, b.value1m as b_val, a.vwap1m, a.direction
FROM alerts a
JOIN alerts b ON a.sym=b.sym
    AND b.ts>a.ts
    AND b.ts<=datetime(a.ts,"+5 minutes")
    AND a.tag!=b.tag
WHERE a.vwap1m<5 AND a.value1m>50000 AND b.value1m>50000
ORDER BY a.value1m DESC
LIMIT 30
'''
cur.execute(sql)
for r in cur.fetchall():
    print(f'  {r[0]:6s} {r[1][:16]} {r[2]}->{r[4]} val1={int(r[3]):,} val2={int(r[5]):,} price={r[6]:.3f} {r[7]}')

print('\nSWEEP:SMALL value1m > 200k:')
cur.execute('SELECT ts, sym, delta, value1m, vwap1m, direction, cnt1m FROM alerts WHERE tag=? AND value1m > 200000 ORDER BY value1m DESC LIMIT 20', ('sweep:small',))
for r in cur.fetchall(): print(f'  {r[0][:16]} {r[1]:6s} delta={r[2]} val={int(r[3]):,} price={r[4]:.3f} {r[5]} cnt={r[6]}')

print('\nNEW + ESCALATION alerts (nano):')
cur.execute('SELECT ts, sym, tag, delta, value1m, vwap1m, direction FROM alerts WHERE tag IN (?,?) AND vwap1m<5 ORDER BY value1m DESC LIMIT 20', ('new','escalation'))
for r in cur.fetchall():
    print(f'  {r[0][:16]} {r[1]:6s} tag={r[2]:12s} delta={r[3]} val={int(r[4]):,} price={r[5]:.3f} {r[6]}')

conn.close()
print('\nDONE')
