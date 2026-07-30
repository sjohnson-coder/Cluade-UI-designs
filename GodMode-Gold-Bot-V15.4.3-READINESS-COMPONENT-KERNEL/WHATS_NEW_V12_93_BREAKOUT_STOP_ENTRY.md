# GodMode Gold Bot V12.93 — Breakout-STOP entry (own the pump WITHOUT chasing)

## The problem
The single M5 candle 4033 -> 4103 (~70 pts). You want to trade moves like this. Market-chasing
the break is a trap: by the time it is visibly pumping you enter near 4098 with a 15pt stop back
to the base, and the candle often round-trips before fast-fail can even act (fast-fail is locked
out for the first 600s; the candle is 300s). "Nothing to lose because BE/fast-fail" is false
there — BE only arms AFTER you are already in profit, and fast-fail is asleep during the spike.

## The fix — pre-positioned breakout-STOP bracket
Instead of chasing, when price is in a TIGHT consolidation the bot now pre-places pending STOP
orders at the edges:
- BUY_STOP just above the range high, SELL_STOP just below the range low (HTF-aligned side only
  by default — it will not bracket into the higher-timeframe river; if HTF is flat it does not arm
  at all, because a break from a flat base is a coin toss).
- Each leg's protective SL sits just beyond the OPPOSITE edge of the base.
- If price breaks, you are FILLED AT THE LEVEL (e.g. ~4022 on that base), not 15pts into the move.
  Then your fast dynamic BE has a real, large profit to protect as the candle runs — exactly the
  scenario where your BE argument becomes TRUE.
- OCO: filling one side cancels the other. Expiry: if neither triggers within
  breakoutExpiryMinutes (25), both are cancelled. One bracket at a time.

On the 4033->4103 candle: a bracket armed on the 4018-4022 base would have filled ~4022 and ridden
the whole ~80pt move with BE locking profit — owning the pump at a sane price.

## New capability
- Bridge gained place_pending_stop() and cancel_pending() (BUY_STOP / SELL_STOP with broker-side
  validation that the trigger is correctly above/below market).
- Lots sized by the existing risk model (riskPerTrade % over the leg's own stop distance).
- GET /api/ai/breakout-bracket shows armed legs, range, expiry.

## Safety
- Ships OFF (breakoutStopEnabled=false) and DEMO-ONLY (breakoutStopDemoOnly=true). Verified: on a
  live account it refuses to arm until you turn demo-only off.
- Tight-base only (0.35-1.20 ATR range, >=6 base candles) so it does not bracket noise.
- Does not touch the retest engine, burst, or any existing path — it is a parallel opt-in.

## What it still will NOT do
Chase a break with a market order. That remains refused — it is the thing that produced your
oversized losers. This is the disciplined alternative: be positioned BEFORE the break, not after.

## Validation
Boot 0.095s. Arm places HTF-aligned STOP above the base with SL beyond the opposite edge; OCO
cancels the sibling on fill; expiry cancels unfilled legs; demo gate blocks live accounts. Full
V12.67-93 regression green (burst risk-sizing, telegram fix, why-silent, news, shallow retest,
reversal-off all intact).

## To try it
Settings -> automation: set breakoutStopEnabled=true (leave breakoutStopDemoOnly=true). Watch it
on demo: on tight bases you will see BUY_STOP/SELL_STOP pending orders appear at the edges, fill
on a real break, and cancel on expiry. Prove it on demo before turning off demo-only.
