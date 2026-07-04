LOWFLOAT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Low-Float Spike Backtest</title>
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

.row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end}
.f{display:flex;flex-direction:column;gap:3px}
.f label{font-size:.67rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
.f input,.f select{background:#0d1117;border:1px solid #374151;border-radius:6px;color:#e2e8f0;padding:5px 8px;font-size:.83rem;width:120px}
.f input:focus,.f select:focus{outline:none;border-color:#60a5fa}
.f input.narrow{width:88px}

button{background:#2563eb;color:#fff;border:none;border-radius:7px;padding:8px 20px;font-size:.85rem;font-weight:600;cursor:pointer}
button:hover{background:#1d4ed8}
button:disabled{background:#374151;cursor:not-allowed}
button.green{background:#059669}button.green:hover{background:#047857}

.status{font-size:.78rem;color:#94a3b8;margin-left:10px}
.status.err{color:#f87171}

table{width:100%;border-collapse:collapse;font-size:.78rem}
th{color:#94a3b8;text-transform:uppercase;font-size:.63rem;letter-spacing:.05em;text-align:right;padding:6px 8px;border-bottom:1px solid #2d3748;white-space:nowrap;cursor:default}
td{padding:5px 8px;border-bottom:1px solid #1f2735;text-align:right;white-space:nowrap}
th:nth-child(-n+3),td:nth-child(-n+3){text-align:left}
tr.pass{background:rgba(16,185,129,.06)}
tr.dim td{color:#4b5563}
tr:hover{background:rgba(96,165,250,.08)}
td.sym{font-weight:700;color:#60a5fa}
.pos{color:#34d399}.neg{color:#f87171}
.badge{display:inline-block;font-size:.62rem;font-weight:700;border-radius:4px;padding:1px 6px;margin-left:5px}
.badge.lf{background:#065f46;color:#6ee7b7}
.badge.sp{background:#713f12;color:#fcd34d}

.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
.card{background:#0d1117;border:1px solid #2d3748;border-radius:10px;padding:10px 13px}
.card .k{font-size:.62rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.card .v{font-size:1.15rem;font-weight:700}

.dist{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.dist-item{background:#0d1117;border:1px solid #2d3748;border-radius:8px;padding:8px 14px;text-align:center;min-width:96px}
.dist-item .p{font-size:.68rem;color:#94a3b8}
.dist-item .n{font-size:1.05rem;font-weight:700;color:#fbbf24}

.chart-card{background:#0d1117;border:1px solid #2d3748;border-radius:10px;padding:12px 14px;margin-bottom:12px}
.chart-head{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px;font-size:.78rem;color:#94a3b8}
.chart-head b{color:#e2e8f0;font-size:.92rem}
.chart-wrap{height:300px;position:relative}
.hidden{display:none}
.hint{font-size:.72rem;color:#64748b;margin-top:8px}
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
  <a href="/alerts">Alerts</a>
  <a href="/lowfloat" class="active">Low Float</a>
</div>

<div class="container">

  <div class="panel">
    <h2>1 · Scan a day for low-float spikers</h2>
    <div class="meta-line" id="metaLine">Loading alert database…</div>
    <div class="row">
      <div class="f"><label>Date</label><input type="date" id="scanDate"></div>
      <div class="f"><label>Max float (M shares)</label><input type="number" id="maxFloat" value="3" step="0.5" min="0.1" class="narrow"></div>
      <div class="f"><label>Min day spike %</label><input type="number" id="minSpike" value="10" step="1" class="narrow"></div>
      <div class="f"><label>Scan top N by $ flow</label><input type="number" id="topN" value="60" step="10" min="10" max="200" class="narrow"></div>
      <div class="f"><label>Max price ($, 0=off)</label><input type="number" id="maxPrice" value="0" step="1" min="0" class="narrow"></div>
      <button id="scanBtn">Scan Day</button>
      <span class="status" id="scanStatus"></span>
    </div>
    <div class="hint">Symbols are ranked by total alert dollar-flow from alerts.db. Float comes from Yahoo Finance (cached — first scan of new symbols takes ~10-20s). Spike % = day high vs previous close.</div>
  </div>

  <div class="panel hidden" id="candPanel">
    <h2>2 · Pick tickers <span style="color:#64748b;font-weight:400">(rows matching float + spike filters are highlighted &amp; pre-checked)</span></h2>
    <div style="overflow-x:auto">
    <table id="candTable">
      <thead><tr>
        <th></th><th>#</th><th>Sym</th><th>Float M</th><th>Spike %</th><th>Close %</th><th>Gap %</th>
        <th>$ Flow</th><th>Alerts</th><th>Sweeps</th><th>Vol</th><th>1st Alert</th>
        <th>Prev Cls</th><th>Day High</th><th>Day Cls</th><th>Day Vol</th>
      </tr></thead>
      <tbody></tbody>
    </table>
    </div>
  </div>

  <div class="panel hidden" id="btPanel">
    <h2>3 · Backtest parameters</h2>
    <div class="row">
      <div class="f"><label>Spike trigger %</label><input type="number" id="pSpike" value="10" step="0.5" class="narrow"></div>
      <div class="f"><label>Entry delta %</label><input type="number" id="pDelta" value="1" step="0.25" class="narrow"></div>
      <div class="f"><label>$ per trade</label><input type="number" id="pAmount" value="1000" step="100" class="narrow"></div>
      <div class="f"><label>Stop loss %</label><input type="number" id="pSL" value="10" step="1" class="narrow"></div>
      <div class="f"><label>Trailing stop % (0 = off)</label><input type="number" id="pTrail" value="10" step="1" class="narrow"></div>
      <div class="f"><label>Baseline</label>
        <select id="pBaseline"><option value="prev_close">Prev close</option><option value="day_open">Day open</option></select>
      </div>
      <div class="f"><label>Entry window start</label><input type="time" id="pStart" value="09:30" class="narrow"></div>
      <div class="f"><label>Entry window end</label><input type="time" id="pEnd" value="15:30" class="narrow"></div>
      <div class="f"><label>Force exit time</label><input type="time" id="pExit" value="15:55" class="narrow"></div>
      <button class="green" id="runBtn">Run Backtest</button>
      <span class="status" id="runStatus"></span>
    </div>
    <div class="hint">Entry fills at baseline × (1 + spike% + delta%) — e.g. 10% + 1% ⇒ buy at +11%. If a bar gaps through the level, fill is that bar's open. Exit: hard stop at entry − SL%, ratcheted up to (post-entry high − trail%) as the stock makes new highs — winners ride until they pull back trail% from their peak. Set entry window start to 04:00 to include pre-market.</div>
  </div>

  <div class="panel hidden" id="resPanel">
    <h2>4 · Results</h2>
    <div class="cards" id="statCards"></div>
    <h2 style="margin-top:6px">How far did the runners go after the trigger?</h2>
    <div class="dist" id="runupDist"></div>
    <div class="hint" id="runupNote"></div>
    <div style="overflow-x:auto;margin-top:14px">
    <table id="tradeTable">
      <thead><tr>
        <th>Sym</th><th>Baseline</th><th>Status</th><th>Entry Time</th><th>Entry $</th><th>Exit Time</th><th>Exit $</th>
        <th>Reason</th><th>Hold m</th><th>P&amp;L %</th><th>P&amp;L $</th><th>Max gain %</th><th>Max DD %</th><th>Day max vs base %</th>
      </tr></thead>
      <tbody></tbody>
    </table>
    </div>
    <div id="charts" style="margin-top:16px"></div>
  </div>

</div>

<script>
const $ = id => document.getElementById(id);
const fmt$ = v => v==null ? '—' : '$'+Number(v).toLocaleString(undefined,{maximumFractionDigits:0});
const fmtN = (v,d=2) => v==null ? '—' : Number(v).toFixed(d);
const cls  = v => v==null ? '' : (v>=0 ? 'pos' : 'neg');
let charts = [];

async function loadMeta(){
  try{
    const m = await (await fetch('/api/lowfloat/meta')).json();
    $('metaLine').innerHTML = `alerts.db: <b>${m.total_rows.toLocaleString()}</b> alerts, <b>${m.min_date}</b> → <b>${m.max_date}</b>`;
    $('scanDate').min = m.min_date; $('scanDate').max = m.max_date; $('scanDate').value = m.max_date;
  }catch(e){ $('metaLine').textContent = 'Could not read alerts.db meta: '+e; }
}
loadMeta();

$('scanBtn').onclick = async () => {
  const day = $('scanDate').value;
  if(!day){ $('scanStatus').textContent = 'pick a date'; return; }
  $('scanBtn').disabled = true;
  $('scanStatus').className = 'status';
  $('scanStatus').textContent = 'scanning… (float lookups may take a while on first run)';
  try{
    const q = new URLSearchParams({day, max_float_m: $('maxFloat').value, min_spike_pct: $('minSpike').value,
                                   top_n: $('topN').value, max_price: $('maxPrice').value});
    const r = await fetch('/api/lowfloat/candidates?'+q);
    if(!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const d = await r.json();
    renderCandidates(d);
    $('scanStatus').textContent = `${d.total_active} active symbols · scanned top ${d.scanned} · ${d.passing} pass float+spike filters`;
  }catch(e){
    $('scanStatus').className = 'status err';
    $('scanStatus').textContent = 'error: '+e.message;
  }finally{ $('scanBtn').disabled = false; }
};

function renderCandidates(d){
  const tb = $('candTable').querySelector('tbody');
  tb.innerHTML = '';
  let checked = 0;
  d.candidates.forEach((c,i) => {
    const pass = c.passes_float && c.passes_spike;
    const tr = document.createElement('tr');
    tr.className = pass ? 'pass' : 'dim';
    const autoCheck = pass && checked < 10; if(autoCheck) checked++;
    tr.innerHTML = `
      <td><input type="checkbox" class="pick" value="${c.sym}" ${autoCheck?'checked':''}></td>
      <td>${i+1}</td>
      <td class="sym">${c.sym}${c.passes_float?'<span class="badge lf">LOW FLOAT</span>':''}${c.passes_spike?'<span class="badge sp">SPIKE</span>':''}<br><span style="font-size:.63rem;color:#64748b;font-weight:400">${c.name||''}</span></td>
      <td>${c.float_m==null?'?':fmtN(c.float_m,2)}</td>
      <td class="${cls(c.spike_pct)}">${fmtN(c.spike_pct,1)}</td>
      <td class="${cls(c.close_pct)}">${fmtN(c.close_pct,1)}</td>
      <td class="${cls(c.gap_pct)}">${fmtN(c.gap_pct,1)}</td>
      <td>${fmt$(c.dollar_flow)}</td>
      <td>${c.alerts}</td><td>${c.sweeps}</td><td>${c.vol_spikes}</td>
      <td>${c.first_alert||'—'}</td>
      <td>${fmtN(c.prev_close)}</td><td>${fmtN(c.day_high)}</td><td>${fmtN(c.day_close)}</td>
      <td>${c.day_volume==null?'—':Number(c.day_volume).toLocaleString()}</td>`;
    tr.onclick = e => { if(e.target.tagName!=='INPUT'){ const cb=tr.querySelector('.pick'); cb.checked=!cb.checked; } };
    tb.appendChild(tr);
  });
  $('candPanel').classList.remove('hidden');
  $('btPanel').classList.remove('hidden');
  $('pSpike').value = $('minSpike').value;
}

$('runBtn').onclick = async () => {
  const syms = [...document.querySelectorAll('.pick:checked')].map(cb => cb.value);
  if(syms.length === 0){ $('runStatus').className='status err'; $('runStatus').textContent='select at least one ticker'; return; }
  if(syms.length > 20){ $('runStatus').className='status err'; $('runStatus').textContent='max 20 tickers per run'; return; }
  $('runBtn').disabled = true;
  $('runStatus').className='status'; $('runStatus').textContent = `running ${syms.length} tickers…`;
  try{
    const q = new URLSearchParams({
      day: $('scanDate').value, symbols: syms.join(','),
      spike_pct: $('pSpike').value, entry_delta_pct: $('pDelta').value, amount: $('pAmount').value,
      sl_pct: $('pSL').value, trail_pct: $('pTrail').value, baseline: $('pBaseline').value,
      entry_start: $('pStart').value, entry_end: $('pEnd').value, exit_time: $('pExit').value,
    });
    const r = await fetch('/api/lowfloat/backtest?'+q);
    if(!r.ok) throw new Error((await r.json()).detail || r.statusText);
    renderResults(await r.json());
    $('runStatus').textContent = 'done';
  }catch(e){
    $('runStatus').className='status err';
    $('runStatus').textContent = 'error: '+e.message;
  }finally{ $('runBtn').disabled = false; }
};

function card(k,v,color){ return `<div class="card"><div class="k">${k}</div><div class="v" style="${color?'color:'+color:''}">${v}</div></div>`; }

function renderResults(d){
  const s = d.stats || {};
  const pnlColor = (s.total_pnl||0) >= 0 ? '#34d399' : '#f87171';
  $('statCards').innerHTML =
    card('Symbols run', d.n_symbols) +
    card('Triggered ≥'+d.params.spike_pct+'%', d.n_triggered) +
    card('Trades entered', d.n_trades) +
    (s.n ? (
      card('Win rate', s.win_rate+'%') +
      card('Avg P&L / trade', s.avg_pnl_pct+'%', s.avg_pnl_pct>=0?'#34d399':'#f87171') +
      card('Total P&L', fmt$(s.total_pnl)+' on '+fmt$(s.invested), pnlColor) +
      card('Trail / SL / Time', `${s.trail_hits} / ${s.sl_hits} / ${s.time_exits}`) +
      card('Avg hold', s.avg_hold_min+' min') +
      card('Avg max gain after entry', s.avg_mfe_pct+'%', '#fbbf24') +
      card('Median max gain', s.med_mfe_pct+'%', '#fbbf24')
    ) : card('Trades','none triggered'));

  $('runupDist').innerHTML = (d.runup_distribution||[]).map(b =>
    `<div class="dist-item"><div class="n">${b.count} / ${d.n_triggered}</div><div class="p">ran ≥ +${b.gte}% more</div></div>`).join('');
  $('runupNote').textContent = d.avg_runup_after_trigger==null ? '' :
    `After crossing the +${d.params.spike_pct}% trigger, these stocks ran a further ${d.avg_runup_after_trigger}% on average (median ${d.med_runup_after_trigger}%) before end of day — measured to the day's high.`;

  const tb = $('tradeTable').querySelector('tbody');
  tb.innerHTML = '';
  d.results.forEach(r => {
    const tr = document.createElement('tr');
    if(r.error){
      tr.innerHTML = `<td class="sym">${r.sym}</td><td colspan="13" style="text-align:left;color:#f87171">${r.error}</td>`;
    }else if(!r.entered){
      const status = r.triggered ? 'triggered, no fill' : 'never hit trigger';
      tr.className = 'dim';
      tr.innerHTML = `<td class="sym">${r.sym}</td><td>${fmtN(r.baseline)}</td><td style="text-align:left">${status}</td>
        <td colspan="10"></td><td class="${cls(r.day_max_vs_baseline)}">${fmtN(r.day_max_vs_baseline,1)}</td>`;
    }else{
      tr.innerHTML = `
        <td class="sym">${r.sym}</td><td>${fmtN(r.baseline)}</td><td style="text-align:left">traded</td>
        <td>${r.entry_ts.slice(11,16)}</td><td>${fmtN(r.entry_price)}</td>
        <td>${r.exit_ts.slice(11,16)}</td><td>${fmtN(r.exit_price)}</td>
        <td>${r.exit_reason.toUpperCase()}</td><td>${fmtN(r.hold_min,0)}</td>
        <td class="${cls(r.pnl_pct)}">${fmtN(r.pnl_pct)}</td>
        <td class="${cls(r.pnl_dollar)}">${fmt$(r.pnl_dollar)}</td>
        <td class="pos">${fmtN(r.mfe_pct,1)}</td><td class="neg">${fmtN(r.mae_pct,1)}</td>
        <td class="${cls(r.day_max_vs_baseline)}">${fmtN(r.day_max_vs_baseline,1)}</td>`;
    }
    tb.appendChild(tr);
  });

  charts.forEach(c => c.destroy()); charts = [];
  $('charts').innerHTML = '';
  d.results.forEach(r => {
    const ser = d.series && d.series[r.sym];
    if(!ser || r.error) return;
    drawChart(r, ser);
  });
  $('resPanel').classList.remove('hidden');
  $('resPanel').scrollIntoView({behavior:'smooth'});
}

function drawChart(r, ser){
  const wrap = document.createElement('div');
  wrap.className = 'chart-card';
  const head = r.entered
    ? `<b>${r.sym}</b> entry ${fmtN(r.entry_price)} @ ${r.entry_ts.slice(11,16)} → exit ${fmtN(r.exit_price)} @ ${r.exit_ts.slice(11,16)} (${r.exit_reason.toUpperCase()}) <span class="${cls(r.pnl_pct)}">${fmtN(r.pnl_pct)}%</span>`
    : `<b>${r.sym}</b> ${r.triggered ? 'triggered but never filled' : 'never hit the trigger'} — day max vs baseline <span class="${cls(r.day_max_vs_baseline)}">${fmtN(r.day_max_vs_baseline,1)}%</span>`;
  wrap.innerHTML = `<div class="chart-head">${head}</div><div class="chart-wrap"><canvas></canvas></div>`;
  $('charts').appendChild(wrap);

  const labels = ser.t.map(t => t.slice(11,16));
  const n = labels.length;
  const flat = v => Array(n).fill(v);
  const datasets = [
    {label:'Close', data:ser.c, borderColor:'#60a5fa', borderWidth:1.4, pointRadius:0, tension:.1},
    {label:'Baseline', data:flat(r.baseline), borderColor:'#64748b', borderWidth:1, borderDash:[6,4], pointRadius:0},
    {label:'Trigger +'+'%', data:flat(r.trigger_level), borderColor:'#fbbf24', borderWidth:1, borderDash:[4,4], pointRadius:0},
    {label:'Entry level', data:flat(r.entry_level), borderColor:'#34d399', borderWidth:1, borderDash:[4,4], pointRadius:0},
  ];
  if(r.entered){
    if(r.trail_curve && r.trail_curve.length){
      const tmap = new Map(r.trail_curve.map(p => [p[0].slice(11,16), p[1]]));
      datasets.push({label:'Trailing stop', data: labels.map(l => tmap.has(l) ? tmap.get(l) : null),
                     borderColor:'#f97316', borderWidth:1.3, borderDash:[5,3], pointRadius:0, stepped:true});
    }
    datasets.push({label:'SL', data:flat(r.sl_price), borderColor:'#ef4444', borderWidth:1, borderDash:[2,3], pointRadius:0});
    const mark = (ts, px, color, style) => ({
      label:'', data: labels.map((l,i)=> ser.t[i].slice(11,16)===ts.slice(11,16) ? px : null),
      pointBackgroundColor:color, pointBorderColor:color, pointRadius:6, pointStyle:style, showLine:false});
    datasets.push(mark(r.entry_ts, r.entry_price, '#34d399', 'triangle'));
    datasets.push(mark(r.exit_ts,  r.exit_price,  r.pnl_pct>=0?'#10b981':'#ef4444', 'rectRot'));
  }
  const ch = new Chart(wrap.querySelector('canvas'), {
    type:'line',
    data:{labels, datasets},
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{mode:'index', intersect:false},
      plugins:{legend:{labels:{color:'#94a3b8', boxWidth:14, font:{size:10}, filter:i=>i.text!==''}}},
      scales:{
        x:{ticks:{color:'#64748b', maxTicksLimit:16, font:{size:10}}, grid:{color:'#1f2735'}},
        y:{ticks:{color:'#64748b', font:{size:10}}, grid:{color:'#1f2735'}},
      },
    },
  });
  charts.push(ch);
}
</script>
</body>
</html>"""
