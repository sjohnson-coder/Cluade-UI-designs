# GodMode Gold Bot V12.90 — Telegram trade alerts fixed (Quiet Mode was eating them)

## Symptom
Trades fire correctly, the Telegram connection TEST works ("alerts are connected"), but no
trade alerts arrive.

## Root cause — Quiet Mode (minimalMode) misclassification
The Telegram connection test sends a plain message that bypasses Quiet-Mode filtering. Real
trade alerts go through `_telegram_allowed_by_minimal_mode`, which classifies each message and
suppresses anything it deems "noise" when minimalMode is ON (the default). Two real bugs there:
- The chart that accompanies an entry carried the caption "Chart context — buttons were sent
  first for speed." → classified as `other` → the fallthrough is `return False` → DROPPED.
- The V12.84 "FAST SNIPER SETUP — BLOCKED, NOT SENT" loud-block alert → classified as
  `watchlist` → suppressed by default.
So the exact messages that matter most (execution truth) were the ones Quiet Mode ate.

## Fix
1. **Execution events now bypass Quiet Mode entirely.** Trade fired, order sent, order
   blocked/not-sent, trade closed/close-failed, the entry chart, and burst-campaign-closed
   always reach the phone regardless of minimalMode. Quiet Mode still silences genuine noise
   (BE/trailing chatter, watchlist, market-open heartbeats).
2. **Telegram send-log** — every attempt is now recorded with its outcome: sent, skipped_minimal
   (Quiet Mode), skipped_dedupe, no_creds, disabled, or send_failed (with the API error).
   Exposed at GET /api/system/telegram-log and shown inside the /tools "Why is the bot silent?"
   panel. The NEXT time anything is off, you see exactly which message was dropped and why —
   no more guessing.

## Why the test worked but alerts didn't
The test path doesn't run through the Quiet-Mode classifier; trade alerts do. That's the whole
gap, now closed.

## Everything preserved
V12.87 shallow retest + reversal-off + news UA fix + loud blocks; V12.88 campaign-burst fix +
200s burst fast-fail + burst OFF; V12.89 why-silent diagnostic. All intact.

## Validation
Boot 0.102s. The four previously-dropped message types now PASS minimal mode; send-log captures
sent/skipped/failed with reasons. Full V12.67-90 regression green.

## After upgrading
Run the upgrade helper, start the bot. Alerts should now arrive on every fire. If any category
is still missing, open /tools → "Why is the bot silent?" and read the Telegram attempts log — it
names the outcome per message.
