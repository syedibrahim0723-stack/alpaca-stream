"""Batch analysis HTML — served at /batch"""

BATCH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Batch Backtest — 100xTrade</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI',system-ui,sans-serif}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}

header{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;
       display:flex;align-items:center;gap:14px;flex-wrap:wrap}
header h1{font-size:1.08rem;font-weight:700;color:#58a6ff;white-space:nowrap}
.nav-link{font-size:.80rem;color:#8b949e;padding:4px 10px;border:1px solid #30363d;
          border-radius:5px;background:#21262d}
.nav-link:hover{color:#e6edf3;background:#2d333b;text-decoration:none}

.container{max-width:1380px;margin:0 auto;padding:14px}

/* controls */
.controls{background:#161b22;border:1px solid #30363d;border-radius:10px;
          padding:12px 16px;margin-bottom:14px}
.ctrl-row{display:flex;gap:9px;flex-wrap:wrap;align-items:flex-end}
.ctrl-group{display:flex;flex-direction:column;padding:8px 11px;background:#0d1117;
            border:1px solid #21262d;border-radius:7px}
.ctrl-group-label{font-size:.62rem;color:#484f58;text-transform:uppercase;
                  letter-spacing:.08em;margin-bottom:5px;white-space:nowrap}
.ctrl-fields{display:flex;gap:7px;flex-wrap:wrap;align-items:flex-end}
.field{display:flex;flex-direction:column;gap:3px}
label{font-size:.67rem;color:#8b949e;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
label .hint{font-size:.59rem;color:#484f58;text-transform:none;letter-spacing:0}
input[type=number],input[type=time]{background:#161b22;border:1px solid #30363d;
  color:#e6edf3;padding:5px 8px;border-radius:5px;font-size:.87rem;outline:none}
input[type=number]{width:70px}
input[type=time]{width:95px;color-scheme:dark}
input:focus{border-color:#58a6ff}
.btn-run{background:linear-gradient(135deg,#1f6feb,#388bfd);color:#fff;border:none;
         border-radius:6px;padding:8px 22px;font-size:.92rem;font-weight:700;cursor:pointer}
.btn-run:hover{opacity:.85}
.btn-run:disabled{background:#21262d;color:#484f58;cursor:not-allowed}
#status{font-size:.78rem;color:#8b949e;min-height:16px;margin-top:6px}

/* progress */
#progress{display:none;margin-bottom:14px}
.prog-bar-wrap{background:#21262d;border-radius:4px;height:6px;overflow:hidden;margin-bottom:5px}
.prog-bar{background:#1f6feb;height:100%;width:0%;transition:width .3s}
.prog-label{font-size:.76rem;color:#8b949e}

/* cards */
.cards{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.card{background:#161b22;border:1px solid #30363d;border-radius:7px;
      padding:10px 13px;flex:1;min-width:120px}
.card-label{font-size:.64rem;color:#8b949e;text-transform:uppercase;
            letter-spacing:.06em;margin-bottom:3px}
.card-value{font-size:1.22rem;font-weight:700}
.green{color:#3fb950}.red{color:#f85149}.blue{color:#58a6ff}
.yellow{color:#d29922}.purple{color:#bc8cff}.orange{color:#f0883e}

/* rank hypothesis */
.hypothesis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
.hyp-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 16px}
.hyp-title{font-size:.80rem;font-weight:700;margin-bottom:10px;color:#e6edf3}
.hyp-row{display:flex;justify-content:space-between;font-size:.78rem;
         color:#8b949e;padding:3px 0;border-bottom:1px solid #21262d}
.hyp-row:last-child{border-bottom:none}
.hyp-row b{color:#e6edf3}
.hyp-winner{border-color:#3fb950!important;background:#0d1f15}
.hyp-winner .hyp-title{color:#3fb950}

/* charts row */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.chart-box{background:#161b22;border:1px solid #30363d;border-radius:8px;
           padding:10px 14px;height:260px}

/* tables */
.section-title{font-size:.88rem;font-weight:600;margin-bottom:8px;
               display:flex;align-items:center;gap:8px}
.tag{background:#21262d;border-radius:4px;padding:2px 7px;
     font-size:.68rem;color:#8b949e;font-weight:400}
.tbl-wrap{overflow-x:auto;margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:.80rem}
th{background:#21262d;color:#8b949e;padding:6px 10px;text-align:left;
   font-weight:500;border-bottom:1px solid #30363d;white-space:nowrap;cursor:pointer}
th:hover{color:#e6edf3}
th.sort-asc::after{content:' ↑'}
th.sort-desc::after{content:' ↓'}
td{padding:6px 10px;border-bottom:1px solid #21262d;white-space:nowrap}
tr:hover td{background:#1c2128}

/* rank badges */
.rk1{background:#b8860b22;color:#d4a017;border-radius:4px;padding:1px 6px;font-weight:700;font-size:.72rem}
.rk2{background:#70706022;color:#a0a080;border-radius:4px;padding:1px 6px;font-weight:700;font-size:.72rem}
.rk3{background:#80604020;color:#8b7355;border-radius:4px;padding:1px 6px;font-weight:700;font-size:.72rem}
.rk45{background:#30363d;color:#8b949e;border-radius:4px;padding:1px 6px;font-size:.72rem}

/* day row coloring by PNL */
.day-pos td:first-child{border-left:3px solid #3fb950}
.day-neg td:first-child{border-left:3px solid #f85149}
.day-zero td:first-child{border-left:3px solid #484f58}
</style>
</head>
<body>

<header>
  <h1>&#128202; Batch Backtest — Premarket Sweep Stocks</h1>
  <a class="nav-link" href="/">&#9654; Single Day</a>
  <a class="nav-link" href="/multiday">&#128197; Multi-Day</a>
  <a class="nav-link" href="/momentum">&#9889; Momentum</a>
  <a class="nav-link" href="/alerts">&#128276; Alerts</a>
  <a class="nav-link" href="/lowfloat">Low Float</a>
</header>

<div class="container">

<!-- controls -->
<div class="controls">
  <div class="ctrl-row">
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
      <div class="ctrl-group-label">Trailing Stop</div>
      <div class="ctrl-fields">
        <div class="field"><label>RSI trigger</label><input type="number" id="rsiTrailTrigger" value="60" min="30" max="99"></div>
        <div class="field"><label>Price +%</label><input type="number" id="trailActivate" value="3" min="0.1" max="50" step="0.5"></div>
        <div class="field"><label>Trail %</label><input type="number" id="trailDist" value="3" min="0.1" max="30" step="0.5"></div>
      </div>
    </div>
    <div class="ctrl-group">
      <div class="ctrl-group-label">Time Windows</div>
      <div class="ctrl-fields">
        <div class="field">
          <label>Start Time ET <span class="hint">buys open</span></label>
          <input type="time" id="startTime" value="09:30">
        </div>
        <div class="field">
          <label>Exit Time ET <span class="hint">close profitable</span></label>
          <input type="time" id="exitTime" value="13:00">
        </div>
        <div class="field">
          <label>Final Exit ET <span class="hint">close all</span></label>
          <input type="time" id="finalExitTime" value="15:30">
        </div>
      </div>
    </div>
    <div class="ctrl-group">
      <div class="ctrl-group-label">Sizing</div>
      <div class="ctrl-fields">
        <div class="field">
          <label>Buy Amount $ <span class="hint">per dip</span></label>
          <input type="number" id="buyAmount" value="1000" min="100" max="100000" step="100">
        </div>
      </div>
    </div>
    <button class="btn-run" id="runBtn" onclick="runBatch()">&#9654; Run All Days</button>
  </div>
  <div id="status"></div>
</div>

<!-- progress bar -->
<div id="progress">
  <div class="prog-bar-wrap"><div class="prog-bar" id="progBar"></div></div>
  <div class="prog-label" id="progLabel">Running...</div>
</div>

<!-- summary cards -->
<div class="cards" id="cards" style="display:none">
  <div class="card"><div class="card-label">Total PNL</div><div class="card-value" id="cTotal">—</div></div>
  <div class="card"><div class="card-label">Days</div><div class="card-value blue" id="cDays">—</div></div>
  <div class="card"><div class="card-label">Stocks Run</div><div class="card-value blue" id="cStocks">—</div></div>
  <div class="card"><div class="card-label">Total Trades</div><div class="card-value purple" id="cTrades">—</div></div>
  <div class="card"><div class="card-label">Win Days</div><div class="card-value yellow" id="cWinDays">—</div></div>
  <div class="card"><div class="card-label">Avg Day PNL</div><div class="card-value" id="cAvgDay">—</div></div>
  <div class="card"><div class="card-label">Best Day</div><div class="card-value green" id="cBest">—</div></div>
  <div class="card"><div class="card-label">Worst Day</div><div class="card-value red" id="cWorst">—</div></div>
</div>

<!-- rank hypothesis -->
<div id="hypothesis" style="display:none">
  <div class="section-title">&#128204; Rank Hypothesis: Does Rank 1-2 Outperform Rank 4-5?</div>
  <div class="hypothesis">
    <div class="hyp-card" id="grp12">
      <div class="hyp-title">&#129351; Rank 1-2 (Top Sweeps)</div>
      <div class="hyp-row"><span>Trades</span><b id="h12count">—</b></div>
      <div class="hyp-row"><span>Total PNL</span><b id="h12total">—</b></div>
      <div class="hyp-row"><span>Avg PNL/trade</span><b id="h12avg">—</b></div>
      <div class="hyp-row"><span>Win Rate</span><b id="h12wr">—</b></div>
    </div>
    <div class="hyp-card" id="grp3">
      <div class="hyp-title">&#129352; Rank 3 (Middle)</div>
      <div class="hyp-row"><span>Trades</span><b id="h3count">—</b></div>
      <div class="hyp-row"><span>Total PNL</span><b id="h3total">—</b></div>
      <div class="hyp-row"><span>Avg PNL/trade</span><b id="h3avg">—</b></div>
      <div class="hyp-row"><span>Win Rate</span><b id="h3wr">—</b></div>
    </div>
    <div class="hyp-card" id="grp45">
      <div class="hyp-title">&#129353; Rank 4-5 (Lower Sweeps)</div>
      <div class="hyp-row"><span>Trades</span><b id="h45count">—</b></div>
      <div class="hyp-row"><span>Total PNL</span><b id="h45total">—</b></div>
      <div class="hyp-row"><span>Avg PNL/trade</span><b id="h45avg">—</b></div>
      <div class="hyp-row"><span>Win Rate</span><b id="h45wr">—</b></div>
    </div>
  </div>
</div>

<!-- charts -->
<div class="charts-row" id="chartsRow" style="display:none">
  <div class="chart-box"><canvas id="dailyPnlChart"></canvas></div>
  <div class="chart-box"><canvas id="rankChart"></canvas></div>
</div>

<!-- daily summary table -->
<div id="dailySection" style="display:none">
  <div class="section-title">Daily PNL Summary <span class="tag" id="dailyTag"></span></div>
  <div class="tbl-wrap">
    <table id="dailyTable">
      <thead>
        <tr>
          <th onclick="sortTable('daily',0)">Date</th>
          <th onclick="sortTable('daily',1)">Day PNL</th>
          <th onclick="sortTable('daily',2)">Trades</th>
          <th>Rank&#x00A0;1</th>
          <th>Rank&#x00A0;2</th>
          <th>Rank&#x00A0;3</th>
          <th>Rank&#x00A0;4</th>
          <th>Rank&#x00A0;5</th>
        </tr>
      </thead>
      <tbody id="dailyBody"></tbody>
    </table>
  </div>
</div>

<!-- all-tickers table -->
<div id="tickerSection" style="display:none">
  <div class="section-title">All Ticker Results <span class="tag" id="tickerTag"></span></div>
  <div class="tbl-wrap">
    <table id="tickerTable">
      <thead>
        <tr>
          <th onclick="sortTable('ticker',0)">Date</th>
          <th onclick="sortTable('ticker',1)">Symbol</th>
          <th onclick="sortTable('ticker',2)">Rank</th>
          <th onclick="sortTable('ticker',3)">Sweeps</th>
          <th onclick="sortTable('ticker',4)">Net PNL</th>
          <th onclick="sortTable('ticker',5)">Trades</th>
          <th onclick="sortTable('ticker',6)">Status</th>
        </tr>
      </thead>
      <tbody id="tickerBody"></tbody>
    </table>
  </div>
</div>

</div>

<script>
let dailyChart = null, rankChart = null;
let _dailyData = [], _tickerData = [];

const $ = id => document.getElementById(id);
const fmtPnl = v => (v >= 0 ? '+' : '') + '$' + v.toFixed(2);
const cls = v => v > 0 ? 'green' : v < 0 ? 'red' : '';

async function runBatch() {
  const btn = $('runBtn');
  btn.disabled = true;
  $('status').textContent = 'Sending request...';
  ['cards','hypothesis','chartsRow','dailySection','tickerSection'].forEach(id =>
    $(id).style.display = 'none');

  const qs = new URLSearchParams({
    rsi_period:           +$('rsiPeriod').value         || 12,
    rsi_buy:              +$('rsiBuy').value            || 30,
    rsi_sell:             +$('rsiSell').value           || 65,
    profit_target_pct:    +$('profitTarget').value,
    trail_pct:            +$('trailDist').value         || 3,
    trail_activate_pct:   +$('trailActivate').value     || 3,
    rsi_trail_trigger:    +$('rsiTrailTrigger').value   || 60,
    start_time_str:       $('startTime').value          || '09:30',
    exit_time_str:        $('exitTime').value           || '13:00',
    final_exit_time_str:  $('finalExitTime').value      || '15:30',
    buy_amount:           +$('buyAmount').value         || 1000,
    concurrency:          8,
  });

  // Show progress (fake poll — actual request is single call)
  $('progress').style.display = 'block';
  const prog = $('progBar');
  const progLbl = $('progLabel');
  prog.style.width = '5%';
  progLbl.textContent = 'Fetching all days in parallel (this may take ~30s)...';

  // Animate progress bar while waiting
  let pct = 5;
  const ticker = setInterval(() => {
    pct = Math.min(pct + 2, 90);
    prog.style.width = pct + '%';
  }, 800);

  try {
    const res  = await fetch('/api/batch?' + qs);
    clearInterval(ticker);
    prog.style.width = '100%';

    if (!res.ok) {
      const e = await res.json();
      $('status').textContent = 'Error: ' + (e.detail || res.statusText);
      $('progress').style.display = 'none';
      return;
    }
    const data = await res.json();
    $('progress').style.display = 'none';
    $('status').textContent = 'Done — ' + data.total_rows + ' rows | Total PNL: $' + data.total_pnl;
    render(data);
  } catch(e) {
    clearInterval(ticker);
    $('progress').style.display = 'none';
    $('status').textContent = 'Network error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

function render(data) {
  const { daily, rank_groups, rows, total_pnl } = data;
  _dailyData  = daily;
  _tickerData = rows;

  // ── Summary cards ──
  const winDays  = daily.filter(d => d.total_pnl > 0).length;
  const allDayPnl= daily.map(d => d.total_pnl);
  const avgDay   = daily.length ? (total_pnl / daily.length) : 0;
  const bestDay  = daily.reduce((a,b) => b.total_pnl > a.total_pnl ? b : a, daily[0]);
  const worstDay = daily.reduce((a,b) => b.total_pnl < a.total_pnl ? b : a, daily[0]);
  const totalTrades = rows.reduce((s,r) => s + (r.trades||[]).length, 0);

  const pEl = $('cTotal');
  pEl.textContent = fmtPnl(total_pnl);
  pEl.className   = 'card-value ' + cls(total_pnl);
  $('cDays').textContent   = daily.length;
  $('cStocks').textContent = rows.length;
  $('cTrades').textContent = totalTrades;
  $('cWinDays').textContent= winDays + '/' + daily.length;
  const aEl = $('cAvgDay');
  aEl.textContent = fmtPnl(avgDay);
  aEl.className   = 'card-value ' + cls(avgDay);
  $('cBest').textContent  = bestDay  ? bestDay.date  + ' ' + fmtPnl(bestDay.total_pnl)  : '—';
  $('cWorst').textContent = worstDay ? worstDay.date + ' ' + fmtPnl(worstDay.total_pnl) : '—';
  $('cards').style.display = 'flex';

  // ── Rank hypothesis ──
  const grps = [
    {id:'12', key:'1-2', el:'grp12'}, {id:'3', key:'3', el:'grp3'}, {id:'45', key:'4-5', el:'grp45'}
  ];
  let bestGrpAvg = -Infinity, bestGrpEl = null;
  grps.forEach(g => {
    const gd = rank_groups[g.key] || {};
    $('h' + g.id + 'count').textContent = gd.count || 0;
    const tot = $('h' + g.id + 'total');
    tot.textContent = fmtPnl(gd.total || 0);
    tot.className   = cls(gd.total || 0);
    const avg = $('h' + g.id + 'avg');
    avg.textContent = fmtPnl(gd.avg || 0);
    avg.className   = cls(gd.avg || 0);
    $('h' + g.id + 'wr').textContent = (gd.win_rate || 0) + '% (' + (gd.wins||0) + '/' + (gd.count||0) + ')';
    if ((gd.avg || 0) > bestGrpAvg) { bestGrpAvg = gd.avg || 0; bestGrpEl = g.el; }
  });
  // Highlight winner
  ['grp12','grp3','grp45'].forEach(id => {
    $(id).className = 'hyp-card' + (id === bestGrpEl ? ' hyp-winner' : '');
  });
  $('hypothesis').style.display = 'block';

  // ── Charts ──
  drawDailyChart(daily);
  drawRankChart(rank_groups);
  $('chartsRow').style.display = 'grid';

  // ── Daily table ──
  renderDailyTable(daily);
  $('dailyTag').textContent = daily.length + ' trading days';
  $('dailySection').style.display = 'block';

  // ── Ticker table ──
  renderTickerTable(rows);
  $('tickerTag').textContent = rows.length + ' ticker results';
  $('tickerSection').style.display = 'block';
}

// ── Charts ─────────────────────────────────────────────────────────────────

function drawDailyChart(daily) {
  if (dailyChart) { dailyChart.destroy(); dailyChart = null; }
  const labels = daily.map(d => d.date.slice(5)); // MM-DD
  const pnls   = daily.map(d => d.total_pnl);
  const colors = pnls.map(v => v >= 0 ? 'rgba(63,185,80,.75)' : 'rgba(248,81,73,.75)');

  dailyChart = new Chart($('dailyPnlChart').getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{
      label: 'Day PNL ($)', data: pnls,
      backgroundColor: colors, borderColor: colors, borderWidth: 1,
    }]},
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: { labels: { color: '#8b949e' } },
        title:  { display: true, text: 'Daily Net PNL', color: '#e6edf3', font: { size: 13 } },
      },
      scales: {
        x: { ticks: { color: '#8b949e', maxRotation: 45 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } }
      }
    }
  });
}

function drawRankChart(rank_groups) {
  if (rankChart) { rankChart.destroy(); rankChart = null; }
  const grpKeys = ['1-2','3','4-5'];
  const labels  = ['Rank 1-2', 'Rank 3', 'Rank 4-5'];
  const totals  = grpKeys.map(k => (rank_groups[k]||{}).total || 0);
  const avgs    = grpKeys.map(k => (rank_groups[k]||{}).avg   || 0);
  const wrs     = grpKeys.map(k => (rank_groups[k]||{}).win_rate || 0);

  rankChart = new Chart($('rankChart').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Total PNL ($)', data: totals, backgroundColor: 'rgba(88,166,255,.7)', yAxisID: 'y' },
        { label: 'Avg PNL/trade ($)', data: avgs, backgroundColor: 'rgba(240,136,62,.7)', yAxisID: 'y' },
        { label: 'Win Rate (%)', data: wrs, backgroundColor: 'rgba(188,140,255,.5)',
          type: 'line', yAxisID: 'y2', borderColor: '#bc8cff', pointRadius: 5, tension: 0 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: {
        legend: { labels: { color: '#8b949e', boxWidth: 11, font: { size: 10 } } },
        title:  { display: true, text: 'Rank Group Comparison', color: '#e6edf3', font: { size: 13 } },
      },
      scales: {
        x:  { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
        y:  { ticks: { color: '#8b949e' }, grid: { color: '#21262d' }, position: 'left' },
        y2: { ticks: { color: '#bc8cff' }, position: 'right', grid: { drawOnChartArea: false },
              min: 0, max: 100 }
      }
    }
  });
}

// ── Daily table ──────────────────────────────────────────────────────────────

function renderDailyTable(daily) {
  const tbody = $('dailyBody');
  tbody.innerHTML = '';
  daily.forEach(d => {
    const rowCls = d.total_pnl > 0 ? 'day-pos' : d.total_pnl < 0 ? 'day-neg' : 'day-zero';
    // Build rank cells
    let rankCells = '';
    for (let rk = 1; rk <= 5; rk++) {
      const ri = d.ranks[rk];
      if (!ri) { rankCells += '<td style="color:#484f58">—</td>'; continue; }
      const pnl = ri.net_pnl;
      const pc  = pnl > 0 ? 'green' : pnl < 0 ? 'red' : '';
      const sym = ri.error ? '<span style="color:#f85149">' + ri.symbol + ' ✗</span>' : ri.symbol;
      rankCells += '<td>' + sym + ' <span class="' + pc + '" style="font-weight:700">'
                 + fmtPnl(pnl) + '</span></td>';
    }
    tbody.innerHTML +=
      '<tr class="' + rowCls + '">' +
        '<td>' + d.date + '</td>' +
        '<td class="' + cls(d.total_pnl) + '" style="font-weight:700">' + fmtPnl(d.total_pnl) + '</td>' +
        '<td>' + d.total_trades + '</td>' +
        rankCells +
      '</tr>';
  });
}

// ── Ticker table ─────────────────────────────────────────────────────────────

function renderTickerTable(rows) {
  const tbody = $('tickerBody');
  tbody.innerHTML = '';
  rows.forEach(r => {
    const rkBadge = r.rank <= 2 ? 'rk' + r.rank : r.rank === 3 ? 'rk3' : 'rk45';
    const rkLabel = r.rank <= 2 ? '#' + r.rank + ' &#9733;' : '#' + r.rank;
    const pnl     = r.net_pnl || 0;
    const trades  = (r.trades||[]).length;
    const status  = r.error ? '<span style="color:#f85149">No data</span>'
                  : trades === 0 ? '<span style="color:#484f58">No trades</span>'
                  : '<span class="green">&#10003; ' + trades + ' exit' + (trades!==1?'s':'') + '</span>';
    tbody.innerHTML +=
      '<tr>' +
        '<td>' + r.date + '</td>' +
        '<td style="font-weight:600;color:#58a6ff">' + r.symbol + '</td>' +
        '<td><span class="' + rkBadge + '">' + rkLabel + '</span></td>' +
        '<td>' + r.sweep_count + '</td>' +
        '<td class="' + cls(pnl) + '" style="font-weight:700">' + fmtPnl(pnl) + '</td>' +
        '<td>' + trades + '</td>' +
        '<td>' + status + '</td>' +
      '</tr>';
  });
}

// ── Sort ──────────────────────────────────────────────────────────────────────

const sortState = {};
function sortTable(which, colIdx) {
  const key  = which + '-' + colIdx;
  const asc  = sortState[key] !== true;
  sortState[key] = asc;

  // Update header indicators
  const tbl = $(which === 'daily' ? 'dailyTable' : 'tickerTable');
  tbl.querySelectorAll('th').forEach((th, i) => {
    th.className = i === colIdx ? (asc ? 'sort-asc' : 'sort-desc') : '';
  });

  const getVal = (row, idx) => {
    const td = row.querySelectorAll('td')[idx];
    if (!td) return '';
    const txt = td.textContent.replace(/[+$,★✓✗]/g,'').trim();
    const n = parseFloat(txt);
    return isNaN(n) ? txt.toLowerCase() : n;
  };
  const tbody = $(which === 'daily' ? 'dailyBody' : 'tickerBody');
  const trs   = Array.from(tbody.querySelectorAll('tr'));
  trs.sort((a, b) => {
    const va = getVal(a, colIdx), vb = getVal(b, colIdx);
    if (va < vb) return asc ? -1 : 1;
    if (va > vb) return asc ? 1 : -1;
    return 0;
  });
  trs.forEach(tr => tbody.appendChild(tr));
}
</script>
</body>
</html>"""
