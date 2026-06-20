MOMENTUM_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Momentum — Flush &amp; Base</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0d0f14;color:#e2e8f0;min-height:100vh}

/* NAV */
.nav{display:flex;align-items:center;gap:14px;padding:9px 20px;background:#161b26;border-bottom:1px solid #2d3748;flex-wrap:wrap}
.nav-title{font-size:.93rem;font-weight:700;color:#fff;margin-right:4px}
.nav a{font-size:.8rem;color:#94a3b8;padding:4px 9px;border-radius:6px}
.nav a:hover,.nav a.active{background:#2d3748;color:#e2e8f0;text-decoration:none}

/* LAYOUT */
.container{max-width:1480px;margin:0 auto;padding:16px 20px}
.panel{background:#161b26;border:1px solid #2d3748;border-radius:12px;padding:16px 18px;margin-bottom:16px}
h2{font-size:.74rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}

/* CONTROLS — top bar */
.ctrl-top{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:14px}
.field{display:flex;flex-direction:column;gap:3px}
.field label{font-size:.67rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
.field input{background:#0d1117;border:1px solid #374151;border-radius:6px;color:#e2e8f0;padding:5px 8px;font-size:.84rem;width:120px}
.field input:focus{outline:none;border-color:#60a5fa}
.field input.wide{width:155px}
.field input.narrow{width:74px}

/* PARAM GRID */
.param-grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px}
@media(max-width:1000px){.param-grid{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.param-grid{grid-template-columns:1fr}}
.param-sec{background:#1a2035;border-radius:9px;padding:11px 13px}
.param-sec h3{font-size:.67rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
.g1-color{color:#fbbf24}.g2-color{color:#f97316}.g3-color{color:#f59e0b}
.entry-color{color:#34d399}.exit-color{color:#f87171}
.pf{display:flex;flex-direction:column;gap:3px;margin-bottom:6px}
.pf:last-child{margin-bottom:0}
.pf label{font-size:.65rem;color:#94a3b8}
.pf input{background:#0d0f14;border:1px solid #374151;border-radius:5px;color:#e2e8f0;padding:4px 7px;font-size:.82rem;width:100%}
.pf input:focus{outline:none;border-color:#60a5fa}

/* BUTTONS */
.btn{border:none;border-radius:7px;cursor:pointer;font-size:.85rem;font-weight:600;padding:8px 20px;transition:opacity .18s}
.btn:hover{opacity:.82}.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-run{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff}
.btn-range{background:linear-gradient(135deg,#059669,#0d9488);color:#fff}

/* PROGRESS */
.prog-wrap{display:none;margin-top:10px}
.prog-bar{height:4px;background:#1e2535;border-radius:2px;overflow:hidden}
.prog-fill{height:100%;width:0%;background:linear-gradient(90deg,#3b82f6,#6366f1);border-radius:2px;transition:width .3s}
.prog-lbl{font-size:.7rem;color:#94a3b8;margin-top:3px;text-align:center}

/* SUMMARY CARDS */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:9px;margin-bottom:14px}
.card{background:#161b26;border:1px solid #2d3748;border-radius:9px;padding:11px 13px;text-align:center}
.card-lbl{font-size:.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}
.card-val{font-size:1.25rem;font-weight:700}
.green{color:#34d399}.red{color:#f87171}.white{color:#e2e8f0}.blue{color:#60a5fa}.yellow{color:#fbbf24}

/* STRATEGY LEGEND */
.legend-bar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px;padding:10px 14px;background:#1a2035;border-radius:8px;font-size:.72rem}
.lg{display:flex;align-items:center;gap:5px;color:#94a3b8}
.lg-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.lg-line{width:24px;height:2px;flex-shrink:0}
.lg-dash{width:24px;height:0;border-top:2px dashed;flex-shrink:0}

/* CHART */
.chart-wrap{position:relative;height:340px;margin-bottom:14px}
.chart-wrap canvas{width:100%!important;height:100%!important}

/* GATE LOG */
.gate-log{max-height:180px;overflow-y:auto;font-size:.73rem;font-family:monospace;line-height:1.6}
.gate-row{display:flex;gap:6px;padding:2px 4px;border-radius:3px}
.gate-row:hover{background:#1e2535}
.gt{color:#94a3b8;min-width:58px}
.g-pass{color:#34d399}
.g-fail{color:#374151}
.g-na{color:#374151}
.g-buy{background:#0f2a1a;border:1px solid #166534;border-radius:4px;padding:0 6px;color:#4ade80;font-weight:700}
.g-skip{background:#2a1a00;border:1px solid #ca8a04;border-radius:4px;padding:0 6px;color:#fbbf24}

/* RANGE SECTION */
.range-row{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px}
.range-row .field{flex:1;min-width:140px}

/* TABLE */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.77rem}
th{background:#1a2035;color:#94a3b8;text-transform:uppercase;font-size:.63rem;letter-spacing:.05em;padding:7px 9px;text-align:right;cursor:pointer;white-space:nowrap}
th:first-child{text-align:left}
th:hover{color:#e2e8f0}
td{padding:6px 9px;border-bottom:1px solid #1e2535;text-align:right;white-space:nowrap}
td:first-child{text-align:left}
tr:hover td{background:#1a2035}
.pp{color:#34d399;font-weight:600}.np{color:#f87171;font-weight:600}.zp{color:#94a3b8}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:.67rem;font-weight:600}
.b-stop{background:#3a1212;color:#f87171;border:1px solid #7f1d1d}
.b-t1{background:#1a2a40;color:#60a5fa;border:1px solid #1d4ed8}
.b-t2{background:#0f2a20;color:#34d399;border:1px solid #166534}
.b-trail{background:#1e2a1e;color:#86efac}
.b-time{background:#2a2620;color:#fbbf24;border:1px solid #ca8a04}
.b-eod{background:#222;color:#9ca3af}
.exp-row{display:none}
.exp-row td{padding:0;border-bottom:none}
.exp-inner{background:#111827;padding:7px 13px;border-bottom:1px solid #374151}
.leg-tbl{width:100%;border-collapse:collapse;font-size:.73rem}
.leg-tbl th{background:#0d0f14;color:#6b7280;padding:3px 7px;text-align:right}
.leg-tbl th:first-child{text-align:left}
.leg-tbl td{padding:2px 7px;color:#d1d5db;text-align:right}
.leg-tbl td:first-child{text-align:left}
.exp-btn{background:none;border:none;color:#60a5fa;cursor:pointer;font-size:.7rem;padding:0 2px}
.exp-btn:hover{color:#93c5fd}

.err-box{background:#2a1515;border:1px solid #7f1d1d;border-radius:8px;padding:11px;color:#fca5a5;font-size:.82rem;margin-bottom:14px}
.hidden{display:none}
.sep{border:none;border-top:1px solid #2d3748;margin:16px 0}
</style>
</head>
<body>

<div class="nav">
  <span class="nav-title">100x RSI Backtester</span>
  <a href="/">Single Day RSI</a>
  <a href="/batch">Batch</a>
  <a href="/multiday">Multi-Day</a>
  <a href="/momentum" class="active">Momentum</a>
  <a href="/alerts">Alerts</a>
</div>

<div class="container">

<!-- ── CONTROLS ─────────────────────────────────────────────────────────────── -->
<div class="panel">
  <h2>Flush &amp; Base Momentum Strategy</h2>

  <!-- Top: symbol + date + watch end + risk + run button -->
  <div class="ctrl-top">
    <div class="field">
      <label>Symbol</label>
      <input type="text" id="symbol" value="SOXL" class="wide" style="text-transform:uppercase">
    </div>
    <div class="field">
      <label>Date</label>
      <input type="date" id="dateStr" class="wide">
    </div>
    <div class="field">
      <label>Watch End (ET)</label>
      <input type="time" id="watchEnd" value="11:00" class="narrow" style="width:90px">
    </div>
    <div class="field">
      <label>Max Risk $</label>
      <input type="number" id="maxRisk" value="200" min="10" max="10000" class="narrow">
    </div>
    <div class="field">
      <label>Stop Buffer $</label>
      <input type="number" id="stopBuffer" value="0.10" min="0.01" max="2" step="0.01" class="narrow">
    </div>
    <button class="btn btn-run" id="runBtn" onclick="runSingle()" style="align-self:flex-end">▶ Run Day</button>
    <span id="statusMsg" style="font-size:.76rem;color:#94a3b8;align-self:flex-end"></span>
  </div>

  <!-- Param grid: 4 sections -->
  <div class="param-grid">
    <!-- Gate 1 -->
    <div class="param-sec">
      <h3 class="g1-color">⬡ Gate 1 — Flush</h3>
      <div class="pf"><label>Drop % threshold</label><input type="number" id="flushPct" value="5" min="1" max="30" step="0.5"></div>
      <div class="pf"><label>Lookback bars</label><input type="number" id="flushLookback" value="10" min="3" max="30"></div>
    </div>
    <!-- Gate 2 -->
    <div class="param-sec">
      <h3 class="g2-color">⬡ Gate 2 — Base</h3>
      <div class="pf"><label>Base candles</label><input type="number" id="baseCandles" value="5" min="3" max="15"></div>
      <div class="pf"><label>Max range %</label><input type="number" id="baseRangePct" value="2" min="0.5" max="10" step="0.5"></div>
    </div>
    <!-- Gate 3 + VWAP -->
    <div class="param-sec">
      <h3 class="g3-color">⬡ Gate 3 — Trigger + VWAP</h3>
      <div class="pf"><label>Body ≥ N × ATR</label><input type="number" id="triggerAtrMult" value="1.5" min="0.5" max="5" step="0.1"></div>
      <div class="pf"><label>Vol ≥ N × base avg</label><input type="number" id="triggerVolMult" value="2" min="1" max="10" step="0.5"></div>
      <div class="pf"><label>ATR period</label><input type="number" id="atrPeriod" value="14" min="5" max="50"></div>
    </div>
    <!-- Exits -->
    <div class="param-sec">
      <h3 class="exit-color">⬡ Exits</h3>
      <div class="pf"><label>T1 = entry + R ×</label><input type="number" id="t1R" value="1" min="0.5" max="5" step="0.5"></div>
      <div class="pf"><label>T2 = entry + R ×</label><input type="number" id="t2R" value="2" min="1" max="10" step="0.5"></div>
      <div class="pf"><label>T1 scale-out %</label><input type="number" id="t1Scale" value="40" min="10" max="90"></div>
      <div class="pf"><label>T2 scale-out %</label><input type="number" id="t2Scale" value="40" min="10" max="90"></div>
      <div class="pf"><label>Trail % (remainder)</label><input type="number" id="trailPct" value="3" min="0.5" max="20" step="0.5"></div>
      <div class="pf"><label>Time exit bars</label><input type="number" id="timeExitBars" value="10" min="3" max="60"></div>
    </div>
  </div>

  <div class="prog-wrap" id="progWrap">
    <div class="prog-bar"><div class="prog-fill" id="progFill"></div></div>
    <div class="prog-lbl" id="progLbl">Loading…</div>
  </div>
</div>

<div class="err-box hidden" id="errBox"></div>

<!-- ── SINGLE DAY RESULTS ────────────────────────────────────────────────────── -->
<div id="singleResults" class="hidden">
  <div class="cards" id="summaryCards"></div>

  <!-- Legend -->
  <div class="legend-bar">
    <span class="lg"><span class="lg-line" style="background:#94a3b8"></span>Price</span>
    <span class="lg"><span class="lg-line" style="background:#fbbf24"></span>VWAP</span>
    <span class="lg"><span class="lg-dash" style="border-color:#f87171"></span>Stop</span>
    <span class="lg"><span class="lg-dash" style="border-color:#60a5fa"></span>T1</span>
    <span class="lg"><span class="lg-dash" style="border-color:#34d399"></span>T2</span>
    <span class="lg"><span class="lg-dash" style="border-color:#e2e8f0"></span>Entry</span>
    <span class="lg"><span class="lg-dash" style="border-color:#a78bfa"></span>Trail Stop</span>
    <span class="lg"><span class="lg-dot" style="background:#22c55e"></span>Buy</span>
    <span class="lg"><span class="lg-dot" style="background:#60a5fa"></span>T1 hit</span>
    <span class="lg"><span class="lg-dot" style="background:#34d399"></span>T2 hit</span>
    <span class="lg"><span class="lg-dot" style="background:#f87171"></span>Exit</span>
    <span class="lg"><span class="lg-dot" style="background:#f97316"></span>VWAP skip</span>
  </div>

  <div class="panel" style="padding:12px 14px">
    <div class="chart-wrap">
      <canvas id="priceChart"></canvas>
    </div>
  </div>

  <div class="panel">
    <h2>Gate Log — bars where all 3 gates fired</h2>
    <div class="gate-log" id="gateLog"></div>
  </div>

  <div class="panel">
    <h2>Trades</h2>
    <div class="tbl-wrap">
      <table id="tradesTbl">
        <thead>
          <tr>
            <th onclick="srt('tradesTbl',0)">Entry Time</th>
            <th onclick="srt('tradesTbl',1)">Entry $</th>
            <th onclick="srt('tradesTbl',2)">Stop $</th>
            <th onclick="srt('tradesTbl',3)">R ($)</th>
            <th onclick="srt('tradesTbl',4)">Shares</th>
            <th onclick="srt('tradesTbl',5)">T1 $</th>
            <th onclick="srt('tradesTbl',6)">T2 $</th>
            <th onclick="srt('tradesTbl',7)">Exit $</th>
            <th onclick="srt('tradesTbl',8)">Reason</th>
            <th onclick="srt('tradesTbl',9)">P&amp;L</th>
            <th>Parts</th>
          </tr>
        </thead>
        <tbody id="tradesBody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ── DATE RANGE SWEEP ─────────────────────────────────────────────────────── -->
<div class="panel">
  <h2>Date Range Sweep — same symbol, multiple days</h2>
  <div class="range-row">
    <div class="field"><label>Start Date</label><input type="date" id="startDate" class="wide"></div>
    <div class="field"><label>End Date</label><input type="date" id="endDate" class="wide"></div>
    <button class="btn btn-range" id="rangeBtn" onclick="runRange()" style="align-self:flex-end">▶ Run Range</button>
    <span id="rangeStatus" style="font-size:.76rem;color:#94a3b8;align-self:flex-end"></span>
  </div>
  <div class="prog-wrap" id="rangeProg">
    <div class="prog-bar"><div class="prog-fill" id="rangeFill"></div></div>
    <div class="prog-lbl" id="rangeLbl">Running…</div>
  </div>

  <div id="rangeResults" class="hidden">
    <div class="cards" id="rangeCards"></div>
    <hr class="sep">
    <div class="tbl-wrap">
      <table id="rangeTbl">
        <thead>
          <tr>
            <th onclick="srt('rangeTbl',0)">Date</th>
            <th onclick="srt('rangeTbl',1)">Bars</th>
            <th onclick="srt('rangeTbl',2)">Trades</th>
            <th onclick="srt('rangeTbl',3)">Net P&amp;L</th>
            <th onclick="srt('rangeTbl',4)">Reason</th>
            <th onclick="srt('rangeTbl',5)">Entry $</th>
            <th onclick="srt('rangeTbl',6)">Stop $</th>
            <th onclick="srt('rangeTbl',7)">T1 $</th>
          </tr>
        </thead>
        <tbody id="rangeBody"></tbody>
      </table>
    </div>
  </div>
</div>

</div><!-- /container -->

<script>
// ── Default dates ────────────────────────────────────────────────────────────
(function() {
  const today = new Date();
  const end = new Date(today);
  while (end.getDay() === 0 || end.getDay() === 6) end.setDate(end.getDate()-1);
  const start = new Date(end); start.setDate(start.getDate()-20);
  const fmt = d => d.toISOString().slice(0,10);
  document.getElementById('dateStr').value   = fmt(end);
  document.getElementById('startDate').value = fmt(start);
  document.getElementById('endDate').value   = fmt(end);
})();

// ── Collect params ────────────────────────────────────────────────────────────
function collectParams() {
  return new URLSearchParams({
    flush_pct:          document.getElementById('flushPct').value,
    flush_lookback:     document.getElementById('flushLookback').value,
    base_candles:       document.getElementById('baseCandles').value,
    base_range_pct:     document.getElementById('baseRangePct').value,
    trigger_atr_mult:   document.getElementById('triggerAtrMult').value,
    trigger_vol_mult:   document.getElementById('triggerVolMult').value,
    atr_period:         document.getElementById('atrPeriod').value,
    max_risk:           document.getElementById('maxRisk').value,
    stop_buffer:        document.getElementById('stopBuffer').value,
    t1_r:               document.getElementById('t1R').value,
    t2_r:               document.getElementById('t2R').value,
    t1_scale_pct:       document.getElementById('t1Scale').value,
    t2_scale_pct:       document.getElementById('t2Scale').value,
    trail_pct:          document.getElementById('trailPct').value,
    time_exit_bars:     document.getElementById('timeExitBars').value,
    watch_end_str:      document.getElementById('watchEnd').value,
  });
}

// ── Progress helpers ─────────────────────────────────────────────────────────
let _pt = null;
function startProg(wrapId, fillId, lblId, ms) {
  const wrap = document.getElementById(wrapId);
  const fill = document.getElementById(fillId);
  const lbl  = document.getElementById(lblId);
  wrap.style.display = 'block'; fill.style.width = '0%';
  let p = 0;
  const step = 100 / (ms / 300);
  _pt = setInterval(() => {
    p = Math.min(p + step * (0.5 + Math.random()), 90);
    fill.style.width = p + '%';
    lbl.textContent  = 'Running… ' + Math.round(p) + '%';
  }, 300);
}
function stopProg(fillId, lblId, wrapId) {
  clearInterval(_pt);
  document.getElementById(fillId).style.width = '100%';
  document.getElementById(lblId).textContent  = 'Done!';
  setTimeout(() => { document.getElementById(wrapId).style.display = 'none'; }, 600);
}

function showErr(msg) {
  const b = document.getElementById('errBox');
  b.textContent = msg; b.classList.remove('hidden');
}

// ── SINGLE DAY RUN ────────────────────────────────────────────────────────────
let priceChartInst = null;

async function runSingle() {
  const sym  = document.getElementById('symbol').value.trim().toUpperCase();
  const date = document.getElementById('dateStr').value;
  if (!sym || !date) { alert('Enter symbol and date.'); return; }

  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  document.getElementById('errBox').classList.add('hidden');
  document.getElementById('singleResults').classList.add('hidden');
  document.getElementById('statusMsg').textContent = '';

  startProg('progWrap','progFill','progLbl', 6000);

  const params = collectParams();
  params.set('symbol', sym); params.set('date_str', date);

  try {
    const res  = await fetch('/api/momentum?' + params);
    const data = await res.json();
    stopProg('progFill','progLbl','progWrap');
    if (!res.ok) { showErr(data.detail || JSON.stringify(data)); return; }
    renderSingle(data);
    document.getElementById('statusMsg').textContent =
      data.bars + ' bars · ' + data.trades.length + ' trade(s)';
  } catch(e) {
    stopProg('progFill','progLbl','progWrap');
    showErr('Request failed: ' + e.message);
  } finally { btn.disabled = false; }
}

function fmtPnl(v) { return (v>=0?'+':'') + v.toFixed(2); }
function pc(v) { return v>0?'pp':v<0?'np':'zp'; }

function renderSingle(data) {
  document.getElementById('singleResults').classList.remove('hidden');
  const trades = data.trades || [];
  const chart  = data.chart  || [];
  const wins   = trades.filter(t => t.pnl > 0).length;
  const net    = data.net_pnl;

  // ── Cards ──
  document.getElementById('summaryCards').innerHTML = `
    <div class="card"><div class="card-lbl">Bars</div><div class="card-val white">${data.bars}</div></div>
    <div class="card"><div class="card-lbl">Signals</div><div class="card-val blue">${chart.filter(c=>c.g3===true).length}</div></div>
    <div class="card"><div class="card-lbl">Trades</div><div class="card-val white">${trades.length}</div></div>
    <div class="card"><div class="card-lbl">Wins / Losses</div><div class="card-val white">${wins} / ${trades.length-wins}</div></div>
    <div class="card"><div class="card-lbl">Net P&L</div><div class="card-val ${pc(net)}">${fmtPnl(net)}</div></div>
    <div class="card"><div class="card-lbl">Max Risk</div><div class="card-val yellow">$${document.getElementById('maxRisk').value}</div></div>
    <div class="card"><div class="card-lbl">VWAP Skips</div><div class="card-val yellow">${chart.filter(c=>c.signal==='skip_vwap').length}</div></div>
  `;

  // ── Chart ──
  // Filter to 9:00 AM – 3:00 PM for clarity
  const filtered = chart.filter(c => {
    const h = new Date(c.t).getHours();
    return h >= 9 && h < 15;
  });
  const labels    = filtered.map(c => c.t.slice(11,16));   // HH:MM
  const closes    = filtered.map(c => c.c);
  const vwaps     = filtered.map(c => c.vwap);
  const stopLine  = filtered.map(c => c.stop_orig);
  const entryLine = filtered.map(c => c.entry);
  const t1Line    = filtered.map(c => c.t1);
  const t2Line    = filtered.map(c => c.t2);
  const trailLine = filtered.map(c => c.trail_stop);

  // Signal scatter (use index position for x)
  const buys   = []; const t1s = []; const t2s = []; const exits = []; const skips = [];
  filtered.forEach((c, idx) => {
    if (!c.signal) return;
    if (c.signal === 'buy')       buys.push({x: idx, y: c.c});
    else if (c.signal === 'T1')   t1s.push({x: idx, y: c.t1});
    else if (c.signal === 'T2')   t2s.push({x: idx, y: c.t2});
    else if (c.signal === 'T1T2') { t1s.push({x: idx, y: c.t1}); t2s.push({x: idx, y: c.t2}); }
    else if (c.signal && c.signal.startsWith('exit_')) exits.push({x: idx, y: c.c});
    else if (c.signal === 'skip_vwap') skips.push({x: idx, y: c.c});
  });

  const idxLabels = filtered.map((_, i) => i);
  if (priceChartInst) priceChartInst.destroy();
  priceChartInst = new Chart(document.getElementById('priceChart'), {
    type: 'line',
    data: {
      labels: idxLabels,
      datasets: [
        { label: 'Price',      data: closes,    borderColor: '#64748b', backgroundColor: 'transparent',
          borderWidth: 1.5, pointRadius: 0, tension: 0 },
        { label: 'VWAP',       data: vwaps,     borderColor: '#fbbf24', backgroundColor: 'transparent',
          borderWidth: 1.8, pointRadius: 0, tension: 0.1, borderDash: [] },
        { label: 'Entry',      data: entryLine, borderColor: '#e2e8f0', backgroundColor: 'transparent',
          borderWidth: 1, pointRadius: 0, borderDash: [4,3], tension: 0 },
        { label: 'Stop',       data: stopLine,  borderColor: '#f87171', backgroundColor: 'transparent',
          borderWidth: 1.2, pointRadius: 0, borderDash: [4,3], tension: 0 },
        { label: 'T1',         data: t1Line,    borderColor: '#60a5fa', backgroundColor: 'transparent',
          borderWidth: 1.2, pointRadius: 0, borderDash: [4,3], tension: 0 },
        { label: 'T2',         data: t2Line,    borderColor: '#34d399', backgroundColor: 'transparent',
          borderWidth: 1.2, pointRadius: 0, borderDash: [4,3], tension: 0 },
        { label: 'Trail Stop', data: trailLine, borderColor: '#a78bfa', backgroundColor: 'transparent',
          borderWidth: 1, pointRadius: 0, borderDash: [2,3], tension: 0 },
        // Scatter signals
        { label: 'Buy',  type: 'scatter', data: buys,  backgroundColor: '#22c55e',
          pointRadius: 7, pointStyle: 'triangle', rotation: 0 },
        { label: 'T1 hit', type: 'scatter', data: t1s, backgroundColor: '#60a5fa',
          pointRadius: 7, pointStyle: 'triangle', rotation: 0 },
        { label: 'T2 hit', type: 'scatter', data: t2s, backgroundColor: '#34d399',
          pointRadius: 7, pointStyle: 'triangle', rotation: 0 },
        { label: 'Exit',   type: 'scatter', data: exits, backgroundColor: '#f87171',
          pointRadius: 7, pointStyle: 'triangle', rotation: 180 },
        { label: 'VWAP skip', type: 'scatter', data: skips, backgroundColor: '#f97316',
          pointRadius: 5, pointStyle: 'crossRot' },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          type: 'category',
          ticks: {
            color: '#94a3b8', maxTicksLimit: 20,
            callback: (val, idx) => labels[idx] || '',
          },
          grid: { color: '#1e2535' }
        },
        y: { ticks: { color: '#94a3b8', callback: v => '$' + v.toFixed(2) }, grid: { color: '#1e2535' } }
      },
      plugins: {
        legend: { labels: { color: '#94a3b8', boxWidth: 14, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            title: (items) => {
              const idx = items[0].dataIndex;
              return labels[idx] || '';
            },
            label: (item) => {
              const v = item.raw;
              if (typeof v === 'object') return `${item.dataset.label}: $${v.y?.toFixed(4)||''}`;
              return v != null ? `${item.dataset.label}: $${v.toFixed(4)}` : null;
            }
          }
        }
      }
    }
  });

  // ── Gate log ──
  const logEl = document.getElementById('gateLog');
  const logRows = chart.filter(c => c.g1 === true || c.signal === 'buy' || c.signal === 'skip_vwap');
  if (!logRows.length) {
    logEl.innerHTML = '<span style="color:#4b5563">No Gate 1 activations in window — no flush detected.</span>';
  } else {
    logEl.innerHTML = logRows.map(c => {
      const t   = c.t.slice(11,16);
      const g1  = c.g1    === true ? '<span class="g-pass">G1✓</span>' : '<span class="g-na">G1·</span>';
      const g2  = c.g2    === true ? '<span class="g-pass">G2✓</span>' : c.g2===false ? '<span class="g-fail">G2✗</span>' : '<span class="g-na">G2·</span>';
      const g3  = c.g3    === true ? '<span class="g-pass">G3✓</span>' : c.g3===false ? '<span class="g-fail">G3✗</span>' : '<span class="g-na">G3·</span>';
      const vw  = c.vwap_ok===true ? '<span class="g-pass">VWAP✓</span>' : c.vwap_ok===false ? '<span class="g-skip">VWAP✗</span>' : '';
      const sig = c.signal === 'buy'       ? '<span class="g-buy">ENTRY</span>'
                : c.signal === 'skip_vwap' ? '<span class="g-skip">SKIP(VWAP)</span>' : '';
      return `<div class="gate-row"><span class="gt">${t}</span>${g1} ${g2} ${g3} ${vw} ${sig}</div>`;
    }).join('');
  }

  // ── Trades table ──
  const tb = document.getElementById('tradesBody');
  tb.innerHTML = '';
  trades.forEach((t, i) => {
    const expId = 'exp' + i;
    const reasonBadge = {
      stop: '<span class="badge b-stop">Stop</span>',
      trail: '<span class="badge b-trail">Trail</span>',
      T1: '<span class="badge b-t1">T1 scale</span>',
      T2: '<span class="badge b-t2">T2 scale</span>',
      time: '<span class="badge b-time">Time</span>',
      eod:  '<span class="badge b-eod">EOD</span>',
    }[t.exit_reason] || `<span class="badge b-eod">${t.exit_reason}</span>`;

    const tr1 = document.createElement('tr');
    tr1.innerHTML = `
      <td style="color:#94a3b8;font-size:.73rem">${t.entry_time.slice(11,16)}</td>
      <td>$${t.entry_price}</td>
      <td style="color:#f87171">$${t.stop_orig}</td>
      <td style="color:#94a3b8">$${t.R}</td>
      <td>${t.orig_shares}</td>
      <td style="color:#60a5fa">$${t.t1}</td>
      <td style="color:#34d399">$${t.t2}</td>
      <td>$${t.exit_price}</td>
      <td>${reasonBadge}</td>
      <td class="${pc(t.pnl)}">${fmtPnl(t.pnl)}</td>
      <td><button class="exp-btn" onclick="toggleExp('${expId}',this)">▶ ${t.parts.length}</button></td>
    `;
    tb.appendChild(tr1);

    const tr2 = document.createElement('tr');
    tr2.id = expId; tr2.className = 'exp-row';
    const partsHtml = t.parts.map(p =>
      `<tr><td>${p.time.slice(11,16)}</td><td>$${p.price}</td><td>${p.shares}</td><td class="${pc(p.pnl)}">${fmtPnl(p.pnl)}</td><td style="color:#94a3b8">${p.reason}</td></tr>`
    ).join('');
    tr2.innerHTML = `<td colspan="11"><div class="exp-inner">
      <table class="leg-tbl"><thead><tr><th>Time</th><th>Price</th><th>Shares</th><th>P&L</th><th>Reason</th></tr></thead>
      <tbody>${partsHtml}</tbody></table>
    </div></td>`;
    tb.appendChild(tr2);
  });
}

// ── DATE RANGE ─────────────────────────────────────────────────────────────────
async function runRange() {
  const sym = document.getElementById('symbol').value.trim().toUpperCase();
  const sd  = document.getElementById('startDate').value;
  const ed  = document.getElementById('endDate').value;
  if (!sym || !sd || !ed) { alert('Fill in symbol and dates.'); return; }

  const btn = document.getElementById('rangeBtn');
  btn.disabled = true;
  document.getElementById('rangeResults').classList.add('hidden');
  document.getElementById('rangeStatus').textContent = '';

  const calDays = Math.round((new Date(ed)-new Date(sd))/86400000);
  startProg('rangeProg','rangeFill','rangeLbl', calDays * 800 + 3000);

  const params = collectParams();
  params.set('symbol', sym); params.set('start_date', sd); params.set('end_date', ed);

  try {
    const res  = await fetch('/api/momentum/range?' + params);
    const data = await res.json();
    stopProg('rangeFill','rangeLbl','rangeProg');
    if (!res.ok) { showErr(data.detail || JSON.stringify(data)); return; }
    renderRange(data);
    document.getElementById('rangeStatus').textContent =
      data.days_tested + ' days · ' + data.total_trades + ' trades';
  } catch(e) {
    stopProg('rangeFill','rangeLbl','rangeProg');
    showErr('Range failed: ' + e.message);
  } finally { btn.disabled = false; }
}

function renderRange(data) {
  document.getElementById('rangeResults').classList.remove('hidden');
  const net = data.net_pnl;
  document.getElementById('rangeCards').innerHTML = `
    <div class="card"><div class="card-lbl">Days Tested</div><div class="card-val white">${data.days_tested}</div></div>
    <div class="card"><div class="card-lbl">Trades</div><div class="card-val white">${data.total_trades}</div></div>
    <div class="card"><div class="card-lbl">Wins</div><div class="card-val green">${data.wins}</div></div>
    <div class="card"><div class="card-lbl">Losses</div><div class="card-val red">${data.losses}</div></div>
    <div class="card"><div class="card-lbl">Win Rate</div><div class="card-val ${data.win_rate>=50?'green':'red'}">${data.win_rate}%</div></div>
    <div class="card"><div class="card-lbl">Net P&L</div><div class="card-val ${pc(net)}">${fmtPnl(net)}</div></div>
    <div class="card"><div class="card-lbl">Avg Trade</div><div class="card-val ${pc(data.avg_trade)}">${fmtPnl(data.avg_trade)}</div></div>
    <div class="card"><div class="card-lbl">Best Trade</div><div class="card-val green">${fmtPnl(data.best_trade)}</div></div>
    <div class="card"><div class="card-lbl">Worst Trade</div><div class="card-val red">${fmtPnl(data.worst_trade)}</div></div>
  `;

  const rb = document.getElementById('rangeBody');
  rb.innerHTML = '';
  (data.days || []).filter(d => d.bars > 0).sort((a,b) => a.date.localeCompare(b.date)).forEach(d => {
    (d.trades || []).forEach(t => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><a href="#" onclick="loadDay('${d.date}');return false" style="color:#60a5fa">${d.date}</a></td>
        <td>${d.bars}</td>
        <td>${d.trades.length}</td>
        <td class="${pc(d.net_pnl)}">${fmtPnl(d.net_pnl)}</td>
        <td>${t.exit_reason}</td>
        <td>$${t.entry_price}</td>
        <td style="color:#f87171">$${t.stop_orig}</td>
        <td style="color:#60a5fa">$${t.t1}</td>
      `;
      rb.appendChild(tr);
    });
    if (!d.trades || d.trades.length === 0) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><a href="#" onclick="loadDay('${d.date}');return false" style="color:#60a5fa">${d.date}</a></td>
        <td>${d.bars}</td>
        <td style="color:#4b5563">0</td>
        <td style="color:#4b5563">—</td>
        <td colspan="4" style="color:#4b5563;text-align:left">No setup</td>
      `;
      rb.appendChild(tr);
    }
  });
}

function loadDay(dateStr) {
  document.getElementById('dateStr').value = dateStr;
  window.scrollTo(0, 0);
  runSingle();
}

function toggleExp(id, btn) {
  const r = document.getElementById(id);
  const open = r.style.display === 'table-row';
  r.style.display = open ? 'none' : 'table-row';
  btn.textContent = btn.textContent.replace(open?'▼':'▶', open?'▶':'▼');
}

const _ss = {};
function srt(tblId, col) {
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
