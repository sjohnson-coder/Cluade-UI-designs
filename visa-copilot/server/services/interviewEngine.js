// Interview Coach (Sparring Partner) — role-specific questions + answer scoring.
import { keywords, contains, tokens } from './text.js';

export function generateQuestions({ job, nhs = false }) {
  const kw = keywords(`${job.title} ${job.description}`, 12);
  const topic = (i) => kw[i] || 'the role';
  const technical = [
    `Walk me through a time you applied ${topic(0)} in a real situation. What was the outcome?`,
    `How would you approach ${topic(1)} in the context of ${job.title}?`,
    `What does "good" look like for ${topic(2)} in this role, and how do you measure it?`,
  ];
  const behavioural = nhs
    ? [
        'Tell me about a time you raised a safeguarding or patient-safety concern (STAR).',
        'Describe a situation where you maintained confidentiality under pressure (STAR).',
      ]
    : [
        'Tell me about a time you handled conflict within a team (STAR).',
        'Describe a situation where you delivered under a tight deadline (STAR).',
      ];
  const curveball = nhs
    ? ['A colleague asks you to overlook a documentation error to save time. What do you do?']
    : ['If your top priority was cancelled the day before launch, what would you do first?'];

  return [
    ...technical.map((q, i) => ({ id: `t${i + 1}`, type: 'technical', question: q })),
    ...behavioural.map((q, i) => ({ id: `b${i + 1}`, type: 'behavioural', question: q })),
    ...curveball.map((q, i) => ({ id: `c${i + 1}`, type: 'curveball', question: q })),
  ];
}

// Score an answer 0–10 on STAR completeness + specificity + relevance.
export function scoreAnswer({ question, answer, job }) {
  const a = (answer || '').trim();
  const words = tokens(a).length;
  const hasSituation = /when|while|during|at\b|role|team|ward|project/i.test(a);
  const hasAction = /\bi\b|we\b|led|built|supported|handled|managed|analysed|coordinated|escalated/i.test(a);
  const hasResult = /result|so that|which|reduced|improved|increased|outcome|led to|resulting/i.test(a);
  const jobKw = keywords(`${job?.title || ''} ${job?.description || ''}`, 12);
  const relevance = jobKw.filter((k) => contains(a, k)).length;

  let score = 0;
  if (words >= 25) score += 3; else if (words >= 12) score += 2; else if (words) score += 1;
  if (hasSituation) score += 2;
  if (hasAction) score += 2;
  if (hasResult) score += 2;
  score += Math.min(1, relevance ? 1 : 0);
  score = Math.min(10, score);

  const gaps = [];
  if (!hasSituation) gaps.push('set the scene (Situation/Task)');
  if (!hasAction) gaps.push('state clearly what YOU did (Action)');
  if (!hasResult) gaps.push('finish with the measurable Result');
  if (words < 25) gaps.push('add more specific detail');
  if (!relevance) gaps.push(`connect it to the role (${jobKw.slice(0, 3).join(', ')})`);

  const rewrite = score < 9 ? rewriteAnswer({ answer: a, gaps, job }) : null;
  return { score, gaps, needs_rewrite: score < 9, suggested_rewrite: rewrite };
}

function rewriteAnswer({ answer, gaps, job }) {
  const base = answer || 'In a previous role';
  return (
    `Situation: ${base.split('.')[0] || 'In my previous role,'}. ` +
    `Task: I was responsible for the outcome. ` +
    `Action: I [describe the specific steps you took]. ` +
    `Result: [add the truthful result — a number, a stakeholder outcome, or a quality/safety improvement]. ` +
    `\n\n(Structured for STAR. Keep it in your own words and use only real experience — do not invent detail.)`
  );
}
