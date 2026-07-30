# GodMode Gold Bot V12.91 — Burst fires near break-even, self-protected, ON by default

## What the video showed
A SELL base leg reaching break-even with a live winning edge (price 4017 -> 4014, +2.38), SL
trailing down toward entry — but the burst add did NOT hit at that moment. The old rule required
the base SL to be COMFORTABLY past BE before adding, so on slow M5 grinds the add fired late or
missed the window entirely ("missing many good moves").

## Your request
Fire the burst a few points BEFORE BE fully locks, keep it protected, and only while the winning
edge is still there. If that early window passes, still allow the burst any time the base is in
profit + protected. Turn burst ON by default.

## The fix — two-tier arm
- **Tier A — BE-locked (unchanged):** every base leg's SL already beyond true BE + cost buffer.
- **Tier B — near-BE early (NEW):** base is >= 80% of the way to a locked BE (nearBeArmFraction)
  AND the edge is still valid at fire time (direction intact, recovery score healthy, not
  over-extended). Because the base SL hasn't formally flipped yet, each new burst leg gets its
  OWN tight protective stop immediately (nearBeLegStopAtr, ~0.55 ATR from the add price). So the
  basket is NEVER unprotected — the early fire is safe by construction, not by hope.

This directly resolves the contradiction in "fire before BE but stay protected": the base may
not be BE-locked, but the adds carry their own stops.

## Settings (all in Protected Burst)
- enabled: TRUE (now ON by default, per your choice)
- demoOnlyUntilValidated: TRUE (still gates live accounts — burst runs on demo until you turn
  this off after validation; this is a deliberate safety, not a bug)
- nearBeEarlyArm: true, nearBeArmFraction: 0.80, nearBeSelfProtectLegs: true,
  nearBeLegStopAtr: 0.55, requireEdgeValidAtFire: true
- Kept from V12.88: one-batch-per-campaign, fixed lot, basket hard-loss/giveback, 200s fast-fail.

## Edge protection at fire time
The near-BE tier will NOT fire if the winning edge has decayed: recovery score below threshold or
price over-extended cancels it. So "add while winning" means add while the win is still probable,
not blindly.

## Validation
Simulated both tiers end-to-end: near-BE fires with self-protected legs (SELL leg SL correctly
placed ABOVE current price); BE-locked fires in a clean campaign; campaign gate still blocks a
second batch on the same impulse. Boot 0.088s. Full V12.67-91 regression green (telegram fix,
why-silent, news, shallow retest, reversal-off all intact).

## IMPORTANT — burst is now ON
It will run on DEMO immediately (demoOnlyUntilValidated gates live). Watch the next several demo
bursts: you want to see adds appear as the base nears BE, each with its own stop, and the basket
close together on the campaign hard-loss/giveback. When you're satisfied on demo, turn OFF
demoOnlyUntilValidated to allow it live. Keep letting the base sample build.
