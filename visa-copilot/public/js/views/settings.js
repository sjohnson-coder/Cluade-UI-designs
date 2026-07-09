import { api } from '../api.js';
import { topbar, badge, esc } from '../ui.js';

export async function renderSettings(main) {
  const [status, audit, sponsors] = await Promise.all([api.status(), api.audit(), api.sponsors()]);
  const ai = status.ai;

  main.innerHTML = topbar('Settings', 'AI provider, privacy, sources and compliance') + `
    <div class="grid cols-2" style="margin-bottom:18px">
      <div class="card pad fade-in">
        <div class="section-title" style="font-size:15px">🤖 AI provider</div>
        <div class="notice ${ai.llm_enabled ? 'safe' : 'info'}" style="margin-bottom:12px"><span>${ai.llm_enabled ? '✓' : 'ℹ'}</span><span>${esc(ai.note)}</span></div>
        <div class="list-row"><span style="flex:1;font-size:12.5px" class="muted">Active engine</span><b style="font-size:12.5px">${esc(ai.provider)}</b></div>
        <div class="list-row"><span style="flex:1;font-size:12.5px" class="muted">Model</span><b style="font-size:12.5px">${esc(ai.model)}</b></div>
        <div class="list-row"><span style="flex:1;font-size:12.5px" class="muted">LLM enrichment</span>${badge(ai.llm_enabled ? 'On' : 'Off', ai.llm_enabled ? 'high' : 'ghost')}</div>
        <p class="dim" style="font-size:11.5px;margin-top:10px">Provider-agnostic: set <code>AI_PROVIDER=openai|claude</code> plus an API key on the server to route CV/NHS/interview tasks to a model. All output still passes fact & banned-phrase guards.</p>
      </div>

      <div class="card pad fade-in">
        <div class="section-title" style="font-size:15px">🔒 Privacy & data control</div>
        ${['Encryption at rest & in transit', 'Explicit consent for sensitive fields', 'Inspect & approve every AI change', 'Export or delete your data anytime', 'MFA & signed document URLs'].map((t) => `<div class="list-row"><span>✓</span><span style="font-size:12.5px" class="muted">${t}</span></div>`).join('')}
        <div style="display:flex;gap:10px;margin-top:12px"><button class="btn sm">Export my data</button><button class="btn sm">Delete account</button></div>
      </div>
    </div>

    <div class="grid cols-2" style="margin-bottom:18px">
      <div class="card pad fade-in">
        <div class="section-title" style="font-size:15px">🏛 Licensed sponsor register</div>
        <p class="muted" style="font-size:12.5px;margin-bottom:12px">${sponsors.sponsors.length} organisations imported (sample of the UK Register of Licensed Sponsors).</p>
        <input class="input" id="spSearch" placeholder="🔍 Search sponsor…" style="width:100%;margin-bottom:12px" />
        <div id="spList">${sponsorRows(sponsors.sponsors.slice(0, 6))}</div>
      </div>

      <div class="card pad fade-in">
        <div class="section-title" style="font-size:15px">📋 Compliance / audit log</div>
        <p class="muted" style="font-size:12.5px;margin-bottom:10px">Every AI change and application action is recorded.</p>
        <div style="max-height:280px;overflow-y:auto">${audit.logs.length ? audit.logs.slice(0, 20).map(auditRow).join('') : '<p class="dim" style="font-size:12px">No activity yet.</p>'}</div>
      </div>
    </div>

    <div class="card pad fade-in">
      <div class="section-title" style="font-size:15px">⚠ Automation limitation notices</div>
      <div class="grid cols-2">
        ${[['Interview guarantee', 'Improves targeting & quality — does not guarantee interviews.'], ['Visa sponsorship', 'A sponsor licence match is not a promise to sponsor a specific role.'], ['ATS score', 'An internal parser estimate, not an official employer ATS score.'], ['Job-board automation', 'Restricted sources use manual apply only — no prohibited scraping.']].map(([h, b]) => `<div class="notice warn" style="margin-bottom:0"><span>⚠</span><span><b>${h}:</b> ${b}</span></div>`).join('')}
      </div>
    </div>`;

  const search = main.querySelector('#spSearch');
  search.addEventListener('input', async (e) => {
    const res = await api.sponsors(e.target.value);
    main.querySelector('#spList').innerHTML = sponsorRows(res.sponsors.slice(0, 8));
  });
}

function sponsorRows(rows) {
  return rows.map((s) => `<div class="list-row">
    <div style="flex:1"><b style="font-size:12.5px">${esc(s.organisation_name)}</b><div class="dim" style="font-size:11px">${esc(s.town)}, ${esc(s.county)}</div></div>
    ${badge(s.rating, 'high')}<span class="dim" style="font-size:11px">${esc(s.route)}</span>
  </div>`).join('') || '<p class="dim" style="font-size:12px">No match.</p>';
}

function auditRow(l) {
  return `<div class="list-row" style="padding:9px 0"><span style="font-size:12px">•</span>
    <div style="flex:1"><b style="font-size:12px">${esc(l.action)}</b>${l.detail ? `<span class="dim" style="font-size:11px"> · ${esc(String(l.detail).slice(0, 40))}</span>` : ''}</div>
    <span class="dim" style="font-size:10.5px">${new Date(l.timestamp).toLocaleTimeString()}</span></div>`;
}
