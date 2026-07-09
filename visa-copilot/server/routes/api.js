// REST API — maps directly onto the service modules from the scope
// (Auth/User, CV, Job Scout, Sponsor, NHS, AI Orchestrator, Application, Interview).
import { Router } from 'express';
import { table, find, filter, insert, update, remove, audit } from '../db.js';
import { scoreJobForProfile } from '../services/scoring.js';
import { visaConfidence } from '../services/sponsor.js';
import * as ai from '../ai/orchestrator.js';
import { keywords } from '../services/text.js';

const router = Router();
const DEMO_USER = 'demo-user';

// Helpers -------------------------------------------------------------------
function currentUser() {
  return find('users', (u) => u.id === DEMO_USER) || find('users', () => true);
}
function currentProfile() {
  const u = currentUser();
  return find('career_profiles', (p) => p.user_id === u?.id);
}
function vaultContext() {
  const profile = currentProfile();
  return {
    profile,
    skills: filter('skills', (s) => s.profile_id === profile?.id),
    work: filter('work_experiences', (w) => w.profile_id === profile?.id),
    sponsors: table('sponsor_records'),
  };
}
function jobWithScore(job) {
  const ctx = vaultContext();
  let score = find('job_scores', (s) => s.job_id === job.id && s.user_id === (currentUser()?.id));
  if (!score) {
    score = scoreJobForProfile(job, ctx);
  }
  return { ...job, score };
}

// --- Status / provider ------------------------------------------------------
router.get('/status', (req, res) => {
  res.json({
    ok: true,
    ai: ai.providerStatus(),
    counts: {
      jobs: table('jobs').length,
      sponsors: table('sponsor_records').length,
      applications: table('applications').length,
    },
  });
});

// --- Auth / User (demo single-user; structure ready for real auth) ----------
router.get('/me', (req, res) => {
  const user = currentUser();
  const profile = currentProfile();
  res.json({ user, profile });
});

router.get('/vault', (req, res) => {
  const ctx = vaultContext();
  res.json({
    profile: ctx.profile,
    skills: ctx.skills,
    work_experiences: ctx.work,
    documents: filter('documents', (d) => d.user_id === currentUser()?.id),
  });
});

router.post('/vault/experience', (req, res) => {
  const profile = currentProfile();
  const row = insert('work_experiences', { profile_id: profile.id, evidence_status: 'user-confirmed', ...req.body });
  audit({ action: 'vault.add_experience', entity_type: 'work_experiences', entity_id: row.id, user_id: currentUser()?.id });
  res.status(201).json(row);
});

router.post('/vault/skill', (req, res) => {
  const profile = currentProfile();
  const row = insert('skills', { profile_id: profile.id, evidence_source: 'user-confirmed', ...req.body });
  res.status(201).json(row);
});

// --- Sponsors ---------------------------------------------------------------
router.get('/sponsors', (req, res) => {
  const q = (req.query.q || '').toLowerCase();
  let rows = table('sponsor_records');
  if (q) rows = rows.filter((s) => s.organisation_name.toLowerCase().includes(q));
  res.json({ sponsors: rows });
});

router.get('/sponsors/verify', (req, res) => {
  const { company = '', description = '' } = req.query;
  res.json(visaConfidence({ company, description, sponsors: table('sponsor_records') }));
});

// --- Job Scout --------------------------------------------------------------
router.get('/jobs', (req, res) => {
  const {
    q, sector, visaOnly, sponsorOnly, nhs, remote, minFit, minSponsor, sort, exclude,
  } = req.query;
  let jobs = table('jobs').map(jobWithScore);

  if (q) {
    const needle = String(q).toLowerCase();
    jobs = jobs.filter((j) => `${j.title} ${j.company} ${j.description}`.toLowerCase().includes(needle));
  }
  if (exclude) {
    const bad = String(exclude).toLowerCase().split(',').map((s) => s.trim()).filter(Boolean);
    jobs = jobs.filter((j) => !bad.some((b) => `${j.title} ${j.description}`.toLowerCase().includes(b)));
  }
  if (sector) jobs = jobs.filter((j) => (j.sector || '').toLowerCase() === String(sector).toLowerCase());
  if (nhs === 'true') jobs = jobs.filter((j) => j.nhs);
  if (remote) jobs = jobs.filter((j) => (j.remote || '').toLowerCase() === String(remote).toLowerCase());
  if (visaOnly === 'true') jobs = jobs.filter((j) => j.score.sponsor_confidence >= 45 && j.score.risk_signals.length === 0);
  if (sponsorOnly === 'true') jobs = jobs.filter((j) => j.score.sponsor_matched);
  if (minFit) jobs = jobs.filter((j) => j.score.fit_score >= Number(minFit));
  if (minSponsor) jobs = jobs.filter((j) => j.score.sponsor_confidence >= Number(minSponsor));

  const sorters = {
    fit: (a, b) => b.score.fit_score - a.score.fit_score,
    sponsor: (a, b) => b.score.sponsor_confidence - a.score.sponsor_confidence,
    closing: (a, b) => new Date(a.closing_date) - new Date(b.closing_date),
    salary: (a, b) => (b.salary_max || 0) - (a.salary_max || 0),
  };
  jobs.sort(sorters[sort] || sorters.fit);

  res.json({ count: jobs.length, jobs });
});

router.get('/jobs/:id', (req, res) => {
  const job = find('jobs', (j) => j.id === req.params.id);
  if (!job) return res.status(404).json({ error: 'Job not found' });
  const scored = jobWithScore(job);
  scored.transparency = {
    why_recommended: `Fit ${scored.score.fit_score}/100 and sponsor confidence ${scored.score.sponsor_confidence}/100. ${scored.score.recommended_action}.`,
    source_url: job.source_url,
    source: job.source,
    last_checked: new Date().toISOString(),
    data_freshness: `Posted ${job.posted_date}, closes ${job.closing_date}.`,
    limitations: scored.score.disclaimer,
  };
  res.json(scored);
});

// Add a job by URL / manual paste (user-submitted source).
router.post('/jobs', (req, res) => {
  const { title, company, description = '', source_url = '', location = 'UK', salary_min, salary_max, sector = 'General' } = req.body;
  if (!title || !company) return res.status(400).json({ error: 'title and company are required' });
  const job = insert('jobs', {
    title, company, description, source_url, location, salary_min, salary_max, sector,
    source: 'User-submitted', status: 'active',
    posted_date: new Date().toISOString().slice(0, 10),
    closing_date: null,
    essential_criteria: keywords(description, 6),
    desirable_criteria: [],
  });
  audit({ action: 'job.add', entity_type: 'jobs', entity_id: job.id, user_id: currentUser()?.id });
  res.status(201).json(jobWithScore(job));
});

// --- CV Studio (four-step loop) --------------------------------------------
function cvTextFor(req) {
  if (req.body.cvText) return req.body.cvText;
  const ctx = vaultContext();
  // Reconstruct a plain-text CV from the career vault if none supplied.
  const lines = [
    ctx.profile?.name ? `${ctx.profile.name}` : '',
    'email: demo@visacopilot.app',
    '',
    'EXPERIENCE',
    ...ctx.work.map((w) => `${w.title}, ${w.employer} (${w.start_date}–${w.end_date})\n• ${w.responsibilities}\n• ${w.achievements}`),
    '',
    'SKILLS',
    ctx.skills.map((s) => s.skill).join(', '),
  ];
  return lines.filter(Boolean).join('\n');
}
function jobFor(req) {
  if (req.body.job) return req.body.job;
  return find('jobs', (j) => j.id === req.body.jobId) || table('jobs')[0];
}

router.post('/cv/scan', async (req, res) => {
  const result = await ai.scanCV({ cvText: cvTextFor(req), job: jobFor(req) });
  audit({ action: 'cv.scan', user_id: currentUser()?.id });
  res.json(result);
});

router.post('/cv/surgeon', async (req, res) => {
  const ctx = vaultContext();
  // Rewrite the user's pasted CV when supplied; otherwise rewrite structured vault evidence.
  const result = await ai.surgeonCV({ cvText: req.body.cvText, job: jobFor(req), evidence: ctx.work });
  res.json(result);
});

router.post('/cv/stress-test', async (req, res) => {
  const result = await ai.stressTestCV({ cvText: cvTextFor(req), job: jobFor(req) });
  res.json(result);
});

// --- NHS Studio -------------------------------------------------------------
router.post('/nhs/matrix', async (req, res) => {
  const ctx = vaultContext();
  const job = jobFor(req);
  const matrix = await ai.nhsMatrix({ job, profile: ctx.profile, skills: ctx.skills, work: ctx.work });
  res.json({ job: { id: job.id, title: job.title, company: job.company, band: job.band }, matrix });
});

router.post('/nhs/statement', async (req, res) => {
  const ctx = vaultContext();
  const job = jobFor(req);
  const matrix = await ai.nhsMatrix({ job, profile: ctx.profile, skills: ctx.skills, work: ctx.work });
  const statement = await ai.nhsStatement({ job, profile: { ...ctx.profile, name: currentUser()?.name }, matrix, work: ctx.work });
  res.json({ statement, matrix });
});

// --- Interview Coach --------------------------------------------------------
router.post('/interview/questions', async (req, res) => {
  const job = jobFor(req);
  const result = await ai.interviewQuestions({ job, nhs: !!job.nhs });
  res.json(result);
});

router.post('/interview/score', (req, res) => {
  const { question, answer, jobId } = req.body;
  const job = find('jobs', (j) => j.id === jobId) || table('jobs')[0];
  res.json(ai.scoreInterviewAnswer({ question, answer, job }));
});

// --- Applications / Tracker -------------------------------------------------
const STAGES = ['Saved', 'Drafting', 'Ready', 'Applied', 'Interview', 'Offer', 'Rejected', 'Follow-up'];

router.get('/applications', (req, res) => {
  const user = currentUser();
  const apps = filter('applications', (a) => a.user_id === user?.id).map((a) => {
    const job = find('jobs', (j) => j.id === a.job_id);
    return { ...a, job: job ? { id: job.id, title: job.title, company: job.company, location: job.location, source: job.source } : null };
  });
  res.json({ stages: STAGES, applications: apps });
});

router.post('/applications', (req, res) => {
  const { job_id, status = 'Saved', method = 'Manual', notes = '' } = req.body;
  const user = currentUser();
  const existing = find('applications', (a) => a.user_id === user?.id && a.job_id === job_id);
  if (existing) return res.json(update('applications', existing.id, { status }));
  const app = insert('applications', {
    user_id: user?.id, job_id, status, method, notes,
    applied_at: status === 'Applied' ? new Date().toISOString() : null,
    current_stage: status, next_follow_up: null,
  });
  audit({ action: 'application.create', entity_type: 'applications', entity_id: app.id, user_id: user?.id, detail: status });
  res.status(201).json(app);
});

router.patch('/applications/:id', (req, res) => {
  const patch = { ...req.body };
  if (patch.status === 'Applied' && !patch.applied_at) patch.applied_at = new Date().toISOString();
  const row = update('applications', req.params.id, patch);
  if (!row) return res.status(404).json({ error: 'Not found' });
  audit({ action: 'application.update', entity_type: 'applications', entity_id: row.id, user_id: currentUser()?.id, detail: JSON.stringify(patch) });
  res.json(row);
});

router.delete('/applications/:id', (req, res) => {
  const ok = remove('applications', req.params.id);
  res.json({ ok });
});

// --- Compliance / audit log -------------------------------------------------
router.get('/audit', (req, res) => {
  res.json({ logs: table('audit_logs').slice(-100).reverse() });
});

export default router;
