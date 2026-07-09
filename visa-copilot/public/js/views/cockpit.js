import { api } from '../api.js';
import { topbar, badge, esc, money, toast, loading } from '../ui.js';

const MODES = [
  { id: 'manual', t: 'Manual Apply', d: 'Open the original page with tailored docs beside it.', safe: 'All sources · safest' },
  { id: 'autofill', t: 'Extension Autofill', d: 'Detects fields and inserts approved profile data.', safe: 'Supported ATS' },
  { id: 'watched', t: 'Watched Copilot', d: 'Remote browser fills the form while you watch; pauses for approval.', safe: 'Whitelisted sites' },
];

export async function renderCockpit(main, { param } = {}) {
  const jobs = (await api.jobs({ sort: 'fit' })).jobs;
  let jobId = param || jobs[0]?.id;
  let job = jobs.find((j) => j.id === jobId) || jobs[0];

  const vault = await api.vault();

  const draw = () => {
    main.innerHTML = topbar('Application Cockpit', 'Assisted apply with field mapping, pauses, and approval before submit') + `
      <div class="card pad fade-in" style="margin-bottom:18px;display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap">
        <div style="flex:1;min-width:240px"><div class="dim" style="font-size:11px;margin-bottom:6px">Application</div>
          <select class="select" id="ckJob" style="width:100%">${jobs.map((j) => `<option value="${j.id}" ${j.id === job.id ? 'selected' : ''}>${esc(j.title)} — ${esc(j.company)}</option>`).join('')}</select>
        </div>
      </div>

      <div class="grid cols-3" style="margin-bottom:18px">
        ${MODES.map((m) => `<div class="card pad hover" data-mode="${m.id}" style="cursor:pointer">
          <div style="font-weight:650;font-size:14px">${m.t}</div>
          <p class="muted" style="font-size:12px;margin:6px 0 10px">${m.d}</p>
          ${badge(m.safe, 'cyan')}</div>`).join('')}
      </div>

      <div class="grid cols-3">
        <div class="card pad span-2 fade-in">
          <div class="section-title" style="font-size:15px">🖥 Watched browser session</div>
          <div id="browserView" style="border:1px solid var(--glass-border);border-radius:14px;overflow:hidden;min-height:300px;background:rgba(0,0,0,0.25)">
            ${browserIdle(job)}
          </div>
          <div style="display:flex;gap:10px;margin-top:14px" id="ckControls">
            <button class="btn primary" id="startSession">▶ Start watched apply</button>
            <button class="btn" id="pauseSession" disabled>⏸ Pause</button>
          </div>
        </div>

        <div class="card pad fade-in">
          <div class="section-title" style="font-size:15px">🗺 Field map</div>
          <div id="fieldMap">${fieldMap(vault, job)}</div>
        </div>
      </div>

      <div class="grid cols-2" style="margin-top:18px">
        <div class="card pad">
          <div class="section-title" style="font-size:14px">🛡 Automation rules in force</div>
          ${['No hidden submission — you approve before every apply', 'No CAPTCHA / MFA / login bypass — it pauses for you', 'No fake right-to-work, sponsorship or registration answers', 'Full audit trail of every AI-filled value'].map((r) => `<div class="list-row"><span>✓</span><span style="font-size:12.5px" class="muted">${r}</span></div>`).join('')}
        </div>
        <div class="card pad">
          <div class="section-title" style="font-size:14px">📎 Attached documents</div>
          ${(vault.documents || []).length ? vault.documents.map((d) => `<div class="list-row"><span>📄</span><span style="flex:1;font-size:12.5px">${esc(d.type || 'Document')}</span>${badge('v' + (d.version || 1), 'ghost')}</div>`).join('')
            : `<div class="list-row"><span>📄</span><span style="flex:1;font-size:12.5px">Tailored CV (from CV Studio)</span>${badge('ready', 'high')}</div>
               <div class="list-row"><span>✚</span><span style="flex:1;font-size:12.5px">NHS supporting statement</span>${badge(job.nhs ? 'ready' : 'n/a', job.nhs ? 'high' : 'ghost')}</div>`}
        </div>
      </div>`;

    main.querySelector('#ckJob').addEventListener('change', (e) => { job = jobs.find((j) => j.id === e.target.value); draw(); });
    main.querySelectorAll('[data-mode]').forEach((n) => n.addEventListener('click', () => toast(MODES.find((m) => m.id === n.dataset.mode).t + ' selected', 'info')));
    main.querySelector('#startSession').addEventListener('click', () => runSession(vault, job));
  };
  draw();
}

function browserIdle(job) {
  return `<div style="padding:30px;text-align:center;color:var(--dim)">
    <div style="font-size:34px">🌐</div>
    <div style="margin-top:10px;font-size:13px">Ready to open <b>${esc(job.source)}</b> for<br>${esc(job.title)} — ${esc(job.company)}</div>
    <div style="font-size:11.5px;margin-top:8px">The session runs in an isolated environment. You stay in control.</div>
  </div>`;
}

function fieldMap(vault, job) {
  const p = vault.profile || {};
  const fields = [
    { label: 'Full name', value: 'Amara Okafor', status: 'auto' },
    { label: 'Email', value: 'demo@visacopilot.app', status: 'auto' },
    { label: 'Location', value: p.location || 'London', status: 'auto' },
    { label: 'Right to work / visa status', value: p.visa_status || '', status: 'pause' },
    { label: 'Requires sponsorship?', value: 'Yes — Skilled Worker', status: 'pause' },
    { label: 'Professional registration', value: 'NMC (in progress)', status: 'pause' },
    { label: 'CV upload', value: 'Tailored_CV.docx', status: 'auto' },
  ];
  return fields.map((f) => `<div class="list-row" style="align-items:flex-start">
    <div style="flex:1"><div style="font-size:12px;font-weight:600">${esc(f.label)}</div>
      <div class="muted" style="font-size:11.5px;margin-top:2px">${esc(f.value || '— needs your input —')}</div></div>
    ${f.status === 'auto' ? badge('auto', 'high') : badge('you approve', 'mod')}
  </div>`).join('');
}

async function runSession(vault, job) {
  const view = document.getElementById('browserView');
  const start = document.getElementById('startSession');
  start.disabled = true;
  const steps = [
    'Opening ' + job.source + ' in isolated browser…',
    'Locating the application form…',
    'Uploading tailored CV…',
    'Filling name, email and location from your vault…',
    '⏸ Paused — sensitive field: “Do you require sponsorship?” Please confirm.',
  ];
  for (let i = 0; i < steps.length; i++) {
    view.innerHTML = `<div style="padding:24px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px"><div class="dot"></div><span class="muted" style="font-size:12px">live · ${esc(job.source)}</span></div>
      ${steps.slice(0, i + 1).map((s, k) => `<div style="display:flex;gap:10px;font-size:12.5px;margin-bottom:9px;color:${k === i ? 'var(--text)' : 'var(--dim)'}">
        <span>${s.startsWith('⏸') ? '⏸' : k === i ? '▸' : '✓'}</span><span>${esc(s.replace('⏸ ', ''))}</span></div>`).join('')}
    </div>`;
    await new Promise((r) => setTimeout(r, 700));
  }
  document.getElementById('pauseSession').disabled = false;
  view.innerHTML += `<div style="padding:0 24px 24px"><div class="notice warn" style="margin-bottom:12px"><span>⚠</span><span>The copilot paused on a sensitive question. It will never answer right-to-work or sponsorship questions on your behalf.</span></div>
    <button class="btn primary" id="approveField">✓ Confirm “Yes — requires Skilled Worker sponsorship”</button></div>`;
  document.getElementById('approveField').addEventListener('click', () => reviewScreen(job));
}

function reviewScreen(job) {
  const view = document.getElementById('browserView');
  view.innerHTML = `<div style="padding:24px">
    <div class="section-title" style="font-size:14px">Review before submit</div>
    <div class="notice info" style="margin-bottom:14px"><span>ℹ</span><span>Nothing is submitted until you approve. Check every value below.</span></div>
    ${[['Name', 'Amara Okafor'], ['Email', 'demo@visacopilot.app'], ['Sponsorship required', 'Yes — Skilled Worker'], ['CV', 'Tailored_CV.docx'], ['Cover note', 'Tailored to ' + job.title]].map(([k, v]) => `<div class="list-row"><span style="flex:1;font-size:12.5px" class="muted">${esc(k)}</span><b style="font-size:12.5px">${esc(v)}</b></div>`).join('')}
    <button class="btn primary" id="finalSubmit" style="margin-top:16px;width:100%">✓ Approve & submit application</button>
  </div>`;
  document.getElementById('finalSubmit').addEventListener('click', async () => {
    await api.saveApplication({ job_id: job.id, status: 'Applied', method: 'Watched Copilot' });
    toast('Application submitted & logged to tracker', 'success');
    view.innerHTML = `<div style="padding:40px;text-align:center"><div style="font-size:44px">🎉</div>
      <h3 style="margin:12px 0 6px">Application submitted</h3><p class="muted" style="font-size:13px">Logged with source, document version and timestamp. Track it in your pipeline.</p>
      <a class="btn primary" href="#tracker" style="margin-top:16px">Go to tracker →</a></div>`;
  });
}
