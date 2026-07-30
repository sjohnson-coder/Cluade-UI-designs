# GodMode Gold Bot V12.88 — Campaign-Aware Burst Fix (finalized)

## What the video showed
Multiple SELL burst legs opened near ONE price, sharing one wide ~8-9pt stop, aggregate profit
near zero. Classic burst failure: over-stacking on a single impulse, no basket-level exit.

## The fix (ChatGPT's burst work, reviewed + finalized by Claude)
KEPT (well-engineered, verified):
- **One batch per campaign** — a stable campaign ID (anchored to the earliest open ticket) means
  repeated scanner ticks CANNOT rediscover the same impulse and pile on more legs. Direct fix for
  the video.
- **Fixed lot per leg** (fixedLotBatch) — kills ladder/martingale sizing; all legs equal size.
- **Basket-level defence** — the burst is managed as ONE exposure unit: hard-loss cut at -$0.75,
  give-back cut (peak >=$0.50, give back >=$0.60) closes ALL legs together. Runs every cycle in
  the management loop, independent of new setups.
- **Re-entry lock** — 300s after a campaign closes, serial rediscovery is blocked.
- **Tighter gates** — maxPositions 10->4, minConfidence 82->88, minRecovery 72->78.
- **Still default OFF + demo-only-until-validated.**

CHANGED by Claude before sign-off:
- **Burst fast-fail 30s -> 200s.** ChatGPT's 30s would knife legs on M5-gold noise (30s is 1/10th
  of a candle). 200s gives a leg room to work; the basket stops are the real exit, this is only a
  backstop. Enforced in THREE places so no path can reintroduce a knife-timer: default 200,
  migration clamps any saved value <180 up to 200, and the effective floor is max(120,...).
- **Version bumped** to 4.12.0-v12.88-campaign-burst-fix (ChatGPT left it on v12.87, so epoch and
  build-tracking would not have registered the change).

## On ChatGPT's "Campaign Health Score" proposal
Right idea, wrong time. You cannot fit a composite health-score model with ZERO live burst
trades — that is curve-fitting against one video, and a blended score fails silently ("the score
dropped") which destroys the loud, attributable diagnosis we spent V12.81-84 building. The bot
ALREADY has multi-factor campaign health, implemented as layered auditable gates (recovery score
+ fast-fail + basket hard-loss + give-back) rather than one opaque number. Revisit a learned
score AFTER ~30-50 logged demo campaigns give it real data — and even then, build it as layered
gates, not a black box.

## Everything from V12.87 preserved
Shallow-retest continuation (12-58% zone), reversal scouts OFF by default, news browser-UA fix,
/api/news/test, loud block alerts. Verified intact.

## Validation
Boot 0.164s. Campaign gate blocks a second batch on the same impulse; fixed-lot confirmed; burst
OFF by default; fast-fail 200 in all three references. Full V12.67-88 regression green.

## After upgrading
Run UPGRADE_HELPER_COPY_MY_SETTINGS.bat, start bot. Burst stays OFF — this build makes it SAFE
for when you validate it later; it does not turn it on. Keep letting the base + expired-arm
tracker accumulate toward ~50 trades before enabling anything new.
