ALERTS_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alert-Driven Backtest — Nano Spike + Sweep</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
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
.meta-line{font-size:.76rem;color:#64748b;margin-bottom:12px}
.meta-line b{color:#94a3b8}

.global-row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px}
.f{display:flex;flex-direction:column;gap:3px}
.f label{font-size:.67rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
.f input,.f select{background:#0d1117;border:1px solid #374151;border-radius:6px;color:#e2e8f0;padding:5px 8px;font-size:.83rem}
.f input:focus,.f select:focus{outline:none;border-color:#60a5fa}
.f input{width:110px}
.f input.narrow{width:80px}
.f input.wide{width:170px}
.f select{width:140px}
.f input[type=checkbox]{width:auto;height:16px;align-self:center}
.ck{display:flex;align-items:center;gap:6px;flex-direction:row !important}
.ck label{text-transform:none;font-size:.78rem}

.cap-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:900px){.cap-grid{grid-template-columns:1fr}}
.cap-section{border-radius:10px;padding:13px 15px}
.cap-nano{background:#1a1a2e;border:1px solid #312e81}
.cap-sweep{background:#1f1a0f;border:1px solid #78350f}
.cap-trade{background:#1a2a1a;border:1px solid #166534}
.cap-section h3{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:9px}
.nano-title{color:#a5b4fc}.sweep-title{color:#fbbf24}.trade-title{color:#4ade80}
.pf{display:flex;flex-direction:column;gap:3px;margin-bottom:6px}
.pf:last-child{margin-bottom:0}
.pf label{font-size:.65rem;color:#94a3b8}
.pf input,.pf select{background:#0d0f14;border:1px solid #374151;border-radius:5px;color:#e2e8f0;padding:4px 7px;font-size:.82rem;width:100%}
.pf input:focus,.pf select:focus{outline:none;border-color:#60a5fa}
.pf-row{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.pf-row input[type=checkbox]{width:auto}
.pf-row label{font-size:.7rem;color:#cbd5e1}

.chip-wrap{display:flex;flex-wrap:wrap;gap:4px;align-items:center;background:#0d0f14;border:1px solid #374151;border-radius:6px;padding:4px 7px;min-height:34px;min-width:200px;cursor:text}
.chip{display:flex;align-items:center;gap:3px;background:#1e3a5f;border-radius:16px;padding:2px 8px;font-size:.76rem;color:#93c5fd}
.chip button{background:none;border:none;color:#93c5fd;cursor:pointer;font-size:.85rem;padding:0}
.chip button:hover{color:#f87171}
.chip-input{background:none;border:none;color:#e2e8f0;font-size:.82rem;outline:none;min-width:60px}

.btn{border:none;border-radius:7px;cursor:pointer;font-size:.84rem;font-weight:600;padding:8px 18px;transition:opacity .18s}
.btn:hover{opacity:.82}.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-find{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff}
.btn-run{background:linear-gradient(135deg,#059669,#0d9488);color:#fff}

.prog-wrap{display:none;margin-top:10px}
.prog-lbl{font-size:.75rem;color:#94a3b8;margin-top:3px}

.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:9px;margin-bottom:14px}
.card{background:#161b26;border:1px solid #2d3748;border-radius:9px;padding:11px 13px;text-align:center}
.card-lbl{font-size:.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}
.card-val{font-size:1.2rem;font-weight:700}
.green{color:#34d399}.red{color:#f87171}.white{color:#e2e8f0}.blue{color:#60a5fa}.yellow{color:#fbbf24}.purple{color:#a78bfa}

.class-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
@media(max-width:700px){.class-grid{grid-template-columns:1fr}}
.class-card{border-radius:10px;padding:14px 16px}
.class-sweep{background:#1f1a0f;border:1px solid #78350f}
.class-nosweep{background:#161b26;border:1px solid #2d3748}
.class-card-title{font-size:.85rem;font-weight:700;margin-bottom:8px}
.class-stat{display:flex;justify-content:space-between;font-size:.76rem;color:#94a3b8;margin-bottom:3px}
.class-stat span:last-child{color:#e2e8f0;font-weight:600}

.chart-box{background:#161b26;border:1px solid #2d3748;border-radius:10px;padding:13px;margin-bottom:14px}
.chart-box canvas{max-height:260px}

.result-tabs{display:flex;gap:0;margin-bottom:0}
.rtab{background:#1a2035;border:1px solid #2d3748;border-bottom:none;border-radius:6px 6px 0 0;color:#94a3b8;cursor:pointer;font-size:.78rem;padding:6px 14px;transition:all .15s}
.rtab.active{background:#161b26;color:#e2e8f0;border-bottom:1px solid #161b26}
.rtab-panel{display:none}.rtab-panel.active{display:block}

.tbl-wrap{overflow-x:auto;max-height:520px;overflow-y:auto}
table{width:100%;border-collapse:collapse;font-size:.77rem}
th{background:#1a2035;color:#94a3b8;text-transform:uppercase;font-size:.63rem;letter-spacing:.05em;padding:7px 9px;text-align:right;white-space:nowrap;position:sticky;top:0}
th:first-child,th:nth-child(2),th:nth-child(3){text-align:left}
td{padding:6px 9px;border-bottom:1px solid #1e2535;text-align:right;white-space:nowrap}
td:first-child,td:nth-child(2),td:nth-child(3){text-align:left}
tr:hover td{background:#1a2035}
.pp{color:#34d399;font-weight:600}.np{color:#f87171;font-weight:600}.zp{color:#94a3b8}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:.68rem;font-weight:600}
.b-bull{background:#0f2a20;color:#34d399}.b-bear{background:#2a1212;color:#f87171}.b-neutral{background:#222;color:#9ca3af}
.b-tp{background:#0f2a20;color:#34d399}.b-sl{background:#2a1212;color:#f87171}
.b-time{background:#2a2610;color:#fbbf24}.b-eod{background:#222;color:#9ca3af}
.b-sweep{background:#2a2008;color:#fbbf24;border:1px solid #78350f}.b-nosweep{background:#1a1f2e;color:#64748b}

.err-box{background:#2a1515;border:1px solid #7f1d1d;border-radius:8px;padding:11px;color:#fca5a5;font-size:.82rem;margin-bottom:12px}
.note{font-size:.7rem;color:#64748b;margin-top:8px;line-height:1.5}
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
  <a href="/spike">Spike</a>
  <a href="/grid">Grid</a>
  <a href="/alerts" class="active">Alerts</a>
  <a href="/lowfloat">Low Float</a>
</div>

<div class="container">

<!-- ── FILTERS ──────────────────────────────────────────────────────────────── -->
<div class="panel">
  <h2>Alert-Driven Backtest — Nano Spike + Prior Sweep</h2>
  <div class="meta-line" id="metaLine">Loading alert history…</div>

  <!-- Date range + core signal filters -->
  <div class="global-row">
    <div class="f"><label>Start Date</label><input type="date" id="startDate"></div>
    <div class="f"><label>End Date</label><input type="date" id="endDate"></div>
    <div class="f"><label>Tags</label><input type="text" id="tags" value="new,escalation" class="wide"></div>
    <div class="f"><label>Direction</label>
      <select id="direction">
        <option value="bull" selected>Bull (spike up)</option>
        <option value="bear">Bear (spike down)</option>
        <option value="any">Any</option>
      </select>
    </div>
    <div class="f"><label>Symbols (optional)</label>
      <div class="chip-wrap" id="symChipWrap" onclick="document.getElementById('symChipInput').focus()">
        <input class="chip-input" id="symChipInput" placeholder="Symbol + Enter…">
      </div>
    </div>
  </div>

  <div class="cap-grid">
    <!-- Nano spike signal params -->
    <div class="cap-section cap-nano">
      <h3 class="nano-title">🔵 Spike Signal — "Nano Stock"</h3>
      <div class="pf"><label>Max Price ($) — nano ceiling</label><input type="number" id="maxPrice" value="5" min="0.01" max="500" step="0.5"></div>
      <div class="pf"><label>Min Price ($)</label><input type="number" id="minPrice" value="0" min="0" step="0.1"></div>
      <div class="pf"><label>Min Spike % (delta)</label><input type="number" id="minDelta" value="10" min="0" step="0.5"></div>
      <div class="pf"><label>Max Spike % (delta)</label><input type="number" id="maxDelta" value="1000" min="0" step="1"></div>
      <div class="pf"><label>Min $ Value (1m)</label><input type="number" id="minValue" value="100000" min="0" step="10000"></div>
      <div class="pf"><label>Min Trade Count (1m)</label><input type="number" id="minCnt" value="0" min="0" step="10"></div>
    </div>

    <!-- Prior sweep hypothesis params -->
    <div class="cap-section cap-sweep">
      <h3 class="sweep-title">🟡 Prior Sweep Filter — Hypothesis #2</h3>
      <div class="pf-row"><input type="checkbox" id="requireSweep"><label for="requireSweep">Require a prior sweep alert before the spike</label></div>
      <div class="pf"><label>Lookback Window (minutes before spike)</label><input type="number" id="sweepLookback" value="15" min="1" max="240" step="1"></div>
      <div class="pf"><label>Min Sweep Conviction Score (0–99)</label><input type="number" id="sweepMinScore" value="0" min="0" max="99" step="1"></div>
      <div class="pf"><label>Min Sweep $ Value</label><input type="number" id="sweepMinValue" value="0" min="0" step="10000"></div>
      <div class="pf-row"><input type="checkbox" id="sweepMatchDir"><label for="sweepMatchDir">Sweep direction must match spike direction</label></div>
      <div class="note">Even with "Require" unchecked, every result row shows whether a qualifying sweep preceded it — use the With/Without Sweep comparison after running a backtest to see if it mattered.</div>
    </div>
  </div>

  <!-- Trade / exit params -->
  <div class="cap-grid" style="margin-top:12px">
    <div class="cap-section cap-trade">
      <h3 class="trade-title">🟢 Trade Simulation</h3>
      <div class="pf"><label>Buy Amount ($ per trade)</label><input type="number" id="buyAmount" value="500" min="10" step="50"></div>
      <div class="pf"><label>Take Profit % (p)</label><input type="number" id="tpPct" value="20" min="0.5" step="0.5"></div>
      <div class="pf"><label>Stop Loss % (l)</label><input type="number" id="slPct" value="5" min="0.5" step="0.5"></div>
      <div class="pf"><label>Max Hold (minutes, 0 = until session end)</label><input type="number" id="maxHold" value="60" min="0" step="5"></div>
      <div class="pf"><label>Entry Timing</label>
        <select id="entryMode">
          <option value="next_open" selected>Next bar open (realistic, no lookahead)</option>
          <option value="same_close">Same bar close (immediate, optimistic)</option>
        </select>
      </div>
      <div class="pf"><label>If TP &amp; SL both hit in same bar</label>
        <select id="sameBarRule">
          <option value="sl_first" selected>Assume Stop-Loss hit first (conservative)</option>
          <option value="tp_first">Assume Take-Profit hit first (optimistic)</option>
        </select>
      </div>
      <div class="pf"><label>Max Alerts to Backtest (caps Alpaca calls)</label><input type="number" id="maxAlerts" value="300" min="1" max="2000" step="50"></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;justify-content:flex-end">
      <button class="btn btn-find" id="btnFind" onclick="findAlerts()">🔍 Find Alerts</button>
      <button class="btn btn-run" id="btnRun" onclick="runBacktest()">▶ Run Backtest</button>
      <div class="prog-wrap" id="progWrap"><div class="prog-lbl" id="progLbl">Running…</div></div>
      <div class="note">"Find Alerts" just browses the log with your filters. "Run Backtest" fetches real Alpaca 1-min bars for every matched alert and simulates the buy → TP/SL exit.</div>
    </div>
  </div>
</div>

<div class="err-box hidden" id="errBox"></div>

<!-- ── RESULTS ────────────────────────────────────────────────────────────── -->
<div id="results" class="hidden">

  <div class="result-tabs" id="resultTabs">
    <button class="rtab active" onclick="showTab('tabAlerts')">📋 Alerts Found</button>
    <button class="rtab" onclick="showTab('tabBacktest')">📈 Backtest Results</button>
  </div>

  <div id="tabAlerts" class="rtab-panel active panel" style="border-radius:0 0 12px 12px">
    <div class="meta-line" id="alertsMetaLine"></div>
    <div class="tbl-wrap">
      <table id="alertsTable">
        <thead><tr>
          <th>Time (ET)</th><th>Symbol</th><th>Tag</th><th>Direction</th><th>Spike %</th>
          <th>$ Value</th><th>Price</th><th>Cnt/1m</th><th>Prior Sweep?</th><th>Sweep Score</th>
        </tr></thead>
        <tbody id="alertsBody"></tbody>
      </table>
    </div>
  </div>

  <div id="tabBacktest" class="rtab-panel" style="border-radius:0 0 12px 12px">
    <div class="panel" style="margin-top:0">
      <div class="meta-line" id="btMetaLine"></div>
      <div class="cards" id="summaryCards"></div>
      <div class="class-grid" id="sweepClassGrid"></div>
      <div class="chart-box"><canvas id="equityChart"></canvas></div>
    </div>
    <div class="panel">
      <h2>All Simulated Trades</h2>
      <div class="tbl-wrap">
        <table id="tradesTable">
          <thead><tr>
            <th>Symbol</th><th>Tag</th><th>Direction</th><th>Sweep?</th>
            <th>Entry Time</th><th>Entry $</th><th>Exit Time</th><th>Exit $</th>
            <th>Exit Reason</th><th>Hold (min)</th><th>PnL %</th><th>PnL $</th>
          </tr></thead>
          <tbody id="tradesBody"></tbody>
        </table>
      </div>
    </div>
  </div>

</div>

</div>

<script>
let symbols = [];
let equityChart = null;

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}

// ── Symbol chip input ─────────────────────────────────────────────────────
const symInput = document.getElementById('symChipInput');
symInput.addEventListener('keydown', e=>{
  if(e.key==='Enter' && symInput.value.trim()){
    e.preventDefault();
    const sym = symInput.value.trim().toUpperCase();
    if(!symbols.includes(sym)){ symbols.push(sym); renderSymChips(); }
    symInput.value='';
  } else if(e.key==='Backspace' && !symInput.value && symbols.length){
    symbols.pop(); renderSymChips();
  }
});
function renderSymChips(){
  const wrap = document.getElementById('symChipWrap');
  wrap.querySelectorAll('.chip').forEach(c=>c.remove());
  symbols.forEach((s,i)=>{
    const chip = document.createElement('span');
    chip.className='chip';
    chip.innerHTML = `${escHtml(s)} <button onclick="removeSym(${i},event)">×</button>`;
    wrap.insertBefore(chip, symInput);
  });
}
function removeSym(i,e){ e.stopPropagation(); symbols.splice(i,1); renderSymChips(); }

// ── Init: load meta + default date range ────────────────────────────────────
async function loadMeta(){
  try{
    const r = await fetch('/api/alerts/meta');
    const m = await r.json();
    if(m.min_date){
      document.getElementById('metaLine').innerHTML =
        `Data covers <b>${m.min_date}</b> to <b>${m.max_date}</b> &middot; <b>${m.total_rows.toLocaleString()}</b> alert rows &middot; <b>${m.unique_symbols.toLocaleString()}</b> symbols`;
      document.getElementById('endDate').value = m.max_date;
      const start = new Date(m.max_date + 'T00:00:00');
      start.setDate(start.getDate()-13);
      const minD = new Date(m.min_date + 'T00:00:00');
      document.getElementById('startDate').value = (start < minD ? minD : start).toISOString().slice(0,10);
    } else {
      document.getElementById('metaLine').textContent = 'No alert_history.csv data found.';
    }
  }catch(e){
    document.getElementById('metaLine').textContent = 'Could not load alert history meta.';
  }
}
loadMeta();

// ── Shared filter collection ─────────────────────────────────────────────
function collectFilterParams(){
  return {
    start_date: document.getElementById('startDate').value,
    end_date:   document.getElementById('endDate').value,
    tags:       document.getElementById('tags').value || 'new,escalation',
    direction:  document.getElementById('direction').value,
    min_delta:  document.getElementById('minDelta').value,
    max_delta:  document.getElementById('maxDelta').value,
    min_value:  document.getElementById('minValue').value,
    max_price:  document.getElementById('maxPrice').value,
    min_price:  document.getElementById('minPrice').value,
    min_cnt:    document.getElementById('minCnt').value,
    symbols:    symbols.join(','),
    require_sweep:          document.getElementById('requireSweep').checked,
    sweep_lookback_min:     document.getElementById('sweepLookback').value,
    sweep_min_value:        document.getElementById('sweepMinValue').value,
    sweep_min_score:        document.getElementById('sweepMinScore').value,
    sweep_match_direction:  document.getElementById('sweepMatchDir').checked,
  };
}
function qs(obj){ return Object.entries(obj).map(([k,v])=>`${k}=${encodeURIComponent(v)}`).join('&'); }
function showErr(msg){ const b=document.getElementById('errBox'); b.textContent=msg; b.classList.remove('hidden'); }
function clearErr(){ document.getElementById('errBox').classList.add('hidden'); }

function showTab(id){
  document.querySelectorAll('.rtab').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.rtab-panel').forEach(p=>p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  const idx = id==='tabAlerts' ? 0 : 1;
  document.querySelectorAll('.rtab')[idx].classList.add('active');
}

function dirBadge(d){
  const cls = d==='bull' ? 'b-bull' : d==='bear' ? 'b-bear' : 'b-neutral';
  return `<span class="badge ${cls}">${escHtml(d||'—')}</span>`;
}
function sweepBadge(had){
  return had ? `<span class="badge b-sweep">YES</span>` : `<span class="badge b-nosweep">no</span>`;
}
function exitBadge(reason){
  const map = {tp:'b-tp', sl:'b-sl', time:'b-time', eod:'b-eod'};
  return `<span class="badge ${map[reason]||'b-eod'}">${escHtml(reason||'—').toUpperCase()}</span>`;
}
function pnlSpan(v, suffix){
  const cls = v>0?'pp':v<0?'np':'zp';
  const sign = v>0?'+':'';
  return `<span class="${cls}">${sign}${v.toFixed(2)}${suffix}</span>`;
}

// ── Find Alerts ───────────────────────────────────────────────────────────
async function findAlerts(){
  clearErr();
  if(!document.getElementById('startDate').value || !document.getElementById('endDate').value){
    showErr('Pick a start and end date first.'); return;
  }
  const btn = document.getElementById('btnFind');
  btn.disabled = true; btn.textContent = 'Searching…';
  try{
    const params = collectFilterParams();
    params.limit = 1000;
    const r = await fetch('/api/alerts/query?'+qs(params));
    if(!r.ok){ const t = await r.text(); throw new Error(t); }
    const data = await r.json();
    renderAlerts(data);
    document.getElementById('results').classList.remove('hidden');
    showTab('tabAlerts');
  }catch(e){
    showErr('Find Alerts failed: '+e.message);
  }finally{
    btn.disabled = false; btn.textContent = '🔍 Find Alerts';
  }
}

function renderAlerts(data){
  document.getElementById('alertsMetaLine').innerHTML =
    `<b>${data.total_matched.toLocaleString()}</b> alerts matched your filters &middot; showing <b>${data.returned.toLocaleString()}</b>`;
  const body = document.getElementById('alertsBody');
  body.innerHTML = data.alerts.map(a=>`
    <tr>
      <td>${escHtml(a.ts.replace('T',' ').slice(0,19))}</td>
      <td><b>${escHtml(a.sym)}</b></td>
      <td>${escHtml(a.tag)}</td>
      <td>${dirBadge(a.direction)}</td>
      <td>${a.delta.toFixed(1)}%</td>
      <td>$${Math.round(a.value1m).toLocaleString()}</td>
      <td>$${a.price.toFixed(4)}</td>
      <td>${Math.round(a.cnt1m)}</td>
      <td>${sweepBadge(a.had_sweep)}</td>
      <td>${a.sweep_score!=null ? a.sweep_score.toFixed(0) : '—'}</td>
    </tr>`).join('');
}

// ── Run Backtest ──────────────────────────────────────────────────────────
async function runBacktest(){
  clearErr();
  if(!document.getElementById('startDate').value || !document.getElementById('endDate').value){
    showErr('Pick a start and end date first.'); return;
  }
  const btn = document.getElementById('btnRun');
  btn.disabled = true; btn.textContent = 'Running…';
  document.getElementById('progWrap').style.display = 'block';
  document.getElementById('progLbl').textContent = 'Fetching alert log + Alpaca bars — this can take a bit for large date ranges…';
  try{
    const params = collectFilterParams();
    params.buy_amount     = document.getElementById('buyAmount').value;
    params.tp_pct         = document.getElementById('tpPct').value;
    params.sl_pct         = document.getElementById('slPct').value;
    params.max_hold_min   = document.getElementById('maxHold').value;
    params.entry_mode     = document.getElementById('entryMode').value;
    params.same_bar_rule  = document.getElementById('sameBarRule').value;
    params.max_alerts     = document.getElementById('maxAlerts').value;
    const r = await fetch('/api/alerts/backtest?'+qs(params));
    if(!r.ok){ const t = await r.text(); throw new Error(t); }
    const data = await r.json();
    renderBacktest(data);
    document.getElementById('results').classList.remove('hidden');
    showTab('tabBacktest');
  }catch(e){
    showErr('Run Backtest failed: '+e.message);
  }finally{
    btn.disabled = false; btn.textContent = '▶ Run Backtest';
    document.getElementById('progWrap').style.display = 'none';
  }
}

function statCards(s){
  return [
    {lbl:'Trades', val:s.n, cls:'white'},
    {lbl:'Win Rate', val:s.win_rate+'%', cls: s.win_rate>=50?'green':'red'},
    {lbl:'Total PnL $', val:(s.total_pnl>=0?'+':'')+'$'+s.total_pnl.toFixed(2), cls: s.total_pnl>=0?'green':'red'},
    {lbl:'Avg PnL %', val:(s.avg_pnl_pct>=0?'+':'')+s.avg_pnl_pct.toFixed(2)+'%', cls: s.avg_pnl_pct>=0?'green':'red'},
    {lbl:'TP Hits', val:s.tp_hits, cls:'green'},
    {lbl:'SL Hits', val:s.sl_hits, cls:'red'},
    {lbl:'Time/EOD Exits', val:s.time_exits, cls:'yellow'},
    {lbl:'Avg Hold (min)', val:s.avg_hold_min, cls:'blue'},
  ];
}

function renderBacktest(data){
  document.getElementById('btMetaLine').innerHTML =
    `<b>${data.total_matched.toLocaleString()}</b> alerts matched &middot; <b>${data.alerts_considered.toLocaleString()}</b> considered (cap) &middot; ` +
    `<b>${data.trades_executed.toLocaleString()}</b> trades simulated &middot; <b>${data.skipped.toLocaleString()}</b> skipped (no bar data)`;

  document.getElementById('summaryCards').innerHTML = statCards(data.overall).map(c=>`
    <div class="card"><div class="card-lbl">${c.lbl}</div><div class="card-val ${c.cls}">${c.val}</div></div>`).join('');

  const ws = data.with_sweep, wos = data.without_sweep;
  document.getElementById('sweepClassGrid').innerHTML = `
    <div class="class-card class-sweep">
      <div class="class-card-title" style="color:#fbbf24">🟡 With Prior Sweep (n=${ws.n})</div>
      <div class="class-stat"><span>Win Rate</span><span>${ws.win_rate}%</span></div>
      <div class="class-stat"><span>Avg PnL %</span><span>${ws.avg_pnl_pct>=0?'+':''}${ws.avg_pnl_pct}%</span></div>
      <div class="class-stat"><span>Total PnL $</span><span>${ws.total_pnl>=0?'+':''}$${ws.total_pnl.toFixed(2)}</span></div>
      <div class="class-stat"><span>TP / SL / Time</span><span>${ws.tp_hits} / ${ws.sl_hits} / ${ws.time_exits}</span></div>
    </div>
    <div class="class-card class-nosweep">
      <div class="class-card-title" style="color:#94a3b8">⚪ Without Prior Sweep (n=${wos.n})</div>
      <div class="class-stat"><span>Win Rate</span><span>${wos.win_rate}%</span></div>
      <div class="class-stat"><span>Avg PnL %</span><span>${wos.avg_pnl_pct>=0?'+':''}${wos.avg_pnl_pct}%</span></div>
      <div class="class-stat"><span>Total PnL $</span><span>${wos.total_pnl>=0?'+':''}$${wos.total_pnl.toFixed(2)}</span></div>
      <div class="class-stat"><span>TP / SL / Time</span><span>${wos.tp_hits} / ${wos.sl_hits} / ${wos.time_exits}</span></div>
    </div>`;

  renderEquityChart(data.equity_curve);

  const body = document.getElementById('tradesBody');
  body.innerHTML = data.trades.map(t=>`
    <tr>
      <td><b>${escHtml(t.sym)}</b></td>
      <td>${escHtml(t.tag)}</td>
      <td>${dirBadge(t.direction)}</td>
      <td>${sweepBadge(t.had_sweep)}</td>
      <td>${escHtml(t.entry_ts.replace('T',' ').slice(0,19))}</td>
      <td>$${t.entry_price.toFixed(4)}</td>
      <td>${escHtml(t.exit_ts.replace('T',' ').slice(0,19))}</td>
      <td>$${t.exit_price.toFixed(4)}</td>
      <td>${exitBadge(t.exit_reason)}</td>
      <td>${t.hold_min}</td>
      <td>${pnlSpan(t.pnl_pct,'%')}</td>
      <td>${pnlSpan(t.pnl_dollar,'')}</td>
    </tr>`).join('');
}

function renderEquityChart(curve){
  const ctx = document.getElementById('equityChart');
  const labels = curve.map(p=>p.i);
  const vals = curve.map(p=>p.cum_pnl);
  if(equityChart) equityChart.destroy();
  equityChart = new Chart(ctx, {
    type:'line',
    data:{ labels, datasets:[{
      label:'Cumulative PnL ($)', data:vals, borderColor:'#3b82f6',
      backgroundColor:'rgba(59,130,246,0.12)', fill:true, tension:0.15, pointRadius:0, borderWidth:2,
    }]},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{labels:{color:'#94a3b8'}} },
      scales:{
        x:{ title:{display:true,text:'Trade #',color:'#64748b'}, ticks:{color:'#64748b'}, grid:{color:'#1e2535'} },
        y:{ title:{display:true,text:'Cumulative PnL ($)',color:'#64748b'}, ticks:{color:'#64748b'}, grid:{color:'#1e2535'} },
      }
    }
  });
}
</script>
</body>
</html>
"""
