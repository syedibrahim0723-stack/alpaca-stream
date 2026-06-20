import csv, pytz, math, sys
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

ET           = pytz.timezone('America/New_York')
NOTIONAL     = 1000.0
ENTRY_CONSEC = 2
CSV_PATH     = "alert_history.csv"

with open(CSV_PATH, encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

day_sym_sweeps = defaultdict(lambda: defaultdict(list))
for r in rows:
    if r['type'] != 'sweep':
        continue
    if r['direction'] not in ('bull', 'bear', 'neutral'):
        continue
    try:
        price = float(r['vwap1m'])
        if price <= 0:
            continue
        ts = datetime.fromisoformat(r['ts'].replace('Z', '+00:00')).astimezone(ET)
    except Exception:
        continue
    day = ts.strftime('%Y-%m-%d')
    day_sym_sweeps[day][r['sym']].append({'ts': ts, 'dir': r['direction'], 'price': price})


def simulate(sweeps, trigger_dir, stop_mult, n_consec):
    opposite = 'bull' if trigger_dir == 'bear' else 'bear'
    trades = []
    consec = 0
    in_pos = False
    entry_price = stop_price = stop_basis = shares = 0

    for s in sweeps:
        if s['dir'] == 'neutral':
            continue
        if not in_pos:
            if s['dir'] == trigger_dir:
                consec += 1
                if consec == n_consec:
                    entry_price = s['price']
                    shares = math.floor(NOTIONAL / entry_price)
                    if shares < 1:
                        consec = 0
                        continue
                    stop_basis = entry_price
                    stop_price = round(entry_price * stop_mult, 4)
                    in_pos = True
                    trades.append({'entry': entry_price, 'shares': shares,
                                   'entry_ts': s['ts'], 'exit': None, 'exit_ts': None})
                    consec = 0
            else:
                consec = 0
        else:
            if trigger_dir == 'bull':
                if s['dir'] == 'bull' and s['price'] > stop_basis:
                    stop_basis = s['price']
                    stop_price = round(s['price'] * stop_mult, 4)
                elif s['dir'] == 'bear' and s['price'] <= stop_price:
                    trades[-1]['exit']    = stop_price
                    trades[-1]['exit_ts'] = s['ts']
                    in_pos = False
                    consec = 0
            else:
                if s['dir'] == 'bear' and s['price'] < stop_basis:
                    stop_basis = s['price']
                    stop_price = round(s['price'] * stop_mult, 4)
                elif s['dir'] == 'bull' and s['price'] >= stop_price:
                    trades[-1]['exit']    = stop_price
                    trades[-1]['exit_ts'] = s['ts']
                    in_pos = False
                    consec = 0

    if in_pos and sweeps:
        trades[-1]['exit']    = sweeps[-1]['price']
        trades[-1]['exit_ts'] = sweeps[-1]['ts']

    closed = [t for t in trades if t['exit'] is not None]
    if trigger_dir == 'bull':
        pnl  = sum((t['exit'] - t['entry']) * t['shares'] for t in closed)
        wins = sum(1 for t in closed if t['exit'] > t['entry'])
    else:
        pnl  = sum((t['entry'] - t['exit']) * t['shares'] for t in closed)
        wins = sum(1 for t in closed if t['exit'] < t['entry'])
    return len(closed), wins, pnl, closed


all_long  = []
all_short = []

for day in sorted(day_sym_sweeps.keys()):
    market_open = ET.localize(datetime.strptime(day + ' 09:30:00', '%Y-%m-%d %H:%M:%S'))
    market_h1   = ET.localize(datetime.strptime(day + ' 10:30:00', '%Y-%m-%d %H:%M:%S'))

    bull_h1 = {}
    for sym, sweeps in day_sym_sweeps[day].items():
        cnt = sum(1 for s in sweeps if s['dir'] == 'bull' and market_open <= s['ts'] < market_h1)
        if cnt > 0:
            bull_h1[sym] = cnt

    top3 = sorted(bull_h1.items(), key=lambda x: -x[1])[:3]
    if not top3:
        continue

    for sym, bull_cnt in top3:
        sweeps = sorted(day_sym_sweeps[day][sym], key=lambda x: x['ts'])

        n_l, w_l, p_l, tl = simulate(sweeps, 'bull', 0.98, ENTRY_CONSEC)
        n_s, w_s, p_s, ts_ = simulate(sweeps, 'bear', 1.02, ENTRY_CONSEC)

        all_long.append( {'day': day, 'sym': sym, 'bull_h1': bull_cnt,
                           'n': n_l, 'wins': w_l, 'pnl': p_l})
        all_short.append({'day': day, 'sym': sym, 'bull_h1': bull_cnt,
                           'n': n_s, 'wins': w_s, 'pnl': p_s})

# Print results
H = "{:<12} {:<8} {:>6}    {:>6} {:>5} {:>9}    {:>6} {:>5} {:>9}"
S = "{:<12} {:<8} {:>6}    {:>6} {:>4}% {:>+9.2f}    {:>6} {:>4}% {:>+9.2f}{}"
print(H.format("Day", "Sym", "BullH1", "Trades", "Win%", "PnL", "Trades", "Win%", "PnL"))
print("{:<30}    {:<21}    {:<22}".format("", "-- LONG  2xBull --", "-- SHORT 2xBear --"))
print("-" * 86)

gl = gs = 0
for l, s in zip(all_long, all_short):
    wl   = l['wins'] / l['n'] * 100 if l['n'] else 0
    ws   = s['wins'] / s['n'] * 100 if s['n'] else 0
    gl  += l['pnl']
    gs  += s['pnl']
    note = "  (>$1000/sh)" if l['n'] == 0 else ""
    print(S.format(l['day'], l['sym'], l['bull_h1'],
                   l['n'], int(wl), l['pnl'],
                   s['n'], int(ws), s['pnl'], note))

print("-" * 86)
tl = sum(r['n'] for r in all_long)
ts = sum(r['n'] for r in all_short)
print("{:<38}    {:>6} {:>5} {:>+9.2f}    {:>6} {:>5} {:>+9.2f}".format(
    "GRAND TOTAL", tl, "", gl, ts, "", gs))
print()
print("Long  only : {:>+9.2f}  ({} trades)".format(gl, tl))
print("Short only : {:>+9.2f}  ({} trades)".format(gs, ts))
print("Combined   : {:>+9.2f}  ({} trades)".format(gl + gs, tl + ts))
