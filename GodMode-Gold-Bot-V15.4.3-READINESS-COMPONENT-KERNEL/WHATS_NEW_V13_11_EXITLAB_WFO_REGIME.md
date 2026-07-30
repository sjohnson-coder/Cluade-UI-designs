# GodMode Gold Bot V13.11 — Phases 1-3 of the superbot roadmap, built and verified

## PHASE 1 — Exit Lab (GET /api/analysis/exit-lab)
Turns maeR/mfeR into arithmetic the moment 30 instrumented trades exist:
  • LOSS-CAP SWEEP: for caps -0.4R..-1.0R — losers saved vs winners killed (a winner whose maeR
    went deeper than the cap would have been stopped BEFORE it paid), net R per cap, best cap,
    recommend yes/no. Verified on crafted data: correct on both sides of the ledger.
  • TRAIL GIVEBACK: median banked-fraction-of-peak. Crafted test: winners peaking 2.0R banking
    0.5R -> "banks only 25% of peak — the trail is strangling them". This is the lever your
    +0.24/+0.30 banked wins have been pointing at all along.
  • REFUSES below 30 instrumented trades. An answer from 5 trades is worse than no answer.
  Recommendations map to already-whitelisted coach paths (fastFailLossR, giveback fraction) —
  one tap to apply once the data says so.

## PHASE 2 — REAL walk-forward optimization (POST /api/backtest/walk-forward)
**Replaced a fake.** The old walk-forward endpoint returned RANDOM numbers — rng.uniform(58,74)
win rates, fabricated PnL, and a dice-roll "passed: true". Any confidence ever taken from that
button was fiction. The new harness wraps the cost-aware backtester over real MT5 candles:
optimize a small param grid in-sample -> validate on the NEXT unseen window -> roll -> judge
ONLY concatenated out-of-sample results. <5 scored cycles = "treat as chance" by construction;
grids over 60 combos are refused (a huge grid IS the overfitting machine). Reports param
stability (same config winning repeatedly = real; config churn = noise-chasing). Synthetic
fallback is loudly labelled meaningless when MT5 is disconnected.

## PHASE 3 — Regime switching (automation.regimeSwitchingEnabled, ON)
Explainable classifier — no ML, no fitting: directional efficiency + volatility-vs-24h-baseline
+ range-in-ATR. Verified 4/4 on synthetic weather: TREND / RANGE / QUIET / SHOCK + news blackout.
Policy (automation.regimePolicy, editable):
  TREND : everything on (mirrors current behaviour — switching this on does not strangle you)
  RANGE : counter-HTF momentum OFF (fake pumps live in chop) — everything else on
  QUIET : stand down entirely (3h range under 2 ATR: spread eats every target)
  SHOCK : sniper OFF, brackets STAY ON (a pre-placed stop at a base edge is exactly the
          shock-day instrument)
Every entry is stamped with its regime in the journal -> "which engine pays in which weather"
becomes a measurable question, which is exactly how the policy gets tuned next.
Caught during build: my first stand-down bracket call used the wrong _fast_sniper_mtf_matrix
signature — a TypeError my own try/except would have swallowed silently. Fixed before ship.

## Where to see it
  • Exit Lab + WFO: API endpoints above (UI cards next version if you want them on-screen)
  • Regime: stamped on every journal entry + named in every "why silent" reason
  • The autopsy card from V13.10 now shows regime-aware blocking reasons automatically

## Validation
Regime 4/4 + blackout. WFO mechanics: 7 cycles on synthetic, honest labelling. Exit Lab both
verdicts + small-sample refusal. Boot clean, endpoints failing: NONE, full regression green.
