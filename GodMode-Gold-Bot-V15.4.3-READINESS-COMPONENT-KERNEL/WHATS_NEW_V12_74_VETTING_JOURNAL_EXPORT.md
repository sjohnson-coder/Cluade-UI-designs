# GodMode Gold Bot V12.74 — Vetting-Grade Journal Export + Continued Audit

## New: professional trade-journal export (CSV + PDF)

`GET /api/journal/export?format=csv` and `?format=pdf` — plus **Export CSV / Export PDF
buttons on the Journal page** (frontend rebuild needed to see the buttons; the endpoints
work immediately from any browser tab).

Each closed trade is exported as ONE flat row joined across three sources: the broker
deal (entry/exit/lots/PnL/hold time/exit reason), the bot's entry context (strategy,
confidence, session, quality, full entry reason), and the AI Entry-Auditor verdict for
that ticket. Computed per row: R-multiple from the ORIGINAL stop, hold minutes, WIN/LOSS.

- **CSV**: proper `csv` module quoting — strategy names or reasons containing commas and
  quotes survive Excel round-trips intact (verified by re-parsing).
- **PDF**: dark-editorial report — page 1: KPI summary (win rate, PF, expectancy,
  avg win/loss), probability-calibration table (stated confidence vs actual win rate),
  per-strategy table; following pages: the full trade table, PnL color-coded, ~26 rows per
  page. Rendered via the lazy matplotlib loader — zero startup cost.

## Audit round 3 — checked and fixed
- **Probability calibration buckets sorted numerically** (were string-sorted, so
  "100-109" printed before "20-29"). Math itself verified correct.
- **Pyramiding add-ladder** audited: monotonic base+step climb, hard-capped at maxLot,
  optional deliberate final-add pressure leg. Correct.
- **Telegram approval flow** audited: pending-trade expiry, loss-feedback gate and
  invalid-side block all present and ordered correctly. Correct.
- **AI recovery scorer** audited: HTF flip penalised, structure agreement rewarded,
  bounded 0-100. Correct.
- **Journal file rotation** already covers the new audit-outcomes file.

## Validation
Export tested with 40 synthetic trades: 41-line CSV re-parsed cleanly with embedded
commas/quotes in strategy names; 3-page PDF (valid %PDF header, summary + 2 table pages,
52KB). Full V12.67-74 regression suite passes: secret-safe save, rollback, signals list
guarantee, pure settings read, audit scoreboard, repaired fast-fail clock, range-fade
crash-block. py_compile clean across all modules.
