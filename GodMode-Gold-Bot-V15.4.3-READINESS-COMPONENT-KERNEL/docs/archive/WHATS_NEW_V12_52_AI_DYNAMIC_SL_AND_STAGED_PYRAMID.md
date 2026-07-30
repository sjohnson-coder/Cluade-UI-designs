# GodMode Gold Bot V12.52 — AI Dynamic SL + Staged Pyramid Upgrade

## Why this build exists
The previous builds still treated BE, trailing, recovery room and Dynamic SL as separate layers. That allowed normal trailing to protect too loosely, and Dynamic SL was mostly a losing-trade recovery module. This build changes that model.

## Main change: AI Dynamic SL becomes the protection brain
Dynamic SL now acts as the unified protection controller for profitable trades:

- It locks profit earlier.
- It ratchets the protected floor based on best open profit reached.
- It does not use one static trailing distance only.
- If price pulls back toward the protected stop and recovery probability is strong, it can widen/relax the stop only down to a protected in-profit floor.
- If recovery probability is weak or the setup invalidates, it tightens/fast-fails instead of widening.

The old BE/trailing labels still exist internally for compatibility, but the decision is now controlled by the AI Dynamic SL floor and recovery score.

## Dynamic SL winner behaviour
For a BUY example:

1. Trade goes into profit.
2. Dynamic SL moves SL to BE/+buffer and then into profit.
3. As the best open profit increases, the protected SL floor also rises.
4. If price pulls back near SL:
   - high recovery score: SL can breathe back to the protected profit floor;
   - low recovery score: SL tightens or the trade is fast-failed.
5. The trade should not give back all locked profit just because it is breathing.

## More aggressive profit retention
Defaults were tightened:

- BE starts earlier.
- Profit lock starts earlier.
- Dynamic lock now keeps roughly two-thirds of peak open profit by default.
- Dynamic trail ATR is tighter than the old static trailing.

## Staged pyramiding upgrade
Pyramiding now follows your requested sequence:

1. First trade opens.
2. It must lock profit with Dynamic SL.
3. If probability remains high, open only one additional position.
4. That new add must also lock profit before the next add is allowed.
5. Lot size climbs using lotStep until maxLot/max positions are reached.
6. The bot does not open all max positions at once.
7. Every add is still capital-aware and is capped by account risk, broker lot limits, maxLot and maxTotalLots.

## Safety
The pyramid engine will not add if:

- any existing leg is not protected,
- the newest add has not proved itself,
- news/dirty market is active,
- recovery score is below the configured floor,
- the direction flips,
- maxAdd/maxLot/maxTotalLots or risk caps are reached.

## Files changed
- backend/app.py

## Testing note
Run this on demo first and watch for these alerts:

- AI Dynamic SL locked
- AI Dynamic SL adjusted
- AI Dynamic SL recovery room
- Pyramid add opened
