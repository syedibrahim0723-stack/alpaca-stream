MULTIDAY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Multi-Day (Overnight) RSI Backtest</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0d0f14;color:#e2e8f0;min-height:100vh}
a{color:#60a5fa;text-decoration:none}a:hover{text-decoration:underline}

.nav{display:flex;align-items:center;gap:16px;padding:10px 22px;background:#161b26;border-bottom:1px solid #2d3748;flex-wrap:wrap}
.nav-title{font-size:.95rem;font-weight:700;color:#fff;white-space:nowrap;margin-right:6px}
.nav a{font-size:.82rem;color:#94a3b8;padding:4px 10px;border-radius:6px;transition:background .2s}
.nav a:hover,.nav a.active{background:#2d3748;color:#e2e8f0;text-decoration:none}

.container{max-width:1380px;margin:0 auto;padding:18px 22px}
.panel{background:#161b26;border:1px solid #2d3748;border-radius:12px;padding:18px 20px;margin-bottom:18px}
h2{font-size:.78rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}

/* Controls */
.ctrl-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
@media(max-width:900px){.ctrl-grid{grid-template-columns:1fr 1fr}}
@media(max-width:580px){.ctrl-grid{grid-template-columns:1fr}}
.ctrl-section{background:#1e2535;border-radius:10px;padding:13px 15px}
.ctrl-section h3{font-size:.7rem;font-weight:700;color:#60a5fa;text-transform:uppercase;letter-spacing:.08em;margin-bottom:9px}
.f{display:flex;flex-direction:column;gap:3px;margin-bottom:7px}
.f:last-child{margin-bottom:0}
.f label{font-size:.68rem;color:#94a3b8}
.f input{background:#0d0f14;border:1px solid #374151;border-radius:6px;color:#e2e8f0;padding:5px 8px;font-size:.84rem;width:100%}
.f input:focus{outline:none;border-color:#60a5fa}

/* Chip ticker input */
.sym-wrap{display:flex;flex-wrap:wrap;gap:5px;align-items:center;background:#0d0f14;border:1px solid #374151;border-radius:8px;padding:5px 8px;min-height:36px;cursor:text}
.chip{display:flex;align-items:center;gap:4px;background:#1e3a5f;border-radius:20px;padding:2px 10px;font-size:.78rem;color:#93c5fd}
.chip button{background:none;border:none;color:#93c5fd;cursor:pointer;font-size:.88rem;line-height:1;padding:0}
.chip button:hover{color:#f87171}
.sym-input{background:none;border:none;color:#e2e8f0;font-size:.84rem;outline:none;min-width:70px;flex:1}

/* Date row */
.date-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:13px}
.date-row .f{flex:1;min-width:145px;margin-bottom:0}

/* Badge: overnight notice */
.notice{background:#1a2a1a;border:1px solid #166534;border-radius:8px;padding:8px 14px;font-size:.78rem;color:#86efac;margin-bottom:14px;line-height:1.5}
.notice strong{color:#4ade80}

/* Run button */
.run-btn{background:linear-gradient(135deg,#3b82f6,#6366f1);border:none;border-radius:8px;color:#fff;cursor:pointer;font-size:.88rem;font-weight:600;padding:9px 26px;transition:opacity .2s}
.run-btn:hover{opacity:.85}.run-btn:disabled{opacity:.45;cursor:not-allowed}

/* Progress */
.prog-wrap{display:none;margin-top:12px}
.prog-bar{height:5px;background:#1e2535;border-radius:3px;overflow:hidden}
.prog-fill{height:100%;width:0%;background:linear-gradient(90deg,#3b82f6,#6366f1);border-radius:3px;transition:width .35s}
.prog-lbl{font-size:.72rem;color:#94a3b8;margin-top:4px;text-align:center}

/* Summary cards */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px}
.card{background:#161b26;border:1px solid #2d3748;border-radius:10px;padding:13px;text-align:center}
.card-label{font-size:.67rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.card-val{font-size:1.3rem;font-weight:700}
.green{color:#34d399}.red{color:#f87171}.white{color:#e2e8f0}.blue{color:#60a5fa}.yellow{color:#fbbf24}.purple{color:#a78bfa}

/* Symbol cards */
.sym-cards{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}
.sym-card{background:#161b26;border:1px solid #2d3748;border-radius:10px;padding:13px 16px;min-width:155px;flex:1}
.sym-card-title{font-size:.84rem;font-weight:700;margin-bottom:7px}
.sym-card-stat{display:flex;justify-content:space-between;font-size:.75rem;color:#94a3b8;margin-bottom:2px}
.sym-card-stat span:last-child{color:#e2e8f0;font-weight:600}
.open-badge{display:inline-block;background:#2a1f00;border:1px solid #ca8a04;color:#fbbf24;border-radius:10px;font-size:.65rem;padding:1px 7px;margin-left:5px}

/* Charts */
.chart-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px}
@media(max-width:860px){.chart-row{grid-template-columns:1fr}}
.chart-box{background:#161b26;border:1px solid #2d3748;border-radius:12px;padding:14px}
.chart-box canvas{max-height:260px}

/* Tables */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{background:#1a2035;color:#94a3b8;text-transform:uppercase;font-size:.65rem;letter-spacing:.05em;padding:7px 9px;text-align:right;cursor:pointer;white-space:nowrap}
th:first-child,th:nth-child(2){text-align:left}
th:hover{color:#e2e8f0}
td{padding:6px 9px;border-bottom:1px solid #1e2535;text-align:right;white-space:nowrap}
td:first-child,td:nth-child(2){text-align:left}
tr:hover td{background:#1a2035}
.pp{color:#34d399;font-weight:600}.np{color:#f87171;font-weight:600}.zp{color:#94a3b8}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:.68rem;font-weight:600}
.b-sym{background:#1e3a5f;color:#93c5fd}
.b-open{background:#2a1f00;color:#fbbf24;border:1px solid #ca8a04}
.b-trail{background:#1e2a1e;color:#86efac}
.b-target{background:#1e2a2a;color:#67e8f9}
.b-eod{background:#2a2a1e;color:#fbbf24}

/* Expand rows */
.exp-row{display:none}
.exp-row td{padding:0;border-bottom:none}
.exp-inner{background:#111827;padding:8px 14px;border-bottom:1px solid #374151}
.leg-tbl{width:100%;border-collapse:collapse;font-size:.73rem}
.leg-tbl th{background:#0d0f14;color:#6b7280;padding:3px 7px;text-align:right}
.leg-tbl th:first-child{text-align:left}
.leg-tbl td{padding:2px 7px;color:#d1d5db;text-align:right}
.leg-tbl td:first-child{text-align:left}
.exp-btn{background:none;border:none;color:#60a5fa;cursor:pointer;font-size:.72rem;padding:0 3px}
.exp-btn:hover{color:#93c5fd}

.err-box{background:#2a1515;border:1px solid #7f1d1d;border-radius:8px;padding:11px;color:#fca5a5;font-size:.83rem;margin-bottom:14px}
.hidden{display:none}
</style>
</head>
<body>

<div class="nav">
  <span class="nav-title">100x RSI Backtester</span>
  <a href="/">Single Day</a>
  <a href="/batch">Batch Analysis</a>
  <a href="/multiday" class="active">Multi-Day Overnight</a>
  <a href="/alerts">Alerts</a>
</div>

<div class="container">
  <div class="panel">
    <h2>Multi-Day Overnight RSI Backtest</h2>

    <div class="notice">
      <strong>Overnight mode:</strong> Positions carry through extended hours and overnight — no forced EOD close.
      Buys only during regular hours (09:30–16:00 ET).
      Trailing stop fires <strong>only when price &gt; avg entry</strong> — never exits at a loss.
    </div>

    <!-- Symbols -->
    <div class="f" style="margin-bottom:12px">
      <label>TICKERS</label>
      <div class="sym-wrap" id="chipWrap" onclick="document.getElementById('symInput').focus()">
        <input class="sym-input" id="symInput" placeholder="Type symbol + Enter…" />
      </div>
    </div>

    <!-- Date range -->
    <div class="date-row">
      <div class="f"><label>Start Date</label><input type="date" id="startDate" /></div>
      <div class="f"><label>End Date</label><input type="date" id="endDate" /></div>
    </div>

    <!-- Param grid -->
    <div class="ctrl-grid">
      <div class="ctrl-section">
        <h3>RSI Settings</h3>
        <div class="f"><label>Period</label><input type="number" id="rsiPeriod" value="12" min="2" max="50"></div>
        <div class="f"><label>Buy ↓ threshold</label><input type="number" id="rsiBuy" value="30" min="1" max="49"></div>
        <div class="f"><label>OB → arms trail</label><input type="number" id="rsiSell" value="65" min="50" max="100"></div>
        <div class="f"><label>Early-arm RSI trigger</label><input type="number" id="rsiTrailTrigger" value="60" min="40" max="100"></div>
      </div>
      <div class="ctrl-section">
        <h3>Instant Exit</h3>
        <div class="f"><label>Profit Target % (0 = off)</label><input type="number" id="profitTarget" value="10" min="0" max="200" step="0.5"></div>
      </div>
      <div class="ctrl-section">
        <h3>Trailing Stop</h3>
        <div class="f"><label>Trail % from peak</label><input type="number" id="trailPct" value="3" min="0.5" max="20" step="0.5"></div>
        <div class="f"><label>Price +% above avg to arm</label><input type="number" id="trailActivate" value="3" min="0.5" max="20" step="0.5"></div>
        <div style="font-size:.7rem;color:#4b5563;margin-top:7px;line-height:1.6">
          No exit-time forcing.<br>
          Trail only fires above avg cost — always.
        </div>
      </div>
    </div>

    <div style="margin-top:13px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <button class="run-btn" id="runBtn" onclick="runAnalysis()">▶ Run Overnight Backtest</button>
      <span id="statusMsg" style="font-size:.78rem;color:#94a3b8"></span>
    </div>

    <div class="prog-wrap" id="progWrap">
      <div class="prog-bar"><div class="prog-fill" id="progFill"></div></div>
      <div class="prog-lbl" id="progLbl">Fetching data…</div>
    </div>
  </div>

  <div class="err-box hidden" id="errBox"></div>

  <div id="results" class="hidden">
    <div class="cards" id="summaryCards"></div>
    <div class="sym-cards" id="symCards"></div>

    <div class="chart-row">
      <div class="chart-box">
        <h2>Cumulative P&amp;L by Symbol</h2>
        <canvas id="cumulChart"></canvas>
      </div>
      <div class="chart-box">
        <h2>Daily Closed P&amp;L (by exit date)</h2>
        <canvas id="dailyChart"></canvas>
      </div>
    </div>

    <div class="panel" style="margin-bottom:16px">
      <h2>Daily Breakdown (by trade exit date)</h2>
      <div class="tbl-wrap">
        <table id="dailyTbl">
          <thead id="dailyHead"></thead>
          <tbody id="dailyBody"></tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h2>All Trades</h2>
      <div class="tbl-wrap">
        <table id="tradesTbl">
          <thead>
            <tr>
              <th onclick="sortTbl('tradesTbl',0)">Symbol</th>
              <th onclick="sortTbl('tradesTbl',1)">Exit Date</th>
              <th onclick="sortTbl('tradesTbl',2)">Avg Entry</th>
              <th onclick="sortTbl('tradesTbl',3)">Shares</th>
              <th onclick="sortTbl('tradesTbl',4)">Cost</th>
              <th onclick="sortTbl('tradesTbl',5)">Exit Price</th>
              <th onclick="sortTbl('tradesTbl',6)">Exit Time</th>
              <th onclick="sortTbl('tradesTbl',7)">P&amp;L</th>
              <th onclick="sortTbl('tradesTbl',8)">Reason</th>
              <th>Legs</th>
            </tr>
          </thead>
          <tbody id="tradesBody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
// ── Chip input ───────────────────────────────────────────────────────────────
const DEFAULT_SYMS = ['SOXL','SOXS','DRAM'];
let chips = [];

function addChip(sym) {
  sym = sym.trim().toUpperCase().replace(/[^A-Z]/g,'');
  if (!sym || chips.includes(sym)) return;
  chips.push(sym);
  renderChips();
}
function removeChip(sym) { chips = chips.filter(s => s !== sym); renderChips(); }
function renderChips() {
  const wrap = document.getElementById('chipWrap');
  const inp  = document.getElementById('symInput');
  wrap.querySelectorAll('.chip').forEach(c => c.remove());
  chips.forEach(sym => {
    const c = document.createElement('div');
    c.className = 'chip';
    c.innerHTML = sym + '<button onclick="removeChip(\'' + sym + '\')" title="Remove">&times;</button>';
    wrap.insertBefore(c, inp);
  });
}
document.getElementById('symInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault(); addChip(e.target.value); e.target.value = '';
  }
  if (e.key === 'Backspace' && !e.target.value && chips.length) {
    removeChip(chips[chips.length - 1]);
  }
});
DEFAULT_SYMS.forEach(addChip);

// ── Default dates ────────────────────────────────────────────────────────────
(function() {
  const today = new Date();
  const end = new Date(today);
  while (end.getDay() === 0 || end.getDay() === 6) end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - 28);
  const fmt = d => d.toISOString().slice(0,10);
  document.getElementById('startDate').value = fmt(start);
  document.getElementById('endDate').value   = fmt(end);
})();

// ── Chart instances ──────────────────────────────────────────────────────────
let cumulInst = null, dailyInst = null;
const PALETTE = ['#60a5fa','#34d399','#f472b6','#fbbf24','#a78bfa','#fb923c','#22d3ee','#e879f9'];

// ── Progress ─────────────────────────────────────────────────────────────────
let _pt = null;
function startProgress(ms) {
  const wrap = document.getElementById('progWrap');
  const fill = document.getElementById('progFill');
  const lbl  = document.getElementById('progLbl');
  wrap.style.display = 'block'; fill.style.width = '0%';
  let p = 0;
  const step = 100 / (ms / 250);
  _pt = setInterval(() => {
    p = Math.min(p + step * (0.4 + Math.random() * 0.8), 90);
    fill.style.width = p + '%';
    lbl.textContent = 'Fetching & running… ' + Math.round(p) + '%';
  }, 250);
}
function stopProgress() {
  clearInterval(_pt);
  document.getElementById('progFill').style.width = '100%';
  document.getElementById('progLbl').textContent = 'Done!';
  setTimeout(() => { document.getElementById('progWrap').style.display = 'none'; }, 700);
}

// ── Run ───────────────────────────────────────────────────────────────────────
async function runAnalysis() {
  if (!chips.length) { alert('Add at least one symbol.'); return; }
  const sd = document.getElementById('startDate').value;
  const ed = document.getElementById('endDate').value;
  if (!sd || !ed) { alert('Select start and end dates.'); return; }

  const p = new URLSearchParams({
    symbols:            chips.join(','),
    start_date:         sd,
    end_date:           ed,
    rsi_period:         document.getElementById('rsiPeriod').value,
    rsi_buy:            document.getElementById('rsiBuy').value,
    rsi_sell:           document.getElementById('rsiSell').value,
    profit_target_pct:  document.getElementById('profitTarget').value,
    trail_pct:          document.getElementById('trailPct').value,
    trail_activate_pct: document.getElementById('trailActivate').value,
    rsi_trail_trigger:  document.getElementById('rsiTrailTrigger').value,
  });

  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  document.getElementById('statusMsg').textContent = '';
  document.getElementById('errBox').classList.add('hidden');
  document.getElementById('results').classList.add('hidden');

  const calDays = Math.round((new Date(ed) - new Date(sd)) / 86400000);
  startProgress(chips.length * calDays * 200 + 3000);

  try {
    const res  = await fetch('/api/multiday?' + p);
    const data = await res.json();
    stopProgress();
    if (!res.ok) {
      showErr(data.detail || JSON.stringify(data));
      return;
    }
    renderResults(data);
    document.getElementById('statusMsg').textContent =
      data.trading_days + ' days with exits · ' + data.symbols.length + ' symbols';
  } catch(e) {
    stopProgress(); showErr('Request failed: ' + e.message);
  } finally { btn.disabled = false; }
}

function showErr(msg) {
  const b = document.getElementById('errBox');
  b.textContent = msg; b.classList.remove('hidden');
}

// ── Render ────────────────────────────────────────────────────────────────────
function fmtPnl(v) {
  if (v === null || v === undefined) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(2);
}
function pc(v) { return v > 0 ? 'pp' : v < 0 ? 'np' : 'zp'; }

function renderResults(data) {
  document.getElementById('results').classList.remove('hidden');
  const syms = data.symbols || [];
  const bySym = data.by_symbol || {};

  // ── Summary cards ──
  const totalPnl = data.total_pnl;
  const allTrades = syms.reduce((s,sym) => s + (bySym[sym]?.trades || 0), 0);
  const allWins   = syms.reduce((s,sym) => s + (bySym[sym]?.win_trades || 0), 0);
  const winRate   = allTrades ? Math.round(allWins / allTrades * 100) : 0;
  const daily     = data.daily || [];
  const best      = daily.length ? Math.max(...daily.map(d => d.net_pnl)) : 0;
  const worst     = daily.length ? Math.min(...daily.map(d => d.net_pnl)) : 0;
  const openPositions = syms.filter(s => bySym[s]?.open_position).length;

  document.getElementById('summaryCards').innerHTML = `
    <div class="card"><div class="card-label">Total P&L</div><div class="card-val ${pc(totalPnl)}">${fmtPnl(totalPnl)}</div></div>
    <div class="card"><div class="card-label">Days w/ Exits</div><div class="card-val white">${daily.length}</div></div>
    <div class="card"><div class="card-label">Total Trades</div><div class="card-val white">${allTrades}</div></div>
    <div class="card"><div class="card-label">Win Rate</div><div class="card-val ${winRate>=50?'green':'red'}">${winRate}%</div></div>
    <div class="card"><div class="card-label">Best Day Exit</div><div class="card-val green">${fmtPnl(best)}</div></div>
    <div class="card"><div class="card-label">Worst Day Exit</div><div class="card-val red">${fmtPnl(worst)}</div></div>
    <div class="card"><div class="card-label">Open Positions</div><div class="card-val yellow">${openPositions}</div></div>
  `;

  // ── Per-symbol cards ──
  document.getElementById('symCards').innerHTML = syms.map((sym,i) => {
    const s = bySym[sym] || {};
    const clr = PALETTE[i % PALETTE.length];
    const openBadge = s.open_position ? '<span class="open-badge">OPEN</span>' : '';
    const errBadge  = s.error ? `<div style="font-size:.7rem;color:#f87171;margin-top:4px">${s.error}</div>` : '';
    return `<div class="sym-card" style="border-top:3px solid ${clr}">
      <div class="sym-card-title" style="color:${clr}">${sym}${openBadge}</div>
      <div class="sym-card-stat"><span>Net P&L</span><span class="${pc(s.net_pnl)}">${fmtPnl(s.net_pnl)}</span></div>
      <div class="sym-card-stat"><span>Trades</span><span>${s.trades || 0}</span></div>
      <div class="sym-card-stat"><span>Win Rate</span><span>${s.win_rate || 0}%</span></div>
      <div class="sym-card-stat"><span>Bars</span><span>${s.bars || 0}</span></div>
      ${errBadge}
    </div>`;
  }).join('');

  // ── Cumulative P&L chart ──
  // Build cumulative from rows (trades sorted by exit_date)
  const allDates = [...new Set(daily.map(d => d.date))].sort();
  if (cumulInst) cumulInst.destroy();
  const cumulDs = syms.map((sym,i) => {
    let cum = 0;
    const rows = (data.rows || []).find(r => r.symbol === sym);
    const tradesByDate = {};
    ((rows && rows.trades) || []).forEach(t => {
      const d = t.exit_date || data.end_date;
      tradesByDate[d] = (tradesByDate[d] || 0) + t.pnl;
    });
    const vals = allDates.map(d => {
      cum += (tradesByDate[d] || 0);
      return { x: d, y: parseFloat(cum.toFixed(2)) };
    });
    return {
      label: sym, data: vals,
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: PALETTE[i % PALETTE.length] + '18',
      tension: 0.3, pointRadius: 3, fill: false,
    };
  });
  cumulInst = new Chart(document.getElementById('cumulChart'), {
    type: 'line',
    data: { datasets: cumulDs },
    options: {
      responsive: true, maintainAspectRatio: true,
      scales: {
        x: { type: 'category', ticks: { color: '#94a3b8', maxRotation: 45 }, grid: { color: '#1e2535' } },
        y: { ticks: { color: '#94a3b8', callback: v => '$' + v }, grid: { color: '#1e2535' } }
      },
      plugins: {
        legend: { labels: { color: '#94a3b8', boxWidth: 12 } },
        annotation: { annotations: { z: { type:'line', yMin:0, yMax:0, borderColor:'#374151', borderWidth:1, borderDash:[4,4] }}}
      }
    }
  });

  // ── Daily bar chart ──
  if (dailyInst) dailyInst.destroy();
  dailyInst = new Chart(document.getElementById('dailyChart'), {
    type: 'bar',
    data: {
      labels: daily.map(d => d.date),
      datasets: [{
        label: 'Day P&L',
        data: daily.map(d => d.net_pnl),
        backgroundColor: daily.map(d => d.net_pnl >= 0 ? '#34d39970' : '#f8717170'),
        borderColor:     daily.map(d => d.net_pnl >= 0 ? '#34d399'   : '#f87171'),
        borderWidth: 1, borderRadius: 3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      scales: {
        x: { ticks: { color: '#94a3b8', maxRotation: 45 }, grid: { color: '#1e2535' } },
        y: { ticks: { color: '#94a3b8', callback: v => '$' + v }, grid: { color: '#1e2535' } }
      },
      plugins: {
        legend: { display: false },
        annotation: { annotations: { z: { type:'line', yMin:0, yMax:0, borderColor:'#374151', borderWidth:1, borderDash:[4,4] }}}
      }
    }
  });

  // ── Daily table ──
  document.getElementById('dailyHead').innerHTML =
    '<tr><th onclick="sortTbl(\'dailyTbl\',0)">Exit Date</th>' +
    '<th onclick="sortTbl(\'dailyTbl\',1)">Day P&L</th>' +
    '<th onclick="sortTbl(\'dailyTbl\',2)">Trades</th>' +
    syms.map((s,i) => `<th onclick="sortTbl('dailyTbl',${3+i})">${s}</th>`).join('') +
    '</tr>';

  const dailyBody = document.getElementById('dailyBody');
  dailyBody.innerHTML = '';
  daily.forEach(d => {
    const tr = document.createElement('tr');
    const symCols = syms.map(s => {
      const v = d.symbols && d.symbols[s] ? d.symbols[s].pnl : null;
      return v === null ? '<td style="color:#374151">—</td>' :
        `<td class="${pc(v)}">${fmtPnl(v)}</td>`;
    }).join('');
    tr.innerHTML = `<td>${d.date}</td><td class="${pc(d.net_pnl)}">${fmtPnl(d.net_pnl)}</td><td>${d.trades}</td>${symCols}`;
    dailyBody.appendChild(tr);
  });

  // ── All trades ──
  const tradesBody = document.getElementById('tradesBody');
  tradesBody.innerHTML = '';
  let idx = 0;
  (data.rows || []).forEach(r => {
    (r.trades || []).forEach(t => {
      const id  = 'e' + idx++;
      const et  = t.exit_time ? t.exit_time.slice(0,16).replace('T',' ') : '—';
      const reason = t.open
        ? '<span class="badge b-open">OPEN</span>'
        : t.reason === 'trail'
          ? `<span class="badge b-trail">trail <small>[${t.trail_reason||''}]</small></span>`
          : t.reason === 'target'
            ? '<span class="badge b-target">target</span>'
            : `<span class="badge b-eod">${t.reason}</span>`;

      const tr1 = document.createElement('tr');
      tr1.innerHTML = `
        <td><span class="badge b-sym">${r.symbol}</span></td>
        <td>${t.exit_date || '—'}</td>
        <td>$${t.avg_entry}</td>
        <td>${t.total_shares}</td>
        <td>$${t.total_cost.toFixed(2)}</td>
        <td>$${t.exit_price}</td>
        <td style="color:#94a3b8;font-size:.72rem">${et}</td>
        <td class="${pc(t.pnl)}">${fmtPnl(t.pnl)}</td>
        <td>${reason}</td>
        <td><button class="exp-btn" onclick="toggleLegs('${id}',this)">▶ ${t.buys ? t.buys.length : 0}</button></td>
      `;
      tradesBody.appendChild(tr1);

      const tr2 = document.createElement('tr');
      tr2.id = id; tr2.className = 'exp-row';
      const legsHtml = t.buys && t.buys.length
        ? `<table class="leg-tbl"><thead><tr><th>Time</th><th>Price</th><th>Shares</th><th>Spend</th></tr></thead><tbody>` +
          t.buys.map(b => `<tr><td>${b.time.slice(0,16).replace('T',' ')}</td><td>$${b.price}</td><td>${b.shares}</td><td>$${b.spend.toFixed(2)}</td></tr>`).join('') +
          `</tbody></table>`
        : '<em style="color:#6b7280">No buy legs</em>';
      tr2.innerHTML = `<td colspan="10"><div class="exp-inner">${legsHtml}</div></td>`;
      tradesBody.appendChild(tr2);
    });
  });
}

function toggleLegs(id, btn) {
  const r = document.getElementById(id);
  const open = r.style.display === 'table-row';
  r.style.display = open ? 'none' : 'table-row';
  btn.textContent = btn.textContent.replace(open ? '▼' : '▶', open ? '▶' : '▼');
}

const _ss = {};
function sortTbl(tblId, col) {
  const tbl  = document.getElementById(tblId);
  const tb   = tbl.querySelector('tbody');
  const rows = [...tb.querySelectorAll('tr:not(.exp-row)')];
  const asc  = !_ss[tblId+col]; _ss[tblId+col] = asc;
  rows.sort((a,b) => {
    const va = (a.cells[col]?.textContent||'').trim().replace(/[$+,]/g,'');
    const vb = (b.cells[col]?.textContent||'').trim().replace(/[$+,]/g,'');
    const na = parseFloat(va), nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) return asc ? na-nb : nb-na;
    return asc ? va.localeCompare(vb) : vb.localeCompare(va);
  });
  rows.forEach(r => tb.appendChild(r));
}
</script>
</body>
</html>"""
