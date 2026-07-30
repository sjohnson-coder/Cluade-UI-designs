# V15.1.1 Impulse Capture Upgrade

## Objective
Detect genuine sudden XAUUSD downward dumps and upward pumps early enough to join the move, while preventing late entries at exhausted extremes.

## Root causes corrected

1. The fast sniper lane required a completed M5 candle. This could delay recognition by almost five minutes.
2. A genuine volatility impulse was classified as SHOCK, but the SHOCK policy disabled the sniper and momentum lanes before the strong-momentum detector ran.
3. The cascade-aligned proposal replaced the local decision but did not rebuild the action matrix. The proposal could be logged as adopted while `takeThisTrade` remained false from the original WAIT decision.

## New behaviour

- Evaluates the forming M5 candle every 0.5 seconds.
- Detects breakouts using the latest four-bar structure rather than waiting through six bars.
- Allows only high-displacement SHOCK impulses through the early regime gate.
- Continues to enforce spread, news/dirty-market, RSI, exhaustion, overextension, MTF, HTF, SL, sizing and broker validation gates.
- Uses a tighter 1.25 ATR extension ceiling for SHOCK entries. If price is already too extended, the bot arms a retest instead of chasing.
- Rebuilds the complete action matrix when a cascade-retest proposal is adopted.

## Default controls

- `fastSniperLoopSeconds`: 0.5
- `fastSniperRequireClosedM5`: false
- `fastSniperMinDisplacementAtr`: 0.60
- `fastSniperBreakoutLookback`: 4
- `shockImpulseEntryEnabled`: true
- `shockImpulseMinDisplacementAtr`: 1.10
- `shockImpulseMaxStretchAtr`: 1.25

## Safety boundary

This upgrade improves detection latency. It does not guarantee that every pump or dump continues after entry. Demo-account forward testing remains required before live capital is used.

## Verification

- Python compilation passed.
- Full automated suite: 334 passed.
