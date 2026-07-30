# GodMode Gold Bot V12.99.3 — News OFF root-caused + chart stops inventing TP lines

## BUG 1 (REAL, FIXED) — News shows OFF even with a valid free URL + API key
Root cause found, and it was NOT the feed. /api/feeds/status (which drives the dashboard News
card) calls _apply_data_feed_env() on EVERY poll, and that function called force_refresh() on
SEVEN feed objects every time — nuking each cache and forcing blocking live fetches on every
single dashboard tick. Measured 861ms in a sandbox with NO network; on your machine, where the
calendar 401s and retries, it is far worse. The frontend request times out and falls back to its
default object — whose values are literally {status:'not_configured'} for all three feeds. That
fallback IS the OFF card you kept seeing. Your feeds were fine; the status endpoint was too slow
to answer.

FIXED: feeds now force-refresh ONLY when the feed CONFIG actually changes (URL/key edit), not on
every poll. Measured: 861ms -> ~21ms warm. Changing a URL still forces an immediate refetch, so
correctness is kept. Your free/keyless calendar URL should now report LIVE.

## BUG 2 (REAL, FIXED) — TP/SL lines on the chart with no open trade
You were right, and it was worse than it looked. The dashboard drew ENTRY/SL/TP1-3 whenever a
price existed — and when no real plan existed it FABRICATED them as priceNow±6/8/14. Those TP
lines were invented arithmetic, not a plan.
FIXED: levels are now only drawn when they are REAL —
  • an open bot trade -> its actual entry/SL/TP
  • a live TAKE_TRADE proposal with real SL/TP -> dashed PLAN lines
  • otherwise -> nothing is drawn.
No fabricated levels anywhere.

## VERIFIED (you asked) — burst lot increment works
Tested against your real 392,130 demo balance:
  batch=2 -> [0.05, 0.03]        batch=3 -> [0.05, 0.03, 0.01]      batch=4 -> [0.04,0.02,0.01,0.01]
All incremental-DOWN (biggest leg first), sized from 1% account risk. With caps raised the true
0.6x shape shows: [5.0, 3.06, 1.83]. NOTE: your maxPerPositionLot=0.05 / maxTotalLots=0.10 are
what flatten the ladder at small size — raise those two when you want to scale up.

## NOT DONE THIS ROUND — being straight with you
These are real requests I did not touch, rather than half-do them alongside two logic fixes:
  • Daily/Weekly AI Review + Rollback buttons not working — needs its own investigation.
  • "Applied" state + Revert button on approved Recommended Actions — needs the apply flow to
    persist per-proposal state; real work, next round.
  • TradingView-grade responsive/reactive chart — that is a substantial frontend rebuild, not a
    patch. It deserves a dedicated version.
Ask for these next and I will do them properly.

## Validation
Boot 0.073s. feeds_status 861ms -> ~21ms warm. Full regression green. V12.99.2 fixes intact
(coach proposals apply, history cap 2000). No defaults changed.
