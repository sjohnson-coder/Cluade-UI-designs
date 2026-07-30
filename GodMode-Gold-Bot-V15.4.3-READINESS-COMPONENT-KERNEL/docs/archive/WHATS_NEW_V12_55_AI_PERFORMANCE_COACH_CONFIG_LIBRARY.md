# GodMode Gold Bot V12.55 — AI Performance Coach + Safe Optimisation + Config Library

## Main upgrade
V12.55 adds an AI Performance Coach / self-training layer. It reviews daily and weekly closed bot trades, detects repeat mistakes, proposes safe setting-level optimisations, and lets you apply or rollback fixes.

## What changed

### 1. AI Performance Coach in AI Agent
- Daily AI review.
- Weekly AI review.
- Mistake diagnosis for late entries, repeat same-direction losses, profit giveback, weak dynamic SL outcomes, and early pyramid adds.
- Recommended safe setting patches.
- Apply Fix button.
- Rollback button.
- Local rule-based fallback when Claude/OpenAI is not configured.

### 2. Claude / OpenAI provider connection test
- Settings now has a Save + Test AI Connection button.
- The backend makes a real request to the selected provider.
- OpenAI uses the Responses API.
- Claude uses the Anthropic Messages API.
- Error messages include HTTP/key/model details where the provider returns them.

### 3. Safe optimisation engine
- The AI cannot change code.
- The AI cannot execute trades.
- The AI can only propose whitelisted setting changes.
- Every setting is clamped to a safe range.
- A rollback snapshot is saved before every apply.

### 4. Config import/export
- Export config from Settings.
- Import config JSON from Settings.
- Exports exclude secrets by default.
- Import saves rollback snapshot before applying.

### 5. Config library
Built-in profiles:
- Balanced Sniper
- London Momentum
- Anti-Chop Defensive
- News / Dirty Market
- Trend Runner

You can apply a profile manually and save your current config as a custom library profile.

### 6. Strategy Lab AI path improved
- OpenAI Strategy Lab generation now uses the modern Responses API first.
- Parser still supports legacy Chat Completions output shape for backward compatibility.

## Safety model
Recommended workflow:
1. Let bot trade on demo.
2. Generate Daily/Weekly AI Review.
3. Read diagnosis.
4. Apply Fix only if it makes sense.
5. Monitor next sample.
6. Rollback if performance worsens.

AI auto-select can be turned on, but the safer default is manual approval.
