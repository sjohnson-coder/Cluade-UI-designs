# GodMode Gold Bot V12.70 — Edge Upgrades + Junk Removal

## New edge

**1. Auditor Outcome Scoreboard (the learning loop).**
Every AI Entry-Auditor verdict is now automatically paired with the trade's realised
result at close. `GET /api/ai/audit/scoreboard` answers the only question that matters:
*is the AI layer adding edge?* — win-rate and net USD for APPROVEd vs DOWNGRADEd entries,
veto count, and a plain-English assessment ("downgrades win 31% vs 58% for approves —
the AI is correctly spotting second-rate setups; consider letting DOWNGRADE become VETO").
The assessment also appears in the coach's diagnosis once ≥5 trades are scored.
Dedup-safe: one close scores at most one verdict; vetoed setups never traded so they
are counted, not scored.

**2. Spread-spike entry gate.**
Static maxSpread misses the killer case: the broker widening spread 2-3x for seconds
around news/rollover — exactly when a scalp's expectancy dies at the entry tick. The bot
now keeps a rolling ~20-minute spread history and blocks any new entry when the live
spread exceeds 2.2x the rolling median (with an absolute floor). Fires only with enough
history; pyramid adds unaffected (they have their own spread gate).

## Junk removed

- **102 → 10 root docs.** 92 stale changelogs/reports moved to `docs/archive/` (history
  kept, clutter gone).
- **TRADE_REVIEWS memory leak capped** at 300 newest — it grew unbounded on long live runs.
- (V12.69 already: lazy matplotlib = 1.96s→0.10s boot; jsonl auto-rotation.)
- Audit confirmed: **no dead services** — all 22 service modules are genuinely in use;
  nothing safe to delete beyond the above.

## Validation
Spike gate (normal passes, 2.9x spike blocks, borderline passes); scorer pairs verdict→
outcome and refuses double-scoring; TRADE_REVIEWS cap keeps newest/evicts oldest; full
V12.67-69 regression suite passes; py_compile clean.
