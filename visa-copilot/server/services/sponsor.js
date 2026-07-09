// Sponsor Verifier — matches an employer against the licensed-sponsor register
// and derives a visa confidence signal from the job text.
// Guardrail: a licence match is NEVER a promise of sponsorship for a specific role.
import { jaccard, normalise } from './text.js';

const POSITIVE = [
  ['visa sponsorship', 3], ['sponsorship available', 3], ['skilled worker', 3],
  ['health and care worker', 3], ['certificate of sponsorship', 3], ['tier 2', 2],
  ['we sponsor', 3], ['sponsor visa', 3], ['relocation support', 2], ['relocation', 1],
  ['overseas applicants', 2], ['welcome overseas', 2], ['licensed sponsor', 3],
  ['visa transfer', 2], ['switch visa', 2],
];

const NEGATIVE = [
  ['no sponsorship', -6], ['unable to offer visa', -6], ['cannot offer sponsorship', -6],
  ['must have right to work', -4], ['right to work in the uk', -3], ['no visa', -5],
  ['sponsorship is not available', -6], ['we do not sponsor', -6],
];

export function matchSponsor(companyName, sponsors) {
  const target = normalise(companyName);
  let best = null;
  for (const s of sponsors) {
    const name = normalise(s.organisation_name);
    let sim = 0;
    if (name === target) sim = 1;
    else if (name.includes(target) || target.includes(name)) sim = 0.9;
    else sim = jaccard(companyName, s.organisation_name);
    if (!best || sim > best.similarity) best = { sponsor: s, similarity: sim };
  }
  if (best && best.similarity >= 0.55) {
    return { matched: true, ...best };
  }
  return { matched: false, similarity: best ? best.similarity : 0, sponsor: null };
}

export function textSignals(description = '') {
  const d = normalise(description);
  const positives = [];
  const negatives = [];
  let raw = 0;
  for (const [phrase, w] of POSITIVE) if (d.includes(phrase)) { raw += w; positives.push(phrase); }
  for (const [phrase, w] of NEGATIVE) if (d.includes(phrase)) { raw += w; negatives.push(phrase); }
  return { raw, positives, negatives };
}

// Combine register match + text signals into a 0–100 visa confidence with reasons.
export function visaConfidence({ company, description, sponsors }) {
  const match = matchSponsor(company, sponsors);
  const signals = textSignals(description);
  const reasons = [];

  let score = 25; // neutral baseline
  if (match.matched) {
    score += 35;
    reasons.push(`Employer matches the licensed sponsor register (${match.sponsor.rating}, ${match.sponsor.route}).`);
  } else {
    reasons.push('Employer not found on the licensed sponsor register — verify the entity before applying.');
  }

  score += Math.max(-45, Math.min(35, signals.raw * 6));
  signals.positives.forEach((p) => reasons.push(`Job text mentions "${p}".`));
  signals.negatives.forEach((n) => reasons.push(`⚠ Job text says "${n}".`));

  // Hard cap: explicit "no sponsorship" language dominates.
  if (signals.negatives.length) score = Math.min(score, 20);

  score = Math.max(2, Math.min(98, Math.round(score)));

  let band = 'Low';
  if (score >= 70) band = 'High';
  else if (score >= 45) band = 'Moderate';

  return {
    sponsor_confidence: score,
    confidence_band: band,
    sponsor_matched: match.matched,
    sponsor_record: match.sponsor,
    match_similarity: Math.round(match.similarity * 100) / 100,
    positive_signals: signals.positives,
    risk_signals: signals.negatives,
    reasons,
    disclaimer: 'A licensed-sponsor match indicates the employer can sponsor workers — it is not a guarantee they will sponsor this specific role.',
  };
}
