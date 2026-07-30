# GodMode Gold Bot V12.83 — Expired-Arm Opportunity-Cost Tracker

## The question it answers
"Is no-chase the right strategy, or is it costing me fast moves?" — your Sunday chart showed a
45-point staircase grind where armed retests expired untriggered while the trend ran. This
tracker turns that from a feeling into a number.

## What it does (measurement only — zero change to trading behaviour)
- Every armed retest that EXPIRES UNTRIGGERED is logged (`data/expired_arms.jsonl`) with side,
  leg, price at expiry, ATR and reason.
- ~90 minutes later a throttled sweep (piggybacks the normal scan, no-op when nothing pending)
  replays the M5 candles after expiry and scores a conservative 1R counterfactual scalp entered
  at expiry price: **would_have_won / would_have_lost / faded / ambiguous** (both-in-one-candle
  never counts as a win), plus max favorable/adverse excursion in ATR.
- `GET /api/ai/expired-arms` and the review engine now report: total expired, evaluated,
  would-have-won vs would-have-lost, and an estimated net R the no-chase rule forfeited.
  /tools shows it as a "No-chase opportunity cost (estimate)" strip. Clearly labelled ESTIMATE
  (no spread/slippage; not a promise a shallow-retest mode would capture it).

## How to use it
Let it run alongside the ~50-trade base sample. If it shows e.g. "14 expired, 9 would have won,
3 lost, +6R forfeited" — a shallow-retest mode (15-25% floor) becomes a data-justified single
change. If it shows the misses mostly faded or lost, the no-chase rule is vindicated and you
stop wondering.

## Validation
Simulated end-to-end: arm expiry logs the record; a post-expiry sell-off evaluates the SELL arm
as would_have_won (1.14 ATR favorable, 0.06 adverse); a post-expiry rally evaluates as
would_have_lost; both endpoints and the /tools panel report the summary. Boot 0.08s;
/api/signals unchanged; full V12.67-83 regression green including the V12.82 news trading wire.
