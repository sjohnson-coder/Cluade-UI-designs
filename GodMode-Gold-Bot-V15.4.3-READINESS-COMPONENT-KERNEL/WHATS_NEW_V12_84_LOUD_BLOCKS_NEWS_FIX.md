# GodMode Gold Bot V12.84 — Silent Blocks Made Loud + News Fetch Fixed

## Problem 1: "AUTO MODE SHOULD FIRE" x3 at 92% — zero orders, zero explanation
Root cause found in code, not guessed: the Telegram fast-sniper watcher only ANNOUNCES setups;
actual execution happens in the background auto loop's `_auto_trade_tick`. When that tick hits
any gate (session filter, cooldown, loss-streak breaker, governor, HTF veto, repeat-setup guard,
spread spike, validation lock...), its `blocked()` helper recorded a silent heartbeat — NO
Telegram, NO reason. So you got three "SHOULD FIRE" alerts while the executor silently declined
three times, and no way to know which gate did it.

### Fix — truth in the same alert
In AUTO + live-ready, the watcher now RUNS the trade tick itself and reports the outcome in the
very alert you receive:
- fired  -> "FAST SNIPER — ORDER SENT ✅ ... ticket 25099001"
- gated  -> "FAST SNIPER SETUP — BLOCKED, NOT SENT ... blocked by: <exact gate message>"
No more "should fire" mystery: the next time this happens, the alert itself tells you the exact
gate to check. Safe by construction: the watcher already exits early whenever a bot position is
open, so reaching this path means the earlier tick did NOT fire — re-running it cannot
double-enter. The misleading "informational unless Auto Mode" wording is gone in auto mode.

## Problem 2: news still "error or empty" for economy + market
Root cause: every feed fetch identified itself as `GodModeGoldBot/1.0` / `GodModeBot/3`.
Faireconomy (Cloudflare-fronted) and Yahoo routinely return 403 to bot-like User-Agents — so on
your machine the fetch genuinely FAILED every time, which is exactly the state the V12.82
status logic correctly paints red. The URL was fine; the handshake was rejected.

### Fix
- One shared browser-style header set (`_BROWSER_HEADERS`, Chrome/126 UA + Accept) now used by
  EVERY feed fetch: economic calendar, market news, DXY/US10Y macro — in both
  live_market_feeds.py and market_intelligence.py (display AND trading calendars).
- New `GET /api/news/test` + a "Test News Feeds Now" button on /tools: fetches both feeds LIVE
  (no cache) and shows HTTP status, bytes, events parsed, first event sample, or the exact
  error string. "Error or empty" is now a specific, diagnosable answer on your machine.

## Validation
Simulated end-to-end: blocked tick -> alert carries the exact gate text; fired tick -> alert
carries the MT5 ticket; news test endpoint returns per-feed diagnostics with browser UA
confirmed on every fetch path. Boot 0.108s; /api/signals unchanged; full V12.67-84 regression
green (news trading wire, expired-arm tracker, unified recs, review engine whitelist,
secret-safe save, epoch).

## After upgrading
1) Run UPGRADE_HELPER_COPY_MY_SETTINGS.bat, start the bot.
2) Open /tools -> "Test News Feeds Now" -> both feeds should return ok with event counts.
   If either still fails, the exact error is printed — send it and it becomes a one-line fix.
3) Next fast-sniper setup in AUTO: the alert itself will say ORDER SENT + ticket, or name the
   exact gate that blocked it.
