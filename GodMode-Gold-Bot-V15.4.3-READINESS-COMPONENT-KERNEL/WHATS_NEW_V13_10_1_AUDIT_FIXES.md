# GodMode Gold Bot V13.10.1 — self-audit of V13.8–V13.10: two real bugs found, fixed

## Bug 1 (mine, V13.9): 1 Hz execution-tick spam when Telegram alerts are OFF
The auto path relied on the ALERT-send section to advance the throttle anchor. With alerts
disabled that section is skipped -> `throttled` stayed False forever -> a persistent blocked TAKE
re-ran the full _auto_trade_tick every single second. Anchor now set at execution time. The
25s retry cadence works with alerts on OR off; a NEW setup (different side/price) still fires
immediately.

## Bug 2 (mine, V13.9): the missed-pump autopsy was blind to the misses that matter
The autopsy read `fast.displacementAtr` — but 9 of the blocking return paths (hard veto, MTF
matrix, exhaustion holds, spread, news blackout, reversal floor, min-confidence) did NOT carry
that field. Blocked pumps scored displacement 0 and never logged. Exactly the rows you asked to
see were the ones being dropped. All 9 paths now report displacement; verified NONE remain.

## Also audited, found sound
Watchdog loop (names, state, alert-once logic), counter-HTF lane variable scope, bridge candle
"time" key used by the what-could-have-been scorer, V13.8.1 migration behaviour, V13.7 excursion
capture, frontend build-breaker sweep. Regression: endpoints failing NONE.
