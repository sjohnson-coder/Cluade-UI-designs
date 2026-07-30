(() => {
  'use strict';
  const BUILD = 'V15.4.3-READINESS-COMPONENT-KERNEL';
  const API = window.location.origin;
  let latest = null;
  let source = null;
  let pollTimer = 0;
  let reconnectTimer = 0;
  let lastEventAt = 0;

  const apiKey = () => { try { return sessionStorage.getItem('godmode_api_key') || ''; } catch { return ''; } };
  const headers = () => ({...(apiKey() ? {'X-GodMode-Key': apiKey()} : {})});
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pct = value => Math.max(0, Math.min(100, Number(value || 0) * 100));
  const num = (value, fallback=0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const text = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = String(value); };
  const statusClass = status => {
    const s = String(status || '').toUpperCase();
    if (['ORDER_SENT','CONFIRMED','INTENT','PROBE','LIVE','WATCH'].includes(s)) return 'is-live';
    if (['COLLECTING','STARTING'].includes(s)) return 'is-collecting';
    return 'is-recovering';
  };

  async function fetchStatus(timeout=2200) {
    // The React Dashboard polls this exact endpoint at 1 Hz as well. Going through the shared bus
    // means the two consumers make one request per second between them rather than two, which
    // matters because every one of these hits a synchronous handler in a bounded thread pool.
    if (window.__godmodeFetchJSON) {
      const shared = await window.__godmodeFetchJSON(API + '/api/fast-sniper/status', 700);
      if (shared && shared.ok !== false) return shared;
      throw new Error((shared && shared.message) || 'Predictor status unavailable');
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(API + '/api/fast-sniper/status', {headers: headers(), cache:'no-store', credentials:'omit', signal:controller.signal});
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body.ok === false) throw new Error(body.message || `HTTP ${response.status}`);
      return body;
    } finally { clearTimeout(timer); }
  }

  function chosenState(data) {
    const intent = data?.earlyIntent || {};
    const impulse = data?.earlyImpulse || {};
    return num(intent.probability) >= num(impulse.probability) ? intent : impulse;
  }

  function dashboardHtml() {
    return `<section id="godmode-predictor-dashboard" class="card predictor-dashboard-card predictor-heartbeat is-collecting" aria-live="polite">
      <div class="predictor-dashboard-head">
        <div class="predictor-title-wrap"><span class="predictor-orb"><i></i></span><div><span class="eyebrow">LIVE EARLY ENTRY ENGINE</span><h3>Early Intent & Impulse</h3></div></div>
        <div class="button-wrap"><span id="pid-transport" class="tag blue">CONNECTING</span><span id="pid-stage" class="tag blue">STARTING</span><button id="pid-refresh" type="button" class="outline-button predictor-refresh">↻ Refresh</button></div>
      </div>
      <div class="predictor-live-grid">
        <div class="predictor-stage-panel"><div><span>Early Intent</span><strong id="pid-intent-state">— · STARTING</strong></div><b id="pid-intent-prob">0%</b><div class="predictor-stage-meter"><i id="pid-intent-bar"></i></div></div>
        <div class="predictor-stage-panel"><div><span>Impulse Confirmation</span><strong id="pid-impulse-state">— · STARTING</strong></div><b id="pid-impulse-prob">0%</b><div class="predictor-stage-meter"><i id="pid-impulse-bar"></i></div></div>
        <div class="predictor-radar" aria-hidden="true"><span></span><i></i><b></b></div>
        <div class="predictor-status-panel"><span>Priority execution lane</span><strong id="pid-priority-state">STARTING</strong><small id="pid-priority-reason">Building the live tick sample.</small></div>
      </div>
      <div class="predictor-metrics">
        ${[['Velocity','velocity_score'],['Acceleration','acceleration_score'],['Persistence','directional_score'],['Compression','compression_release_score'],['Spread quality','spread_score'],['Live candle','candle_score']].map(([label,key]) => `<div><span>${label}</span><strong id="pid-${key}-value">0%</strong><em><i id="pid-${key}-bar"></i></em></div>`).join('')}
      </div>
      <div class="predictor-runtime-strip">
        <span><small>Loop</small><strong id="pid-loop">0.25s</strong></span>
        <span><small>Ticks</small><strong id="pid-ticks">0 / 10</strong></span>
        <span><small>Tick age</small><strong id="pid-age">—</strong></span>
        <span><small>Move</small><strong id="pid-move">0.00 ATR</strong></span>
        <span><small>MT5</small><strong id="pid-mt5">CHECKING</strong></span>
        <span><small>Updated</small><strong id="pid-updated">—</strong></span>
      </div>
      <div id="pid-blocker" class="predictor-blocker">Waiting for the first completed priority scan.</div>
    </section>`;
  }

  function ensureDashboardCard() {
    if (!location.hash.toLowerCase().includes('dashboard')) return;
    if (document.getElementById('godmode-predictor-dashboard')) return;
    const top = document.querySelector('.dashboard-top');
    const anchor = document.getElementById('godmode-predictor-dashboard-anchor');
    if (!top && !anchor) return;
    const holder = document.createElement('div');
    holder.innerHTML = dashboardHtml();
    if (anchor) anchor.insertAdjacentElement('afterend', holder.firstElementChild); else top.insertAdjacentElement('afterend', holder.firstElementChild);
    document.getElementById('pid-refresh')?.addEventListener('click', manualRefresh);
    if (latest) render(latest);
  }

  function setBar(prefix, key, state) {
    const value = pct(state?.[key]);
    text(`${prefix}-${key}-value`, `${value.toFixed(0)}%`);
    const bar = document.getElementById(`${prefix}-${key}-bar`);
    if (bar) bar.style.width = `${value}%`;
  }

  function renderSettings(data) {
    if (!document.getElementById('godmode-early-impulse-settings')) return;
    const intent = data?.earlyIntent || {};
    const impulse = data?.earlyImpulse || {};
    const state = chosenState(data);
    const priority = data?.priorityIntent || {};
    const health = priority.health || {};
    const stage = String(state.runtimeStatus || state.stage || data?.endpointStatus || 'STARTING').toUpperCase();
    const side = String(state.side || '—').toUpperCase();
    const probability = pct(state.probability);
    const tag = document.getElementById('eip-stage-tag');
    if (tag) { tag.textContent = stage; tag.className = `tag ${statusClass(stage)==='is-live'?'green':statusClass(stage)==='is-collecting'?'blue':'red'}`; }
    text('eip-side-stage', `${side} · ${stage}`);
    text('eip-probability', `${probability.toFixed(0)}%`);
    ['velocity_score','acceleration_score','directional_score','compression_release_score','spread_score','candle_score'].forEach(key => setBar('eip', key, state));
    text('eip-move', `${num(state.displacement_atr).toFixed(2)} ATR`);
    text('eip-sweep', `${pct(state.sweep_penalty || state.reversal_penalty).toFixed(0)}%`);
    const context = state.context || {};
    text('eip-context', context.allowed === false ? 'BLOCKED' : context.allowed === true ? `${pct(context.score).toFixed(0)}% OK` : '—');
    text('eip-lifecycle', stage);
    text('eip-loop', `${num(health.expectedIntervalSeconds, .25).toFixed(2)}s`);
    text('eip-mt5', data?.mt5?.connected ? 'LIVE' : 'OFFLINE');
    text('eip-tick-age', state.latestTickAgeMs == null ? '—' : `${num(state.latestTickAgeMs).toFixed(0)}ms`);
    text('eip-fetch-latency', `${num(data?.endpointLatencyMs).toFixed(1)}ms`);
    const pstate = String(priority.runtimeStatus || health.runtimeStatus || data?.endpointStatus || 'STARTING').toUpperCase();
    text('eip-priority-state', pstate);
    text('eip-priority-reason', priority.lastBlocker || priority.lastExecution?.message || priority.lastDecision?.reason || `Heartbeat sequence ${health.scanSequence || 0}.`);
    text('eip-reason', `${state.reason || 'Collecting live ticks.'} Ticks: ${num(state.tickCount)}${state.requiredTickCount ? ` / ${state.requiredTickCount}` : ''}.`);
    document.querySelectorAll('.impulse-stage-track [data-stage]').forEach(el => el.classList.toggle('active', el.dataset.stage === stage));
    const card = document.getElementById('godmode-early-impulse-settings');
    if (card) { card.classList.remove('is-live','is-collecting','is-recovering'); card.classList.add(statusClass(pstate)); }
    const error = document.getElementById('eip-error');
    if (error) error.hidden = true;
  }

  function renderDashboard(data) {
    ensureDashboardCard();
    const card = document.getElementById('godmode-predictor-dashboard');
    if (!card) return;
    const intent = data?.earlyIntent || {};
    const impulse = data?.earlyImpulse || {};
    const chosen = chosenState(data);
    const priority = data?.priorityIntent || {};
    const health = priority.health || {};
    const pstate = String(priority.runtimeStatus || health.runtimeStatus || data?.endpointStatus || 'STARTING').toUpperCase();
    card.classList.remove('is-live','is-collecting','is-recovering');
    card.classList.add(statusClass(pstate));
    text('pid-transport', source === 'sse' ? 'LIVE STREAM' : source === 'poll' ? 'LIVE POLL' : 'CONNECTING');
    text('pid-stage', pstate);
    const transport = document.getElementById('pid-transport'); if (transport) transport.className = `tag ${source==='sse'?'green':'blue'}`;
    const stageTag = document.getElementById('pid-stage'); if (stageTag) stageTag.className = `tag ${statusClass(pstate)==='is-live'?'green':statusClass(pstate)==='is-collecting'?'blue':'red'}`;
    const setStage = (prefix, state) => {
      const stage = String(state.runtimeStatus || state.stage || 'STARTING').toUpperCase();
      const side = String(state.side || '—').toUpperCase();
      const probability = pct(state.probability);
      text(`pid-${prefix}-state`, `${side} · ${stage}`);
      text(`pid-${prefix}-prob`, `${probability.toFixed(0)}%`);
      const bar = document.getElementById(`pid-${prefix}-bar`); if (bar) bar.style.width = `${probability}%`;
    };
    setStage('intent', intent); setStage('impulse', impulse);
    ['velocity_score','acceleration_score','directional_score','compression_release_score','spread_score','candle_score'].forEach(key => setBar('pid', key, chosen));
    text('pid-priority-state', pstate);
    text('pid-priority-reason', priority.lastExecution?.message || priority.lastDecision?.reason || priority.lastBlocker || `Priority worker heartbeat ${health.scanSequence || 0}.`);
    text('pid-loop', `${num(health.expectedIntervalSeconds, .25).toFixed(2)}s`);
    text('pid-ticks', `${num(chosen.tickCount)} / ${num(chosen.requiredTickCount || chosen.targetTickCount || 10, 10)}`);
    text('pid-age', chosen.latestTickAgeMs == null ? '—' : `${num(chosen.latestTickAgeMs).toFixed(0)}ms`);
    text('pid-move', `${num(chosen.displacement_atr).toFixed(2)} ATR`);
    text('pid-mt5', data?.mt5?.connected ? 'LIVE' : 'OFFLINE');
    text('pid-updated', new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}));
    const context = chosen.context || {};
    const contextReason = context.allowed === false && Array.isArray(context.reasons) ? `Context blocked: ${context.reasons.slice(0,2).join('; ')}` : '';
    text('pid-blocker', priority.lastBlocker || contextReason || chosen.reason || 'Live scanner is active. Waiting for a context-qualified burst near structure.');
  }

  function render(data) {
    latest = data;
    lastEventAt = Date.now();
    window.__godmodePredictorLiveLatest = data;
    renderSettings(data);
    renderDashboard(data);
  }

  async function manualRefresh(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    event?.stopImmediatePropagation?.();
    const button = event?.currentTarget || document.getElementById('eip-refresh') || document.getElementById('pid-refresh');
    const original = button?.textContent || '↻ Refresh';
    if (button) { button.disabled = true; button.classList.add('eip-refresh-spin'); button.textContent = '↻ Refreshing…'; }
    try {
      const data = await fetchStatus(3500); source = source || 'poll'; render(data);
      if (button) button.textContent = `✓ Updated ${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
    } catch (error) {
      if (button) button.textContent = '⚠ Status retrying';
      markTransportError(error);
    } finally {
      setTimeout(() => { if (button) { button.disabled = false; button.classList.remove('eip-refresh-spin'); button.textContent = original; } }, 1400);
    }
  }

  function bindSettingsRefresh() {
    const button = document.getElementById('eip-refresh');
    if (button && !button.dataset.liveBound) {
      button.dataset.liveBound = '1';
      button.addEventListener('click', manualRefresh, true);
    }
  }

  function markTransportError(error) {
    const message = String(error?.message || error || 'Predictor transport interrupted');
    const card = document.getElementById('godmode-predictor-dashboard');
    if (card) { card.classList.remove('is-live','is-collecting'); card.classList.add('is-recovering'); }
    text('pid-transport', 'RECONNECTING');
    text('pid-blocker', `Diagnostics transport interrupted. Engine health is being rechecked: ${message}`);
    const settingsError = document.getElementById('eip-error');
    if (settingsError) { settingsError.hidden = false; settingsError.textContent = `Live diagnostics reconnecting. This does not by itself mean MT5 or the trading engine is offline. ${message}`; }
  }

  function startPolling() {
    source = 'poll';
    if (pollTimer) return;
    const run = async () => { if (document.hidden) return; try { render(await fetchStatus()); } catch (error) { markTransportError(error); } };
    void run();
    pollTimer = setInterval(run, 1000);
  }

  function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = 0; }

  function connectStream() {
    if (apiKey()) { startPolling(); return; }
    try {
      source = 'sse';
      const es = new EventSource(API + '/api/fast-sniper/stream');
      source = es;
      es.addEventListener('predictor', event => {
        try { source = 'sse'; stopPolling(); render(JSON.parse(event.data)); } catch (error) { markTransportError(error); }
      });
      es.addEventListener('predictor-error', event => { try { markTransportError(JSON.parse(event.data)?.message); } catch { markTransportError('Predictor stream error'); } });
      es.onerror = () => {
        es.close(); source = null; markTransportError('stream disconnected'); startPolling();
        clearTimeout(reconnectTimer); reconnectTimer = setTimeout(() => { stopPolling(); connectStream(); }, 5000);
      };
    } catch (error) { markTransportError(error); startPolling(); }
  }

  window.__godmodeLegacyPredictorPollStop?.();
  const observer = new MutationObserver(() => { ensureDashboardCard(); bindSettingsRefresh(); if (latest) { renderSettings(latest); renderDashboard(latest); } });
  observer.observe(document.documentElement, {childList:true, subtree:true});
  window.addEventListener('hashchange', () => setTimeout(() => { ensureDashboardCard(); bindSettingsRefresh(); if (latest) render(latest); }, 80));
  setInterval(() => {
    const stale = lastEventAt && Date.now() - lastEventAt > 3500;
    if (stale) markTransportError('no status heartbeat for more than 3.5 seconds');
  }, 1000);
  ensureDashboardCard(); bindSettingsRefresh(); connectStream();
})();
