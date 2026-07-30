# GodMode Gold Bot V13.16 — Top Strategies card shows real names, not cryptic codes

## The confusion
The Dashboard "Top Strategies" card showed rows like Irc, Fsrc, Fsmms, Tp1, Tp2, Tp3 — none of
which appear on the Strategies tab. Two different problems mashed together:

1. FAST-LANE / LEGACY CODES (Irc, Fsrc, Fsmms): these ARE real internal strategies (Impulse
   Retest Continuation, Fast Sniper Retest Continuation, Fast Sniper Momentum Shift) but they are
   not in the displayed catalog, so strategy_from_comment fell through to capitalising the raw
   comment token -> cryptic 3-letter codes. FIX: mapped to readable names.

2. Tp1/Tp2/Tp3/Tp4: these are NOT strategies at all — they are take-profit PARTIAL-CLOSE legs
   (exit events). They were being counted as if they were entry strategies. FIX: exit artifacts
   now decode to None and are SKIPPED from the strategy breakdown entirely.

## After the fix
Top Strategies shows only real strategy names: Volatility Compression Breakout, Impulse Retest
Continuation, Fast Sniper Retest Continuation, HTF Trend Continuation, etc. No Tp* rows, no
cryptic codes. Verified with a mixed history containing exactly those bad codes -> clean output.

## Validation
Decode 7/7 correct (codes -> names, TP legs -> filtered). Dashboard renders. endpoints failing:
NONE. Full regression green.
