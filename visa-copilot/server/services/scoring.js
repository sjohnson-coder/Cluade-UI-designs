// Job scoring: fit score, sponsor confidence, salary/eligibility risk, missing criteria,
// and a recommended action. Combines rule-based signals so every number is explainable.
import { keywords, contains, contentTokens } from './text.js';
import { visaConfidence } from './sponsor.js';

// Approximate 2024 Skilled Worker general salary floor used only as guidance.
const SKILLED_WORKER_FLOOR = 38700;
const HEALTH_CARE_FLOOR = 23200;

function profileKeywordSet(profile, skills) {
  const set = new Set();
  (skills || []).forEach((s) => contentTokens(s.skill).forEach((t) => set.add(t)));
  (profile?.target_roles || []).forEach((r) => contentTokens(r).forEach((t) => set.add(t)));
  return set;
}

export function scoreJobForProfile(job, { profile, skills, sponsors }) {
  const visa = visaConfidence({ company: job.company, description: job.description, sponsors });

  // --- Fit score: overlap between job keywords and the user's evidence -------
  const jobKw = keywords(`${job.title} ${job.description}`, 30);
  const profSet = profileKeywordSet(profile, skills);
  const hay = [
    ...(skills || []).map((s) => s.skill),
    ...(profile?.target_roles || []),
    profile?.sectors?.join(' ') || '',
  ].join(' ');

  const matched = [];
  const missing = [];
  jobKw.forEach((kw) => {
    const hit = kw.split(' ').some((w) => profSet.has(w)) || contains(hay, kw);
    (hit ? matched : missing).push(kw);
  });
  const coverage = jobKw.length ? matched.length / jobKw.length : 0;

  // Sector alignment bonus.
  const sectorAligned = (profile?.sectors || [])
    .some((s) => s.toLowerCase() === (job.sector || '').toLowerCase());
  let fit = Math.round(coverage * 82 + (sectorAligned ? 12 : 0) + 6);
  fit = Math.max(4, Math.min(98, fit));

  // --- Missing essential criteria (for jobs that publish a person spec) ------
  const missingEssential = (job.essential_criteria || []).filter(
    (c) => !contains(hay, keywords(c, 2)[0] || c)
  );

  // --- Salary / eligibility risk --------------------------------------------
  const floor = job.nhs || job.sector === 'Care' || job.sector === 'Healthcare'
    ? HEALTH_CARE_FLOOR : SKILLED_WORKER_FLOOR;
  const salaryTop = job.salary_max || job.salary_min || 0;
  let salaryRisk = 'Low';
  const salaryNotes = [];
  if (salaryTop && salaryTop < floor) {
    salaryRisk = 'High';
    salaryNotes.push(`Advertised salary (£${salaryTop.toLocaleString()}) is below the ~£${floor.toLocaleString()} guidance for this route.`);
  } else if (salaryTop && salaryTop < floor * 1.1) {
    salaryRisk = 'Moderate';
    salaryNotes.push('Salary is close to the route threshold — confirm the going rate for the occupation code.');
  } else if (salaryTop) {
    salaryNotes.push('Salary appears comfortably above the route guidance threshold.');
  }

  // --- Application difficulty -------------------------------------------------
  const difficultyBySource = {
    'NHS Jobs': 'High', Workday: 'High', Taleo: 'High', iCIMS: 'High',
    Greenhouse: 'Medium', Lever: 'Medium', Ashby: 'Medium', Workable: 'Medium',
    'Employer site': 'Medium', 'Job board': 'Low',
  };
  const difficulty = difficultyBySource[job.source] || 'Medium';

  // --- Recommended action ----------------------------------------------------
  let action = 'Review';
  if (visa.risk_signals.length) action = 'Skip — no sponsorship signalled';
  else if (fit >= 70 && visa.sponsor_confidence >= 60) action = 'Prioritise — tailor & apply';
  else if (fit >= 55) action = 'Tailor CV before applying';
  else if (visa.sponsor_confidence >= 60) action = 'Close skill gaps, then apply';

  return {
    fit_score: fit,
    keyword_coverage: Math.round(coverage * 100),
    matched_keywords: matched.slice(0, 12),
    missing_keywords_json: missing.slice(0, 12),
    missing_essential: missingEssential,
    sponsor_confidence: visa.sponsor_confidence,
    confidence_band: visa.confidence_band,
    sponsor_matched: visa.sponsor_matched,
    sponsor_record: visa.sponsor_record,
    positive_signals: visa.positive_signals,
    risk_signals: visa.risk_signals,
    salary_risk: salaryRisk,
    salary_notes: salaryNotes,
    application_difficulty: difficulty,
    recommended_action: action,
    reasons: visa.reasons,
    disclaimer: visa.disclaimer,
    scored_at: new Date().toISOString(),
  };
}
