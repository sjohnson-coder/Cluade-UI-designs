# GodMode Gold Bot V12.99 — Settings audit: all 33 new keys now visible (was 20 missing)

## You asked me to confirm. I audited instead of asserting. The answer was NO.
I enumerated every config key added in V12.80-98 and tested each against both UI surfaces.
Result: 33 keys, **20 had no UI anywhere**. Worst offender: the ENTIRE V12.91/92 burst group
(near-BE arm + risk-based incremental sizing) — the feature you specifically asked for — had
zero fields. Burst is ON by default and you could not see or tune any of it.

## All 20 gaps now closed
| Group | Was | Now |
|---|---|---|
| V12.87 shallow retest (fibMax, reversal toggle) | 2 missing | all visible |
| V12.91 burst near-BE arm (5 keys) | ALL missing | all visible |
| V12.92 burst risk sizing (6 keys) | ALL missing | all visible |
| V12.93 breakout-stop (5 of 10 missing) | 5 missing | all visible |
| V12.94 exhaustion guard | complete | complete |
| V12.97 strong momentum (RSI floors) | 2 missing | all visible |

**Re-audit result: 0 gaps.**

## Two surfaces
- **/tools -> "Pump & Dump Engine"** (instant, no npm build): now has TWO sections — "Entry engine
  (V12.93-97)" and "Protected Burst (V12.91-92)" including risk model, burst risk % of balance,
  lot distribution, step factor, near-BE arm + early-leg own-stop. Each with plain-English help.
- **React Settings page**: new subsections under Fast Sniper Lane and Protected Burst with every
  key, including the breakout geometry (min range, trigger buffer, SL beyond opposite, OCO, HTF
  align) and the strong-momentum RSI safety floors.

## Verified
Save/read loop tested on BOTH roots (automation.* and tradingModes.protectedBurst.*) — numeric,
text and boolean fields all flip the live value and read back. Boot 0.076s. Full V12.67-99
regression green. No defaults changed.

## IMPORTANT — trade-history epoch resets on every version bump
Noticed during this audit: each upgrade prints "New engine version detected. Trade history reset:
only trades from this version onward will be counted." Since you are trying to accumulate a
~50-trade validation base, upgrading keeps resetting the count. **Set GODMODE_KEEP_HISTORY_ON_UPGRADE=1
before starting the bot** to preserve the history across upgrades — otherwise the 50-trade base
never accumulates while we keep shipping versions.
