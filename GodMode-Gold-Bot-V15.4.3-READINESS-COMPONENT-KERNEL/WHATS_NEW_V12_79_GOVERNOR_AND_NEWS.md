# GodMode Gold Bot V12.79 — The Governor Was Eating The Rally + News Works Out Of The Box

Built from the July-9 Telegram log and MT5 history (-6.53 on the day).

## 1. The loss-feedback governor locked the bot out of the whole rally

Your 5:15 PM alert: the V12.71 retest tracker COMPLETED a textbook BUY —
*"impulse leg 24.1 pulled back 55.0% into the 25%-62% zone and printed a rejection close"* —
79% quality, "AUTO MODE SHOULD FIRE". No order was sent. Meanwhile eight
"Entry blocked after loss" alerts fired every ~3 minutes, all saying
`confidence 77-82 needs >=88.3`, all because of ONE BUY loss 70-90 minutes earlier.
Price ran from ~4098 to ~4131 while the bot stood aside.

Four root causes, all fixed:

1. **The confidence demand was uncapped.** It was `last_loser_confidence + 5`. After an 83%
   loser it demanded >=88.3% — a number the engine almost never prints. Now capped:
   `postLossConfidenceCap` (default **85.0**).
2. **A hard interlock between two of my own features.** V12.71 retest continuations fire at
   SCOUT quality by default, and `postLossNoScoutSameDirection` auto-failed every post-loss
   scout. So the tracker's completed setups — impulse + pullback + rejection close, the
   literal definition of a fresh edge — could never pass after a single same-side loss.
   A completed retest continuation is now exempt from the scout block, and passes the
   override on its own at >= `postLossRetestMinConfidence` (**74.0**) with real displacement.
3. **Proof bar too high.** 5-of-6 after a single loss; "structure break" rarely prints
   mid-trend, so the confidence bar was doing the gating twice. Now `postLossProofNeeded`
   = **4** of 6 after one loss, **5** of 6 once hard-locked.
4. **No time decay.** The governor held for the full 90-minute loss window. Now it releases
   after `postLossGovernorMaxMinutes` (**60.0**), even inside that window.

Alert throttle raised 180s -> 900s so Telegram is not spammed while the governor holds fire.

**Revenge protection is intact and was verified, not assumed.** During testing the first
version of the scout exemption leaked: because `is_retest_continuation` disabled
`scout_block`, the `notScout` proof bit was satisfied and a hard-locked (2+ same-side losses)
retest could pass. That is a bug that would have cost real money. The exemption now applies
only after a SINGLE loss; once hard-locked every scout is blocked again.

Verified with a connected-MT5 simulation of your exact sequence:
- 1 loss + completed retest 79% -> **ALLOWED**
- 1 loss + weak 68% same-strategy scout -> **BLOCKED**
- hard lock (2 losses) + completed retest -> **BLOCKED**
- hard lock + weak scout -> **BLOCKED**
- loss older than 60 min -> governor released
- 85% confidence now satisfies the cap (was demanding 88.3)

## 2. News: `not_configured` on every fresh install (real cause)

V12.77 wired the feeds correctly — but `dataFeeds` defaults were **empty strings**. Every new
zip you unpack into a new folder starts with no URL, so the calendar reports `not_configured`
until you retype it. (The old dashboard bundle reads `/api/feeds/status`, which is also wired.)

The bot now ships with free, keyless defaults — the exact URLs the Settings "Use free ..."
buttons write: ForexFactory weekly JSON (faireconomy mirror), Yahoo gold-futures RSS, Yahoo
DXY and ^TNX. **News works on first boot with no typing.** Any value you save, or the matching
env var, still overrides them.

Verified on a clean install: `live_calendar.url` populated, `/api/news/status` and
`/api/feeds/status` both report `configured: true`.

## 3. Settings keep resetting between zips
Not a bug — each zip is a fresh folder. Run **`UPGRADE_HELPER_COPY_MY_SETTINGS.bat`** (shipped
in V12.78) in the new folder and point it at the old one.

## Speed
Boot **0.083s**. `/api/signals` unchanged. All changes are in gate logic and defaults; the
decision hot path is untouched.

## Validation
Full V12.67-79 regression green: secret-safe save, rollback, signals list guarantee, pure
settings read, audit scoreboard, data epoch, build status, repaired fast-fail clock, feeds
wiring, config import incl. aiAuditor, M5 timeframe, journal rows, range-fade crash block,
and all six governor scenarios. py_compile clean across every module.
