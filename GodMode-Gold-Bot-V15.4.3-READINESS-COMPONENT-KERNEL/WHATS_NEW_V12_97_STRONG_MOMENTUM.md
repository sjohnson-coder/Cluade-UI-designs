# GodMode Gold Bot V12.97 — Catch the dump, not the bottom (RSI-floor fix)

## The bug your chart proved
On the 4090->4060 breakdown the bot took NO entry during the 30pt dump, then sold right at the
4060 bottom where the move was already over ("didn't go far"). Root cause found in code:

The SELL trigger required RSI 22-46. A HARD breakdown pins RSI BELOW 20, so the continuation
never armed during the actual move. Then at the exhaustion LOW, RSI recovered back up into 22-46,
a small down-candle printed, and the trigger finally fired — selling the bottom. The RSI floor was
systematically pushing entries to the END of moves. Same mechanism for buying tops.

## The fix — Strong-Momentum Continuation Override
A STRONG, HTF-aligned break can now take the continuation PAST the RSI floor, gated so it is not a
blind chase:
- Requires real momentum: displacement >= 1.05 ATR (a genuine break body, not a drift).
- Requires HTF agreement (matrix not opposing; no hard veto).
- Refuses if already over-extended (> 2.20 ATR from EMA) — that is the un-catchable vertical
  spike, correctly left alone.
- Has a hard lower floor (RSI >= 8 for sells / <= 92 for buys) so it does not sell a single-print
  capitulation low or buy a blow-off top.

Verified against your exact chart: strong breakdown RSI 15 + HTF bearish -> now TAKES the SELL
continuation (was: nothing, then sold the bottom). Capitulation RSI 5 -> refused. Weak break
(no displacement) -> refused. Over-extended spike -> refused. HTF opposing -> refused.

## Why ON by default
This is a gate-FIX to existing continuation logic, not a new chase strategy. It makes the bot
enter the move it was already trying to trade, at a sane point, instead of at the exhausted end.
Every guard above prevents it from becoming a spike-chaser. Tunable via the strongMomentum* keys.

## Pairs with the earlier fixes
- Exhaustion guard (V12.94) stops selling BOTTOMS.
- This (V12.97) stops MISSING the move and selling the bottom LATE.
- Breakout-stop (V12.93, demo) catches the break from a base.
Together they move entries from "end of move" toward "start of move".

## Validation
Boot 0.080s, /api/signals unchanged. Full V12.67-97 regression green. Everything intact:
auto-frontend-build, news-cache fix, burst risk-sizing, telegram fix, why-silent.

## Honest note
This will catch strong continuations it used to miss. It still will NOT catch a single-candle
vertical spike (un-tradeable after the fact) and it still refuses over-extended chases. That is
correct, not a limitation.
