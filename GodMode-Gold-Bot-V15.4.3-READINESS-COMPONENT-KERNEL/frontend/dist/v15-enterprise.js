(() => {
  'use strict';
  const BUILD = 'V15.4.3-READINESS-COMPONENT-KERNEL';
  const HOST_ID = 'godmode-v15-enterprise-panel';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const pct = (value) => Number.isFinite(Number(value)) ? `${Math.round(Number(value) * 100)}%` : '—';
  const isAIPage = () => /(^|\/)ai(?:-|\/|$)/i.test(location.pathname) || /ai agent/i.test(document.title);

  async function getJSON(url) {
    const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function metric(label, value) {
    return `<div class="v15-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
  }

  function render(data) {
    const forecast = data.forecast || {};
    const probabilities = forecast.probabilities || {};
    const health = data.health || {};
    const regime = data.regime || {};
    const exit = data.exit || {};
    const burst = data.burst || {};
    const gates = (burst.gates || []).map((gate) => `<span class="v15-gate ${gate.passed ? 'pass' : 'block'}">${esc(gate.name)}: ${gate.passed ? 'PASS' : 'BLOCK'}</span>`).join('');
    return `
      <style>
        #${HOST_ID}{margin-top:16px;padding:16px;border:1px solid var(--border,rgba(148,163,184,.18));border-radius:14px;background:var(--card-bg,rgba(15,23,42,.65));color:inherit;box-shadow:0 8px 30px rgba(0,0,0,.08)}
        #${HOST_ID} .v15-head{display:flex;justify-content:space-between;gap:12px;align-items:center}
        #${HOST_ID} .v15-title{font-weight:800;font-size:17px}
        #${HOST_ID} .v15-sub{font-size:12px;opacity:.65;margin-top:3px}
        #${HOST_ID} .v15-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-top:13px}
        #${HOST_ID} .v15-metric{padding:12px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:rgba(15,23,42,.22)}
        #${HOST_ID} .v15-metric span{display:block;font-size:11px;opacity:.65;text-transform:uppercase;letter-spacing:.06em}
        #${HOST_ID} .v15-metric strong{display:block;font-size:20px;margin-top:4px}
        #${HOST_ID} .v15-two{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
        #${HOST_ID} .v15-box{padding:12px;border:1px solid rgba(148,163,184,.16);border-radius:12px}
        #${HOST_ID} .v15-gate{display:inline-flex;padding:5px 8px;border-radius:999px;margin:3px;font-size:11px}
        #${HOST_ID} .v15-gate.pass{background:rgba(34,197,94,.15);color:#86efac}
        #${HOST_ID} .v15-gate.block{background:rgba(239,68,68,.15);color:#fca5a5}
        #${HOST_ID} button{border:1px solid rgba(148,163,184,.22);border-radius:9px;padding:8px 10px;background:transparent;color:inherit;cursor:pointer}
        @media(max-width:900px){#${HOST_ID} .v15-grid{grid-template-columns:repeat(2,minmax(0,1fr))}#${HOST_ID} .v15-two{grid-template-columns:1fr}}
      </style>
      <div class="v15-head"><div><div class="v15-title">V15.1.4 Operational Intelligence</div><div class="v15-sub">Shadow-mode decision intelligence · ${esc(data.build_id || BUILD)}</div></div><button data-v15-refresh>Refresh</button></div>
      <div class="v15-grid">
        ${metric('Health', `${Math.round(Number(health.score || 0))}%`)}
        ${metric('Status', data.status || 'warming')}
        ${metric('Regime', regime.primary || 'Unknown')}
        ${metric('Score type', forecast.score_type || 'Not evaluated')}
        ${metric('Continuation', pct(probabilities.continuation))}
        ${metric('Recovery', pct(probabilities.recovery))}
        ${metric('TP before SL', pct(probabilities.tp_before_sl))}
        ${metric('Fast-fail risk', pct(probabilities.fast_fail))}
      </div>
      <div class="v15-two"><div class="v15-box"><b>Exit recommendation: ${esc(exit.action || 'Waiting')}</b><div class="v15-sub">${esc(exit.reason || 'A live shadow evaluation has not completed.')}</div></div><div class="v15-box"><b>Burst: ${burst.allowed ? 'ALLOWED' : 'BLOCKED'}</b><div>${gates || '<span class="v15-sub">Gate trace appears after evaluation.</span>'}</div></div></div>
      ${data.explanation?.summary ? `<div class="v15-box" style="margin-top:10px">${esc(data.explanation.summary)}</div>` : ''}`;
  }

  async function refresh(host) {
    host.setAttribute('aria-busy', 'true');
    try {
      host.innerHTML = render(await getJSON('/api/v15/overview'));
      host.querySelector('[data-v15-refresh]')?.addEventListener('click', () => refresh(host), {once: true});
    } catch (error) {
      host.innerHTML = `<b>V15 Intelligence unavailable</b><div class="v15-sub">${esc(error.message)}</div>`;
    } finally {
      host.setAttribute('aria-busy', 'false');
    }
  }

  function findMountPoint() {
    return document.querySelector('.ai-agent-page > div:first-child') || document.querySelector('main');
  }

  function mount(attempt = 0) {
    const existing = document.getElementById(HOST_ID);
    if (!isAIPage()) {
      existing?.remove();
      return;
    }
    if (existing) return;
    const target = findMountPoint();
    if (!target) {
      if (attempt < 20) setTimeout(() => mount(attempt + 1), 250);
      return;
    }
    const host = document.createElement('section');
    host.id = HOST_ID;
    host.dataset.build = BUILD;
    const header = target.querySelector('.page-header');
    if (header?.nextSibling) target.insertBefore(host, header.nextSibling); else target.prepend(host);
    refresh(host);
  }

  const notifyRoute = () => window.dispatchEvent(new Event('godmode:routechange'));
  for (const method of ['pushState', 'replaceState']) {
    const original = history[method];
    history[method] = function (...args) { const result = original.apply(this, args); notifyRoute(); return result; };
  }
  window.addEventListener('popstate', notifyRoute);
  window.addEventListener('godmode:routechange', () => setTimeout(() => mount(), 0));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => mount(), {once: true}); else mount();
})();
