# GodMode Gold Bot V12.68 — AI Entry Auditor (chart-vision second opinion)

Builds on V12.67. The connected AI now directly improves **signal probability, entry
cleanliness and stop placement** — one structured LLM call per candidate entry, never
per tick.

## What it is

When the deterministic engine approves an entry, the **AI Entry Auditor** sends ONE call
to your configured provider (Settings → 12d; Claude recommended) containing:

- the full setup facts (side, entry/SL/TP, engine confidence, strategy, session, spread,
  ATR, all decision features, macro DXY/US10Y snapshot, news-blackout state, the bot's own
  live track record, last 40 candles), **plus**
- a **rendered chart image** of the actual broker candles with entry/SL/TP annotated
  (chart vision — the AI literally reads the chart).

The AI returns a strict-JSON verdict:

| Verdict | Effect |
|---|---|
| **APPROVE** | trade proceeds unchanged (± bounded confidence adjust, journalled) |
| **DOWNGRADE** | valid setup, second-rate location/timing → executed at **scout size** |
| **VETO** | concrete contextual defect (into supply, exhausted impulse, fighting fresh HTF shift, pre-news trap) → entry **blocked** |

It can also return an **invalidation price** — the level that proves the entry wrong.
If enabled, the bot tightens the SL toward it, **bounded**: the level must sit between
entry and the structural stop and may never cut the stop below 50% of the engine's stop
distance. A hallucinated level can't create a noise stop.

## Safety contract (why this can't hurt you)

- **Veto/downgrade only — the AI can never create a trade.** The rules engine stays the
  only signal source.
- **Fail-open by default.** No key, timeout, provider error → audit skipped, engine
  decision stands. AI downtime never halts a validated bot. (`Fail-closed` toggle flips
  this for "no AI check, no trade" users.)
- **Cooldown cache** — an identical setup signature is not re-audited within N seconds,
  so a retrying loop can't burn API calls. Real cost ≈ one call per actual trade.
- **Every verdict is journalled** (`category: ai_audit`) with latency, adjust, reason —
  the new **Verdict Log panel on the AI Agent page** lets you compare AI calls vs
  realised outcomes before you trust it with veto power.
- Pyramid adds are NOT audited (they're already gated by proven profit). Manual executes
  and Telegram-approved trades are skipped by default (you already decided) — both
  opt-in toggles exist.

## New controls — Settings → 12d-2

Enable, veto power, downgrade-to-scout, chart image on/off, SL-tighten on/off, max
confidence adjust, timeout, cooldown, fail-closed, apply-to-manual / apply-to-Telegram.
Plus **"Save + Preview Audit on Current Setup"** — runs a live audit on whatever the
engine sees right now, without executing anything, so you can test the verdict quality
first.

## New endpoints

- `POST /api/ai/audit/preview` — audit the current live decision, no execution.
- `GET  /api/ai/audit/log` — recent verdicts + counts.

## Technical

- New service `backend/services/ai_entry_auditor.py` (bounded parsing, signature cache,
  fail-open contract — 6 unit tests).
- `_llm_json_call` now supports **image blocks** for both Claude (`image` source blocks)
  and OpenAI (`input_image`), verified against both request schemas.
- Hook point: auto-entry flow, after validation lock, before the semi-auto/Telegram gate
  — so in semi-auto mode the Telegram approval card is only queued for AI-cleared setups.
- Reuses the existing `_trade_chart_image` renderer (real broker candles only; if MT5
  candles aren't available the audit runs text-only).

## Validation performed

- `py_compile` on app.py + new service passes.
- Unit: downgrade + bounded invalidation; cooldown cache (0 extra LLM calls); hallucinated
  out-of-bounds invalidation rejected + confidence adjust clamped; fail-open on provider
  death; fail-closed blocks when set; missing key = clean skip.
- Integration (real app functions, mocked provider): VETO blocks through the wrapper and
  journals; SL-tighten applies; disabled = zero-cost None; manual skipped by default;
  audit-log endpoint aggregates verdict counts.
- Vision payload structure verified for both Claude and OpenAI; text-only path unchanged.

## Rebuild note

Backend (the auditor itself, endpoints, gating) is **live on restart — no rebuild**.
The Settings 12d-2 card and AI Agent Verdict-Log panel are source changes: run
`cd frontend && npm install && npm run build` to see them. Until you rebuild, you can
still drive everything via the API endpoints and the config keys under `aiAuditor` in
settings.json.

## Recommended rollout

1. Add your Claude key in Settings 12d, Save + Test.
2. Use **Preview Audit** a few times across different market states — sanity-check verdicts.
3. Enable the auditor with veto power OFF first (downgrade-only) on demo; watch the
   Verdict Log vs outcomes for a few days.
4. Then enable veto power. Leave fail-closed OFF unless you accept AI downtime = no trades.
