# V12.60 — Protected Burst Lot Ladder Fix

This build fixes the Protected Burst lot sizing behaviour reported after V12.59.

## Problem fixed
Protected Burst could repeat the same per-position lot inside a batch, e.g. 0.01, 0.01, 0.01, then a later leg could appear larger because it came from another sizing path or cap.

## New behaviour
Protected Burst now uses an explicit incremental ladder:

- Base trade uses `Burst Start Lot`.
- Burst add #1 uses `Burst Start Lot + 1 × Burst Lot Increment`.
- Burst add #2 uses `Burst Start Lot + 2 × Burst Lot Increment`.
- Burst add #3 uses `Burst Start Lot + 3 × Burst Lot Increment`.

Example with Start Lot = 0.01 and Increment = 0.01:

```text
Base: 0.01
Add 1: 0.02
Add 2: 0.03
Add 3: 0.04
```

## Safety changes
- Burst mode now forces the base trade to the configured Burst Start Lot for clean audit.
- Burst will not silently downsize a requested ladder leg because that hides configuration problems.
- If the next ladder leg exceeds Max Burst Total Lots or is capped by broker/risk rules, the bot blocks and explains the reason.
- Pyramiding remains OFF while Protected Burst is ON.

## Settings added/clarified
In Settings → Protected Burst:

- Burst Start Lot
- Burst Lot Increment
- Max Lot Per Burst Leg
- Include base in lot ladder

## Validation
- Backend syntax checked.
- Backend import tested.
- Frontend production build completed.
