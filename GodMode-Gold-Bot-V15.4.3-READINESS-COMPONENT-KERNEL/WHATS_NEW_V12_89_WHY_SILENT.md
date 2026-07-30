# GodMode Gold Bot V12.89 — "Why is the bot silent?" diagnostic

## The problem
"Everything is turned on but nothing happens." There are too many independent gates between
"backend running" and "trade fired / alert sent" to diagnose by guessing: the background loop
could be dead, MT5 could be disconnected, market closed, a Telegram toggle off, execution not in
live mode, a bot position already open, or the alert throttle active. Any ONE of these produces
total silence.

## The fix — one button that names the blocker
New GET /api/system/why-silent + a red "Why is the bot silent?" button on /tools. It walks every
gate in order and shows green/red for each with a plain-English reason:
  1. Background loop alive (last tick age — if it never ticked, backend crashed on startup)
  2. MT5 connected (the ENTIRE entry/manage/alert cycle is gated on this — #1 cause of silence)
  3. Market open
  4. Telegram enabled (master switch)
  5. Fast-sniper alerts toggle (the specific switch that sends trade-setup alerts — separate from
     the connection test, which is why the test message works while setups stay silent)
  6. Live execution ready (liveTradingEnabled + dryRun off + autoTradingEnabled — all required to
     auto-fire; alerts can fire without it)
  7. No bot position already open (the watcher intentionally stays quiet while a bot trade is live)

It also surfaces the loop's last result and the seconds since the last fast-sniper alert. The
verdict line names the primary blocker: fix red items top-to-bottom, the top one usually explains
the rest.

## Most likely answer for the current silence
If the Telegram connection TEST worked but no setups arrive, the two usual causes are (a) MT5 not
actually connected to the bridge — the test uses a direct send path that works regardless — or
(b) the loop gates on MT5 connection for the watcher. Run the button; it will point at the exact
one.

## Everything from V12.87/88 preserved
Shallow retest, reversal OFF, news UA fix, /api/news/test, loud blocks, campaign-burst fix,
burst fast-fail 200s, burst still default OFF. Verified.

## Validation
Boot 0.075s. Diagnostic correctly flags MT5-down as primary blocker and reports all-green when
every gate passes. Full V12.67-89 regression green.

## Use it
/tools → "Why is the bot silent?". Send me a screenshot of the red lines and the answer is
immediate.
