SPIKE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spike Momentum — Nano &amp; Small Cap</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0d0f14;color:#e2e8f0;min-height:100vh}

.nav{display:flex;align-items:center;gap:14px;padding:9px 20px;background:#161b26;border-bottom:1px solid #2d3748;flex-wrap:wrap}
.nav-title{font-size:.93rem;font-weight:700;color:#fff;margin-right:4px}
.nav a{font-size:.8rem;color:#94a3b8;padding:4px 9px;border-radius:6px;text-decoration:none}
.nav a:hover,.nav a.active{background:#2d3748;color:#e2e8f0}

.container{max-width:1480px;margin:0 auto;padding:16px 20px}
.panel{background:#161b26;border:1px solid #2d3748;border-radius:12px;padding:16px 18px;margin-bottom:14px}
h2{font-size:.74rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}

/* SPIKE TYPE TOGGLE */
.toggle-group{display:flex;gap:0;border:1px solid #374151;border-radius:7px;overflow:hidden;width:fit-content}
.toggle-btn{background:#0d0f14;border:none;color:#94a3b8;cursor:pointer;font-size:.8rem;padding:6px 16px;transition:all .18s}
.toggle-btn.active{background:#3b82f6;color:#fff;font-weight:600}
.toggle-btn:hover:not(.active){background:#1e2535;color:#e2e8f0}

/* CONTROL ROWS */
.global-row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px}
.f{display:flex;flex-direction:column;gap:3px}
.f label{font-size:.67rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
.f input,.f select{background:#0d1117;border:1px solid #374151;border-radius:6px;color:#e2e8f0;padding:5px 8px;font-size:.83rem}
.f input:focus,.f select:focus{outline:none;border-color:#60a5fa}
.f input{width:110px}
.f input.narrow{width:80px}
.f select{width:140px}

/* CAP PARAM GRID */
.cap-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:700px){.cap-grid{grid-template-columns:1fr}}
.cap-section{border-radius:10px;padding:13px 15px}
.cap-nano{background:#1a1a2e;border:1px solid #312e81}
.cap-small{background:#1a2a1a;border:1px solid #166534}
.cap-section h3{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:9px}
.nano-title{color:#a5b4fc}.small-title{color:#4ade80}
.pf{display:flex;flex-direction:column;gap:3px;margin-bottom:6px}
.pf:last-child{margin-bottom:0}
.pf label{font-size:.65rem;color:#94a3b8}
.pf input{background:#0d0f14;border:1px solid #374151;border-radius:5px;color:#e2e8f0;padding:4px 7px;font-size:.82rem;width:100%}
.pf input:focus{outline:none;border-color:#60a5fa}

/* BUTTONS */
.btn{border:none;border-radius:7px;cursor:pointer;font-size:.84rem;font-weight:600;padding:8px 18px;transition:opacity .18s}
.btn:hover{opacity:.82}.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-single{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff}
.btn-batch{background:linear-gradient(135deg,#d97706,#b45309);color:#fff}
.btn-range{background:linear-gradient(135deg,#059669,#0d9488);color:#fff}

/* RUN MODES */
.run-section{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end}
.run-block{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;padding:10px 12px;background:#1a2035;border-radius:8px}
.run-block-title{font-size:.68rem;color:#60a5fa;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}

/* CHIP INPUT */
.chip-wrap{display:flex;flex-wrap:wrap;gap:4px;align-items:center;background:#0d0f14;border:1px solid #374151;border-radius:6px;padding:4px 7px;min-height:34px;min-width:200px;cursor:text}
.chip{display:flex;align-items:center;gap:3px;background:#1e3a5f;border-radius:16px;padding:2px 8px;font-size:.76rem;color:#93c5fd}
.chip button{background:none;border:none;color:#93c5fd;cursor:pointer;font-size:.85rem;padding:0}
.chip button:hover{color:#f87171}
.chip-input{background:none;border:none;color:#e2e8f0;font-size:.82rem;outline:none;min-width:60px}

/* PROGRESS */
.prog-wrap{display:none;margin-top:10px}
.prog-bar{height:4px;background:#1e2535;border-radius:2px;overflow:hidden}
.prog-fill{height:100%;width:0%;background:linear-gradient(90deg,#3b82f6,#6366f1);transition:width .3s}
.prog-lbl{font-size:.7rem;color:#94a3b8;margin-top:3px;text-align:center}

/* CARDS */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:9px;margin-bottom:14px}
.card{background:#161b26;border:1px solid #2d3748;border-radius:9px;padding:11px 13px;text-align:center}
.card-lbl{font-size:.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}
.card-val{font-size:1.2rem;font-weight:700}
.green{color:#34d399}.red{color:#f87171}.white{color:#e2e8f0}.blue{color:#60a5fa}.yellow{color:#fbbf24}
.purple{color:#a78bfa}.nano-c{color:#a5b4fc}.small-c{color:#4ade80}

/* CLASS COMPARISON */
.class-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
@media(max-width:600px){.class-grid{grid-template-columns:1fr}}
.class-card{border-radius:10px;padding:14px 16px}
.class-nano{background:#1a1a2e;border:1px solid #312e81}
.class-small{background:#1a2a1a;border:1px solid #166534}
.class-card-title{font-size:.85rem;font-weight:700;margin-bottom:8px}
.class-stat{display:flex;justify-content:space-between;font-size:.76rem;color:#94a3b8;margin-bottom:3px}
.class-stat span:last-child{color:#e2e8f0;font-weight:600}

/* CHARTS */
.chart-grid{display:grid;grid-template-columns:1fr;gap:12px;margin-bottom:14px}
.chart-box{background:#161b26;border:1px solid #2d3748;border-radius:10px;padding:13px}
.chart-box canvas{max-height:250px}

/* LEGEND */
.legend-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px;padding:8px 13px;background:#1a2035;border-radius:7px;font-size:.71rem}
.lg{display:flex;align-items:center;gap:5px;color:#94a3b8}
.ld{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.ll{width:22px;height:2px;flex-shrink:0}
.lx{width:22px;height:0;border-top:2px dashed;flex-shrink:0}

/* TABS */
.result-tabs{display:flex;gap:0;margin-bottom:12px}
.rtab{background:#1a2035;border:1px solid #2d3748;border-bottom:none;border-radius:6px 6px 0 0;color:#94a3b8;cursor:pointer;font-size:.78rem;padding:6px 14px;transition:all .15s}
.rtab.active{background:#161b26;color:#e2e8f0;border-bottom:1px solid #161b26}
.rtab-panel{display:none}.rtab-panel.active{display:block}

/* TABLE */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.77rem}
th{background:#1a2035;color:#94a3b8;text-transform:uppercase;font-size:.63rem;letter-spacing:.05em;padding:7px 9px;text-align:right;cursor:pointer;white-space:nowrap}
th:first-child,th:nth-child(2){text-align:left}
th:hover{color:#e2e8f0}
td{padding:6px 9px;border-bottom:1px solid #1e2535;text-align:right;white-space:nowrap}
td:first-child,td:nth-child(2){text-align:left}
tr:hover td{background:#1a2035}
.pp{color:#34d399;font-weight:600}.np{color:#f87171;font-weight:600}.zp{color:#94a3b8}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:.68rem;font-weight:600}
.b-nano{background:#1a1a2e;color:#a5b4fc;border:1px solid #312e81}
.b-small{background:#1a2a1a;color:#4ade80;border:1px solid #166534}
.b-rsi{background:#0f2a20;color:#34d399}
.b-stop{background:#2a1212;color:#f87171}
.b-time{background:#2a2610;color:#fbbf24}
.b-eod{background:#222;color:#9ca3af}

.err-box{background:#2a1515;border:1px solid #7f1d1d;border-radius:8px;padding:11px;color:#fca5a5;font-size:.82rem;margin-bottom:12px}
.hidden{display:none}
</style>
</head>
<body>

<div class="nav">
  <span class="nav-title">100x RSI Backtester</span>
  <a href="/">Single Day RSI</a>
  <a href="/batch">Batch</a>
  <a href="/multiday">Multi-Day</a>
  <a href="/momentum">Momentum</a>
  <a href="/spike" class="active">Spike</a>
  <a href="/grid">Grid</a>
  <a href="/alerts">Alerts</a>
</div>

<div class="container">

<!-- ── CONTROLS ─────────────────────────────────────────────────────────────── -->
<div class="panel">
  <h2>Spike Momentum — Nano &amp; Small Cap</h2>

  <!-- Spike type -->
  <div style="margin-bottom:12px">
    <div style="font-size:.67rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em;margin-bottom:5px">Spike Definition</div>
    <div class="toggle-group">
      <button class="toggle-btn active" id="tbPrevBar" onclick="setSpikeType('prev_bar')">1-Min Spike (prev bar close)</button>
      <button class="toggle-btn"        id="tbDayOpen" onclick="setSpikeType('day_open')">Gap+Run (vs day open)</button>
    </div>
    <input type="hidden" id="spikeType" value="prev_bar">
  </div>

  <!-- Global timing -->
  <div class="global-row" style="margin-bottom:14px">
    <div class="f"><label>Entry Window Start</label><input type="time" id="entryStart" value="09:30" class="narrow"></div>
    <div class="f"><label>Entry Window End</label><input type="time"   id="entryEnd"   value="11:00" class="narrow"></div>
    <div class="f"><label>Time Exit</label><input type="time"          id="timeExit"   value="15:30" class="narrow"></div>
    <div class="f"><label>RSI Period</label><input type="number"       id="rsiPeriod"  value="14" min="5" max="50" class="narrow"></div>
  </div>

  <!-- Cap params -->
  <div class="cap-grid">
    <div class="cap-section cap-nano">
      <h3 class="nano-title">🔵 Nano Cap</h3>
      <div class="pf"><label>Max Price ($) — anything below this</label><input type="number" id="nanoMaxPrice" value="5" min="0.01" max="50" step="0.5"></div>
      <div class="pf"><label>Spike % threshold</label><input type="number" id="nanoSpikePct" value="10" min="1" max="100" step="0.5"></div>
      <div class="pf"><label>Min Volume on spike bar</label><input type="number" id="nanoMinVol" value="50000" min="1000" step="1000"></div>
      <div class="pf"><label>RSI Profit Exit ≥</label><input type="number" id="nanoRsiProfit" value="60" min="40" max="99"></div>
      <div class="pf"><label>Buy Amount $</label><input type="number" id="nanoBuyAmt" value="500" min="50" step="50"></div>
    </div>
    <div class="cap-section cap-small">
      <h3 class="small-title">🟢 Small Cap</h3>
      <div class="pf"><label>Max Price ($) — below nano max–this</label><input type="number" id="smallMaxPrice" value="20" min="1" max="200" step="1"></div>
      <div class="pf"><label>Spike % threshold</label><input type="number" id="smallSpikePct" value="5" min="0.5" max="50" step="0.5"></div>
      <div class="pf"><label>Min Volume on spike bar</label><input type="number" id="smallMinVol" value="200000" min="1000" step="10000"></div>
      <div class="pf"><label>RSI Profit Exit ≥</label><input type="number" id="smallRsiProfit" value="65" min="40" max="99"></div>
      <div class="pf"><label>Buy Amount $</label><input type="number" id="smallBuyAmt" value="1000" min="50" step="50"></div>
    </div>
  </div>

  <!-- Run modes -->
  <div style="margin-top:14px">
    <h2 style="margin-bottom:10px">Run</h2>
    <div class="run-section">

      <!-- Single day -->
      <div>
        <div class="run-block-title">Single Ticker / Day</div>
        <div class="run-block">
          <div class="f"><label>Symbol</label><input type="text" id="singleSym" value="SOXL" style="width:80px;text-transform:uppercase"></div>
          <div class="f"><label>Date</label><input type="date" id="singleDate"></div>
          <button class="btn btn-single" id="btnSingle" onclick="runSingle()" style="align-self:flex-end">▶ Run Day</button>
        </div>
      </div>

      <!-- Batch CSV -->
      <div>
        <div class="run-block-title">Batch — Premarket CSV (all 31 days × 5 tickers)</div>
        <div class="run-block">
          <button class="btn btn-batch" id="btnBatch" onclick="runBatch()" style="align-self:flex-end">▶ Run Batch</button>
          <span id="batchStatus" style="font-size:.75rem;color:#94a3b8;align-self:flex-end"></span>
        </div>
      </div>

      <!-- Custom range -->
      <div>
        <div class="run-block-title">Custom Range</div>
        <div class="run-block">
          <div class="f"><label>Tickers</label>
            <div class="chip-wrap" id="rangeChipWrap" onclick="document.getElementById('rangeChipInput').focus()">
              <input class="chip-input" id="rangeChipInput" placeholder="Symbol + Enter…">
            </div>
          </div>
          <div class="f"><label>Start</label><input type="date" id="rangeStart"></div>
          <div class="f"><label>End</label><input type="date" id="rangeEnd"></div>
          <button class="btn btn-range" id="btnRange" onclick="runRange()" style="align-self:flex-end">▶ Run Range</button>
        </div>
      </div>

    </div>
  </div>

  <div class="prog-wrap" id="progWrap">
    <div class="prog-bar"><div class="prog-fill" id="progFill"></div></div>
    <div class="prog-lbl" id="progLbl">Running…</div>
  </div>
</div>

<div class="err-box hidden" id="errBox"></div>

<!-- ── RESULTS ────────────────────────────────────────────────────────────── -->
<div id="results" class="hidden">

  <!-- Summary cards -->
  <div class="cards" id="summaryCards"></div>

  <!-- Nano vs Small comparison -->
  <div class="class-grid" id="classGrid"></div>

  <!-- Result tabs: Chart | Trades | Daily -->
  <div class="result-tabs" id="resultTabs">
    <button class="rtab active" onclick="showTab('tabChart')">📈 Chart</button>
    <button class="rtab" onclick="showTab('tabTrades')">📋 All Trades</button>
    <button class="rtab" onclick="showTab('tabDaily')">📅 Daily</button>
  </div>

  <div id="tabChart" class="rtab-panel active panel" style="margin-bottom:14px">
    <div class="legend-row">
      <span class="lg"><span class="ll" style="background:#94a3b8"></span>Price</span>
      <span class="lg"><span class="lx" style="border-color:#fbbf24"></span>Avg Entry (limit stop)</span>
      <span class="lg"><span class="ld" style="background:#22c55e"></span>Buy (spike)</span>
      <span class="lg"><span class="ld" style="background:#34d399"></span>RSI profit exit</span>
      <span class="lg"><span class="ld" style="background:#f87171"></span>Stop at avg</span>
      <span class="lg"><span class="ld" style="background:#fbbf24"></span>Time / EOD exit</span>
    </div>
    <div style="height:280px;margin-bottom:10px"><canvas id="priceChart"></canvas></div>
    <div style="height:160px"><canvas id="rsiChart"></canvas></div>
    <div id="noChartMsg" class="hidden" style="color:#4b5563;font-size:.8rem;padding:16px;text-align:center">
      Chart available for single-day runs only. Select a date row in the Trades tab to load it.
    </div>
  </div>

  <div id="tabTrades" class="rtab-panel panel" style="margin-bottom:14px">
    <h2>All Trades</h2>
    <div class="tbl-wrap">
      <table id="tradesTbl">
        <thead>
          <tr>
            <th onclick="srt('tradesTbl',0)">Date</th>
            <th onclick="srt('tradesTbl',1)">Symbol</th>
            <th onclick="srt('tradesTbl',2)">Class</th>
            <th onclick="srt('tradesTbl',3)">Entry Time</th>
            <th onclick="srt('tradesTbl',4)">Entry $</th>
            <th onclick="srt('tradesTbl',5)">Exit $</th>
            <th onclick="srt('tradesTbl',6)">Shares</th>
            <th onclick="srt('tradesTbl',7)">P&amp;L</th>
            <th onclick="srt('tradesTbl',8)">Reason</th>
            <th onclick="srt('tradesTbl',9)">RSI In</th>
            <th onclick="srt('tradesTbl',10)">RSI Out</th>
          </tr>
        </thead>
        <tbody id="tradesBody"></tbody>
      </table>
    </div>
  </div>

  <div id="tabDaily" class="rtab-panel panel">
    <h2>Daily Summary</h2>
    <div class="tbl-wrap">
      <table id="dailyTbl">
        <thead>
          <tr>
            <th onclick="srt('dailyTbl',0)">Date</th>
            <th onclick="srt('dailyTbl',1)">Day P&amp;L</th>
            <th onclick="srt('dailyTbl',2)">Trades</th>
            <th>Symbols</th>
          </tr>
        </thead>
        <tbody id="dailyBody"></tbody>
      </table>
    </div>
  </div>

</div><!-- /results -->

</div><!-- /container -->

<script>
// ── Spike type toggle ─────────────────────────────────────────────────────────
function setSpikeType(v) {
  document.getElementById('spikeType').value = v;
  document.getElementById('tbPrevBar').classList.toggle('active', v === 'prev_bar');
  document.getElementById('tbDayOpen').classList.toggle('active', v === 'day_open');
}

// ── Chip input ────────────────────────────────────────────────────────────────
let rangeChips = [];
function addRangeChip(sym) {
  sym = sym.trim().toUpperCase().replace(/[^A-Z]/g,'');
  if (!sym || rangeChips.includes(sym)) return;
  rangeChips.push(sym);
  renderRangeChips();
}
function removeRangeChip(sym) { rangeChips = rangeChips.filter(s=>s!==sym); renderRangeChips(); }
function renderRangeChips() {
  const wrap = document.getElementById('rangeChipWrap');
  const inp  = document.getElementById('rangeChipInput');
  wrap.querySelectorAll('.chip').forEach(c=>c.remove());
  rangeChips.forEach(sym => {
    const c = document.createElement('div'); c.className = 'chip';
    c.innerHTML = sym + '<button onclick="removeRangeChip(\''+sym+'\')">&times;</button>';
    wrap.insertBefore(c, inp);
  });
}
document.getElementById('rangeChipInput').addEventListener('keydown', e => {
  if (e.key==='Enter'||e.key===',') { e.preventDefault(); addRangeChip(e.target.value); e.target.value=''; }
  if (e.key==='Backspace' && !e.target.value && rangeChips.length) removeRangeChip(rangeChips[rangeChips.length-1]);
});

// ── Default dates ─────────────────────────────────────────────────────────────
(function(){
  const today = new Date();
  const end   = new Date(today);
  while (end.getDay()===0||end.getDay()===6) end.setDate(end.getDate()-1);
  const start = new Date(end); start.setDate(start.getDate()-20);
  const fmt = d => d.toISOString().slice(0,10);
  document.getElementById('singleDate').value = fmt(end);
  document.getElementById('rangeStart').value  = fmt(start);
  document.getElementById('rangeEnd').value    = fmt(end);
})();

// ── Params ────────────────────────────────────────────────────────────────────
function collectParams() {
  return {
    spike_type:       document.getElementById('spikeType').value,
    nano_max_price:   +document.getElementById('nanoMaxPrice').value,
    small_max_price:  +document.getElementById('smallMaxPrice').value,
    nano_spike_pct:   +document.getElementById('nanoSpikePct').value,
    nano_min_vol:     +document.getElementById('nanoMinVol').value,
    nano_rsi_profit:  +document.getElementById('nanoRsiProfit').value,
    nano_buy_amount:  +document.getElementById('nanoBuyAmt').value,
    small_spike_pct:  +document.getElementById('smallSpikePct').value,
    small_min_vol:    +document.getElementById('smallMinVol').value,
    small_rsi_profit: +document.getElementById('smallRsiProfit').value,
    small_buy_amount: +document.getElementById('smallBuyAmt').value,
    entry_start_str:  document.getElementById('entryStart').value,
    entry_end_str:    document.getElementById('entryEnd').value,
    time_exit_str:    document.getElementById('timeExit').value,
    rsi_period:       +document.getElementById('rsiPeriod').value,
  };
}

// ── Progress ──────────────────────────────────────────────────────────────────
let _pt = null;
function startProg(ms) {
  document.getElementById('progWrap').style.display='block';
  const fill=document.getElementById('progFill'), lbl=document.getElementById('progLbl');
  fill.style.width='0%'; let p=0;
  _pt = setInterval(()=>{ p=Math.min(p+(100/(ms/300))*(0.5+Math.random()),90);
    fill.style.width=p+'%'; lbl.textContent='Running… '+Math.round(p)+'%'; },300);
}
function stopProg() {
  clearInterval(_pt);
  document.getElementById('progFill').style.width='100%';
  document.getElementById('progLbl').textContent='Done!';
  setTimeout(()=>document.getElementById('progWrap').style.display='none',600);
}
function showErr(msg) { const b=document.getElementById('errBox'); b.textContent=msg; b.classList.remove('hidden'); }

function hideErr() { document.getElementById('errBox').classList.add('hidden'); }
function fmtPnl(v) { return v==null?'—':(v>=0?'+':'')+v.toFixed(2); }
function pc(v) { return v>0?'pp':v<0?'np':'zp'; }

// ── Chart instances ───────────────────────────────────────────────────────────
let priceInst=null, rsiInst=null;

// ── SINGLE DAY ────────────────────────────────────────────────────────────────
async function runSingle() {
  const sym  = document.getElementById('singleSym').value.trim().toUpperCase();
  const date = document.getElementById('singleDate').value;
  if (!sym||!date) { alert('Enter symbol and date.'); return; }

  const btn = document.getElementById('btnSingle'); btn.disabled=true;
  hideErr(); document.getElementById('results').classList.add('hidden');
  startProg(6000);

  const p = new URLSearchParams({...collectParams(), symbol:sym, date_str:date});
  try {
    const res  = await fetch('/api/spike?'+p);
    const data = await res.json();
    stopProg();
    if (!res.ok) { showErr(data.detail||JSON.stringify(data)); return; }
    renderResults(data.trades, data.chart, [{symbol:sym, date:date, trades:data.trades, net_pnl:data.net_pnl}], 'single');
    document.getElementById('batchStatus').textContent='';
  } catch(e) { stopProg(); showErr('Failed: '+e.message); }
  finally { btn.disabled=false; }
}

// ── BATCH ─────────────────────────────────────────────────────────────────────
async function runBatch() {
  const btn = document.getElementById('btnBatch'); btn.disabled=true;
  document.getElementById('batchStatus').textContent='';
  hideErr(); document.getElementById('results').classList.add('hidden');
  startProg(50000);

  const p = new URLSearchParams({...collectParams()});
  try {
    const res  = await fetch('/api/spike/batch?'+p);
    const data = await res.json();
    stopProg();
    if (!res.ok) { showErr(data.detail||JSON.stringify(data)); return; }
    const allTrades = (data.rows||[]).flatMap(r=>(r.trades||[]).map(t=>({...t, symbol:r.symbol})));
    renderResults([], null, data.rows||[], 'batch', data);
    document.getElementById('batchStatus').textContent=data.total_trades+' trades across '+data.total_rows+' runs';
  } catch(e) { stopProg(); showErr('Failed: '+e.message); }
  finally { btn.disabled=false; }
}

// ── CUSTOM RANGE ──────────────────────────────────────────────────────────────
async function runRange() {
  if (!rangeChips.length) { alert('Add at least one symbol.'); return; }
  const sd = document.getElementById('rangeStart').value;
  const ed = document.getElementById('rangeEnd').value;
  if (!sd||!ed) { alert('Select date range.'); return; }

  const btn = document.getElementById('btnRange'); btn.disabled=true;
  hideErr(); document.getElementById('results').classList.add('hidden');
  const calDays = Math.round((new Date(ed)-new Date(sd))/86400000);
  startProg(calDays * rangeChips.length * 900 + 3000);

  const p = new URLSearchParams({...collectParams(), symbols:rangeChips.join(','), start_date:sd, end_date:ed});
  try {
    const res  = await fetch('/api/spike/range?'+p);
    const data = await res.json();
    stopProg();
    if (!res.ok) { showErr(data.detail||JSON.stringify(data)); return; }
    renderResults([], null, data.rows||[], 'range', data);
  } catch(e) { stopProg(); showErr('Failed: '+e.message); }
  finally { btn.disabled=false; }
}

// ── RENDER ────────────────────────────────────────────────────────────────────
function renderResults(trades, chart, rows, mode, fullData) {
  document.getElementById('results').classList.remove('hidden');

  // Aggregate all trades from rows (batch/range) or use passed trades (single)
  const allTrades = mode==='single' ? trades :
    rows.flatMap(r => (r.trades||[]).map(t => ({...t, symbol:r.symbol||t.symbol})));

  const totalPnl = allTrades.reduce((s,t)=>s+t.pnl,0);
  const wins     = allTrades.filter(t=>t.pnl>0).length;
  const winRate  = allTrades.length ? Math.round(wins/allTrades.length*100) : 0;
  const nanoPnl  = allTrades.filter(t=>t.cap_class==='nano').reduce((s,t)=>s+t.pnl,0);
  const smallPnl = allTrades.filter(t=>t.cap_class==='small').reduce((s,t)=>s+t.pnl,0);
  const best     = allTrades.length ? Math.max(...allTrades.map(t=>t.pnl)) : 0;
  const worst    = allTrades.length ? Math.min(...allTrades.map(t=>t.pnl)) : 0;

  document.getElementById('summaryCards').innerHTML = `
    <div class="card"><div class="card-lbl">Total P&L</div><div class="card-val ${pc(totalPnl)}">${fmtPnl(totalPnl)}</div></div>
    <div class="card"><div class="card-lbl">Trades</div><div class="card-val white">${allTrades.length}</div></div>
    <div class="card"><div class="card-lbl">Win Rate</div><div class="card-val ${winRate>=50?'green':'red'}">${winRate}%</div></div>
    <div class="card"><div class="card-lbl">Nano P&L</div><div class="card-val ${pc(nanoPnl)} nano-c">${fmtPnl(nanoPnl)}</div></div>
    <div class="card"><div class="card-lbl">Small P&L</div><div class="card-val ${pc(smallPnl)} small-c">${fmtPnl(smallPnl)}</div></div>
    <div class="card"><div class="card-lbl">Best Trade</div><div class="card-val green">${fmtPnl(best)}</div></div>
    <div class="card"><div class="card-lbl">Worst Trade</div><div class="card-val red">${fmtPnl(worst)}</div></div>
  `;

  // Class breakdown
  const ns = fullData?.nano  || statsFor(allTrades,'nano');
  const ss = fullData?.small || statsFor(allTrades,'small');
  document.getElementById('classGrid').innerHTML = `
    <div class="class-card class-nano">
      <div class="class-card-title nano-c">🔵 Nano Cap (&lt; $${document.getElementById('nanoMaxPrice').value})</div>
      <div class="class-stat"><span>Trades</span><span>${ns.trades}</span></div>
      <div class="class-stat"><span>Wins / Losses</span><span>${ns.wins} / ${ns.losses}</span></div>
      <div class="class-stat"><span>Win Rate</span><span>${ns.win_rate}%</span></div>
      <div class="class-stat"><span>Net P&L</span><span class="${pc(ns.net_pnl)}">${fmtPnl(ns.net_pnl)}</span></div>
      <div class="class-stat"><span>Avg / Trade</span><span class="${pc(ns.avg_pnl)}">${fmtPnl(ns.avg_pnl)}</span></div>
    </div>
    <div class="class-card class-small">
      <div class="class-card-title small-c">🟢 Small Cap ($${document.getElementById('nanoMaxPrice').value}–$${document.getElementById('smallMaxPrice').value})</div>
      <div class="class-stat"><span>Trades</span><span>${ss.trades}</span></div>
      <div class="class-stat"><span>Wins / Losses</span><span>${ss.wins} / ${ss.losses}</span></div>
      <div class="class-stat"><span>Win Rate</span><span>${ss.win_rate}%</span></div>
      <div class="class-stat"><span>Net P&L</span><span class="${pc(ss.net_pnl)}">${fmtPnl(ss.net_pnl)}</span></div>
      <div class="class-stat"><span>Avg / Trade</span><span class="${pc(ss.avg_pnl)}">${fmtPnl(ss.avg_pnl)}</span></div>
    </div>
  `;

  // Chart (single day only)
  const chartTabBtn = document.querySelector('.result-tabs .rtab');
  if (chart && chart.length && mode === 'single') {
    document.getElementById('noChartMsg').classList.add('hidden');
    renderCharts(chart, allTrades);
    showTab('tabChart');
  } else {
    document.getElementById('noChartMsg').classList.remove('hidden');
    if (priceInst) { priceInst.destroy(); priceInst=null; }
    if (rsiInst)   { rsiInst.destroy();   rsiInst=null; }
    showTab('tabTrades');
  }

  // Trades table
  const tb = document.getElementById('tradesBody');
  tb.innerHTML = '';
  allTrades.forEach(t => {
    const reasonBadge = t.reason==='rsi_profit' ? '<span class="badge b-rsi">RSI Profit</span>'
      : t.reason==='stop_limit' ? '<span class="badge b-stop">Stop</span>'
      : t.reason==='time_exit'  ? '<span class="badge b-time">Time</span>'
      : `<span class="badge b-eod">${t.reason}</span>`;
    const classBadge = t.cap_class==='nano'
      ? '<span class="badge b-nano">Nano</span>'
      : '<span class="badge b-small">Small</span>';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${t.date||'—'}</td>
      <td><span style="color:#60a5fa;font-weight:600">${t.symbol||'—'}</span></td>
      <td>${classBadge}</td>
      <td style="color:#94a3b8;font-size:.71rem">${t.entry_time?t.entry_time.slice(11,16):'—'}</td>
      <td>$${t.entry_price}</td>
      <td>$${t.exit_price}</td>
      <td>${t.shares}</td>
      <td class="${pc(t.pnl)}">${fmtPnl(t.pnl)}</td>
      <td>${reasonBadge}</td>
      <td style="color:#94a3b8">${t.rsi_at_entry!=null?t.rsi_at_entry.toFixed(1):'—'}</td>
      <td style="color:#94a3b8">${t.rsi_at_exit!=null?t.rsi_at_exit.toFixed(1):'—'}</td>
    `;
    tb.appendChild(tr);
  });

  // Daily table
  const daily = fullData?.daily || buildDaily(allTrades);
  const db = document.getElementById('dailyBody');
  db.innerHTML = '';
  daily.forEach(d => {
    const tr = document.createElement('tr');
    const symTxt = d.symbols
      ? Object.entries(d.symbols).map(([s,v])=>`${s}: ${fmtPnl(v.pnl||v)}`).join(', ')
      : '';
    tr.innerHTML = `
      <td>${d.date}</td>
      <td class="${pc(d.net_pnl)}">${fmtPnl(d.net_pnl)}</td>
      <td>${d.trades}</td>
      <td style="color:#94a3b8;font-size:.72rem">${symTxt}</td>
    `;
    db.appendChild(tr);
  });
}

function statsFor(trades, cls) {
  const t = trades.filter(x=>x.cap_class===cls);
  const wins = t.filter(x=>x.pnl>0).length;
  return { trades:t.length, wins, losses:t.length-wins,
    win_rate: t.length?Math.round(wins/t.length*100):0,
    net_pnl:  Math.round(t.reduce((s,x)=>s+x.pnl,0)*100)/100,
    avg_pnl:  t.length?Math.round(t.reduce((s,x)=>s+x.pnl,0)/t.length*100)/100:0 };
}

function buildDaily(trades) {
  const m={};
  trades.forEach(t=>{
    const d=t.date||'unknown';
    if(!m[d]) m[d]={date:d,net_pnl:0,trades:0,symbols:{}};
    m[d].net_pnl=Math.round((m[d].net_pnl+t.pnl)*100)/100;
    m[d].trades++;
    const s=t.symbol||'?';
    m[d].symbols[s]=(m[d].symbols[s]||0)+t.pnl;
  });
  return Object.values(m).sort((a,b)=>a.date.localeCompare(b.date));
}

// ── CHARTS ────────────────────────────────────────────────────────────────────
function renderCharts(chart, trades) {
  // Filter to 9:00 AM – 3:30 PM
  const filtered = chart.filter(c => {
    const h = new Date(c.t).getHours();
    return h >= 9 && h < 15;
  });

  const labels     = filtered.map(c => c.t.slice(11,16));
  const idxLabels  = filtered.map((_,i) => i);
  const closes     = filtered.map(c => c.c);
  const rsiVals    = filtered.map(c => c.rsi);
  const avgLine    = filtered.map(c => c.avg_entry);
  const profitLine = filtered.map(c => c.rsi_profit);

  const buyPts  = [];
  const rsiProfPts = [];
  const stopPts = [];
  const timePts = [];

  filtered.forEach((c,i) => {
    if (!c.signal) return;
    if (c.signal==='buy')  buyPts.push({x:i, y:c.c});
    else if (c.signal==='sell') {
      const t = trades.find(tr=>tr.exit_time&&tr.exit_time.slice(11,16)===c.t.slice(11,16));
      const reason = t ? t.reason : 'sell';
      if (reason==='rsi_profit')  rsiProfPts.push({x:i, y:c.c});
      else if (reason==='stop_limit') stopPts.push({x:i, y:c.avg_entry||c.c});
      else                        timePts.push({x:i, y:c.c});
    }
  });

  if (priceInst) priceInst.destroy();
  priceInst = new Chart(document.getElementById('priceChart'), {
    type: 'line',
    data: {
      labels: idxLabels,
      datasets: [
        { label:'Price',     data:closes,  borderColor:'#64748b', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0 },
        { label:'Avg Entry / Stop', data:avgLine, borderColor:'#fbbf24', backgroundColor:'transparent', borderWidth:1.2, pointRadius:0, borderDash:[4,3], tension:0 },
        { type:'scatter', label:'Buy (spike)',  data:buyPts,     backgroundColor:'#22c55e', pointRadius:8, pointStyle:'triangle' },
        { type:'scatter', label:'RSI Exit',     data:rsiProfPts, backgroundColor:'#34d399', pointRadius:7, pointStyle:'triangle' },
        { type:'scatter', label:'Stop at avg',  data:stopPts,    backgroundColor:'#f87171', pointRadius:7, pointStyle:'triangle', rotation:180 },
        { type:'scatter', label:'Time/EOD Exit',data:timePts,    backgroundColor:'#fbbf24', pointRadius:6, pointStyle:'rectRot' },
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      scales: {
        x: { type:'category', ticks:{ color:'#94a3b8', maxTicksLimit:20, callback:(v,i)=>labels[i]||'' }, grid:{color:'#1e2535'} },
        y: { ticks:{ color:'#94a3b8', callback:v=>'$'+v.toFixed(2) }, grid:{color:'#1e2535'} }
      },
      plugins: { legend:{ labels:{ color:'#94a3b8', boxWidth:12, font:{size:11} }},
        tooltip:{ callbacks:{ title:(items)=>labels[items[0].dataIndex]||'',
          label:(item)=>{ const v=item.raw; return typeof v==='object'?`${item.dataset.label}: $${v.y?.toFixed(4)}`:`${item.dataset.label}: $${v?.toFixed(4)}`; }}}
      }
    }
  });

  if (rsiInst) rsiInst.destroy();
  const rsiProfLevel = filtered.find(c=>c.rsi_profit)?.rsi_profit || 60;
  rsiInst = new Chart(document.getElementById('rsiChart'), {
    type:'line',
    data:{ labels:idxLabels, datasets:[
      { label:'RSI', data:rsiVals, borderColor:'#60a5fa', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.1 },
    ]},
    options:{
      responsive:true, maintainAspectRatio:false,
      scales:{
        x:{ type:'category', ticks:{ color:'#94a3b8', maxTicksLimit:20, callback:(v,i)=>labels[i]||'' }, grid:{color:'#1e2535'} },
        y:{ min:0, max:100, ticks:{ color:'#94a3b8', stepSize:20 }, grid:{color:'#1e2535'} }
      },
      plugins:{
        legend:{ labels:{ color:'#94a3b8', boxWidth:12 }},
        annotation:{ annotations:{
          profitLine:{ type:'line', yMin:rsiProfLevel, yMax:rsiProfLevel, borderColor:'#34d399', borderWidth:1.2, borderDash:[4,3],
            label:{ content:'Profit '+rsiProfLevel, display:true, color:'#34d399', font:{size:10}, position:'start', backgroundColor:'transparent' }},
          midLine:{ type:'line', yMin:50, yMax:50, borderColor:'#374151', borderWidth:1, borderDash:[2,4] },
        }}
      }
    }
  });
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function showTab(id) {
  document.querySelectorAll('.rtab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.rtab').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  const idx = ['tabChart','tabTrades','tabDaily'].indexOf(id);
  document.querySelectorAll('.rtab')[idx]?.classList.add('active');
}

// ── Sort ──────────────────────────────────────────────────────────────────────
const _ss={};
function srt(tblId,col){
  const tbl=document.getElementById(tblId), tb=tbl.querySelector('tbody');
  const rows=[...tb.querySelectorAll('tr')];
  const asc=!_ss[tblId+col]; _ss[tblId+col]=asc;
  rows.sort((a,b)=>{
    const va=(a.cells[col]?.textContent||'').trim().replace(/[$+,]/g,'');
    const vb=(b.cells[col]?.textContent||'').trim().replace(/[$+,]/g,'');
    const na=parseFloat(va),nb=parseFloat(vb);
    if(!isNaN(na)&&!isNaN(nb)) return asc?na-nb:nb-na;
    return asc?va.localeCompare(vb):vb.localeCompare(va);
  });
  rows.forEach(r=>tb.appendChild(r));
}
</script>
</body>
</html>"""
