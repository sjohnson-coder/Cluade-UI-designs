# GodMode Gold Bot V12.50 — Profit Protection Priority Fix

This build fixes a live-management conflict reported after V12.49 where Dynamic SL / Fast-Fail could cut trades before the profit-protection stack had time to engage.

## Fixed

1. Profit protection now has priority on winners
   - Profitable trades are no longer blindly closed by generic dirty-market / structure-invalidated management actions.
   - Dirty/news/spread conditions on a winner tighten/protect instead of immediately closing unless the trade is already red.

2. Dynamic SL recovery no longer overrules Fast-Fail too early
   - Dynamic SL can still cut invalidated, dirty, or deeply failing trades.
   - A weak recovery score alone no longer closes tiny pullbacks before the configured fast-fail floor.

3. Fast-Fail check counter fixed
   - Old wording said “candles” but the loop was counting management checks.
   - New defaults wait for both:
     - minimum checks: 12
     - minimum seconds: 180
   - This prevents a trade being cut after only a few seconds.

4. Break-even lock strengthened
   - Once the BE R threshold is reached, the first stop move is at least BE + configured buffer.
   - Default BE buffer: 0.05 XAUUSD points.

5. TP Push strengthened
   - If broker TP is missing, TP Push can now set the TP4 runner target.
   - If broker TP is below TP4, it can still extend to TP4 when the runner is clean.

## Recommended test settings

- Auto Break Even: ON
- Break Even At R: 0.4–0.8
- BE Buffer Points: 0.05–0.10
- Auto Trailing: ON
- TP Push: ON
- Fast Fail Loss R: -0.5
- No-Progress Checks: 12+
- Minimum Seconds Before Fast-Fail: 180+
- Dynamic SL News Hard Cut: ON
- Dynamic SL Min Recovery Score: 66–70

Run first on demo and watch the management alerts: Profit locked, Trailing up, TP reached, TP pushed, Recovery room, Dynamic SL Recovery.
