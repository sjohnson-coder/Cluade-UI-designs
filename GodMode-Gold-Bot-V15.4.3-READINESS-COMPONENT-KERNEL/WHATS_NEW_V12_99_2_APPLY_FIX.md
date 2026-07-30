# GodMode Gold Bot V12.99.2 — AI suggestions now actually apply + history cap raised

## BUG 1 (REAL, FIXED) — "I approved a suggestion and nothing happened"
You were right. The AI coach proposes 15 different setting paths, but the apply-proposal
whitelist only allowed 5 — and they barely overlapped. Clicking Approve on almost any coach
suggestion was silently rejected as "not in the approved whitelist". The proposer and the
applier were built with different vocabularies.

FIXED: every path the coach can emit is now whitelisted with a safe range:
  fastSniperMaxExtensionAtr, fastSniperMinConfidence, maxSameDirectionLossesBeforeHardLock,
  postLossReentryMinConfidence, postLossReentryConfidenceDelta, aiDynamicMaxGivebackFraction,
  aiDynamicMinLockFraction, ai.scoutConfidence, ai.standardConfidence, ai.maxSpread,
  pyramiding.maxAdds/minAddConfidence/minProfitRFirstAdd (+ the original 5).
Also fixed: integer settings (maxAdds, hard-lock counter) are now coerced to int — writing 2.0
into a counter could break comparisons.
Verified: all 6 sampled coach proposals now apply and the value changes. Range + whitelist
safety still rejects junk (trading.symbol, out-of-range values).

## BUG 2 (REAL, FIXED) — trade counter stuck at ~200-250
_merge_recent_closed hard-capped the history list at 250 entries. Analytics, the coach, the
calibration and the loss governors all read that list — so the count stopped growing no matter
how many new trades closed. Raised to 2000 (bounded, tunable via meta.maxTradeHistory, hard
ceiling 10000).

## ISSUE 3 — News "not working / OFF": NOT a bug, it needs your API key
Your own /tools output says it plainly:
  economicCalendar — fetch_failed — HTTP Error 401: Unauthorized
  https://financialmodelingprep.com/stable/economic-calendar
401 = the URL requires an API key you have not supplied. marketNews is FINE (HTTP 200, 20
events, 8 headlines loaded — Yahoo RSS). So: only the economic CALENDAR is down, and only
because of the missing key.
Fix: Settings -> Data Feeds -> put your FinancialModelingPrep API key in the calendar API-key
field (or switch the calendar URL to a keyless feed). Nothing in the code can bypass a 401.

## ISSUE 4 — Backtest ignoring spread/commission/slippage: traced, source is CORRECT
I traced the whole path: the Analytics page posts {bars, spread, commission, slippage,
timeframe} -> /api/backtest/run-async -> _backtest_params merges them -> CostAwareBacktester
reads p.get("spread")/p.get("commission")/p.get("slippage") and charges them on BOTH fills.
The logic is right in source. The most likely cause is that your browser is running the STALE
compiled bundle (dist is from July 7) whose Analytics page may not send those fields. Let the
V12.96 auto-build finish (or run REBUILD_DASHBOARD.bat), hard-refresh (Ctrl+F5), and retest.
If it STILL ignores costs after a confirmed rebuild, tell me and I will dig further — I am not
going to invent a fix for something whose source path already checks out.

## ISSUE 5 — Recommended-actions card UI upgrade
Acknowledged, not done. It is cosmetic and I would rather not touch the React card in the same
version as two real logic fixes. Next round.

## Validation
Boot 0.076s. Full regression green. No defaults changed.
