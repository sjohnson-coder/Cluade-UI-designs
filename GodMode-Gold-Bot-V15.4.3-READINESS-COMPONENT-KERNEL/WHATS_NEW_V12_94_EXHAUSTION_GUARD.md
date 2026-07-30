# GodMode Gold Bot V12.94 — Stop selling bottoms / buying tops (the real recurring loss)

## Two issues in the charts — addressed separately

### 1. "Missing spikes" — the ANSWER is catch the ramp, not the spike
Both charts: a clean staircase (4013->4035, 3995->4033) BUILT into the vertical rip. The spike
itself is un-catchable after the fact, but the ramp INTO it is exactly what breakout-stop (V12.93)
and shallow-retest (V12.87) are for. Those features exist — turn breakout-stop ON (demo) to catch
the base-and-grind that precedes these spikes. No code change needed; it needs to be enabled and
proven on demo.

### 2. "Sitting out good trades" — ROOT CAUSE FOUND and fixed
The charts show the bot's only entries were SELLs clustered at the BOTTOMS (4015, 3995), right
before price reversed UP. That is not just missing moves — it is entering counter-trend at the
worst spot, then sitting out the trend that follows.

Why it happened: the fast lane's SELL triggers allow RSI 22-46. At a genuine bottom RSI is often
30 and RISING — inside that window. The HTF matrix at a turning point is only "mixed" (it lags),
not a hard veto, so the SELL slips through as a SCOUT while price is actually basing.

FIX — Exhaustion Guard: refuse a continuation SELL when price is already stretched >=1.10 ATR
BELOW the M5 EMA AND RSI is oversold (<=34) and RISING (a bottom, not a continuation). Symmetric
for BUY at a stretched top with RSI overbought and falling. Instead of taking the bad entry, it
ARMS A RETEST — so if a real continuation develops it still participates, but it stops selling the
low. Reversal setups are exempt (separately gated, and off by default anyway).

Verified: a SELL into RSI-30-rising 1.6 ATR below EMA is now HELD; a genuine SELL continuation
(RSI 40 falling) still fires; a SELL near the EMA (not stretched) is unaffected.

## Why this matters more than the spike feature
Your oversized losers have always been counter-trend entries at exhaustion. This guard attacks
that directly — it should both cut the bottoming-SELL losses AND stop the bot being positioned
wrong-way right as the move it is "missing" begins. Fixing the wrong-way entry is half of catching
the move.

## Safety / scope
On by default (it only PREVENTS bad entries, never creates new ones). Tunable via
exhaustionStretchAtr / exhaustionOversold / exhaustionOverbought. Everything else intact: breakout
-stop (off/demo), burst risk-sizing (on/demo), reversal (off), shallow retest, telegram fix,
why-silent.

## Validation
Boot 0.076s. Guard holds bottoming sells, passes real continuations. Full V12.67-94 regression
green.

## Honest note
This reduces selling bottoms; it does not guarantee catching every spike. Combine with breakout
-stop on demo to catch the ramps, and let the expired-arm tracker quantify what is still missed.
