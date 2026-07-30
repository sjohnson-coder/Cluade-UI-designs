# GodMode Gold Bot V12.36 — Execution Gate Repair

This patch targets the issue where Telegram showed high-quality BUY/SELL forecasts but the bot stood aside all day.

## Fixed

1. **Structural stop-loss bug**
   - BUY stops now choose the lower/wider protective stop.
   - SELL stops now choose the higher/wider protective stop.
   - This prevents accidental 1.7–3.0 point stops that made normal XAUUSD spread look uneconomic.

2. **Minimum viable XAUUSD stop distance**
   - First-entry stops now enforce a realistic floor (`minXauStopPoints`, default 7.0).
   - Extreme structural tails are capped (`maxXauStopPoints`, default 18.0).

3. **Graduated cost discipline**
   - Cost above the full-size cap no longer kills the trade immediately.
   - `cost <= cap` = normal trade.
   - `cap < cost <= cap * costScoutMultiplier` = reduced-size SCOUT.
   - `cost > cap * costScoutMultiplier` = hard block.
   - Default `costScoutMultiplier` is 1.5.

4. **Chop/efficiency gate repaired**
   - Low 20-bar efficiency is no longer a universal kill switch.
   - If the bot sees directional context, fresh-leg behaviour, ADX support, sweep/FVG/OB context, or a strategy designed for breakout/continuation/retest, the setup becomes a SCOUT instead of a hard block.
   - Only true dead chop with no confirming context remains hard-blocked.

5. **Hidden spread conflict removed**
   - MarketCleanliness now respects the configured `maxSpread` instead of a hidden hardcoded 0.35 threshold.

6. **Blocked Telegram previews are no longer formatted like executable signals**
   - WAIT/BLOCKED forecast alerts no longer print Entry/SL/TP as if a real order was missed.
   - Only actual `TAKE_TRADE` alerts show the executable trade plan.

## Important

This patch makes the bot take more scout trades instead of standing aside. Keep the first run on demo or very small base lot and validate the behaviour on your broker spread before increasing size.
