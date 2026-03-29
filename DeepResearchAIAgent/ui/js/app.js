/* ============================================================
   finDRA.AI — app.js
   ============================================================ */
'use strict';

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  sessionId:    null,
  plan:         null,
  eventSource:  null,
  reportContent:'',
  revenueChart: null,
  marginsChart: null,
  steps:        [],
  sources:      new Set(),
  thinkTimer:   null,
};

// ── Thinking messages ─────────────────────────────────────────────────────
const THINKING = [
  'Scanning financial databases…',
  'Reading analyst reports…',
  'Fetching market data…',
  'Cross-referencing sources…',
  'Computing financial ratios…',
  'Evaluating sector trends…',
  'Identifying key companies…',
  'Analysing earnings data…',
  'Building intelligence graph…',
  'Extracting key insights…',
];
let thinkIdx = 0;

// ── Helpers ───────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }
function show(id)      { const e=$(id); if(e) e.style.display=''; }
function hide(id)      { const e=$(id); if(e) e.style.display='none'; }
function showBlock(id) { const e=$(id); if(e) e.style.display='block'; }
function showFlex(id)  { const e=$(id); if(e) e.style.display='flex'; }

function setStatus(text, type='idle') {
  $('status-dot').className = 'status-dot ' + type;
  $('status-text').textContent = text;
}

function showToast(message, type='info') {
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = message;
  $('toast-container').appendChild(t);
  requestAnimationFrame(() => { requestAnimationFrame(() => t.classList.add('visible')); });
  setTimeout(() => {
    t.classList.remove('visible');
    setTimeout(() => t.remove(), 300);
  }, 3600);
}

function setBtn(id, disabled, html) {
  const b = $(id);
  if (!b) return;
  b.disabled = disabled;
  if (html !== undefined) b.innerHTML = html;
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── View helpers ──────────────────────────────────────────────────────────
function showHomeView() {
  showBlock('home-view');
  hide('work-view');
  hide('header-center');
  hide('new-query-btn');
  setStatus('Ready', 'idle');
}

function showWorkView(query, plan) {
  hide('home-view');
  showBlock('work-view');

  // Populate sidebar
  $('sq-text').textContent = query;
  if (plan) {
    const badges = $('sidebar-badges');
    badges.innerHTML = '';
    const sectorBadge = document.createElement('span');
    sectorBadge.className = 'sidebar-badge badge-sector';
    sectorBadge.textContent = plan.sector || 'Auto';
    const depthBadge = document.createElement('span');
    depthBadge.className = 'sidebar-badge badge-depth';
    depthBadge.textContent = plan.depth || 'standard';
    badges.appendChild(sectorBadge);
    badges.appendChild(depthBadge);
  }

  // Header query pill
  $('header-query').textContent = query.length > 60 ? query.slice(0, 57) + '…' : query;
  showFlex('header-center');
  showBlock('new-query-btn');

  // Sector pill
  if (plan && plan.sector) {
    $('sector-pill').textContent = plan.sector;
    showBlock('sector-pill');
  }
}

// ── Example chips ─────────────────────────────────────────────────────────
function setExample(btn) {
  $('query-input').value = btn.textContent.trim();
  $('query-input').focus();
}

// ── Generate Plan ─────────────────────────────────────────────────────────
async function generatePlan() {
  const query = $('query-input').value.trim();
  if (!query || query.length < 5) {
    showToast('Please enter a research query (min 5 characters).', 'error');
    return;
  }
  const sector = $('sector-select').value;
  const depth  = $('depth-select').value;

  setBtn('plan-btn', true, '&#9672; Analysing…');
  setStatus('Generating plan…', 'active');

  try {
    const res = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, sector, depth }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Plan generation failed.');
    }
    const plan = await res.json();
    state.plan = plan;
    state.sessionId = plan.session_id;

    showWorkView(query, plan);
    renderPlan(plan);
    showBlock('plan-panel');
    setStatus('Plan ready', 'idle');
    showToast('Research plan ready — review and approve.', 'success');
  } catch (e) {
    showToast(e.message, 'error');
    setStatus('Ready', 'idle');
  } finally {
    setBtn('plan-btn', false, '<span class="search-arrow">&#10148;</span> Research');
  }
}

// ── Render Plan ───────────────────────────────────────────────────────────
function renderPlan(plan) {
  $('plan-query').textContent = `"${plan.query}"`;

  const tags = $('plan-tags');
  tags.innerHTML = '';
  [
    { label: plan.sector, cls: 'tag-sector' },
    { label: plan.query_type.replace(/_/g,' '), cls: 'tag-type' },
    { label: plan.depth, cls: 'tag-depth' },
    { label: `~${plan.estimated_steps} steps`, cls: 'tag-steps' },
  ].forEach(({ label, cls }) => {
    const s = document.createElement('span');
    s.className = `plan-tag ${cls}`;
    s.textContent = label;
    tags.appendChild(s);
  });

  const body = $('plan-body');
  body.innerHTML = '';
  body.appendChild(makePlanSection('Research Aspects',   plan.aspects,          '◈'));
  body.appendChild(makePlanSection('Tools & Data',       plan.tools,            '◇'));
  body.appendChild(makePlanSection('Report Structure',   plan.output_structure, '◆'));
}

function makePlanSection(title, items, icon) {
  const div = document.createElement('div');
  div.className = 'plan-section';
  div.innerHTML = `<h4 class="plan-section-title">${icon} ${escapeHtml(title)}</h4>`;
  const ul = document.createElement('ul');
  ul.className = 'plan-items';
  (items || []).forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    ul.appendChild(li);
  });
  div.appendChild(ul);
  return div;
}

// ── Approve / Modify / Cancel ──────────────────────────────────────────────
async function approvePlan() {
  if (!state.sessionId) return;
  const modifiedScope = $('scope-input').value.trim() || null;

  setBtn('approve-btn', true, '&#10003; Starting…');
  setBtn('modify-btn',  true, undefined);
  setBtn('cancel-btn',  true, undefined);

  try {
    const res = await fetch('/api/research/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, approved: true, modified_scope: modifiedScope }),
    });
    if (!res.ok) throw new Error('Failed to start research.');

    hide('plan-panel');
    hide('scope-row');

    // Reset feed
    $('steps-list').innerHTML = '';
    $('step-badge').textContent = '0';

    // Show sidebar stat
    showBlock('sidebar-stat');

    // Show progress + feed
    const max = state.plan ? state.plan.estimated_steps : 10;
    updateProgress(0, max, 'Initialising…', 'Starting research…');
    showBlock('progress-wrap');
    showBlock('research-feed');

    startThinking();
    setStatus('Researching…', 'active');
    showToast('Research started — watch the live feed below.', 'success');

    listenToStream(state.sessionId);
  } catch (e) {
    showToast(e.message, 'error');
    setBtn('approve-btn', false, '&#10003;&ensp;Approve &amp; Start Research');
    setBtn('modify-btn',  false, undefined);
    setBtn('cancel-btn',  false, undefined);
  }
}

function toggleModify() {
  const row = $('scope-row');
  if (!row.style.display || row.style.display === 'none') {
    showBlock('scope-row');
    $('scope-input').focus();
  } else {
    hide('scope-row');
  }
}

function cancelPlan() {
  hide('plan-panel');
  hide('scope-row');
  $('scope-input').value = '';
  state.plan = null;
  state.sessionId = null;
  showHomeView();
}

// ── Thinking text rotation ────────────────────────────────────────────────
function startThinking() {
  stopThinking();
  thinkIdx = 0;
  $('thinking-text').textContent = THINKING[thinkIdx];
  state.thinkTimer = setInterval(() => {
    thinkIdx = (thinkIdx + 1) % THINKING.length;
    const el = $('thinking-text');
    if (el) el.textContent = THINKING[thinkIdx];
  }, 2800);
}

function stopThinking() {
  if (state.thinkTimer) { clearInterval(state.thinkTimer); state.thinkTimer = null; }
}

// ── SSE Stream ────────────────────────────────────────────────────────────
function listenToStream(sessionId) {
  if (state.eventSource) state.eventSource.close();
  const es = new EventSource(`/api/research/stream/${sessionId}`);
  state.eventSource = es;
  const max = state.plan ? state.plan.estimated_steps : 10;

  es.addEventListener('status', e => {
    const d = JSON.parse(e.data);
    updateProgress(0, max, d.message || 'Starting…', null);
  });

  es.addEventListener('step', e => {
    const d = JSON.parse(e.data);
    addStep(d);
    updateProgress(d.step || state.steps.length, max, null, d.focus || '');
  });

  es.addEventListener('financial_data', e => {
    renderFinancials(JSON.parse(e.data));
  });

  es.addEventListener('report_done', e => {
    const d = JSON.parse(e.data);
    stopThinking();
    hide('progress-wrap');
    markFeedDone();
    renderReport(d.report, d.step_count);
    setStatus('Complete', 'done');
    showToast('Research complete!', 'success');
    es.close();
    state.eventSource = null;
  });

  es.addEventListener('error', e => {
    let msg = null;
    try { const d = JSON.parse(e.data); if (d.message) msg = d.message; } catch {}
    if (msg) {
      stopThinking();
      showToast(`Error: ${msg}`, 'error');
      hide('progress-wrap');
      setStatus('Error', 'error');
      es.close();
      state.eventSource = null;
    }
  });
}

// ── Progress ──────────────────────────────────────────────────────────────
function updateProgress(current, max, thinkingOverride, labelText) {
  const pct = max > 0 ? Math.min((current / max) * 100, 100) : 0;
  $('progress-fill').style.width = `${pct}%`;
  $('progress-steps').textContent = `${current} / ${max}`;
  if (thinkingOverride !== null && thinkingOverride !== undefined) {
    $('thinking-text').textContent = thinkingOverride;
  }
  if (labelText !== null && labelText !== undefined) {
    $('progress-label').textContent = labelText;
  }
}

// ── Steps Feed ────────────────────────────────────────────────────────────
const TOOL_META = {
  analysis:  { cls: 'analysis', icon: '◈' },
  rag:       { cls: 'rag',      icon: '⊡' },
  financial: { cls: 'financial',icon: '$' },
  web:       { cls: 'web',      icon: '↗' },
  default:   { cls: 'web',      icon: '↗' },
};

function getToolMeta(tool) {
  const t = (tool || '').toLowerCase();
  if (t.includes('analys')) return TOOL_META.analysis;
  if (t.includes('rag'))    return TOOL_META.rag;
  if (t.includes('fin'))    return TOOL_META.financial;
  return TOOL_META.web;
}

function addStep(data) {
  state.steps.push(data);
  const n = state.steps.length;
  const meta = getToolMeta(data.tool);
  const text = (data.summary || data.focus || '').slice(0, 220);

  const li = document.createElement('li');
  li.className = 'step-item';
  li.id = `step-${n}`;
  li.innerHTML = `
    <div class="step-left">
      <div class="step-icon ${meta.cls}">${meta.icon}</div>
      <div class="step-connector"></div>
    </div>
    <div class="step-right">
      <div class="step-meta">
        <span class="step-num">#${n}</span>
        <span class="step-tool-label">${escapeHtml(data.tool || 'Search')}</span>
      </div>
      <p class="step-summary">${escapeHtml(text)}</p>
    </div>
  `;

  const list = $('steps-list');
  list.appendChild(li);

  // Auto-scroll main content
  const main = document.querySelector('.main-content');
  if (main) main.scrollTop = main.scrollHeight;

  // Update sidebar counter
  $('step-badge').textContent = n;

  if (data.sources && Array.isArray(data.sources)) {
    data.sources.forEach(s => addSource(s));
  }
}

function markFeedDone() {
  const header = document.querySelector('.feed-title');
  if (header) {
    header.innerHTML = '&#10003;&ensp;Research Completed';
    header.style.color = 'var(--green)';
  }
  // Remove last connector
  const connectors = document.querySelectorAll('.step-connector');
  if (connectors.length) connectors[connectors.length - 1].style.display = 'none';
}

function addSource(url) {
  if (!url || state.sources.has(url)) return;
  state.sources.add(url);
  showBlock('sources-card');
  let hostname = url;
  try { hostname = new URL(url).hostname.replace('www.', ''); } catch {}
  const li = document.createElement('li');
  li.className = 'source-item';
  li.innerHTML = `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(hostname)}</a>`;
  $('sources-list').appendChild(li);
}

// ── Financials ────────────────────────────────────────────────────────────
function renderFinancials(data) {
  const { metrics, chart } = data;
  if (!metrics || !Object.keys(metrics).length) return;

  showBlock('financials-section');
  const tickers = Object.keys(metrics);
  $('fin-sub').textContent = tickers.join('  ·  ');

  const grid = $('metrics-grid');
  grid.innerHTML = '';
  tickers.forEach(ticker => {
    const m = metrics[ticker];
    const rev   = m.revenue      != null ? `$${(m.revenue / 1e9).toFixed(2)}B` : '—';
    const netM  = m.net_margin   != null ? `${(m.net_margin   * 100).toFixed(1)}%` : '—';
    const ebitM = m.ebitda_margin!= null ? `${(m.ebitda_margin* 100).toFixed(1)}%` : '—';
    const pe    = m.pe_ratio     != null ? `${m.pe_ratio.toFixed(1)}x` : '—';

    const card = document.createElement('div');
    card.className = 'metric-card';
    card.innerHTML = `
      <div class="metric-ticker">${escapeHtml(ticker)}</div>
      <div class="metric-name">${escapeHtml(m.name || ticker)}</div>
      <div class="metric-row"><span class="metric-label">Revenue</span><span class="metric-value">${rev}</span></div>
      <div class="metric-row"><span class="metric-label">Net Margin</span><span class="metric-value">${netM}</span></div>
      <div class="metric-row"><span class="metric-label">EBITDA Margin</span><span class="metric-value">${ebitM}</span></div>
      <div class="metric-row"><span class="metric-label">P/E Ratio</span><span class="metric-value">${pe}</span></div>
    `;
    grid.appendChild(card);
  });

  if (chart) renderCharts(chart);
}

function renderCharts(chart) {
  const { labels, revenue_bn, ebitda_margins, net_margins } = chart;
  if (!labels || !labels.length) return;

  const CYAN   = 'rgba(0,212,255,0.85)';
  const PURPLE = 'rgba(167,139,250,0.85)';
  const GREEN  = 'rgba(52,211,153,0.85)';

  const opts = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { labels: { color: '#8888aa', font: { family: 'Poppins', size: 11 } } } },
    scales: {
      x: { ticks: { color: '#46466a', font: { family: 'Poppins', size: 11 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
      y: { ticks: { color: '#46466a', font: { family: 'Poppins', size: 11 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
    },
  };

  if (state.revenueChart) state.revenueChart.destroy();
  state.revenueChart = new Chart($('revenue-chart').getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Revenue (USD Billion)', data: revenue_bn, backgroundColor: CYAN, borderColor: CYAN, borderWidth: 1, borderRadius: 6 }] },
    options: { ...opts },
  });

  if (state.marginsChart) state.marginsChart.destroy();
  state.marginsChart = new Chart($('margins-chart').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'EBITDA Margin %', data: ebitda_margins, backgroundColor: PURPLE, borderColor: PURPLE, borderWidth: 1, borderRadius: 6 },
        { label: 'Net Margin %',    data: net_margins,    backgroundColor: GREEN,  borderColor: GREEN,  borderWidth: 1, borderRadius: 6 },
      ],
    },
    options: { ...opts },
  });
}

// ── Report ────────────────────────────────────────────────────────────────
function renderReport(markdown, stepCount) {
  state.reportContent = markdown || '';
  showBlock('report-section');
  $('report-title').textContent = stepCount
    ? `Research Report  ·  ${stepCount} steps`
    : 'Research Report';

  if (typeof marked !== 'undefined') {
    marked.setOptions({ gfm: true, breaks: true });
    $('report-body').innerHTML = marked.parse(state.reportContent);
  } else {
    $('report-body').innerHTML = `<pre>${escapeHtml(state.reportContent)}</pre>`;
  }
  $('report-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function copyReport() {
  if (!state.reportContent) { showToast('No report yet.', 'error'); return; }
  navigator.clipboard.writeText(state.reportContent)
    .then(() => showToast('Copied to clipboard.', 'success'))
    .catch(() => showToast('Copy failed — select and copy manually.', 'error'));
}

function downloadReport() {
  if (!state.reportContent) { showToast('No report yet.', 'error'); return; }
  const blob = new Blob([state.reportContent], { type: 'text/markdown' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = `finDRA_${state.sessionId || 'report'}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Report downloaded.', 'success');
}

// ── New Query ─────────────────────────────────────────────────────────────
function newQuery() {
  stopThinking();
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }

  // Reset state
  Object.assign(state, {
    sessionId: null, plan: null, reportContent: '',
    steps: [], sources: new Set(),
  });
  if (state.revenueChart) { state.revenueChart.destroy(); state.revenueChart = null; }
  if (state.marginsChart) { state.marginsChart.destroy(); state.marginsChart = null; }

  // Clear DOM
  ['plan-panel','progress-wrap','research-feed','financials-section',
   'report-section','scope-row','sources-card','sidebar-stat'].forEach(hide);
  $('scope-input').value = '';
  $('steps-list').innerHTML = '';
  $('sources-list').innerHTML = '';
  $('metrics-grid').innerHTML = '';
  $('report-body').innerHTML = '';
  $('plan-body').innerHTML = '';
  $('plan-tags').innerHTML = '';
  $('sidebar-badges').innerHTML = '';
  $('step-badge').textContent = '0';
  $('sector-pill').style.display = 'none';
  $('query-input').value = '';

  showHomeView();
  setTimeout(() => $('query-input').focus(), 50);
}

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  $('query-input').addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      generatePlan();
    }
  });

  // Auto-resize textarea
  $('query-input').addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 220) + 'px';
  });
});
