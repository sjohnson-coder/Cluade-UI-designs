import { api } from '../api.js';
import { topbar, ring, meter, badge, esc, loading, toast } from '../ui.js';

export async function renderNHS(main, { param } = {}) {
  const jobsRes = await api.jobs({ nhs: 'true' });
  let nhsJobs = jobsRes.jobs;
  if (!nhsJobs.length) { // fall back to any job so the studio is explorable
    nhsJobs = (await api.jobs({ sort: 'fit' })).jobs.slice(0, 4);
  }
  let jobId = param || nhsJobs[0]?.id;

  main.innerHTML = topbar('NHS Studio', 'Score essential criteria first, then build supporting information in your own voice') + `
    <div class="card pad fade-in" style="margin-bottom:18px;display:flex;gap:14px;align-items:center;flex-wrap:wrap">
      <div style="flex:1;min-width:240px">
        <div class="dim" style="font-size:11px;margin-bottom:6px">NHS / values-based role</div>
        <select class="select" id="nhsJob" style="width:100%">
          ${nhsJobs.map((j) => `<option value="${j.id}" ${j.id === jobId ? 'selected' : ''}>${esc(j.title)} — ${esc(j.company)}${j.band ? ' · ' + j.band : ''}</option>`).join('')}
        </select>
      </div>
      <button class="btn primary" id="nhsRun" style="align-self:flex-end">▶ Build person-spec matrix</button>
    </div>
    <div id="nhsStage"><div class="notice info"><span>✚</span><span>Select a role and build the matrix. NHS shortlisting scores essential criteria first — the app follows the same order before drafting.</span></div></div>`;

  const run = () => buildMatrix(jobId);
  main.querySelector('#nhsJob').addEventListener('change', (e) => { jobId = e.target.value; });
  main.querySelector('#nhsRun').addEventListener('click', run);
  if (param) run();
}

async function buildMatrix(jobId) {
  const stage = document.getElementById('nhsStage');
  stage.innerHTML = loading('Mapping evidence to the person specification…');
  const { matrix, job } = await api.nhsMatrix({ jobId });
  stage.innerHTML = `
    <div class="grid cols-2 fade-in" style="margin-bottom:18px">
      <div class="card pad" style="display:flex;align-items:center;gap:16px">
        ${ring(matrix.essential_coverage)}
        <div><div style="font-weight:600">Essential criteria</div><div class="muted" style="font-size:12px">${matrix.essential.filter((e) => e.status === 'met').length}/${matrix.essential.length} evidenced</div></div>
      </div>
      <div class="card pad" style="display:flex;align-items:center;gap:16px">
        ${ring(matrix.desirable_coverage)}
        <div><div style="font-weight:600">Desirable criteria</div><div class="muted" style="font-size:12px">${matrix.desirable.filter((e) => e.status === 'met').length}/${matrix.desirable.length} evidenced</div></div>
      </div>
    </div>

    <div class="notice ${matrix.ready_to_draft ? 'safe' : 'warn'}" style="margin-bottom:18px"><span>${matrix.ready_to_draft ? '✓' : '⚠'}</span><span>${esc(matrix.guidance)}</span></div>

    <div class="card pad" style="margin-bottom:18px">
      <div class="section-title" style="font-size:15px">Person specification matrix</div>
      ${criteriaTable('Essential', matrix.essential)}
      ${matrix.desirable.length ? criteriaTable('Desirable', matrix.desirable) : ''}
    </div>

    <div style="text-align:right"><button class="btn primary" id="genStatement">✎ Generate supporting statement</button></div>
    <div id="stmtOut" style="margin-top:18px"></div>`;

  document.getElementById('genStatement').addEventListener('click', () => genStatement(jobId));
}

function criteriaTable(kind, rows) {
  return `<div style="margin-top:6px"><div class="dim" style="font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:14px 0 8px">${kind}</div>
    ${rows.map((r) => `
      <div class="list-row" style="align-items:flex-start">
        <span style="font-size:16px;margin-top:1px">${r.status === 'met' ? '✅' : '⭕'}</span>
        <div style="flex:1">
          <b style="font-size:13px">${esc(r.criterion)}</b>
          <div class="muted" style="font-size:12px;margin-top:3px">${r.status === 'met' ? esc(r.evidence || 'Evidenced in your vault.') : esc(r.gap_prompt)}</div>
        </div>
        ${badge(r.status === 'met' ? 'Met' : 'Gap', r.status === 'met' ? 'high' : 'low')}
      </div>`).join('')}</div>`;
}

async function genStatement(jobId) {
  const out = document.getElementById('stmtOut');
  out.innerHTML = loading('Drafting supporting information in your voice…');
  const { statement } = await api.nhsStatement({ jobId });
  const text = statement.sections.map((s) => `${s.heading.toUpperCase()}\n${s.body}`).join('\n\n');
  out.innerHTML = `<div class="card pad fade-in">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
      <div class="section-title" style="margin:0;font-size:15px">Supporting information draft</div>
      <div class="strip">${badge(statement.word_count + ' words', 'info')}<button class="btn sm" id="copyStmt">⧉ Copy</button></div>
    </div>
    ${statement.flags?.length ? `<div class="notice warn" style="margin-bottom:14px"><span>⚠</span><span>${statement.flags.map(esc).join(' · ')}</span></div>` : ''}
    ${statement.sections.map((s) => `<div style="margin-bottom:16px">
      <div style="font-weight:650;font-size:13px;color:var(--cyan);margin-bottom:6px">${esc(s.heading)}</div>
      <div style="font-size:13px;line-height:1.65;white-space:pre-wrap" class="muted">${esc(s.body)}</div></div>`).join('')}
    <div class="notice safe"><span>🛡</span><span>${esc(statement.guardrail)}</span></div>
  </div>`;
  document.getElementById('copyStmt').addEventListener('click', () => { navigator.clipboard?.writeText(text); toast('Copied to clipboard', 'success'); });
}
