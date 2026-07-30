# GodMode Gold Bot V12.71 — Armed Retest Tracker (catches the second leg of big dumps)

## The gap this fixes (from the user's July 8 screenshots)

XAUUSD dumped ~$60 (4120 → 4062). The Fast Sniper correctly refused to chase at 3.89 ATR
extension — that discipline is right (chasing a 3.89-ATR extended spike is how scalpers get
snapped back and stopped). **But "armed retest" was only a Telegram label.** Nothing stored
the armed setup and nothing watched for the pullback. Each new scan saw extension still over
the limit (price stays far from EMA the whole way down a waterfall) and re-armed forever.
The bot missed the ENTIRE move, including the very tradeable second leg after the ~4092
pullback.

## What exists now: a real state machine

1. **ARM** — when the lane declines to chase (extension or hot-RSI), it now stores the
   impulse: side, leg start, leg extreme, ATR, expiry (default 45 min). If the waterfall
   keeps making new extremes, the tracked leg extends with it — the retrace zone always
   follows the CURRENT leg, never a stale one.
2. **WATCH** — every fast-lane scan first checks the armed state (before looking for fresh
   breakouts).
3. **TRIGGER** — a closed trigger-TF candle that (a) pulls back into the 25–62% retrace
   zone of the leg, (b) closes back in trend direction with a real body (≥0.25 ATR), and
   (c) closes in the lower half of the zone → converts into a **Fast Sniper Retest
   Continuation** entry (scout size by default). Verified against a reconstruction of the
   July 8 dump: the 4092 pullback + rejection candle fires a SELL at ~4087 with SL above
   the retest high.
4. **DISARM** — on trigger, on full reclaim of the leg origin (structure invalidated), or
   on expiry. A green bounce alone never fires; only rejection does.

Every triggered continuation still passes the full gauntlet: risk governors, session/news
gates, the V12.70 spread-spike gate, the HTF matrix (blocks only clear opposition), and the
V12.68 AI Entry Auditor. Telegram arm alerts now say the tracker is LIVE and will fire the
second-leg entry automatically.

## New settings (automation.*)
`fastSniperRetestTrackerEnabled` (on), `fastSniperRetestExpiryMinutes` (45),
`fastSniperRetestFibMin/Max` (0.25/0.62), `fastSniperRetestMinBodyAtr` (0.25),
`fastSniperRetestQuality` (SCOUT), `fastSniperRetestMinMtfScore` (-0.35).

## Validation
Reconstructed July-8 waterfall: arm at extension → green bounce does NOT fire → rejection
candle at the retrace zone fires SELL continuation with correct SL/TP → state disarms.
Full-reclaim invalidation disarms without firing. Expiry disarms. BUY mirror passes.
V12.67–70 regression suite passes.

## Honest note
The bot will still skip the FIRST vertical leg of a surprise crash — by design. Entering
at 3.89 ATR extension is statistically poor even when it "looks obvious" in hindsight. What
it will no longer do is stand there re-arming while the market hands it a clean second-leg
entry. Missing leg one is discipline; missing leg two was a bug. The bug is fixed.
