# V12.49 — Transition Scout / Pullback Reclaim Fix

This build fixes the repeated Telegram miss where the bot had a BUY bias and visible M5 transition, but still blocked with:

- `No structure: M15 EMAs unstacked and no H4/D1 bias support`
- confidence just below threshold, for example `71.5% < 72%`

## What changed

1. **M15 unstacked is no longer a universal hard block**
   - If M5/M15 show transition structure and H4/D1 are not both strongly opposing, the bot treats it as a SCOUT caution instead of a full WAIT.
   - H4/D1 still hard-block when both are strongly opposite.

2. **Near-threshold scout allowance**
   - A transition setup within 4% of the minimum score can become SCOUT instead of being rejected by a tiny 0.5–2% gap.

3. **Confluence near-miss allowance**
   - Transition scout can pass if confluence is only one factor below the normal requirement.
   - It remains SCOUT only.

4. **Fast Sniper Pullback/Reclaim trigger**
   - The fast lane no longer needs only a breakout candle.
   - It can also trigger a SCOUT when price retests M5 EMA20/EMA50 and reclaims with M15 transition context.

5. **Settings UI controls**
   - Added in Settings → 5e Fast Sniper Lane:
     - Pullback/reclaim scout
     - Reclaim lookback candles
     - Reclaim min body ATR

## Safety

This does not make the bot chase every move. It only relaxes early-transition misses into SCOUT mode when:

- M5 gives a clean trigger or EMA reclaim,
- M15 is transitioning rather than fully bearish against it,
- H4/D1 are not both strongly opposing,
- spread/news/risk gates are still clean,
- the entry is not extremely extended.

Recommended first test: demo + Auto Mode OFF or lowest lot.
