/* ============================================================
   FinResearchAI — app.js
   All UI logic: plan generation, SSE streaming, charts, report
   ============================================================ */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────────

const state = {
  sessionId: null,
  plan: null,
  eventSource: null,
  reportContent: '',
  revenueChart: null,
  marginsChart: null,
  steps: [],
  sources: new Set(),
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function show(id) { const el = $(id); if (el) el.style.display = ''; }
function hide(id) { const el = $(id); if (el) el.style.display = 'none'; }
function showBlock(id) { const el = $(id); if (el) el.style.display = 'block'; }

function setStatus(text, type = 'idle') {
  const dot = $('status-dot');
  const label = $('status-text');
  dot.className = 'status-dot ' + type;
  label.textContent = text;
}

function showToast(message, type = 'info') {
  const container = $('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.classList.add('visible'), 10);
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 400);
  }, 3800);
}

function setBtn(id, disabled, text) {
  const btn = $(id);
  if (!btn) return;
  btn.disabled = disabled;
  if (text !== undefined) btn.innerHTML = text;
}

// ── Example chips ──────────────────────────────────────────────────────────────

function setExample(btn) {
  $('query-input').value = btn.textContent.trim();
  $('query-input').focus();
}

// ── Generate Plan ──────────────────────────────────────────────────────────────

async function generatePlan() {
  const query = $('query-input').value.trim();
  if (!query || query.length < 5) {
    showToast('Please enter a research query (min 5 characters).', 'error');
    return;
  }

  const sector = $('sector-select').value;
  const depth = $('depth-select').value;

  setBtn('plan-btn', true, '<span class="btn-icon">&#9672;</span> Analysing...');
  setStatus('Generating plan...', 'active');

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

    renderPlan(plan);
    hide('empty-state');
    show('plan-panel');
    setStatus('Plan ready', 'idle');
    showToast('Research plan generated.', 'success');
  } catch (e) {
    showToast(e.message, 'error');
    setStatus('Ready', 'idle');
  } finally {
    setBtn('plan-btn', false, '<span class="btn-icon">&#9672;</span> Generate Research Plan');
  }
}

// ── Render Plan ────────────────────────────────────────────────────────────────

function renderPlan(plan) {
  $('plan-query').textContent = `"${plan.query}"`;

  // Tags
  const tags = $('plan-tags');
  tags.innerHTML = '';
  [
    { label: plan.sector, cls: 'tag-sector' },
    { label: plan.query_type.replace(/_/g, ' '), cls: 'tag-type' },
    { label: plan.depth, cls: 'tag-depth' },
    { label: `~${plan.estimated_steps} steps`, cls: 'tag-steps' },
  ].forEach(({ label, cls }) => {
    const span = document.createElement('span');
    span.className = `plan-tag ${cls}`;
    span.textContent = label;
    tags.appendChild(span);
  });

  // Header sector pill
  const pill = $('sector-pill');
  pill.textContent = plan.sector;
  pill.style.display = 'inline-flex';

  // Plan sections
  const body = $('plan-body');
  body.innerHTML = '';
  body.appendChild(makePlanSection('Research Aspects', plan.aspects, '&#9672;'));
  body.appendChild(makePlanSection('Tools & Data Sources', plan.tools, '&#9671;'));
  body.appendChild(makePlanSection('Report Structure', plan.output_structure, '&#9670;'));
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

// ── Approve / Modify / Cancel ──────────────────────────────────────────────────

async function approvePlan() {
  if (!state.sessionId) return;

  const modifiedScope = $('scope-input').value.trim() || null;

  setBtn('approve-btn', true, '<span>&#10003;</span> Starting...');
  setBtn('modify-btn', true, undefined);
  setBtn('cancel-btn', true, undefined);

  try {
    const res = await fetch('/api/research/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.sessionId,
        approved: true,
        modified_scope: modifiedScope,
      }),
    });

    if (!res.ok) throw new Error('Failed to start research.');

    hide('plan-panel');
    hide('scope-row');

    // Init steps sidebar
    $('steps-list').innerHTML = '';
    $('step-badge').textContent = '0';
    showBlock('steps-card');

    // Progress bar
    const maxSteps = state.plan ? state.plan.estimated_steps : 10;
    updateProgress(0, maxSteps, 'Initialising research...');
    showBlock('progress-wrap');

    setStatus('Researching...', 'active');
    showToast('Research started — live updates streaming.', 'success');

    listenToStream(state.sessionId);
  } catch (e) {
    showToast(e.message, 'error');
    setBtn('approve-btn', false, '<span>&#10003;</span> Approve &amp; Start Research');
    setBtn('modify-btn', false, undefined);
    setBtn('cancel-btn', false, undefined);
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
  $('plan-query').textContent = '';
  $('plan-tags').innerHTML = '';
  $('plan-body').innerHTML = '';
  $('scope-input').value = '';
  $('sector-pill').style.display = 'none';
  setStatus('Ready', 'idle');
  state.plan = null;
  state.sessionId = null;
  show('empty-state');
}

// ── SSE Stream ─────────────────────────────────────────────────────────────────

function listenToStream(sessionId) {
  if (state.eventSource) state.eventSource.close();

  const es = new EventSource(`/api/research/stream/${sessionId}`);
  state.eventSource = es;

  const maxSteps = state.plan ? state.plan.estimated_steps : 10;

  es.addEventListener('status', e => {
    const data = JSON.parse(e.data);
    updateProgress(0, maxSteps, data.message || 'Starting...');
  });

  es.addEventListener('step', e => {
    const data = JSON.parse(e.data);
    addStep(data);
    updateProgress(data.step || state.steps.length, maxSteps, data.focus || 'Researching...');
  });

  es.addEventListener('financial_data', e => {
    const data = JSON.parse(e.data);
    renderFinancials(data);
  });

  es.addEventListener('report_done', e => {
    const data = JSON.parse(e.data);
    hide('progress-wrap');
    renderReport(data.report, data.step_count);
    setStatus('Complete', 'idle');
    showToast('Research complete!', 'success');
    es.close();
    state.eventSource = null;
  });

  es.addEventListener('error', e => {
    let msg = null;
    try {
      const data = JSON.parse(e.data);
      if (data.message) msg = data.message;
    } catch {}
    if (msg) {
      showToast(`Error: ${msg}`, 'error');
      hide('progress-wrap');
      setStatus('Error', 'idle');
      es.close();
      state.eventSource = null;
    }
    // else: connection error / reconnect — ignore
  });
}

// ── Progress ───────────────────────────────────────────────────────────────────

function updateProgress(current, max, label) {
  const pct = max > 0 ? Math.min((current / max) * 100, 100) : 0;
  $('progress-fill').style.width = `${pct}%`;
  $('progress-label').textContent = label;
  $('progress-steps').textContent = `${current} / ${max} steps`;
}

// ── Steps Feed ─────────────────────────────────────────────────────────────────

function addStep(data) {
  state.steps.push(data);

  const list = $('steps-list');
  const li = document.createElement('li');
  li.className = 'step-item';

  const tool = (data.tool || 'search').toLowerCase();
  const toolIcon = tool.includes('analys') ? '&#9672;' :
                   tool.includes('rag')    ? '&#9671;' :
                   tool.includes('fin')    ? '&#36;'   : '&#9711;';

  li.innerHTML = `
    <div class="step-meta">
      <span class="step-num">${data.step || state.steps.length}</span>
      <span class="step-tool-badge">${toolIcon} ${escapeHtml(data.tool || 'search')}</span>
    </div>
    <p class="step-summary">${escapeHtml((data.summary || data.focus || '').slice(0, 200))}</p>
  `;

  list.appendChild(li);
  list.scrollTop = list.scrollHeight;
  $('step-badge').textContent = state.steps.length;

  if (data.sources && Array.isArray(data.sources)) {
    data.sources.forEach(s => addSource(s));
  }
}

function addSource(url) {
  if (!url || state.sources.has(url)) return;
  state.sources.add(url);

  showBlock('sources-card');

  const li = document.createElement('li');
  li.className = 'source-item';

  let hostname = url;
  try { hostname = new URL(url).hostname.replace('www.', ''); } catch {}

  li.innerHTML = `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(hostname)}</a>`;
  $('sources-list').appendChild(li);
}

// ── Financials ─────────────────────────────────────────────────────────────────

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
    const name = m.name || ticker;
    const rev  = m.revenue != null ? `$${(m.revenue / 1e9).toFixed(2)}B` : '—';
    const netM = m.net_margin != null ? `${(m.net_margin * 100).toFixed(1)}%` : '—';
    const ebitM= m.ebitda_margin != null ? `${(m.ebitda_margin * 100).toFixed(1)}%` : '—';
    const pe   = m.pe_ratio != null ? `${m.pe_ratio.toFixed(1)}x` : '—';

    const card = document.createElement('div');
    card.className = 'metric-card';
    card.innerHTML = `
      <div class="metric-ticker">${escapeHtml(ticker)}</div>
      <div class="metric-name">${escapeHtml(name)}</div>
      <div class="metric-row">
        <span class="metric-label">Revenue</span>
        <span class="metric-value">${rev}</span>
      </div>
      <div class="metric-row">
        <span class="metric-label">Net Margin</span>
        <span class="metric-value">${netM}</span>
      </div>
      <div class="metric-row">
        <span class="metric-label">EBITDA Margin</span>
        <span class="metric-value">${ebitM}</span>
      </div>
      <div class="metric-row">
        <span class="metric-label">P/E Ratio</span>
        <span class="metric-value">${pe}</span>
      </div>
    `;
    grid.appendChild(card);
  });

  if (chart) renderCharts(chart);
}

function renderCharts(chart) {
  const { labels, revenue_bn, ebitda_margins, net_margins } = chart;
  if (!labels || !labels.length) return;

  const CYAN   = 'rgba(0,212,255,0.85)';
  const PURPLE = 'rgba(139,92,246,0.85)';
  const GREEN  = 'rgba(16,185,129,0.85)';

  const baseOptions = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: {
        labels: { color: '#a0aec0', font: { family: 'Inter', size: 12 } },
      },
    },
    scales: {
      x: { ticks: { color: '#718096' }, grid: { color: 'rgba(255,255,255,0.04)' } },
      y: { ticks: { color: '#718096' }, grid: { color: 'rgba(255,255,255,0.04)' } },
    },
  };

  if (state.revenueChart) state.revenueChart.destroy();
  state.revenueChart = new Chart($('revenue-chart').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Revenue (USD Billion)',
        data: revenue_bn,
        backgroundColor: CYAN,
        borderColor: CYAN,
        borderWidth: 1,
        borderRadius: 6,
      }],
    },
    options: { ...baseOptions },
  });

  if (state.marginsChart) state.marginsChart.destroy();
  state.marginsChart = new Chart($('margins-chart').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'EBITDA Margin %',
          data: ebitda_margins,
          backgroundColor: PURPLE,
          borderColor: PURPLE,
          borderWidth: 1,
          borderRadius: 6,
        },
        {
          label: 'Net Margin %',
          data: net_margins,
          backgroundColor: GREEN,
          borderColor: GREEN,
          borderWidth: 1,
          borderRadius: 6,
        },
      ],
    },
    options: { ...baseOptions },
  });
}

// ── Report ─────────────────────────────────────────────────────────────────────

function renderReport(markdown, stepCount) {
  state.reportContent = markdown || '';

  showBlock('report-section');

  $('report-title').textContent = stepCount
    ? `Research Report  \u00B7  ${stepCount} steps`
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
  if (!state.reportContent) { showToast('No report to copy.', 'error'); return; }
  navigator.clipboard.writeText(state.reportContent)
    .then(() => showToast('Report copied to clipboard.', 'success'))
    .catch(() => showToast('Copy failed — please select and copy manually.', 'error'));
}

function downloadReport() {
  if (!state.reportContent) { showToast('No report to download.', 'error'); return; }
  const blob = new Blob([state.reportContent], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `finresearch_${state.sessionId || 'report'}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Report downloaded.', 'success');
}

// ── New Query ──────────────────────────────────────────────────────────────────

function newQuery() {
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }

  // Reset state
  state.sessionId = null;
  state.plan = null;
  state.reportContent = '';
  state.steps = [];
  state.sources = new Set();

  if (state.revenueChart) { state.revenueChart.destroy(); state.revenueChart = null; }
  if (state.marginsChart) { state.marginsChart.destroy(); state.marginsChart = null; }

  // Hide panels
  ['plan-panel', 'progress-wrap', 'financials-section', 'report-section',
   'steps-card', 'sources-card', 'scope-row'].forEach(hide);

  // Clear DOM
  ['query-input', 'scope-input'].forEach(id => { $(id).value = ''; });
  ['steps-list', 'sources-list', 'metrics-grid', 'report-body',
   'plan-body', 'plan-tags'].forEach(id => { $(id).innerHTML = ''; });
  $('step-badge').textContent = '0';
  $('sector-pill').style.display = 'none';

  show('empty-state');
  setStatus('Ready', 'idle');
  $('query-input').focus();
}

// ── Utility ────────────────────────────────────────────────────────────────────

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Init ───────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  $('query-input').addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      generatePlan();
    }
  });
});
