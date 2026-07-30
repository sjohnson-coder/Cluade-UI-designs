# GodMode Gold Bot V12.80 — Trade-Review Engine (learns from wins AND losses)

You asked for AI review so wins and losses improve strategy and management. Built as two
layers, propose-only, with all three focuses (management, entry, risk) watched at once.

## Layer 1 — Deterministic Trade-Review Engine (always on, no LLM, no cost)
`services/trade_review.py`, endpoint `GET /api/ai/trade-review-engine`.
Pure arithmetic over your closed trades — identical output for identical input, cannot
hallucinate a pattern. It computes and ranks:
- expectancy and WHERE it comes from (win rate vs R per trade);
- **loss/win size asymmetry** — the July-10 signal (your losses were 4.5x your wins);
- **deep losers** — trades that bled past -1R OR are >=3x your average win (catches the -5.56);
- **winner giveback** — how much of each winner's best move is surrendered before close (exit timing);
- **per-strategy, per-session, per-confidence** breakdown (best vs weakest).

Validated against your real July-10 tape: it reproduced net +4.39, PF 1.54, loss/win 4.54x,
and flagged the asymmetry as the #1 issue — automatically, every session.

## Layer 2 — Optional AI diagnosis (on demand, sample-gated)
Endpoint `POST /api/ai/trade-review-llm`. Reads the DETERMINISTIC AGGREGATES ONLY — never
individual trades — so it cannot overfit to a single outcome. It writes a plain-English
diagnosis and up to 3 proposals. Runs only when there are enough trades and a provider key is
set (Settings 12d); otherwise it cleanly returns the deterministic findings.

## Propose-only, sample-gated (your explicit choice)
- Below **30 trades**: NO proposals at all. The engine says so and refuses to change settings —
  with 16 trades any "pattern" is noise. This is the guardrail that stops curve-fitting.
- At/above 30: proposals appear as diffs you approve ONE AT A TIME.
- `POST /api/ai/apply-proposal` is the only writer. It accepts a **whitelist** of five safe
  paths (fast-fail floor, trail-tighten, no-progress minutes, post-loss cap/proof), validates
  the value is in a safe range, snapshots settings for rollback, then applies and saves.
  Non-whitelisted paths and out-of-range values are rejected. Verified.

## See it now, no rebuild
`http://127.0.0.1:8000/tools` has a new **Trade Review Engine** card: "Run Deterministic
Review" and "Deeper AI Diagnosis", findings colour-coded by severity with a sample-confidence
tag, proposals each with an Approve button.

## Data captured for the engine
Trades now persist their excursion at close — MFE (best R), MAE (worst R), risk basis, checks
seen — via a new `trade_context.merge()`. That's what powers the deep-loser and giveback
findings. Live management state was already tracking peak/worst R; it's now saved at close.

## Speed / safety
Boot 0.163s. `/api/signals` unchanged. The engine only runs on request or at close; the entry
hot path is untouched. Full V12.67-80 regression green (news wiring, secret-safe save, epoch,
governor, signals, audit scoreboard). py_compile clean.

## The honest takeaway it will keep showing you
Your edge is win-rate; your risk is a few oversized losers. The engine points at loss control,
not entries — exactly right. It will not propose anything until you have ~30 trades. Feed it a
clean run and let it earn the right to suggest.
