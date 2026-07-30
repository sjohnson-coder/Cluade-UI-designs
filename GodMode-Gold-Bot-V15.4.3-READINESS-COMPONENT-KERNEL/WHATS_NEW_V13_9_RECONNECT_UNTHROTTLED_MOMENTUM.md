# GodMode Gold Bot V13.9 — the real reason it missed everything, and MT5 that heals itself

## PART 1: WHY IT MISSED THE PUMPS — three structural blockers found in the entry path

### 1. The 25-SECOND BLIND WINDOW (the big one)
The fast-sniper watch — the function that scans, arms breakout brackets AND fires auto-execution —
sat behind the Telegram ALERT throttle: `fastSniperAlertSeconds = 25s`. The "1-second sniper loop"
returned instantly 24 out of every 25 seconds. A pump triggers and finishes inside a window like
that. Every cache-latency fix from V13.5/V13.7 was real — and blindfolded by this one line.
NOW: the scan runs EVERY loop (~1s). Execution fires the moment a setup exists. Only the alert
SENDS obey the 25s throttle (dedupe by side+price bucket, so a NEW setup queues/fires instantly
and only an identical repeat waits).

### 2. The Telegram toggle was a kill switch
`if not telegram.enabled or not sendFastSniperAlerts: return` — at the TOP of the same function.
Turning alerts off (or Telegram breaking) silently killed scanning, bracket arming and execution.
NOW: alerts disabled = silent engine, not a dead engine. Execution happens first; only the send
is skipped.

### 3. Counter-HTF momentum was still soft-blocked
V13.8.1 freed the breakout BRACKETS, but the momentum override still required the HTF score band
(SELL <= 0.10 / BUY >= -0.10) and the downstream hard veto killed any counter-HTF side anyway.
NOW (your explicit design call): `momentumIgnoreHtf: True` with a HIGHER bar for counter-trend —
`momentumCounterHtfMinAtr: 1.25` vs 1.05 aligned. With the trend you take good momentum; against
it you take only UNDENIABLE momentum. Clean breaks + STRONG lane only; scouts/reversals (the
July-8 loser class) keep full HTF protection; exhaustion guard + stretch cap + RSI capitulation
floors all still apply. Entry catches the move — your fastfail(5m)/BE/trailing own the risk.
Counter-HTF entries are tagged `strong-breakout-counter-htf` in the journal so the cohort is
measurable on its own.

### Plus: the MISSED-MOVE AUTOPSY
If the market prints >= 1.25 ATR displacement and the scan still says no, the bot now writes
`category=missed_pump` to the decision journal with the exact blocking reason. "Why did it miss?"
becomes a grep, not a forensic session.

## PART 2: MT5 THAT HEALS ITSELF
Deep-dived the disconnects. Four real defects fixed in the bridge:
  1. NO shutdown-before-retry: a wedged IPC pipe (terminal alive, pipe dead — the classic MT5
     python failure) made bare initialize() fail FOREVER. Now: any retry after a failure does a
     full mt5.shutdown() first. Proven with a fake wedged terminal: fails → teardown → heals.
  2. THE 10-SECOND CORPSE: init success was cached for 10s even after the terminal died. status()
     now calls mark_dead() the moment the terminal stops answering — next call is a real reconnect.
  3. FALSE SUCCESS: initialize() can return True while the terminal is NOT broker-connected. The
     bridge cached that as healthy and the watchdog would have stood down while blind. Now the
     broker link is verified before success is declared. (Caught by my own test before shipping.)
  4. NO WATCHDOG, NO ALERTS: new engine-loop watchdog — after 15s down it hard-reconnects every
     30s; after 60s down you get ONE Telegram warning; on recovery you get the all-clear. You will
     never again discover a disconnect from the dashboard hours later.
BONUS: set MT5_TERMINAL_PATH in the launcher (hook + example added to all three .bat files) and
the bot can RELAUNCH a fully closed terminal, not just re-attach a dropped session.
Honest limit: if Windows sleeps or the broker's server drops, no code can trade through that —
the watchdog's job is to heal the moment it becomes possible and to TELL you meanwhile.

## Validation
Wedged-pipe heal, corpse-cache invalidation, false-success rejection: all proven against a fake
MT5 double. Boot clean. endpoints failing: NONE. Coach can tune momentumCounterHtfMinAtr
(1.05-2.50, floor enforced — verified both accept and reject). missed_pump journaling verified.
Full regression green.

## What to watch (30-50 trades)
  • journal `strong-breakout-counter-htf` cohort: does counter-trend momentum pay?
  • `missed_pump` entries: what still blocks, and is the reason defensible?
  • maeR/mfeR: the loss-cap and trail-giveback arithmetic, finally.
If counter-HTF momentum bleeds, set momentumIgnoreHtf=false — one toggle, engine intact.
