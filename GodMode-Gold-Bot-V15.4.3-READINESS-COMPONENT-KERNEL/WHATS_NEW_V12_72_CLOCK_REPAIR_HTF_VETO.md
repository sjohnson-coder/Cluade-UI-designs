# GodMode Gold Bot V12.72 — Management Clock Repair + HTF Hard Veto

Built from the user's July 7–8 live history (-11.45 and -12.29 on 0.01 lots). Diagnosis:
the ENTRIES were not the main killer — the bot's own management was.

## Root cause 1 — the 45-second guillotine (fixed)

The V12.62 "large loss guard" compressed the fast-fail clock for EVERY trade to
45 seconds / 5 checks (the loop runs ~1s). Any trade not +0.2R within 45 seconds was
closed by the bot itself. Proof from the user's own history: the 10:41 SELL at 4120.65 —
positioned perfectly BEFORE the $60 dump — was closed -2.28 by "no progress". It would
have been ~+58. The endless -0.5…-3 papercuts also manufactured the "8 consecutive
losses" streak, which then triggered pauses and loss-feedback blocks: the bot spent the
day fighting its own management.

**Repair:**
- Large-loss protection now uses ONLY the R floor (-0.35R) + broker-side SL — which
  already cap loss size. The time/check compression is deleted.
- `fastFailMinSeconds` 120 → **600** (10 min minimum hold before any no-progress logic).
- New `fastFailNoProgressMinutes` = **25** (M15-appropriate).
- "No progress" now requires: ≥25 min old AND never peaked +0.15R AND already red
  beyond -0.10R. A flat trade near entry is undecided, not failing — it gets time.
- Burst legs: fast-fail floor 45s → **240s minimum**.
- **One-time migration**: stale saved configs (120s/45s) are lifted automatically on load.

## Root cause 2 — the bot bought against its own analysis (fixed)

The 1:00 PM alert literally said: "Regime=Strong Bullish Trend; **D1 Bearish/H4 Weak
Bearish → bias SELL**" — and then BOUGHT at 4061 with 78% confidence. A short-window
regime label (an M15 bounce) was allowed to overrule the real higher-timeframe read.

**New HTF HARD VETO:** when BOTH D1 and H4 oppose the entry side, the entry is blocked,
with the contradiction spelled out in the block reason. The HTF is the river; an M15
bounce is a ripple. `automation.htfHardVetoEnabled` (default ON),
`automation.htfVetoAllowScout` (default OFF).

## Validation
Reconstructed the killed July-8 BUY: old rule kills at 45s flat — new rule holds; 30-min
red -0.2R still cut; 30-min flat held. HTF veto: BUY vs D1 Bearish + H4 Weak Bearish
blocked; aligned case passes. Migration verified against a stale settings.json (120→600,
45→240). Secret-preserving save + signals regressions pass. py_compile clean.

## What to expect after restarting
Fewer trades, held longer, with losses still capped at -0.35R. The loss-streak pauses and
"entry blocked after loss" spam should mostly disappear because the streaks were being
manufactured by the 45s clock. Judge the next sessions on expectancy, not activity.
