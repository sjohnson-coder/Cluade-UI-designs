import { api } from '../api.js';
import { topbar, badge, esc, toast } from '../ui.js';

const STAGE_COLOR = { Saved: 'ghost', Drafting: 'mod', Ready: 'cyan', Applied: 'info', Interview: 'high', Offer: 'high', Rejected: 'low', 'Follow-up': 'mod' };

export async function renderTracker(main) {
  main.innerHTML = topbar('Tracker', 'Your application pipeline — drag cards between stages') + '<div id="board"></div>';
  await draw();
}

async function draw() {
  const board = document.getElementById('board');
  const { stages, applications } = await api.applications();

  if (!applications.length) {
    board.innerHTML = `<div class="card pad fade-in" style="text-align:center;padding:56px">
      <div style="font-size:44px">▦</div><h3 style="margin:12px 0 6px">No applications yet</h3>
      <p class="muted" style="margin-bottom:16px">Save or apply to roles in the Job Scout and they'll appear here.</p>
      <a class="btn primary" href="#scout">Find sponsor jobs →</a></div>`;
    return;
  }

  const byStage = Object.fromEntries(stages.map((s) => [s, applications.filter((a) => a.status === s)]));
  const visible = stages.filter((s) => byStage[s].length || ['Saved', 'Drafting', 'Applied', 'Interview'].includes(s));

  board.innerHTML = `<div class="kanban fade-in">${visible.map((stage) => `
    <div class="kcol" data-stage="${stage}">
      <div class="khead"><span>${stage}</span><span class="kcount">${byStage[stage].length}</span></div>
      <div class="kdrop" data-stage="${stage}" style="min-height:60px">
        ${byStage[stage].map(appCard).join('')}
      </div>
    </div>`).join('')}</div>`;

  wireDnd(draw);
}

function appCard(a) {
  const j = a.job || {};
  return `<div class="card kcard" draggable="true" data-id="${a.id}">
    <h4>${esc(j.title || 'Role')}</h4>
    <p>${esc(j.company || '')}${j.location ? ' · ' + esc(j.location) : ''}</p>
    <div class="strip" style="margin-top:8px">${badge(a.method || 'Manual', 'ghost')}${a.applied_at ? badge('Applied', 'info') : ''}</div>
  </div>`;
}

function wireDnd(refresh) {
  let dragId = null;
  document.querySelectorAll('.kcard').forEach((c) => {
    c.addEventListener('dragstart', () => { dragId = c.dataset.id; c.style.opacity = '0.4'; });
    c.addEventListener('dragend', () => { c.style.opacity = '1'; });
  });
  document.querySelectorAll('.kdrop').forEach((col) => {
    col.addEventListener('dragover', (e) => { e.preventDefault(); col.closest('.kcol').classList.add('drop-active'); });
    col.addEventListener('dragleave', () => col.closest('.kcol').classList.remove('drop-active'));
    col.addEventListener('drop', async (e) => {
      e.preventDefault();
      col.closest('.kcol').classList.remove('drop-active');
      if (!dragId) return;
      const stage = col.dataset.stage;
      await api.updateApplication(dragId, { status: stage });
      toast('Moved to ' + stage, 'success');
      refresh();
    });
  });
}
