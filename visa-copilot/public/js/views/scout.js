import { api } from '../api.js';
import { topbar, ring, badge, money, confidenceBadge, esc, daysLeft, openModal, toast, meter, kwList, loading } from '../ui.js';

const filters = { q: '', sector: '', sort: 'fit', visaOnly: false, sponsorOnly: false, nhs: false, minFit: '', exclude: '' };

export async function renderScout(main, { param } = {}) {
  main.innerHTML = topbar('Job Scout', 'Sponsor-verified roles ranked by fit and visa confidence',
    `<a class="btn" href="#" id="addJobBtn">＋ Add job by URL</a>`) + `
    <div class="filters" id="filterBar">
      <input class="input search" id="fq" placeholder="🔍 Search title, company, keyword…" value="${esc(filters.q)}" />
      <select class="select" id="fsector">
        <option value="">All sectors</option>
        ${['Healthcare', 'Care', 'Technology', 'Engineering', 'Business', 'Education'].map((s) => `<option ${filters.sector === s ? 'selected' : ''}>${s}</option>`).join('')}
      </select>
      <select class="select" id="fsort">
        <option value="fit" ${filters.sort === 'fit' ? 'selected' : ''}>Sort: Best fit</option>
        <option value="sponsor" ${filters.sort === 'sponsor' ? 'selected' : ''}>Sort: Sponsor confidence</option>
        <option value="closing" ${filters.sort === 'closing' ? 'selected' : ''}>Sort: Closing soon</option>
        <option value="salary" ${filters.sort === 'salary' ? 'selected' : ''}>Sort: Salary</option>
      </select>
      <label class="toggle"><input type="checkbox" id="fvisa" ${filters.visaOnly ? 'checked' : ''} /> Sponsor-friendly only</label>
      <label class="toggle"><input type="checkbox" id="fsponsor" ${filters.sponsorOnly ? 'checked' : ''} /> Licensed sponsor</label>
      <label class="toggle"><input type="checkbox" id="fnhs" ${filters.nhs ? 'checked' : ''} /> NHS only</label>
    </div>
    <div id="jobGrid"><div class="center"><div class="spinner"></div></div></div>`;

  wireFilters(main);
  await loadGrid();
  document.getElementById('addJobBtn').addEventListener('click', (e) => { e.preventDefault(); addJobModal(loadGrid); });

  if (param) openJobDetail(param);
}

function wireFilters(main) {
  const bind = (id, key, ev = 'change', val = (e) => e.target.value) => {
    const node = main.querySelector('#' + id);
    node.addEventListener(ev, (e) => { filters[key] = val(e); loadGrid(); });
  };
  main.querySelector('#fq').addEventListener('input', debounce((e) => { filters.q = e.target.value; loadGrid(); }, 300));
  bind('fsector', 'sector');
  bind('fsort', 'sort');
  bind('fvisa', 'visaOnly', 'change', (e) => e.target.checked);
  bind('fsponsor', 'sponsorOnly', 'change', (e) => e.target.checked);
  bind('fnhs', 'nhs', 'change', (e) => e.target.checked);
}

async function loadGrid() {
  const grid = document.getElementById('jobGrid');
  if (!grid) return;
  const params = { q: filters.q, sort: filters.sort };
  if (filters.sector) params.sector = filters.sector;
  if (filters.visaOnly) params.visaOnly = 'true';
  if (filters.sponsorOnly) params.sponsorOnly = 'true';
  if (filters.nhs) params.nhs = 'true';
  const res = await api.jobs(params);
  grid.innerHTML = `<div class="muted" style="font-size:12.5px;margin-bottom:14px">${res.count} role${res.count === 1 ? '' : 's'} matched</div>
    <div class="grid cols-2">${res.jobs.map(jobCard).join('') || emptyState()}</div>`;
  grid.querySelectorAll('[data-job]').forEach((n) => n.addEventListener('click', (e) => {
    if (e.target.closest('[data-act]')) return;
    openJobDetail(n.dataset.job);
  }));
  grid.querySelectorAll('[data-act]').forEach((n) => n.addEventListener('click', (e) => {
    e.stopPropagation();
    handleAction(n.dataset.act, n.dataset.job, n);
  }));
}

function jobCard(j) {
  const s = j.score;
  const dl = daysLeft(j.closing_date);
  const risk = s.risk_signals.length > 0;
  return `<div class="card job-card hover fade-in" data-job="${j.id}" style="cursor:pointer">
    <div class="job-head">
      <div style="min-width:0">
        <div class="strip" style="margin-bottom:8px">
          ${badge(j.source, 'ghost')}
          ${dl != null && dl <= 7 && dl >= 0 ? badge(`Closes in ${dl}d`, dl <= 3 ? 'low' : 'mod') : ''}
          ${j.nhs ? badge('NHS', 'info') : ''}
        </div>
        <h3>${esc(j.title)}</h3>
        <div class="job-meta"><span>🏢 ${esc(j.company)}</span><span>📍 ${esc(j.location)}</span><span>💷 ${money(j.salary_min, j.salary_max, j.currency)}</span></div>
      </div>
      ${ring(s.fit_score, 'fit')}
    </div>

    <div class="strip">
      ${confidenceBadge(s.sponsor_confidence, s.confidence_band)}
      ${s.sponsor_matched ? badge('Licensed sponsor ✓', 'cyan') : badge('Not on register', 'ghost')}
      ${badge(`Salary risk: ${s.salary_risk}`, s.salary_risk === 'High' ? 'low' : s.salary_risk === 'Moderate' ? 'mod' : 'high')}
    </div>

    ${risk ? `<div class="notice warn" style="padding:9px 12px;font-size:11.5px"><span>⚠</span><span>${esc(s.risk_signals[0])}</span></div>` : ''}

    ${s.missing_keywords_json.length ? `<div><div class="dim" style="font-size:11px;margin-bottom:6px">Missing keywords</div>${kwList(s.missing_keywords_json.slice(0, 5), 'miss')}</div>` : ''}

    <div class="job-actions">
      <button class="btn primary sm" data-act="tailor" data-job="${j.id}">✎ Tailor CV</button>
      ${j.nhs ? `<button class="btn sm" data-act="nhs" data-job="${j.id}">✚ NHS Statement</button>` : ''}
      <button class="btn sm" data-act="save" data-job="${j.id}">☆ Save</button>
      <button class="btn sm" data-act="apply" data-job="${j.id}">📮 Apply</button>
    </div>
  </div>`;
}

function emptyState() {
  return `<div class="card pad" style="grid-column:1/-1;text-align:center;padding:50px"><div style="font-size:40px">🔍</div>
    <h3 style="margin:12px 0 6px">No roles match these filters</h3><p class="muted">Try widening your search or removing a filter.</p></div>`;
}

async function handleAction(act, jobId, node) {
  if (act === 'save') {
    await api.saveApplication({ job_id: jobId, status: 'Saved' });
    toast('Saved to your tracker', 'success');
    node.textContent = '✓ Saved'; node.disabled = true;
  } else if (act === 'apply') {
    await api.saveApplication({ job_id: jobId, status: 'Drafting' });
    location.hash = '#cockpit/' + jobId;
  } else if (act === 'tailor') {
    location.hash = '#cv/' + jobId;
  } else if (act === 'nhs') {
    location.hash = '#nhs/' + jobId;
  }
}

export async function openJobDetail(jobId) {
  const { root } = openModal(loading('Loading role & sponsor record…'), { wide: true });
  let j;
  try { j = await api.job(jobId); } catch { root.innerHTML = '<p class="muted">Could not load this role.</p>'; return; }
  const s = j.score;
  root.innerHTML = `
    <div class="strip" style="margin-bottom:10px">${badge(j.source, 'ghost')} ${j.nhs ? badge('NHS · ' + (j.band || ''), 'info') : ''} ${badge(j.sector, 'ghost')}</div>
    <h2 style="font-family:var(--display);font-size:22px;letter-spacing:-0.5px">${esc(j.title)}</h2>
    <div class="muted" style="margin:6px 0 16px">🏢 ${esc(j.company)} · 📍 ${esc(j.location)} · 💷 ${money(j.salary_min, j.salary_max, j.currency)}</div>

    <div class="grid cols-3" style="margin-bottom:18px">
      ${scoreTile('Fit score', s.fit_score, 'How well your vault matches this role')}
      ${scoreTile('Sponsor confidence', s.sponsor_confidence, s.confidence_band + ' likelihood')}
      ${scoreTile('Salary vs route', s.salary_risk === 'High' ? 25 : s.salary_risk === 'Moderate' ? 60 : 92, s.salary_risk + ' risk')}
    </div>

    <div class="card pad" style="margin-bottom:14px;background:var(--glass)">
      <div class="section-title" style="font-size:14px">🛂 Why this recommendation</div>
      ${s.reasons.map((r) => `<div style="font-size:12.5px;margin-bottom:6px;display:flex;gap:8px"><span>${r.startsWith('⚠') ? '⚠' : '•'}</span><span class="muted">${esc(r.replace('⚠ ', ''))}</span></div>`).join('')}
      <div class="notice info" style="margin-top:10px"><span>ℹ</span><span>${esc(s.disclaimer)}</span></div>
    </div>

    ${s.missing_essential?.length ? `<div class="card pad" style="margin-bottom:14px"><div class="section-title" style="font-size:14px">Missing essential criteria</div>${kwList(s.missing_essential, 'miss')}</div>` : ''}

    <div class="grid cols-2" style="margin-bottom:16px">
      <div><div class="dim" style="font-size:11px;margin-bottom:6px">You already match</div>${kwList(s.matched_keywords, 'have')}</div>
      <div><div class="dim" style="font-size:11px;margin-bottom:6px">Missing keywords</div>${kwList(s.missing_keywords_json, 'miss')}</div>
    </div>

    <div class="card pad" style="margin-bottom:16px">
      <div class="section-title" style="font-size:14px">Job description</div>
      <p class="muted" style="font-size:13px;line-height:1.6">${esc(j.description)}</p>
    </div>

    <div class="notice info" style="margin-bottom:16px"><span>🔗</span><span>Source: ${esc(j.transparency.source)} · ${esc(j.transparency.data_freshness)} · Last checked ${new Date(j.transparency.last_checked).toLocaleString()}</span></div>

    <div class="job-actions">
      <a class="btn primary" href="#cv/${j.id}">✎ Tailor CV in Studio</a>
      ${j.nhs ? `<a class="btn" href="#nhs/${j.id}">✚ Build NHS statement</a>` : ''}
      <a class="btn" href="#interview/${j.id}">◍ Interview prep</a>
      <a class="btn cyan" href="#cockpit/${j.id}">📮 Application cockpit</a>
    </div>`;
  root.querySelectorAll('a[href^="#"]').forEach((a) => a.addEventListener('click', () => root.closest('.modal-bg').remove()));
}

function scoreTile(label, score, sub) {
  return `<div class="card pad" style="text-align:center">
    ${ring(score)}
    <div style="font-weight:600;font-size:13px;margin-top:10px">${label}</div>
    <div class="muted" style="font-size:11.5px;margin-top:2px">${sub}</div>
  </div>`;
}

function addJobModal(onDone) {
  const { root } = openModal(`
    <h2 style="font-family:var(--display);font-size:20px">Add a job by URL or paste</h2>
    <p class="muted" style="font-size:13px;margin:6px 0 16px">Paste a role from an employer career page. The scout will score sponsor confidence and fit.</p>
    <div class="grid" style="gap:12px">
      <input class="input" id="njTitle" placeholder="Job title *" />
      <input class="input" id="njCompany" placeholder="Company *" />
      <input class="input" id="njUrl" placeholder="Source URL" />
      <div class="grid cols-2" style="gap:10px">
        <input class="input" id="njLoc" placeholder="Location" />
        <input class="input" id="njSector" placeholder="Sector" />
      </div>
      <textarea class="input" id="njDesc" placeholder="Paste the job description here…"></textarea>
      <button class="btn primary" id="njSave">Score this role</button>
    </div>`);
  root.querySelector('#njSave').addEventListener('click', async () => {
    const body = {
      title: root.querySelector('#njTitle').value.trim(),
      company: root.querySelector('#njCompany').value.trim(),
      source_url: root.querySelector('#njUrl').value.trim(),
      location: root.querySelector('#njLoc').value.trim() || 'UK',
      sector: root.querySelector('#njSector').value.trim() || 'General',
      description: root.querySelector('#njDesc').value.trim(),
    };
    if (!body.title || !body.company) { toast('Title and company are required', 'error'); return; }
    try {
      const j = await api.addJob(body);
      root.closest('.modal-bg').remove();
      toast('Role scored and added', 'success');
      onDone();
      openJobDetail(j.id);
    } catch (e) { toast('Could not add job', 'error'); }
  });
}

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
