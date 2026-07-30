# GodMode Gold Bot V13.5 — The lag was real. Traced, measured, fixed.

## You were right, and here are the numbers
Your open-trade marker took ages to appear and PnL crawled because the UI was reading data up to
FOURTEEN SECONDS old. Two layers stacked:

  Trades tab : 6.0s backend cache + 8.0s browser poll = up to 14.0s stale
  Dashboard  : 6.0s backend cache + 4.0s browser poll = up to 10.0s stale

Worse, the trades cache was LAZY: it only refreshed when the browser asked, and served the OLD
value while refreshing in the background — so even the first poll AFTER expiry still returned
stale data. That is exactly the "takes a long time before showing" you described.

## Fixed — 14s -> 2.5s
  • Trades cache TTL   6.0s -> 1.0s   (open positions are a cheap MT5 call)
  • Market cache TTL    2.0s -> 0.6s
  • Trades tab poll  8.0s flat -> 1.5s while a trade is OPEN / 8.0s when flat
  • Dashboard poll    4.0s flat -> 1.5s while a trade is OPEN / 4.0s when flat
  • NEW: the engine now PUSHES fresh trade state into the cache on every ~1s loop while a
    position is open, so the cache is warm before the browser even asks — no more lazy refill.
Adaptive by design: it only polls hard while you actually hold a position, so nothing is
hammered when flat.

    WORST-CASE displayed PnL age while open:  14.0s -> 2.5s

Cost of doing this: none. Hot path measured — _live_trades 0.14ms, _live_market 1.19ms,
/api/dashboard 0.28ms.

## Your entry-lag theory: PARTLY right, and I found the real one
You suspected this also made the bot miss momentum pumps/dumps. Here is the honest split:

**Your PROTECTION was never lagging.** _auto_manage_open_trades calls mt5_bridge.open_positions()
DIRECTLY — live, uncached, every ~1s. Break-even, trailing and fast-fail were always reacting to
real prices, not to the stale numbers on your screen. So the lag was NOT giving back profit. The
screen was lying; the engine was not.

**But you were right that there WAS an entry-path staleness bug.** The fast-sniper loop ticks
every 1.0s — yet it read _live_market(), which was cached for 2.0s. So up to HALF of all entry
evaluations were re-scoring a price the engine had already seen. Now 0.6s < 1.0s, which
guarantees every sniper tick reasons about a fresh snapshot. That is a genuine improvement to
momentum-entry responsiveness, and I would not have found it without your question.

## What this does NOT fix
This will not make the bot catch a single-candle vertical spike — that is still un-catchable on
closed-bar M5, as covered before. It removes ~1s of staleness from entry evaluation. Real, worth
having, not a silver bullet. The breakout-STOP engine (still OFF + demo-only in your config) is
the tool actually built for catching the ramp INTO a pump.

## Validation
Boot 0.241s. endpoints failing: NONE. Full regression green. Frontend swept for the
duplicate/use-before-declare class that broke your last build — clean (I caught one while writing
this: hasOpenTrade was being used on line 37 but derived on line 41; fixed before shipping).
