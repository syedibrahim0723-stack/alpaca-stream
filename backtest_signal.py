import csv, pytz, math, sys
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

ET           = pytz.timezone('America/New_York')
NOTIONAL     = 1000.0
ENTRY_CONSEC = 2   # consecutive bull sweeps to enter
EXIT_CONSEC  = 2   # consecutive bear sweeps to exit
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


def simulate_signal(sweeps):
    """
    Buy on 2nd consecutive bull sweep.
    Sell on 2nd consecutive bear sweep.
    No stop loss — pure signal exit.
    """
    trades   = []
    consec_bull = 0
    consec_bear = 0
    in_pos   = False
    entry_price = shares = 0

    for s in sweeps:
        if s['dir'] == 'neutral':
            continue

        if not in_pos:
            if s['dir'] == 'bull':
                consec_bull += 1
                consec_bear  = 0
                if consec_bull == ENTRY_CONSEC:
                    entry_price = s['price']
                    shares = math.floor(NOTIONAL / entry_price)
                    if shares < 1:
                        consec_bull = 0
                        continue
                    in_pos = True
                    trades.append({'entry': entry_price, 'shares': shares,
                                   'entry_ts': s['ts'], 'exit': None,
                                   'exit_ts': None, 'exit_reason': None})
                    consec_bull = 0
                    consec_bear = 0
            else:  # bear
                consec_bear += 1
                consec_bull  = 0
        else:
            # in position — watch for 2 consecutive bear sweeps to exit
            if s['dir'] == 'bear':
                consec_bear += 1
                consec_bull  = 0
                if consec_bear == EXIT_CONSEC:
                    trades[-1]['exit']        = s['price']
                    trades[-1]['exit_ts']     = s['ts']
                    trades[-1]['exit_reason'] = 'signal'
                    in_pos      = False
                    consec_bear = 0
                    consec_bull = 0
            else:  # bull while in position — reset bear count
                consec_bull += 1
                consec_bear  = 0

    # still open at end of data — close at last price
    if in_pos and sweeps:
        trades[-1]['exit']        = sweeps[-1]['price']
        trades[-1]['exit_ts']     = sweeps[-1]['ts']
        trades[-1]['exit_reason'] = 'eod'

    closed = [t for t in trades if t['exit'] is not None]
    pnl    = sum((t['exit'] - t['entry']) * t['shares'] for t in closed)
    wins   = sum(1 for t in closed if t['exit'] > t['entry'])
    return len(closed), wins, pnl, closed


all_signal = []
all_stop   = []   # previous trailing stop results for comparison

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
        n, w, p, closed = simulate_signal(sweeps)
        all_signal.append({'day': day, 'sym': sym, 'bull_h1': bull_cnt,
                            'n': n, 'wins': w, 'pnl': p, 'trades': closed})

# Print full trade log for a sample stock (ATRA May 7 — most active)
print("=== Sample trade log: ATRA 2026-05-07 ===")
sample = next((r for r in all_signal if r['sym']=='ATRA' and r['day']=='2026-05-07'), None)
if sample:
    for i, t in enumerate(sample['trades'][:20]):
        pct = (t['exit']/t['entry']-1)*100
        print("  Trade {:>3}: buy {:>7.4f}  sell {:>7.4f}  {:>+6.2f}%  {}sh  PnL={:>+7.2f}  [{}]  {} -> {}".format(
            i+1, t['entry'], t['exit'], pct, t['shares'],
            (t['exit']-t['entry'])*t['shares'],
            t['exit_reason'],
            t['entry_ts'].strftime('%H:%M:%S'),
            t['exit_ts'].strftime('%H:%M:%S')))
    if len(sample['trades']) > 20:
        print(f"  ... and {len(sample['trades'])-20} more trades")
print()

# Summary table
H = "{:<12} {:<8} {:>6}    {:>6} {:>5} {:>9}  {}"
R = "{:<12} {:<8} {:>6}    {:>6} {:>4}% {:>+9.2f}  {}"
print(H.format("Day", "Sym", "BullH1", "Trades", "Win%", "PnL", "Note"))
print("-" * 70)

grand_pnl    = 0
grand_trades = 0
grand_wins   = 0

for r in all_signal:
    wr = r['wins'] / r['n'] * 100 if r['n'] else 0
    grand_pnl    += r['pnl']
    grand_trades += r['n']
    grand_wins   += r['wins']
    note = ">$1000/sh" if r['n'] == 0 else ""
    print(R.format(r['day'], r['sym'], r['bull_h1'], r['n'], int(wr), r['pnl'], note))

print("-" * 70)
gwr = grand_wins / grand_trades * 100 if grand_trades else 0
print("{:<38}    {:>6} {:>4}% {:>+9.2f}".format(
    "GRAND TOTAL", grand_trades, int(gwr), grand_pnl))
print()
print("Comparison:")
print("  Buy 2xBull / Sell trailing stop 2%  : +$2,045.77  (285 trades, ~44% win rate)")
print("  Buy 2xBull / Short 2xBear (separate): +$2,247.94  (302 trades)")
print("  Buy 2xBull / Sell on 2xBear (this)  : {:>+9.2f}  ({} trades, {}% win rate)".format(
    grand_pnl, grand_trades, int(gwr)))
