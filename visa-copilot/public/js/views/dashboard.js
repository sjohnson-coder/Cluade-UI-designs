import { api } from '../api.js';
import { topbar, ring, meter, badge, money, daysLeft, confidenceBadge, esc } from '../ui.js';

export async function renderDashboard(main) {
  main.innerHTML = topbar('Dashboard', 'Your visa-sponsorship application command centre') +
    '<div class="center"><div class="spinner"></div></div>';

  const [jobsRes, appsRes] = await Promise.all([api.jobs({ sort: 'fit' }), api.applications()]);
  const jobs = jobsRes.jobs;
  const apps = appsRes.applications;

  const recommended = jobs.filter((j) => j.score.risk_signals.length === 0).slice(0, 3);
  const urgent = jobs
    .map((j) => ({ ...j, dl: daysLeft(j.closing_date) }))
    .filter((j) => j.dl != null && j.dl <= 10 && j.dl >= 0)
    .sort((a, b) => a.dl - b.dl).slice(0, 4);

  const applied = apps.filter((a) => ['Applied', 'Interview', 'Offer'].includes(a.status)).length;
  const interviews = apps.filter((a) => a.status === 'Interview').length;
  const avgSponsor = Math.round(jobs.reduce((s, j) => s + j.score.sponsor_confidence, 0) / (jobs.length || 1));

  const stats = [
    { label: 'Sponsor-friendly roles', ic: '🛂', grad: 'var(--grad-primary)', value: jobs.filter((j) => j.score.sponsor_confidence >= 45 && !j.score.risk_signals.length).length, sub: `of ${jobs.length} scanned` },
    { label: 'Applications live', ic: '📮', grad: 'var(--grad-cyan)', value: apps.length, sub: `${applied} submitted` },
    { label: 'Interviews', ic: '🎯', grad: 'var(--grad-emerald)', value: interviews, sub: 'stage reached' },
    { label: 'Avg sponsor confidence', ic: '📊', grad: 'var(--grad-amber)', value: avgSponsor + '%', sub: 'across your matches' },
  ];

  main.innerHTML = topbar('Dashboard', `Welcome back, ${esc(main.__name || 'Amara')} — here's where things stand`,
    `<a class="btn primary" href="#scout">＋ Find sponsor jobs</a>`) + `
    <div class="grid cols-4" style="margin-bottom:18px">
      ${stats.map((s) => `
        <div class="card stat hover fade-in">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div class="label">${s.label}</div>
            <div class="chip-ic" style="background:${s.grad}">${s.ic}</div>
          </div>
          <div class="value">${s.value}</div>
          <div class="sub">${s.sub}</div>
        </div>`).join('')}
    </div>

    <div class="grid cols-3">
      <div class="card pad span-2 fade-in">
        <div class="section-title">✦ Recommended for you</div>
        ${recommended.map((j) => `
          <div class="list-row">
            ${ring(j.score.fit_score, 'fit')}
            <div style="flex:1;min-width:0">
              <div style="font-weight:600;font-size:14px">${esc(j.title)}</div>
              <div class="muted" style="font-size:12px;margin-top:2px">${esc(j.company)} · ${esc(j.location)} · ${money(j.salary_min, j.salary_max, j.currency)}</div>
              <div class="strip" style="margin-top:8px">
                ${confidenceBadge(j.score.sponsor_confidence, j.score.confidence_band)}
                ${j.score.sponsor_matched ? badge('Licensed sponsor ✓', 'cyan') : ''}
                ${badge(j.score.recommended_action, 'info')}
              </div>
            </div>
            <a class="btn sm" href="#scout/${j.id}">View</a>
          </div>`).join('') || '<p class="muted">No matches yet.</p>'}
      </div>

      <div class="card pad fade-in">
        <div class="section-title">⏳ Closing soon</div>
        ${urgent.map((j) => `
          <div class="list-row" style="align-items:flex-start">
            <div style="width:44px;text-align:center">
              <div style="font-family:var(--display);font-size:20px;font-weight:700;color:${j.dl <= 3 ? 'var(--rose)' : 'var(--amber)'}">${j.dl}</div>
              <div class="dim" style="font-size:9px">days</div>
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-weight:600;font-size:13px;line-height:1.3">${esc(j.title)}</div>
              <div class="muted" style="font-size:11.5px">${esc(j.company)}</div>
            </div>
          </div>`).join('') || '<p class="muted">Nothing urgent.</p>'}
      </div>
    </div>

    <div class="grid cols-2" style="margin-top:18px">
      <div class="card pad fade-in">
        <div class="section-title">◷ Pipeline overview</div>
        ${pipeline(apps)}
      </div>
      <div class="card pad fade-in">
        <div class="section-title">🛡 Trust & safety</div>
        <div class="notice info" style="margin-bottom:10px"><span>ℹ</span><span>Every AI change and application is logged and requires your approval before use. Sponsor matches are indicative, not a guarantee.</span></div>
        <div class="list-row"><span style="font-size:18px">✓</span><div style="flex:1"><b style="font-size:13px">Evidence-only tailoring</b><div class="muted" style="font-size:12px">CV claims are checked against your Career Vault.</div></div></div>
        <div class="list-row"><span style="font-size:18px">✓</span><div style="flex:1"><b style="font-size:13px">Human approval before submit</b><div class="muted" style="font-size:12px">Nothing is submitted automatically.</div></div></div>
        <div class="list-row"><span style="font-size:18px">✓</span><div style="flex:1"><b style="font-size:13px">ATS-safe formatting</b><div class="muted" style="font-size:12px">Parser preview on every export.</div></div></div>
      </div>
    </div>`;
}

function pipeline(apps) {
  const stages = ['Saved', 'Drafting', 'Ready', 'Applied', 'Interview', 'Offer'];
  const counts = Object.fromEntries(stages.map((s) => [s, apps.filter((a) => a.status === s).length]));
  const max = Math.max(1, ...Object.values(counts));
  return stages.map((s) => `
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:11px">
      <div style="width:74px;font-size:12px" class="muted">${s}</div>
      <div style="flex:1">${meter((counts[s] / max) * 100, ['Offer', 'Interview'].includes(s) ? 'emerald' : ['Applied'].includes(s) ? 'cyan' : '')}</div>
      <div style="width:22px;text-align:right;font-weight:600;font-size:13px">${counts[s]}</div>
    </div>`).join('');
}
