import { api } from '../api.js';
import { topbar, badge, esc, toast, openModal } from '../ui.js';

export async function renderVault(main) {
  const v = await api.vault();
  const p = v.profile || {};

  main.innerHTML = topbar('Career Vault', 'Your verified evidence — the single source of truth the AI is allowed to use') + `
    <div class="notice info fade-in" style="margin-bottom:18px"><span>🔐</span><span>The optimiser can only use facts stored here. This prevents hallucinated CV claims — every rewrite is traceable to your evidence.</span></div>

    <div class="grid cols-3" style="margin-bottom:18px">
      <div class="card pad span-2">
        <div class="section-title" style="font-size:15px">Profile</div>
        <div class="grid cols-2" style="gap:12px">
          ${field('Name', 'Amara Okafor')}
          ${field('Visa status', p.visa_status)}
          ${field('Target roles', (p.target_roles || []).join(', '))}
          ${field('Location', p.location)}
          ${field('Sectors', (p.sectors || []).join(', '))}
          ${field('Salary expectation', p.salary_expectation ? '£' + Number(p.salary_expectation).toLocaleString() : '—')}
        </div>
      </div>
      <div class="card pad">
        <div class="section-title" style="font-size:15px">NHS profile</div>
        ${field('Staff group', p.nhs_preferences?.staff_group)}
        ${field('Registration', p.nhs_preferences?.registration)}
        ${field('Bands', (p.nhs_preferences?.bands || []).join(', '))}
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card pad">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div class="section-title" style="margin:0;font-size:15px">Work experience</div>
          <button class="btn sm" id="addExp">＋ Add</button>
        </div>
        <div id="expList">${(v.work_experiences || []).map(expRow).join('')}</div>
      </div>
      <div class="card pad">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div class="section-title" style="margin:0;font-size:15px">Skills & evidence</div>
          <button class="btn sm" id="addSkill">＋ Add</button>
        </div>
        <div id="skillList" class="tag-list">${(v.skills || []).map((s) => `<span class="kw have" title="${esc(s.category)} · ${esc(s.level)}">${esc(s.skill)}</span>`).join('')}</div>
      </div>
    </div>`;

  main.querySelector('#addExp').addEventListener('click', () => addExpModal());
  main.querySelector('#addSkill').addEventListener('click', () => addSkillModal());
}

function field(label, value) {
  return `<div><div class="dim" style="font-size:11px">${esc(label)}</div><div style="font-size:13px;margin-top:3px">${esc(value || '—')}</div></div>`;
}

function expRow(w) {
  return `<div class="list-row" style="align-items:flex-start">
    <div style="flex:1">
      <b style="font-size:13px">${esc(w.title)}</b> <span class="muted" style="font-size:12px">· ${esc(w.employer)}</span>
      <div class="dim" style="font-size:11px;margin-top:2px">${esc(w.start_date || '')} – ${esc(w.end_date || 'present')}</div>
      <div class="muted" style="font-size:12px;margin-top:5px">${esc((w.responsibilities || '').slice(0, 130))}${(w.responsibilities || '').length > 130 ? '…' : ''}</div>
    </div>
    ${badge(w.evidence_status || 'verified', w.evidence_status === 'verified' ? 'high' : 'mod')}
  </div>`;
}

function addExpModal() {
  const { root } = openModal(`
    <h2 style="font-family:var(--display);font-size:20px">Add work experience</h2>
    <p class="muted" style="font-size:12.5px;margin:6px 0 16px">Only add real, verifiable experience — this becomes evidence the AI can cite.</p>
    <div class="grid" style="gap:10px">
      <div class="grid cols-2" style="gap:10px"><input class="input" id="eTitle" placeholder="Job title" /><input class="input" id="eEmployer" placeholder="Employer" /></div>
      <div class="grid cols-2" style="gap:10px"><input class="input" id="eStart" placeholder="Start (YYYY-MM)" /><input class="input" id="eEnd" placeholder="End (YYYY-MM or blank)" /></div>
      <textarea class="input" id="eResp" placeholder="Responsibilities"></textarea>
      <textarea class="input" id="eAch" placeholder="Achievements (with real measures where possible)"></textarea>
      <button class="btn primary" id="eSave">Save to vault</button>
    </div>`);
  root.querySelector('#eSave').addEventListener('click', async () => {
    const body = {
      title: root.querySelector('#eTitle').value.trim(), employer: root.querySelector('#eEmployer').value.trim(),
      start_date: root.querySelector('#eStart').value.trim(), end_date: root.querySelector('#eEnd').value.trim(),
      responsibilities: root.querySelector('#eResp').value.trim(), achievements: root.querySelector('#eAch').value.trim(),
    };
    if (!body.title || !body.employer) { toast('Title and employer required', 'error'); return; }
    await api.addExperience(body);
    root.closest('.modal-bg').remove();
    toast('Added to vault', 'success');
    renderVault(document.getElementById('main'));
  });
}

function addSkillModal() {
  const { root } = openModal(`
    <h2 style="font-family:var(--display);font-size:20px">Add skill</h2>
    <div class="grid" style="gap:10px;margin-top:12px">
      <input class="input" id="sName" placeholder="Skill" />
      <div class="grid cols-2" style="gap:10px">
        <select class="select" id="sCat"><option>Clinical</option><option>Technical</option><option>Soft</option><option>Qualification</option><option>Domain</option></select>
        <select class="select" id="sLevel"><option>intermediate</option><option>advanced</option><option>expert</option></select>
      </div>
      <button class="btn primary" id="sSave">Save</button>
    </div>`);
  root.querySelector('#sSave').addEventListener('click', async () => {
    const skill = root.querySelector('#sName').value.trim();
    if (!skill) { toast('Enter a skill', 'error'); return; }
    await api.addSkill({ skill, category: root.querySelector('#sCat').value, level: root.querySelector('#sLevel').value });
    root.closest('.modal-bg').remove();
    toast('Skill added', 'success');
    renderVault(document.getElementById('main'));
  });
}
