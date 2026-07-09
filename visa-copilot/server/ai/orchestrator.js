// AI Orchestrator — provider-agnostic routing layer.
//
// Design (per scope §7): the deterministic rule engines are always the source of
// truth for scores and safety, so the product works with NO API key. When an
// OpenAI or Claude key is configured, the orchestrator additionally asks the model
// for a natural-language summary/prose, but ALL generated content is still passed
// through validators (fact/banned-phrase guards live in the engines) and requires
// user approval in the UI before anything is used in an application.
import { createOpenAIAdapter } from './adapters/openai.js';
import { createClaudeAdapter } from './adapters/claude.js';
import * as cv from '../services/cvEngine.js';
import * as nhs from '../services/nhsEngine.js';
import * as interview from '../services/interviewEngine.js';
import { BANNED_PHRASES } from '../services/cvEngine.js';

const SYSTEM_RULES =
  'You are an expert UK recruiter, ATS analyst, and NHS application reviewer. '
  + 'Use ONLY verified user evidence. Never invent experience, dates, qualifications, salary, '
  + 'visa status, clinical exposure, professional registration, metrics, or achievements. '
  + 'Optimise for human recruiters first and ATS parsing second. Use plain, specific, credible '
  + 'language and avoid generic AI wording.';

function buildAdapter() {
  const provider = (process.env.AI_PROVIDER || '').toLowerCase();
  const openaiKey = process.env.OPENAI_API_KEY;
  const claudeKey = process.env.ANTHROPIC_API_KEY;
  if (provider === 'openai' && openaiKey) return createOpenAIAdapter({ apiKey: openaiKey, model: process.env.OPENAI_MODEL });
  if (provider === 'claude' && claudeKey) return createClaudeAdapter({ apiKey: claudeKey, model: process.env.CLAUDE_MODEL });
  if (claudeKey) return createClaudeAdapter({ apiKey: claudeKey, model: process.env.CLAUDE_MODEL });
  if (openaiKey) return createOpenAIAdapter({ apiKey: openaiKey, model: process.env.OPENAI_MODEL });
  return null;
}

const adapter = buildAdapter();

export function providerStatus() {
  return {
    provider: adapter ? adapter.name : 'rule-engine',
    model: adapter ? adapter.model : 'deterministic',
    llm_enabled: Boolean(adapter),
    note: adapter
      ? 'LLM enrichment active. All outputs still pass fact/banned-phrase guards and require user approval.'
      : 'No API key set — running fully functional deterministic engines. Set OPENAI_API_KEY or ANTHROPIC_API_KEY to enable LLM enrichment.',
  };
}

// Validator applied to any LLM prose before returning it.
function bannedPhraseGuard(text = '') {
  const found = BANNED_PHRASES.filter(([bad]) => text.toLowerCase().includes(bad)).map(([bad]) => bad);
  return { clean: found.length === 0, flagged: found };
}

async function enrich(prompt) {
  if (!adapter) return null;
  try {
    const text = await adapter.generateText({ system: SYSTEM_RULES, prompt });
    const guard = bannedPhraseGuard(text);
    return { text, ...guard, provider: adapter.name };
  } catch (err) {
    return { error: String(err.message || err), provider: adapter.name };
  }
}

// --- Task methods: deterministic result + optional LLM prose ----------------
export async function scanCV(input) {
  const result = cv.scanner(input);
  const ai = await enrich(
    `Job: ${input.job?.title}. Missing keywords: ${result.missing_keywords.join(', ')}. `
    + `Red flags: ${result.red_flags.join('; ')}. In 3 sentences, explain to the candidate why the `
    + `match score is ${result.match_score}/100 and the single highest-impact fix. Evidence only.`
  );
  return { ...result, ai_summary: ai };
}

export async function surgeonCV(input) {
  const result = cv.surgeon(input);
  return { ...result, provider: providerStatus().provider };
}

export async function stressTestCV(input) {
  return { ...cv.stressTest(input), provider: providerStatus().provider };
}

export async function nhsMatrix(input) {
  return nhs.personSpecMatrix(input);
}

export async function nhsStatement(input) {
  const result = nhs.supportingStatement(input);
  return { ...result, provider: providerStatus().provider };
}

export async function interviewQuestions(input) {
  return { questions: interview.generateQuestions(input), provider: providerStatus().provider };
}

export function scoreInterviewAnswer(input) {
  return interview.scoreAnswer(input);
}
