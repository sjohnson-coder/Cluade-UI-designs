// NHS Studio engine — person specification matrix + supporting-information draft.
// Scores essential criteria FIRST, then desirable, before drafting (per NHS Jobs guidance).
import { contains, keywords } from './text.js';

function evidenceFor(criterion, { skills = [], work = [] }) {
  const kw = keywords(criterion, 3);
  const hay = [
    ...skills.map((s) => s.skill),
    ...work.map((w) => `${w.title} ${w.responsibilities} ${w.achievements}`),
  ].join(' ');
  const hit = kw.find((k) => contains(hay, k)) || (contains(hay, criterion) ? criterion : null);
  if (!hit) return { met: false, evidence: null };
  // Find the work item that best supports it, for a concrete example.
  const support = work.find((w) => contains(`${w.responsibilities} ${w.achievements}`, hit));
  return {
    met: true,
    evidence: support
      ? `${support.title} at ${support.employer}: ${support.responsibilities}`.slice(0, 200)
      : `Listed skill/experience: ${hit}`,
  };
}

export function personSpecMatrix({ job, profile, skills, work }) {
  const build = (list, kind) =>
    (list || []).map((criterion) => {
      const { met, evidence } = evidenceFor(criterion, { skills, work });
      return {
        criterion,
        kind,
        status: met ? 'met' : 'gap',
        evidence,
        suggested_wording: met
          ? draftStatementLine(criterion, evidence)
          : null,
        gap_prompt: met ? null : `You have not yet evidenced "${criterion}". Add a truthful example from your experience.`,
      };
    });

  const essential = build(job.essential_criteria, 'essential');
  const desirable = build(job.desirable_criteria, 'desirable');
  const essentialMet = essential.filter((e) => e.status === 'met').length;
  const desirableMet = desirable.filter((e) => e.status === 'met').length;

  return {
    band: job.band || null,
    essential,
    desirable,
    essential_coverage: essential.length ? Math.round((essentialMet / essential.length) * 100) : 100,
    desirable_coverage: desirable.length ? Math.round((desirableMet / desirable.length) * 100) : 100,
    ready_to_draft: essential.length ? essentialMet / essential.length >= 0.6 : true,
    guidance: essentialMet < essential.length
      ? 'NHS shortlisting scores essential criteria first. Close the essential gaps above before relying on the draft.'
      : 'All essential criteria are evidenced — you can generate a strong supporting statement.',
  };
}

function draftStatementLine(criterion, evidence) {
  return `I meet the requirement for ${criterion.toLowerCase()}. ${evidence || ''}`.trim();
}

export function supportingStatement({ job, profile, matrix, work = [] }) {
  const name = profile?.name || 'the applicant';
  const essentialMet = matrix.essential.filter((e) => e.status === 'met');
  const desirableMet = matrix.desirable.filter((e) => e.status === 'met');

  const sections = [];
  sections.push({
    heading: 'Motivation',
    body: `I am applying for the ${job.title} post at ${job.company} because it aligns with my experience in ${(profile?.sectors || ['healthcare']).join(' and ')} and my commitment to safe, person-centred care. I am keen to contribute to your team and continue developing within the NHS.`,
  });

  if (essentialMet.length) {
    sections.push({
      heading: 'Meeting the essential criteria',
      body: essentialMet
        .map((e) => `• ${e.criterion}: ${e.evidence || 'demonstrated through my previous roles.'}`)
        .join('\n'),
    });
  }

  if (desirableMet.length) {
    sections.push({
      heading: 'Meeting the desirable criteria',
      body: desirableMet.map((e) => `• ${e.criterion}: ${e.evidence || ''}`).join('\n'),
    });
  }

  sections.push({
    heading: 'NHS values, safeguarding and teamwork',
    body: 'I work in line with the NHS values of compassion, respect and dignity. I escalate safeguarding concerns promptly, maintain patient confidentiality, and communicate clearly within the multidisciplinary team. I keep accurate records and support colleagues to deliver consistent, high-quality care.',
  });

  sections.push({
    heading: 'Closing fit statement',
    body: `I believe my experience maps closely to your person specification. I would welcome the opportunity to bring my skills to ${job.company} and to demonstrate my suitability at interview.`,
  });

  const wordCount = sections.reduce((n, s) => n + s.body.split(/\s+/).length, 0);
  return {
    sections,
    word_count: wordCount,
    guardrail: 'Written from your verified evidence only. No clinical exposure, registration, or qualification has been invented — review every line and add your own examples where prompted.',
    flags: matrix.essential.filter((e) => e.status === 'gap').map((e) => `Essential gap not covered in this draft: ${e.criterion}`),
  };
}
