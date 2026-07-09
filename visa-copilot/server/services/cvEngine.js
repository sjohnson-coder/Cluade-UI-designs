// CV Studio engine — deterministic implementations of the four-step optimisation
// loop from the scope (Scanner → Surgeon → Stress Test → Sparring Partner).
// These run with no API key; the AI Orchestrator can swap in an LLM for richer output.
import { keywords, contains, contentTokens } from './text.js';

// Generic / AI-sounding phrases the scope asks us to flag, with better alternatives.
export const BANNED_PHRASES = [
  ['dynamic professional', 'name the specific role title or sector experience'],
  ['proven track record', 'a measurable result or concrete example'],
  ['passionate about leveraging', '"experienced in" / "interested in" + the actual skill'],
  ['results-driven individual', 'an achievement-led bullet with an outcome'],
  ['fast-paced environment', 'the real workload, volume, deadline or pressure context'],
  ['utilised my skills to', 'a direct verb: built, supported, analysed, coordinated, improved'],
  ['spearheaded numerous initiatives', 'name the initiative and its result'],
  ['i am uniquely qualified', 'evidence mapped to the role criteria'],
  ['team player', 'a specific example of collaboration'],
  ['go-getter', 'a concrete achievement'],
  ['think outside the box', 'a specific problem you solved'],
  ['hit the ground running', 'relevant experience you can point to'],
];

const RED_FLAG_RULES = [
  { test: (cv) => !/\b(19|20)\d{2}\b/.test(cv), flag: 'No employment dates detected — ATS parsers and recruiters expect clear month/year ranges.' },
  { test: (cv) => !/@/.test(cv), flag: 'No email address detected in the CV text — contact details must be machine-readable.' },
  { test: (cv) => cv.length < 400, flag: 'CV is very short — likely missing achievements or responsibilities.' },
  { test: (cv) => (cv.match(/•|-\s/g) || []).length < 3, flag: 'Few bullet points detected — experience should be broken into scannable achievement bullets.' },
];

const HEADER_RE = /^(experience|employment|education|skills|profile|summary|contact|references|email|phone|tel|address|linkedin)\b/i;

function splitBullets(text) {
  return text
    .split(/\n|•|·|(?<=\.)\s+(?=[A-Z])/)
    .map((s) => s.replace(/^[\s\-*•]+/, '').trim())
    // Keep only real achievement/responsibility lines: skip headers, contact rows,
    // date-only lines and very short fragments so we never "rewrite" an email address.
    .filter((s) => s.length > 24 && !HEADER_RE.test(s) && !s.includes('@') && /[a-z]{4,}/.test(s));
}

// --- Step 1: Scanner --------------------------------------------------------
export function scanner({ cvText = '', job }) {
  const jd = `${job?.title || ''} ${job?.description || ''}`;
  const jobKw = keywords(jd, 30);
  const present = [];
  const missing = [];
  jobKw.forEach((kw) => (contains(cvText, kw) ? present : missing).push(kw));

  const coverage = jobKw.length ? present.length / jobKw.length : 0;

  // Group missing keywords by type for a more useful gap report.
  const groups = { skills: [], tools: [], qualifications: [], soft: [], domain: [] };
  const SOFT = ['communication', 'teamwork', 'leadership', 'stakeholder', 'collaboration', 'mentorship'];
  const QUAL = ['degree', 'qualification', 'registration', 'certificate', 'nmc', 'hcpc', 'gmc', 'qts', 'certified', 'chartered'];
  const TOOLS = ['sql', 'python', 'kubernetes', 'cad', 'catia', 'tableau', 'looker', 'crm', 'go', 'typescript', 'postgresql'];
  missing.forEach((kw) => {
    const w = kw.split(' ')[0];
    if (SOFT.some((s) => kw.includes(s))) groups.soft.push(kw);
    else if (QUAL.some((s) => kw.includes(s))) groups.qualifications.push(kw);
    else if (TOOLS.some((s) => kw.includes(s))) groups.tools.push(kw);
    else if (job?.sector && contentTokens(job.sector).includes(w)) groups.domain.push(kw);
    else groups.skills.push(kw);
  });

  const redFlags = RED_FLAG_RULES.filter((r) => r.test(cvText)).map((r) => r.flag);
  BANNED_PHRASES.forEach(([bad]) => {
    if (contains(cvText, bad)) redFlags.push(`Generic phrase "${bad}" weakens credibility — replace with evidence.`);
  });

  const missingEssential = (job?.essential_criteria || []).filter((c) => !contains(cvText, keywords(c, 2)[0] || c));

  const score = Math.max(6, Math.min(97, Math.round(coverage * 80 + (redFlags.length ? 0 : 8) + 6)));
  const explanation = score >= 70
    ? `Strong alignment: the CV covers ${Math.round(coverage * 100)}% of the job's key terms with ${redFlags.length} red flag(s).`
    : `The score is limited because the CV covers only ${Math.round(coverage * 100)}% of the job's key terms${redFlags.length ? ` and has ${redFlags.length} red flag(s)` : ''}. Close the top gaps below to lift it.`;

  return {
    step: 'scanner',
    match_score: score,
    keyword_coverage: Math.round(coverage * 100),
    present_keywords: present.slice(0, 15),
    missing_keywords: missing.slice(0, 10),
    missing_keywords_grouped: groups,
    missing_essential: missingEssential,
    red_flags: redFlags.slice(0, 5),
    recruiter_notes: explanation,
  };
}

// Turn structured career-vault evidence into achievement bullets (skips titles/dates).
function bulletsFromEvidence(evidence) {
  const out = [];
  evidence.forEach((w) => {
    [w.responsibilities, w.achievements].forEach((chunk) => {
      String(chunk || '')
        .split(/(?<=\.)\s+|;\s*/)
        .map((s) => s.trim().replace(/\.$/, ''))
        .filter((s) => s.length > 24)
        .forEach((s) => out.push({ text: s, metrics: w.metrics, source: 'CV' }));
    });
  });
  return out;
}

// Only weave skill-like keywords; drop generic adjectives that read awkwardly.
const NON_WEAVABLE = new Set(['band', 'ward', 'team', 'general', 'acute', 'effective', 'awareness',
  'quality', 'senior', 'involvement', 'student', 'nurses', 'medical', 'clinical']);
function weavable(kw) {
  return kw && kw.length > 3 && kw.split(' ').every((w) => !NON_WEAVABLE.has(w)) && !NON_WEAVABLE.has(kw);
}

// --- Step 2: Surgeon (Google XYZ rewrite, evidence-only) --------------------
// Accomplished X, as measured by Y, by doing Z. Never fabricates metrics.
export function surgeon({ cvText = '', job, evidence = [] }) {
  // Use the pasted CV if the user supplied one; otherwise rewrite structured vault evidence.
  const source = (cvText && cvText.trim())
    ? splitBullets(cvText).slice(0, 8).map((t) => ({ text: t, metrics: '', source: 'CV' }))
    : bulletsFromEvidence(evidence).slice(0, 8);

  const missing = scanner({ cvText: cvText || bulletsPlain(source), job }).missing_keywords.filter(weavable);
  let ki = 0; // rotate through missing keywords so none is repeated (keyword-balance guard)

  const rewrites = source.map(({ text: original, metrics }) => {
    const verb = strongVerb(original);
    let kw = null;
    for (let n = 0; n < missing.length; n++) {
      const cand = missing[(ki + n) % missing.length];
      if (!contains(original, cand)) { kw = cand; ki = (ki + n + 1) % missing.length; break; }
    }
    const measure = inferMeasure(original, metrics);
    const needsMetric = !measure.value;
    const rewritten = buildXYZ({ verb, original, keyword: kw, measure });
    return {
      original,
      rewritten,
      added_keyword: kw || null,
      measurement: measure.value || null,
      needs_confirmation: needsMetric,
      confidence_tag: needsMetric ? 'needs confirmation' : (measure.source || 'user-confirmed'),
      note: needsMetric
        ? 'No metric found in your evidence — confirm a truthful number, or keep the non-numeric scale evidence used here.'
        : `Measurement sourced from your ${measure.source}.`,
    };
  });

  const coveredNow = missing.filter((k) => rewrites.some((r) => contains(r.rewritten, k)));
  return {
    step: 'surgeon',
    formula: 'Accomplished X, as measured by Y, by doing Z',
    rewrites,
    keywords_woven_in: coveredNow,
    keywords_still_missing: missing.filter((k) => !coveredNow.includes(k)),
    guardrail: 'No metrics were invented. Bullets marked "needs confirmation" require a truthful number from you before use.',
  };
}

function bulletsPlain(source) { return source.map((s) => s.text).join('. '); }

// --- Step 3: Stress Test (ATS filter + 7-second hiring manager) -------------
export function stressTest({ cvText = '', job }) {
  const scan = scanner({ cvText, job });
  const atsChecks = [
    { name: 'Parsing / single column', pass: !/\t{2,}/.test(cvText), detail: 'No multi-column tab artefacts detected.' },
    { name: 'Standard headings', pass: /experience|employment|education|skills/i.test(cvText), detail: 'Expected section headings present.' },
    { name: 'Contact details', pass: /@/.test(cvText), detail: 'Email address is machine-readable.' },
    { name: 'Consistent dates', pass: /(19|20)\d{2}/.test(cvText), detail: 'Year values found for date parsing.' },
    { name: 'Keyword coverage', pass: scan.keyword_coverage >= 55, detail: `${scan.keyword_coverage}% of job keywords covered.` },
    { name: 'No tables/text boxes for core content', pass: !/\|.*\|/.test(cvText), detail: 'No pipe-table layout detected in core content.' },
  ];
  const atsScore = Math.round((atsChecks.filter((c) => c.pass).length / atsChecks.length) * 100);

  const firstImpression = (() => {
    const firstLine = (cvText.split('\n').find((l) => l.trim().length > 10) || '').trim();
    const titleAligned = job?.title && firstLine && contains(firstLine + ' ' + cvText.slice(0, 300), keywords(job.title, 1)[0] || '');
    return titleAligned
      ? 'In the first 7 seconds a hiring manager can see a role-aligned headline — good.'
      : `In the first 7 seconds the top of the CV does not clearly signal "${job?.title || 'the target role'}". Add a role-aligned professional summary.`;
  })();

  const stillSkipped = [];
  if (scan.keyword_coverage < 70) stillSkipped.push('Some essential job terms are still absent from the top third of the CV.');
  if (scan.red_flags.length) stillSkipped.push('Outstanding red flags may cause an early skip.');
  scan.missing_essential.forEach((c) => stillSkipped.push(`Essential criterion not yet evidenced: "${c}".`));

  return {
    step: 'stress_test',
    ats_score: atsScore,
    ats_checks: atsChecks,
    match_score: scan.match_score,
    hiring_manager_first_impression: firstImpression,
    still_gets_skipped: stillSkipped.length ? stillSkipped : ['Nothing major — the CV reads cleanly in a fast scan.'],
    final_recommendations: [
      'Lead with a 2–3 line summary naming the target role and top evidence.',
      'Move the strongest, most relevant achievement into the top third.',
      ...(scan.missing_keywords.length ? [`Weave in remaining terms naturally: ${scan.missing_keywords.slice(0, 5).join(', ')}.`] : []),
    ],
  };
}

// --- helpers ---------------------------------------------------------------
function strongVerb(bullet) {
  const b = bullet.toLowerCase();
  if (/manage|led|lead|oversaw|coordinat/.test(b)) return 'Led';
  if (/support|assist|help/.test(b)) return 'Supported';
  if (/build|develop|creat|design/.test(b)) return 'Built';
  if (/analy|report|dashboard/.test(b)) return 'Analysed';
  if (/care|patient|clinical|nurs/.test(b)) return 'Delivered';
  if (/improv|reduc|increas/.test(b)) return 'Improved';
  return 'Delivered';
}

function inferMeasure(bullet, metricsStr = '') {
  // Capture a number with a tidy unit: prefer a hyphenated unit ("32-bed"),
  // else the number plus up to two following words ("6 student nurses").
  const RE = /\b(\d[\d,]*(?:-[a-z]+)|\d[\d,]*\+?%?(?:\s[a-z]+){1,2})/i;
  const num = bullet.match(RE);
  if (num) return { value: num[1].trim(), source: 'CV' };
  const m = String(metricsStr || '').match(RE);
  if (m) return { value: m[1].trim(), source: 'career vault' };
  // Non-numeric credible scale evidence (allowed by the scope).
  const scale = bullet.match(/team|ward|shift|patients|clients|students|stakeholders|daily|weekly/i);
  if (scale) return { value: null, source: 'scale evidence', scale: scale[0] };
  return { value: null, source: null };
}

function buildXYZ({ verb, original, keyword, measure }) {
  // X — a verb-led statement of what was done.
  let x = original.replace(/^(i |we )/i, '').replace(/\.$/, '').trim();
  // Treat any leading past-tense verb (…ed) or known action verb as already verb-led,
  // so we never produce "Improved contributed…".
  const first = (x.split(/\s+/)[0] || '').toLowerCase();
  const alreadyVerbLed = /(ed|ted|led|ded| built)$/.test(first)
    || /^(led|managed|supported|built|analysed|resolved|coordinated|maintained|introduced|mentored|administered|recorded|escalated|provided|contributed|developed|created|designed|handled|organised|reduced|increased|delivered|improved|achieved)$/.test(first);
  if (!alreadyVerbLed) x = `${verb} ${lower(stripVerb(x))}`;
  x = cap(x);
  // Y — a truthful measure, or a placeholder that is clearly flagged, never a fake number.
  const y = measure.value
    ? `, as measured by ${measure.value}`
    : measure.scale
      ? `, across a ${measure.scale}-level workload`
      : ', [add a truthful measure]';
  // Z / keyword — weave a relevant term naturally rather than tacking it in brackets.
  const z = keyword ? `, demonstrating ${keyword}` : '';
  return `${x}${y}${z}.`;
}

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function lower(s) { return s.charAt(0).toLowerCase() + s.slice(1); }
function stripVerb(s) { return s.replace(/^(led|managed|supported|built|delivered|analysed|improved|responsible for|helped|assisted)\s+/i, ''); }
