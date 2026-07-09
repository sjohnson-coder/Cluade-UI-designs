import { api } from '../api.js';
import { topbar, ring, meter, badge, esc, kwList, loading, toast } from '../ui.js';

const S = { jobId: null, cvText: '', step: 'scanner', results: {} };
const STEPS = [
  { id: 'scanner', n: 'Step 1', t: 'Scanner', s: 'Diagnose the gap' },
  { id: 'surgeon', n: 'Step 2', t: 'Surgeon', s: 'Rewrite with XYZ' },
  { id: 'stress', n: 'Step 3', t: 'Stress Test', s: 'ATS + 7-second scan' },
  { id: 'spar', n: 'Step 4', t: 'Sparring Partner', s: 'Interview readiness' },
];

export async function renderCVStudio(main, { param } = {}) {
  const jobsRes = await api.jobs({ sort: 'fit' });
  const jobs = jobsRes.jobs;
  if (param) S.jobId = param;
  if (!S.jobId) S.jobId = jobs[0]?.id;

  main.innerHTML = topbar('CV Studio', 'A repeatable Scanner → Surgeon → Stress Test loop for every application') + `
    <div class="card pad fade-in" style="margin-bottom:18px">
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <div style="flex:1;min-width:220px">
          <div class="dim" style="font-size:11px;margin-bottom:6px">Target role</div>
          <select class="select" id="cvJob" style="width:100%">
            ${jobs.map((j) => `<option value="${j.id}" ${j.id === S.jobId ? 'selected' : ''}>${esc(j.title)} — ${esc(j.company)}</option>`).join('')}
          </select>
        </div>
        <div style="flex:2;min-width:260px">
          <div class="dim" style="font-size:11px;margin-bottom:6px">Your CV text <span class="muted">(leave blank to use your Career Vault)</span></div>
          <textarea class="input" id="cvText" placeholder="Paste your current CV here, or leave blank to build from your vault…" style="min-height:70px">${esc(S.cvText)}</textarea>
        </div>
      </div>
    </div>

    <div class="steps" id="cvSteps">
      ${STEPS.map((st) => `<div class="step ${st.id === S.step ? 'active' : ''} ${S.results[st.id] ? 'done' : ''}" data-step="${st.id}">
        <div class="n">${st.n}</div><div class="t">${st.t}</div><div class="s">${st.s}</div></div>`).join('')}
    </div>

    <div id="cvStage"></div>`;

  main.querySelector('#cvJob').addEventListener('change', (e) => { S.jobId = e.target.value; S.results = {}; renderStage(); });
  main.querySelector('#cvText').addEventListener('input', (e) => { S.cvText = e.target.value; });
  main.querySelectorAll('[data-step]').forEach((n) => n.addEventListener('click', () => { S.step = n.dataset.step; syncSteps(); renderStage(); }));
  renderStage();
}

function syncSteps() {
  document.querySelectorAll('#cvSteps .step').forEach((n) => {
    n.classList.toggle('active', n.dataset.step === S.step);
    n.classList.toggle('done', !!S.results[n.dataset.step]);
  });
}

function renderStage() {
  const stage = document.getElementById('cvStage');
  if (!stage) return;
  const st = STEPS.find((x) => x.id === S.step);
  if (S.step === 'spar') {
    stage.innerHTML = `<div class="card pad fade-in" style="text-align:center;padding:40px">
      <div style="font-size:40px">◍</div>
      <h3 style="margin:12px 0 6px">Sparring Partner lives in the Interview Coach</h3>
      <p class="muted" style="max-width:440px;margin:0 auto 16px">Once your CV is stress-tested, move into role-specific technical, behavioural and curveball questions with scored, rewritten answers.</p>
      <a class="btn primary" href="#interview/${S.jobId}">Open Interview Coach →</a></div>`;
    return;
  }
  const existing = S.results[S.step];
  stage.innerHTML = `<div class="card pad fade-in">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div class="section-title" style="margin:0">${st.t}</div>
      <button class="btn primary" id="runStep">${existing ? '↻ Re-run' : '▶ Run ' + st.t}</button>
    </div>
    <div id="stepOut">${existing ? renderResult(S.step, existing) : `<p class="muted" style="font-size:13px">${stepIntro(S.step)}</p>`}</div>
  </div>`;
  document.getElementById('runStep').addEventListener('click', runStep);
}

function stepIntro(step) {
  return {
    scanner: 'Acts as a senior recruiter: scores your CV against this job, groups missing keywords, and lists the biggest red flags — with the reasons behind the score.',
    surgeon: 'Rewrites your experience bullets using the Google XYZ formula (Accomplished X, measured by Y, by doing Z). No metrics are invented — anything unverified is flagged for you to confirm.',
    stress: 'Re-checks the CV as an ATS parser, then as a hiring manager with 7 seconds per CV — telling you what still gets skipped.',
  }[step];
}

async function runStep() {
  const out = document.getElementById('stepOut');
  out.innerHTML = loading('Running ' + STEPS.find((s) => s.id === S.step).t + '…');
  const body = { jobId: S.jobId, cvText: S.cvText || undefined };
  try {
    let res;
    if (S.step === 'scanner') res = await api.cvScan(body);
    else if (S.step === 'surgeon') res = await api.cvSurgeon(body);
    else res = await api.cvStress(body);
    S.results[S.step] = res;
    out.innerHTML = renderResult(S.step, res);
    syncSteps();
    toast(STEPS.find((s) => s.id === S.step).t + ' complete', 'success');
  } catch (e) { out.innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`; }
}

function renderResult(step, r) {
  if (step === 'scanner') return scannerResult(r);
  if (step === 'surgeon') return surgeonResult(r);
  return stressResult(r);
}

function scannerResult(r) {
  const g = r.missing_keywords_grouped || {};
  return `
    <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;margin-bottom:18px">
      ${ring(r.match_score)}
      <div style="flex:1;min-width:200px">
        <div style="font-weight:600">Recruiter match score</div>
        <p class="muted" style="font-size:12.5px;margin-top:4px">${esc(r.recruiter_notes)}</p>
        <div style="margin-top:10px">${meter(r.keyword_coverage, 'cyan')}<div class="dim" style="font-size:11px;margin-top:5px">${r.keyword_coverage}% keyword coverage</div></div>
      </div>
    </div>
    ${r.ai_summary?.text ? `<div class="notice info" style="margin-bottom:14px"><span>🤖</span><span>${esc(r.ai_summary.text)}</span></div>` : ''}
    <div class="grid cols-2" style="margin-bottom:14px">
      <div><div class="dim" style="font-size:11px;margin-bottom:6px">✓ Present</div>${kwList(r.present_keywords.slice(0, 10), 'have')}</div>
      <div><div class="dim" style="font-size:11px;margin-bottom:6px">✕ Missing</div>${kwList(r.missing_keywords, 'miss')}</div>
    </div>
    ${r.red_flags.length ? `<div class="card pad" style="background:rgba(251,113,133,0.06)"><div class="section-title" style="font-size:14px;color:#fda4af">⚑ Red flags</div>
      ${r.red_flags.map((f) => `<div style="font-size:12.5px;margin-bottom:6px;display:flex;gap:8px"><span>•</span><span class="muted">${esc(f)}</span></div>`).join('')}</div>` : '<div class="notice safe"><span>✓</span><span>No major red flags detected.</span></div>'}
    <div style="text-align:right;margin-top:16px"><button class="btn primary" onclick="location.hash='#cv/${S.jobId}';document.querySelector('[data-step=surgeon]').click()">Next: Surgeon →</button></div>`;
}

function surgeonResult(r) {
  return `
    <div class="notice info" style="margin-bottom:16px"><span>✎</span><span>Formula: <b>${esc(r.formula)}</b>. ${esc(r.guardrail)}</span></div>
    ${r.rewrites.map((rw) => `
      <div style="margin-bottom:16px">
        <div class="diff">
          <div class="before"><h5>Before</h5>${esc(rw.original)}</div>
          <div class="after"><h5>After</h5>${esc(rw.rewritten)}</div>
        </div>
        <div class="strip" style="margin-top:8px">
          ${rw.added_keyword ? badge('＋ ' + rw.added_keyword, 'cyan') : ''}
          ${badge(rw.confidence_tag, rw.needs_confirmation ? 'mod' : 'high')}
          ${rw.needs_confirmation ? `<span class="dim" style="font-size:11.5px;align-self:center">${esc(rw.note)}</span>` : ''}
        </div>
      </div>`).join('')}
    <hr class="hr" />
    <div class="grid cols-2">
      <div><div class="dim" style="font-size:11px;margin-bottom:6px">Woven in</div>${kwList(r.keywords_woven_in, 'have')}</div>
      <div><div class="dim" style="font-size:11px;margin-bottom:6px">Still to add</div>${kwList(r.keywords_still_missing, 'miss')}</div>
    </div>
    <div style="text-align:right;margin-top:16px"><button class="btn primary" onclick="document.querySelector('[data-step=stress]').click()">Next: Stress Test →</button></div>`;
}

function stressResult(r) {
  return `
    <div class="grid cols-2" style="margin-bottom:18px">
      <div class="card pad" style="text-align:center">${ring(r.ats_score)}<div style="font-weight:600;margin-top:10px">ATS parser score</div></div>
      <div class="card pad" style="text-align:center">${ring(r.match_score)}<div style="font-weight:600;margin-top:10px">Recruiter match</div></div>
    </div>
    <div class="card pad" style="margin-bottom:14px">
      <div class="section-title" style="font-size:14px">ATS checks</div>
      ${r.ats_checks.map((c) => `<div class="list-row"><span style="font-size:16px">${c.pass ? '✅' : '⚠️'}</span>
        <div style="flex:1"><b style="font-size:13px">${esc(c.name)}</b><div class="muted" style="font-size:12px">${esc(c.detail)}</div></div>
        ${badge(c.pass ? 'Pass' : 'Review', c.pass ? 'high' : 'mod')}</div>`).join('')}
    </div>
    <div class="notice ${/does not/.test(r.hiring_manager_first_impression) ? 'warn' : 'safe'}" style="margin-bottom:14px"><span>👁</span><span><b>7-second scan:</b> ${esc(r.hiring_manager_first_impression)}</span></div>
    <div class="card pad" style="margin-bottom:14px">
      <div class="section-title" style="font-size:14px">What still gets skipped</div>
      ${r.still_gets_skipped.map((x) => `<div style="font-size:12.5px;margin-bottom:6px;display:flex;gap:8px"><span>•</span><span class="muted">${esc(x)}</span></div>`).join('')}
    </div>
    <div class="card pad">
      <div class="section-title" style="font-size:14px">Final recommendations</div>
      ${r.final_recommendations.map((x) => `<div style="font-size:12.5px;margin-bottom:6px;display:flex;gap:8px"><span>→</span><span>${esc(x)}</span></div>`).join('')}
    </div>
    <div style="text-align:right;margin-top:16px"><button class="btn cyan" onclick="location.hash='#interview/${S.jobId}'">Next: Sparring Partner →</button></div>`;
}
