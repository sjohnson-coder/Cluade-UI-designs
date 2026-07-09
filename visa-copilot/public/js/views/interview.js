import { api } from '../api.js';
import { topbar, ring, badge, esc, loading, toast } from '../ui.js';

export async function renderInterview(main, { param } = {}) {
  const jobs = (await api.jobs({ sort: 'fit' })).jobs;
  let jobId = param || jobs[0]?.id;

  main.innerHTML = topbar('Interview Coach', 'Role-specific technical, behavioural and curveball questions — scored and rewritten') + `
    <div class="card pad fade-in" style="margin-bottom:18px;display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap">
      <div style="flex:1;min-width:240px">
        <div class="dim" style="font-size:11px;margin-bottom:6px">Prepare for</div>
        <select class="select" id="ivJob" style="width:100%">
          ${jobs.map((j) => `<option value="${j.id}" ${j.id === jobId ? 'selected' : ''}>${esc(j.title)} — ${esc(j.company)}</option>`).join('')}
        </select>
      </div>
      <button class="btn primary" id="ivGen">▶ Generate question set</button>
    </div>
    <div id="ivStage"><div class="notice info"><span>◍</span><span>Generate a set, then answer each question. Answers are scored 0–10 on STAR structure, specificity and relevance — anything under 9 gets a structured rewrite (from your real experience only).</span></div></div>`;

  const gen = () => genQuestions(jobId);
  main.querySelector('#ivJob').addEventListener('change', (e) => { jobId = e.target.value; });
  main.querySelector('#ivGen').addEventListener('click', gen);
  if (param) gen();
}

async function genQuestions(jobId) {
  const stage = document.getElementById('ivStage');
  stage.innerHTML = loading('Building role-specific questions…');
  const { questions } = await api.interviewQuestions({ jobId });
  stage.innerHTML = `<div class="fade-in">${questions.map((q, i) => card(q, i, jobId)).join('')}</div>`;
  stage.querySelectorAll('[data-score]').forEach((btn) => btn.addEventListener('click', () => scoreOne(btn.dataset.qid, jobId)));
}

function card(q, i, jobId) {
  const typeCls = q.type === 'technical' ? 'cyan' : q.type === 'behavioural' ? 'info' : 'mod';
  return `<div class="card pad" style="margin-bottom:14px" data-card="${q.id}">
    <div class="strip" style="margin-bottom:10px">${badge('Q' + (i + 1), 'ghost')}${badge(q.type, typeCls)}</div>
    <div style="font-weight:600;font-size:14.5px;line-height:1.4;margin-bottom:12px">${esc(q.question)}</div>
    <textarea class="input" id="ans-${q.id}" placeholder="Type your answer using STAR — Situation, Task, Action, Result…"></textarea>
    <div style="display:flex;justify-content:flex-end;margin-top:10px"><button class="btn primary sm" data-score data-qid="${q.id}">Rate my answer</button></div>
    <div id="fb-${q.id}"></div>
  </div>`;
}

async function scoreOne(qid, jobId) {
  const answer = document.getElementById('ans-' + qid).value.trim();
  const question = document.querySelector(`[data-card="${qid}"] div[style*="font-weight:600"]`)?.textContent || '';
  const fb = document.getElementById('fb-' + qid);
  if (!answer) { toast('Write an answer first', 'error'); return; }
  fb.innerHTML = loading('Scoring…');
  const r = await api.interviewScore({ question, answer, jobId });
  fb.innerHTML = `<div style="margin-top:14px;display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
    ${ring(r.score * 10, '/100')}
    <div style="flex:1;min-width:220px">
      <div style="font-weight:600">${r.score}/10 ${r.needs_rewrite ? '· improve to reach 9+' : '· strong answer ✓'}</div>
      ${r.gaps.length ? `<div class="muted" style="font-size:12.5px;margin-top:6px">To lift the score: ${r.gaps.map(esc).join('; ')}.</div>` : ''}
      ${r.suggested_rewrite ? `<div class="card pad" style="margin-top:12px;background:rgba(52,211,153,0.06)">
        <div class="dim" style="font-size:11px;margin-bottom:6px">Suggested STAR structure</div>
        <div style="font-size:13px;line-height:1.6;white-space:pre-wrap">${esc(r.suggested_rewrite)}</div></div>` : ''}
    </div>
  </div>`;
}
