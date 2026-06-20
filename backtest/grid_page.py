GRID_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RSI Grid</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0d0f14;color:#e2e8f0;min-height:100vh}

/* NAV */
.nav{display:flex;align-items:center;gap:14px;padding:9px 20px;background:#161b26;border-bottom:1px solid #2d3748;flex-wrap:wrap}
.nav-brand{font-size:.93rem;font-weight:700;color:#fff;margin-right:4px}
.nav a{font-size:.8rem;color:#94a3b8;padding:4px 9px;border-radius:6px;text-decoration:none}
.nav a:hover,.nav a.active{background:#2d3748;color:#e2e8f0}

/* LAYOUT */
.wrap{max-width:1380px;margin:0 auto;padding:18px 20px}
.panel{background:#161b26;border:1px solid #2d3748;border-radius:12px;padding:16px 18px;margin-bottom:14px}
.sec-title{font-size:.72rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}

/* CONTROLS */
.chip-row{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px}
.f{display:flex;flex-direction:column;gap:3px}
.f label{font-size:.67rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em}
.f input{background:#0d1117;border:1px solid #374151;border-radius:6px;color:#e2e8f0;padding:5px 8px;font-size:.84rem;width:130px}
.f input:focus{outline:none;border-color:#60a5fa}
.f input.w80{width:80px}.f input.w100{width:100px}

/* CHIP INPUT */
.chips-wrap{display:flex;flex-wrap:wrap;gap:5px;align-items:center;background:#0d1117;border:1px solid #374151;border-radius:6px;padding:4px 8px;min-height:34px;min-width:180px;cursor:text}
.chip{display:flex;align-items:center;gap:3px;background:#1e3a5f;border-radius:16px;padding:2px 9px;font-size:.76rem;color:#93c5fd}
.chip-rm{background:none;border:none;color:#93c5fd;cursor:pointer;font-size:.88rem;padding:0}
.chip-rm:hover{color:#f87171}
.chip-inp{background:none;border:none;color:#e2e8f0;font-size:.83rem;outline:none;min-width:60px}

/* PARAM GRID */
.param-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}

/* LOGIC PILL TABLE */
.logic-table{width:100%;border-collapse:collapse;font-size:.78rem;margin-bottom:4px}
.logic-table th{background:#1a2035;color:#94a3b8;padding:5px 10px;text-align:center;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.logic-table td{padding:5px 10px;border-bottom:1px solid #1e2535;text-align:center}
.logic-table tr:last-child td{border-bottom:none}
.rsi-low{color:#60a5fa}.rsi-mid{color:#34d399}.rsi-hi{color:#f97316}
.buy-col{color:#22c55e}.sell-col{color:#f87171}

/* RUN */
.run-row{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-top:12px}
.btn{border:none;border-radius:7px;cursor:pointer;font-size:.86rem;font-weight:600;padding:9px 22px;transition:opacity .18s}
.btn:hover{opacity:.82}.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-run{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff}

/* PROGRESS */
.prog-wrap{display:none;margin-top:10px}
.prog-bar{height:4px;background:#1e2535;border-radius:2px;overflow:hidden}
.prog-fill{height:100%;width:0%;background:linear-gradient(90deg,#3b82f6,#6366f1);transition:width .3s}
.prog-lbl{font-size:.7rem;color:#94a3b8;margin-top:3px;text-align:center}

/* CARDS */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:9px;margin-bottom:14px}
.card{background:#161b26;border:1px solid #2d3748;border-radius:9px;padding:12px 14px;text-align:center}
.card-lbl{font-size:.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.card-val{font-size:1.25rem;font-weight:700}
.green{color:#34d399}.red{color:#f87171}.white{color:#e2e8f0}.blue{color:#60a5fa}.yellow{color:#fbbf24}

/* TICKER CARDS */
.ticker-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:14px}
.ticker-card{border-radius:10px;padding:13px 15px;border:1px solid #2d3748}
.tc-title{font-size:.9rem;font-weight:700;margin-bottom:8px}
.tc-stat{display:flex;justify-content:space-between;font-size:.75rem;color:#94a3b8;margin-bottom:3px}
.tc-stat span:last-child{color:#e2e8f0;font-weight:600}
.tc-err{font-size:.75rem;color:#f87171;margin-top:4px}

/* CHART */
.chart-box{background:#161b26;border:1px solid #2d3748;border-radius:10px;padding:13px;margin-bottom:14px}
.chart-box canvas{max-height:280px}

/* TABLE */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.77rem}
th{background:#1a2035;color:#94a3b8;text-transform:uppercase;font-size:.63rem;letter-spacing:.05em;padding:7px 9px;text-align:right;cursor:pointer;white-space:nowrap;user-select:none}
th:first-child{text-align:left}
th:hover{color:#e2e8f0}
td{padding:6px 9px;border-bottom:1px solid #1e2535;text-align:right;white-space:nowrap}
td:first-child{text-align:left}
tr:hover td{background:#1a2035}
.pp{color:#34d399;font-weight:600}.np{color:#f87171;font-weight:600}.zp{color:#94a3b8}
.b-buy{background:#0f2a10;color:#22c55e;border:1px solid #166534;border-radius:8px;padding:1px 7px;font-size:.67rem;font-weight:700}
.b-sell{background:#2a1010;color:#f87171;border:1px solid #7f1d1d;border-radius:8px;padding:1px 7px;font-size:.67rem;font-weight:700}
.sym-badge{background:#1e3a5f;color:#93c5fd;border-radius:8px;padding:1px 7px;font-size:.68rem;font-weight:600}

/* TABS */
.tabs{display:flex;gap:0;margin-bottom:0;border-bottom:1px solid #2d3748}
.tab-btn{background:transparent;border:none;color:#94a3b8;cursor:pointer;font-size:.8rem;padding:7px 16px;border-bottom:2px solid transparent;transition:all .15s}
.tab-btn.active{color:#e2e8f0;border-bottom-color:#60a5fa}
.tab-btn:hover:not(.active){color:#e2e8f0}
.tab-panel{display:none;padding-top:12px}.tab-panel.active{display:block}

.err-box{background:#2a1515;border:1px solid #7f1d1d;border-radius:8px;padding:11px;color:#fca5a5;font-size:.82rem;margin-bottom:12px}
.hidden{display:none}
</style>
</head>
<body>

<div class="nav">
  <span class="nav-brand">100x RSI Backtester</span>
  <a href="/">Single Day</a>
  <a href="/batch">Batch</a>
  <a href="/multiday">Multi-Day</a>
  <a href="/momentum">Momentum</a>
  <a href="/spike">Spike</a>
  <a href="/grid" class="active">RSI Grid</a>
  <a href="/alerts">Alerts</a>
</div>

<div class="wrap">

<!-- ── CONTROLS ─────────────────────────────────────────────────────────────── -->
<div class="panel">
  <div class="sec-title">RSI Grid — Tiered Limit Orders</div>

  <!-- Tickers + date -->
  <div class="chip-row">
    <div class="f">
      <label>Tickers</label>
      <div class="chips-wrap" id="chipWrap" onclick="document.getElementById('chipInp').focus()">
        <input class="chip-inp" id="chipInp" placeholder="Symbol + Enter…">
      </div>
    </div>
    <div class="f"><label>Start Date</label><input type="date" id="startDate"></div>
  </div>

  <!-- Params row -->
  <div class="param-grid" style="margin-bottom:14px">
    <div class="f"><label>Base Qty (shares)</label><input type="number" id="baseQty" value="1" min="1" max="1000" class="w80"></div>
    <div class="f"><label>Buy Drop % (below close)</label><input type="number" id="buyDropPct" value="0.5" min="0.01" max="20" step="0.05" class="w80"></div>
    <div class="f"><label>Sell Rise % (above close)</label><input type="number" id="sellRisePct" value="0.5" min="0.01" max="20" step="0.05" class="w80"></div>
    <div class="f"><label>RSI Period</label><input type="number" id="rsiPeriod" value="14" min="2" max="50" class="w80"></div>
    <div class="f"><label>RSI Low threshold</label><input type="number" id="rsiLow" value="30" min="5" max="49" class="w80"></div>
    <div class="f"><label>RSI High threshold</label><input type="number" id="rsiHigh" value="60" min="51" max="95" class="w80"></div>
    <div class="f">
      <label>Order Expiry (days)</label>
      <input type="number" id="maxOrderDays" value="7" min="1" max="30" class="w80">
      <span style="font-size:.63rem;color:#60a5fa;margin-top:2px">cancel &amp; replace if unfilled</span>
    </div>
  </div>

  <!-- Logic summary table -->
  <table class="logic-table">
    <thead><tr><th>RSI Zone</th><th>Buy Qty</th><th>Buy Price</th><th>Sell Qty</th><th>Sell Price</th></tr></thead>
    <tbody>
      <tr>
        <td id="lbl_low" class="rsi-low">RSI &lt; 30</td>
        <td id="buy_low" class="buy-col">2×</td>
        <td class="buy-col">close × (1 − <span id="bdp_low">0.5</span>%)</td>
        <td id="sell_low" class="sell-col">1×</td>
        <td class="sell-col">close × (1 + <span id="srp_low">0.5</span>%)</td>
      </tr>
      <tr>
        <td id="lbl_mid" class="rsi-mid">30 ≤ RSI ≤ 60</td>
        <td id="buy_mid" class="buy-col">1×</td>
        <td class="buy-col">close × (1 − <span id="bdp_mid">0.5</span>%)</td>
        <td id="sell_mid" class="sell-col">1×</td>
        <td class="sell-col">close × (1 + <span id="srp_mid">0.5</span>%)</td>
      </tr>
      <tr>
        <td id="lbl_high" class="rsi-hi">RSI &gt; 60</td>
        <td id="buy_high" class="buy-col">1×</td>
        <td class="buy-col">close × (1 − <span id="bdp_high">0.5</span>%)</td>
        <td id="sell_high" class="sell-col">2×</td>
        <td class="sell-col">close × (1 + <span id="srp_high">0.5</span>%)</td>
      </tr>
    </tbody>
  </table>
  <div style="font-size:.68rem;color:#4b5563;margin-top:5px">
    GTC orders — persist until filled or expired · one active buy + one active sell at all times ·
    buy fills when bar.low ≤ limit · sell fills when bar.high ≥ limit AND position ≥ qty ·
    after fill or expiry: new order placed immediately at current price ± % · runs on all hours incl. extended
  </div>

  <div class="run-row">
    <button class="btn btn-run" id="runBtn" onclick="runGrid()">▶ Run</button>
    <span id="statusMsg" style="font-size:.77rem;color:#94a3b8;align-self:flex-end"></span>
  </div>

  <div class="prog-wrap" id="progWrap">
    <div class="prog-bar"><div class="prog-fill" id="progFill"></div></div>
    <div class="prog-lbl" id="progLbl">Fetching data…</div>
  </div>
</div>

<div class="err-box hidden" id="errBox"></div>

<!-- ── RESULTS ────────────────────────────────────────────────────────────── -->
<div id="results" class="hidden">

  <!-- Combined summary -->
  <div class="cards" id="summaryCards"></div>

  <!-- Per-ticker cards -->
  <div class="ticker-grid" id="tickerCards"></div>

  <!-- Cumulative PnL chart -->
  <div class="chart-box">
    <div class="sec-title" style="margin-bottom:8px">Cumulative Cash Flow by Day</div>
    <canvas id="cumulChart"></canvas>
  </div>

  <!-- Tabs: Daily | Trades -->
  <div class="panel" style="padding-bottom:0">
    <div class="tabs">
      <button class="tab-btn active" onclick="showTab('tabDaily')">📅 Daily Summary</button>
      <button class="tab-btn"        onclick="showTab('tabTrades')">📋 Recent Trades (last 1000)</button>
    </div>
    <div id="tabDaily" class="tab-panel active">
      <div class="tbl-wrap">
        <table id="dailyTbl">
          <thead>
            <tr>
              <th onclick="srt('dailyTbl',0)">Date</th>
              <th onclick="srt('dailyTbl',1)">Symbol</th>
              <th onclick="srt('dailyTbl',2)" title="1-min bars with valid RSI">Bars</th>
              <th onclick="srt('dailyTbl',3)">Buys Filled</th>
              <th onclick="srt('dailyTbl',4)">Sells Filled</th>
              <th onclick="srt('dailyTbl',5)">Cancels</th>
              <th onclick="srt('dailyTbl',6)">Spent</th>
              <th onclick="srt('dailyTbl',7)">Received</th>
              <th onclick="srt('dailyTbl',8)">Day Cash</th>
              <th onclick="srt('dailyTbl',9)">Cumulative</th>
            </tr>
          </thead>
          <tbody id="dailyBody"></tbody>
        </table>
      </div>
    </div>
    <div id="tabTrades" class="tab-panel">
      <div class="tbl-wrap">
        <table id="tradesTbl">
          <thead>
            <tr>
              <th onclick="srt('tradesTbl',0)">Date</th>
              <th onclick="srt('tradesTbl',1)">Time</th>
              <th onclick="srt('tradesTbl',2)">Symbol</th>
              <th onclick="srt('tradesTbl',3)">Type</th>
              <th onclick="srt('tradesTbl',4)">Qty</th>
              <th onclick="srt('tradesTbl',5)">Price</th>
              <th onclick="srt('tradesTbl',6)">Value</th>
              <th onclick="srt('tradesTbl',7)">RSI</th>
              <th onclick="srt('tradesTbl',8)">Position</th>
            </tr>
          </thead>
          <tbody id="tradesBody"></tbody>
        </table>
      </div>
    </div>
  </div>

</div><!-- /results -->

</div><!-- /wrap -->

<script>
// ── Chips ─────────────────────────────────────────────────────────────────────
let chips = [];
function addChip(s) {
  s = s.trim().toUpperCase().replace(/[^A-Z0-9]/g,'');
  if (!s || chips.includes(s)) return;
  chips.push(s); renderChips();
}
function removeChip(s) { chips = chips.filter(c=>c!==s); renderChips(); }
function renderChips() {
  const wrap = document.getElementById('chipWrap');
  const inp  = document.getElementById('chipInp');
  wrap.querySelectorAll('.chip').forEach(c=>c.remove());
  chips.forEach(s=>{
    const c = document.createElement('div'); c.className='chip';
    c.innerHTML=s+'<button class="chip-rm" onclick="removeChip(\''+s+'\')">&times;</button>';
    wrap.insertBefore(c,inp);
  });
}
document.getElementById('chipInp').addEventListener('keydown', e=>{
  if (e.key==='Enter'||e.key===',') { e.preventDefault(); addChip(e.target.value); e.target.value=''; }
  if (e.key==='Backspace'&&!e.target.value&&chips.length) removeChip(chips[chips.length-1]);
});
['SOXL','SOXS'].forEach(addChip);

// ── Default start date (30 days ago) ─────────────────────────────────────────
(function(){
  const d = new Date(); d.setDate(d.getDate()-30);
  while (d.getDay()===0||d.getDay()===6) d.setDate(d.getDate()-1);
  document.getElementById('startDate').value = d.toISOString().slice(0,10);
})();

// ── Live logic table update ───────────────────────────────────────────────────
function updateLogicTable() {
  const bdp  = document.getElementById('buyDropPct').value  || '?';
  const srp  = document.getElementById('sellRisePct').value || '?';
  const rl   = document.getElementById('rsiLow').value  || '30';
  const rh   = document.getElementById('rsiHigh').value || '60';
  const qty  = document.getElementById('baseQty').value || '1';

  document.getElementById('lbl_low').textContent  = `RSI < ${rl}`;
  document.getElementById('lbl_mid').textContent  = `${rl} ≤ RSI ≤ ${rh}`;
  document.getElementById('lbl_high').textContent = `RSI > ${rh}`;
  document.getElementById('buy_low').textContent  = `${2*qty}×`;
  document.getElementById('buy_mid').textContent  = `${qty}×`;
  document.getElementById('buy_high').textContent = `${qty}×`;
  document.getElementById('sell_low').textContent = `${qty}×`;
  document.getElementById('sell_mid').textContent = `${qty}×`;
  document.getElementById('sell_high').textContent= `${2*qty}×`;
  ['bdp_low','bdp_mid','bdp_high'].forEach(id=>document.getElementById(id).textContent=bdp);
  ['srp_low','srp_mid','srp_high'].forEach(id=>document.getElementById(id).textContent=srp);
}
['baseQty','buyDropPct','sellRisePct','rsiLow','rsiHigh'].forEach(id=>
  document.getElementById(id).addEventListener('input', updateLogicTable));

// ── Progress ──────────────────────────────────────────────────────────────────
let _pt = null;
function startProg(ms) {
  document.getElementById('progWrap').style.display='block';
  const fill=document.getElementById('progFill'), lbl=document.getElementById('progLbl');
  fill.style.width='0%'; let p=0;
  _pt=setInterval(()=>{ p=Math.min(p+(100/(ms/300))*(0.5+Math.random()),92);
    fill.style.width=p+'%'; lbl.textContent='Running… '+Math.round(p)+'%'; },300);
}
function stopProg() {
  clearInterval(_pt);
  document.getElementById('progFill').style.width='100%';
  document.getElementById('progLbl').textContent='Done!';
  setTimeout(()=>document.getElementById('progWrap').style.display='none',600);
}

// ── RUN ───────────────────────────────────────────────────────────────────────
let cumulInst = null;

async function runGrid() {
  if (!chips.length) { alert('Add at least one ticker.'); return; }
  const sd = document.getElementById('startDate').value;
  if (!sd) { alert('Select a start date.'); return; }

  const btn = document.getElementById('runBtn'); btn.disabled=true;
  document.getElementById('errBox').classList.add('hidden');
  document.getElementById('results').classList.add('hidden');
  document.getElementById('statusMsg').textContent='';

  const calDays = Math.round((new Date()-new Date(sd))/86400000);
  startProg(chips.length * calDays * 120 + 4000);

  const p = new URLSearchParams({
    symbols:         chips.join(','),
    start_date:      sd,
    base_qty:        document.getElementById('baseQty').value,
    buy_drop_pct:    document.getElementById('buyDropPct').value,
    sell_rise_pct:   document.getElementById('sellRisePct').value,
    rsi_period:      document.getElementById('rsiPeriod').value,
    rsi_low:         document.getElementById('rsiLow').value,
    rsi_high:        document.getElementById('rsiHigh').value,
    max_order_days:  document.getElementById('maxOrderDays').value,
  });

  try {
    const res  = await fetch('/api/grid?'+p);
    const data = await res.json();
    stopProg();
    if (!res.ok) { showErr(data.detail||JSON.stringify(data)); return; }
    renderResults(data);
    document.getElementById('statusMsg').textContent =
      data.end_date + ' · ' + data.symbols.length + ' symbol(s)';
  } catch(e) { stopProg(); showErr('Failed: '+e.message); }
  finally { btn.disabled=false; }
}

function showErr(m) { const b=document.getElementById('errBox'); b.textContent=m; b.classList.remove('hidden'); }
function fmtD(v) { return v==null?'—':(v>=0?'+':'')+v.toFixed(2); }
function pc(v)   { return v>0?'pp':v<0?'np':'zp'; }

// ── RENDER ────────────────────────────────────────────────────────────────────
const PALETTE = ['#60a5fa','#34d399','#f472b6','#fbbf24','#a78bfa','#fb923c'];

function renderResults(data) {
  document.getElementById('results').classList.remove('hidden');

  const results = data.results || [];
  const total   = data.total_pnl;

  // ── Summary cards ──
  const totalBuys  = results.reduce((s,r)=>s+(r.stats?.total_buys||0),0);
  const totalSells = results.reduce((s,r)=>s+(r.stats?.total_sells||0),0);
  const totalPos   = results.reduce((s,r)=>s+(r.stats?.position||0),0);
  const totalPosVal= results.reduce((s,r)=>s+(r.stats?.position_value||0),0);
  const days       = Math.max(...results.map(r=>r.stats?.trading_days||0));

  const totalCancels = results.reduce((s,r)=>s+(r.stats?.total_cancels||0),0);
  document.getElementById('summaryCards').innerHTML = `
    <div class="card"><div class="card-lbl">Net P&L</div><div class="card-val ${pc(total)}">${fmtD(total)}</div></div>
    <div class="card"><div class="card-lbl">Trading Days</div><div class="card-val white">${days}</div></div>
    <div class="card"><div class="card-lbl">Buy Fills</div><div class="card-val green">${totalBuys.toLocaleString()}</div></div>
    <div class="card"><div class="card-lbl">Sell Fills</div><div class="card-val red">${totalSells.toLocaleString()}</div></div>
    <div class="card"><div class="card-lbl">Cancels (expired)</div><div class="card-val yellow">${totalCancels.toLocaleString()}</div></div>
    <div class="card"><div class="card-lbl">Open Shares</div><div class="card-val yellow">${totalPos}</div></div>
    <div class="card"><div class="card-lbl">Position Value</div><div class="card-val blue">$${totalPosVal.toFixed(2)}</div></div>
  `;

  // ── Per-ticker cards ──
  const colors = PALETTE;
  document.getElementById('tickerCards').innerHTML = results.map((r,i)=>{
    const s = r.stats || {};
    const clr = colors[i%colors.length];
    if (r.error) {
      return `<div class="ticker-card" style="border-top:3px solid #f87171">
        <div class="tc-title" style="color:#f87171">${r.symbol}</div>
        <div class="tc-err">${r.error}</div>
      </div>`;
    }
    return `<div class="ticker-card" style="border-top:3px solid ${clr}">
      <div class="tc-title" style="color:${clr}">${r.symbol}</div>
      <div class="tc-stat"><span>Net P&L</span><span class="${pc(s.net_pnl)}">${fmtD(s.net_pnl)}</span></div>
      <div class="tc-stat"><span>Realized P&L</span><span class="${pc(s.realized_pnl)}">${fmtD(s.realized_pnl)}</span></div>
      <div class="tc-stat"><span>Open Position</span><span>${s.position} shares @ $${s.last_price}</span></div>
      <div class="tc-stat"><span>Position Value</span><span class="blue">$${s.position_value}</span></div>
      <div class="tc-stat"><span>Buys / Sells</span><span>${s.total_buys?.toLocaleString()} / ${s.total_sells?.toLocaleString()}</span></div>
      <div class="tc-stat"><span>Cancels (expired)</span><span style="color:#fbbf24">${s.total_cancels||0}</span></div>
      <div class="tc-stat"><span>Spent / Received</span><span>$${s.total_spent?.toFixed(0)} / $${s.total_received?.toFixed(0)}</span></div>
      <div class="tc-stat"><span>Active Buy Order</span><span style="color:#22c55e;font-size:.72rem">${s.active_buy_order?'$'+s.active_buy_order.price+' × '+s.active_buy_order.qty:'—'}</span></div>
      <div class="tc-stat"><span>Active Sell Order</span><span style="color:#f87171;font-size:.72rem">${s.active_sell_order?'$'+s.active_sell_order.price+' × '+s.active_sell_order.qty:'—'}</span></div>
    </div>`;
  }).join('');

  // ── Cumulative chart ──
  // Collect all dates across all symbols
  const allDates = [...new Set(
    results.flatMap(r=>(r.daily||[]).map(d=>d.date))
  )].sort();

  if (cumulInst) cumulInst.destroy();
  const datasets = results.map((r,i)=>{
    const byDate = {};
    (r.daily||[]).forEach(d=>{ byDate[d.date]=d.cum_cash; });
    let last = 0;
    const vals = allDates.map(d=>{
      if (byDate[d]!==undefined) last=byDate[d];
      return last;
    });
    return {
      label: r.symbol,
      data: vals,
      borderColor: colors[i%colors.length],
      backgroundColor: colors[i%colors.length]+'18',
      tension: 0.3, pointRadius: 2, fill: false,
    };
  });

  cumulInst = new Chart(document.getElementById('cumulChart'),{
    type:'line',
    data:{ labels:allDates, datasets },
    options:{
      responsive:true, maintainAspectRatio:true,
      scales:{
        x:{ ticks:{ color:'#94a3b8', maxRotation:45, maxTicksLimit:20 }, grid:{color:'#1e2535'} },
        y:{ ticks:{ color:'#94a3b8', callback:v=>'$'+v.toFixed(0) }, grid:{color:'#1e2535'} }
      },
      plugins:{
        legend:{ labels:{ color:'#94a3b8', boxWidth:12 }},
        annotation:{ annotations:{ z:{ type:'line', yMin:0, yMax:0, borderColor:'#374151', borderWidth:1, borderDash:[4,4] }}}
      }
    }
  });

  // ── Daily table ──
  const db = document.getElementById('dailyBody');
  db.innerHTML = '';
  results.forEach(r=>{
    (r.daily||[]).forEach(d=>{
      const tr = document.createElement('tr');
      const barsCell = d.bars===0
        ? `<td style="color:#f87171" title="No IEX data — check feed coverage">0 ⚠</td>`
        : `<td style="color:#64748b">${d.bars}</td>`;
      tr.innerHTML = `
        <td>${d.date}</td>
        <td><span class="sym-badge">${r.symbol}</span></td>
        ${barsCell}
        <td class="green">${d.buys}</td>
        <td class="red">${d.sells}</td>
        <td style="color:#fbbf24">${d.cancels||0}</td>
        <td class="red">$${(d.spent||0).toFixed(2)}</td>
        <td class="green">$${(d.received||0).toFixed(2)}</td>
        <td class="${pc(d.net_cash)}">${fmtD(d.net_cash)}</td>
        <td class="${pc(d.cum_cash)}">${fmtD(d.cum_cash)}</td>
      `;
      db.appendChild(tr);
    });
  });

  // ── Trades table ──
  const tb = document.getElementById('tradesBody');
  tb.innerHTML = '';
  // Merge and sort all trades across symbols
  const allTrades = results.flatMap(r=>(r.trades||[]).map(t=>({...t,symbol:r.symbol})));
  allTrades.sort((a,b)=>a.ts.localeCompare(b.ts));
  // Show last 1000
  allTrades.slice(-1000).forEach(t=>{
    const tr = document.createElement('tr');
    const typeBadge = t.type==='buy'
      ? '<span class="b-buy">BUY</span>'
      : '<span class="b-sell">SELL</span>';
    tr.innerHTML = `
      <td>${t.date}</td>
      <td style="color:#94a3b8;font-size:.71rem">${t.ts.slice(11,16)}</td>
      <td><span class="sym-badge">${t.symbol}</span></td>
      <td>${typeBadge}</td>
      <td>${t.qty}</td>
      <td>$${t.price}</td>
      <td class="${t.type==='sell'?'pp':'np'}">$${t.value.toFixed(2)}</td>
      <td style="color:#94a3b8">${t.rsi}</td>
      <td>${t.position}</td>
    `;
    tb.appendChild(tr);
  });
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function showTab(id) {
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  const idx=['tabDaily','tabTrades'].indexOf(id);
  document.querySelectorAll('.tab-btn')[idx]?.classList.add('active');
}

// ── Sort ──────────────────────────────────────────────────────────────────────
const _ss={};
function srt(tid,col){
  const tbl=document.getElementById(tid), tb=tbl.querySelector('tbody');
  const rows=[...tb.querySelectorAll('tr')];
  const asc=!_ss[tid+col]; _ss[tid+col]=asc;
  rows.sort((a,b)=>{
    const va=(a.cells[col]?.textContent||'').trim().replace(/[$+,]/g,'');
    const vb=(b.cells[col]?.textContent||'').trim().replace(/[$+,]/g,'');
    const na=parseFloat(va),nb=parseFloat(vb);
    if (!isNaN(na)&&!isNaN(nb)) return asc?na-nb:nb-na;
    return asc?va.localeCompare(vb):vb.localeCompare(va);
  });
  rows.forEach(r=>tb.appendChild(r));
}
</script>
</body>
</html>"""
