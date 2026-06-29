# GodMode V12.12 — AI Strategy Generator (Claude or ChatGPT, configurable in Settings)

Extends the Strategy Lab (V12.11) with the **AI generator** you asked for: connect **Claude** or
**ChatGPT** and let it propose new candidate strategies — safely.

## Set it up — Settings → 12d. AI Strategy Generator
- **Enable AI generator** (toggle)
- **Provider**: Claude (Anthropic) or ChatGPT (OpenAI)
- **API key** (stored locally, sent only to your chosen provider)
- **Model** (defaults: `claude-sonnet-4-6` / `gpt-4o` — editable)
- **Candidates per run**

Get a key from console.anthropic.com (Claude) or platform.openai.com (ChatGPT).

## Use it — Analytics → Strategy Lab → 🤖 Generate with AI
The AI proposes new candidate **trading-style profiles**, they're added to the pool, and the lab
immediately back/forward-tests them on **your** history alongside the curated library and your live
config. As always, a candidate is only **recommended** if it beats your current setup out-of-sample,
and **nothing installs without your click** (with the evidence shown).

## How it's safe (this is the important part)
The AI is **never** allowed to write or run code. It can only return **parameter profiles** — the
exact same safe shape as the built-in library (strictness mode, confidence bars, R:R target,
efficiency/chop filter, confluence, session focus). Before any AI output can enter the candidate
pool it passes through a **strict whitelist + range-clamp**:
- only the known profile keys survive — **any other key (including anything that looks like code,
  rules, or weights) is silently dropped**;
- every number is **clamped to a safe range** (e.g. R:R 1.0–3.5, confidence 50–98, spread 0.15–1.0);
- sessions are filtered to the four real ones; mode must be one of the four presets.

So the worst a bad/hostile model response can do is propose a **safe-but-mediocre** profile — which
the backtest then rejects. (Tested directly: a profile carrying `os.system('rm -rf /')` comes out
the other side as nothing but its clamped, whitelisted parameters.)

Your key is stored in your local, gitignored settings and is sent **only** to the provider you pick.

## API
`POST /api/lab/generate` (uses your configured provider) — proposes, validates, and adds candidates.

## Validation
Backend compiles ✓ · frontend builds ✓ · the AI Settings card and "Generate with AI" button verified
responsive on mobile in a real browser ✓ · **9 simulation suites pass** — including a dedicated
AI-generator suite proving the safety whitelist/clamp (drops injected code + unknown keys, clamps
out-of-range values), both provider request shapes (Claude `x-api-key` vs OpenAI `Bearer`), response
parsing for both, and graceful handling of no-key / bad-provider / network failure.

> Note: the actual model call happens from **your** machine when you click Generate — so it works with
> your own internet and your own key; no third party sees your data.
