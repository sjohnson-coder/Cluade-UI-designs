# GodMode Gold Bot V13.12 — the scraps machine found, UI cards, journal complete, best config

## THE SCRAPS MACHINE — found in your config arithmetic, fixed on principle
Your complaint was exact: banking pennies, losing dollars. The mechanism:
  breakEvenAtPoints 0.30      -> stop rides to entry after THIRTY CENTS of gold profit
  aiDynamicMinLockFraction .62 + maxGiveback .34 -> from a +$0.60 NOISE peak the bot locked 62%
  and stopped you at ~+$0.35. The ratchet is sound for real winners — it engaged inside noise.
FIX: profitLockMinPeakAtr = 0.55 (new, coach-tunable 0.30–1.20). Below 0.55 ATR of peak profit
the ratchet lock stays OFF — the trade is still fully guarded by the hard SL + fast-fail, it just
is not micro-locked at pennies. Above the floor, everything behaves exactly as before.
This is the principled half of the fix. The DATA half is the Exit Lab: once 30 instrumented
trades exist it measures the real banked-fraction-of-peak and tunes the floor with arithmetic.

## About the 20-Jul chart you sent
Mixed BUY/SELL clusters in the same zone minutes apart (02:05-02:30 @ ~4002-4005, 07:50+ @
~4007-4011) = whipsaw churn: bank pennies -> re-enter -> pay spread -> stop out. The noise floor
attacks the "bank pennies" half directly; the RANGE regime policy (no counter-HTF chasing in
chop) attacks the re-entry half. Export the journal after this session and the Exit Lab card
will put numbers on exactly how much the old trail gave back.

## NEW UI CARDS (Analytics -> Backtest tab)
  • Exit Lab card: loss-cap sweep table (losers saved vs winners killed per cap), trail-giveback
    verdict, banked-%-of-peak. Shows "N/30 TRADES" until the sample exists — it refuses to guess.
  • Walk-Forward card: one button, honest verdict, OOS expectancy, cycles, param stability, and
    a loud warning when candles are synthetic. (Replaces the old button that returned random numbers.)

## JOURNAL COMPLETE
The regime was stamped on entries (V13.11) but never EXPORTED — no column. Added `regime` to the
CSV between exitReason and maeR. "Which engine pays in which weather" is now a spreadsheet filter.

## BEST CONFIG FILE (godmode_best_settings_v13_12.json — download alongside this zip)
Drop-in for backend/data/settings.json (stop bot -> replace file -> start). Contains every tuned
value: fastFail 300s/5min, momentum counter-HTF 1.25 ATR, regime switching ON with the full
policy, breakout-STOP ON both sides, demo guards account-aware, scraps noise floor 0.55, auto
mode with live execution enabled. Migration marker included so nothing re-migrates over it.
NOTE: your Telegram token/chat + MT5 creds live in YOUR current settings — either paste them into
the same fields of this file, or (simpler) apply this file first, then re-enter Telegram in the UI.

## Validation
Boot clean. endpoints failing: NONE. Coach can tune profitLockMinPeakAtr (verified). Regime
column verified in export. Frontend swept: no same-scope duplicates, braces balanced.
