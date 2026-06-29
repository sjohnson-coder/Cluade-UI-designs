# GodMode V12.34 — Pyramiding hardening (the 5 flaws fixed)

You asked whether the lot-scaling pyramid was "perfect without flaws." It wasn't — none were
account-blowing (the safety caps all fail closed), but five were real. This release fixes them.
P4 (broker volume-step rounding) turned out to **already** be handled at the MT5 bridge
(`_norm_volume` clamps every order to broker min/step/max), so nothing was needed there.

## P1 — The dormant "failed add" lock is now wired (the real safety gap)
The engine already had a rule "disable new adds after a pyramid add fails this session" — but the
flag that triggers it (`previousPyramidAddFailed`) was **read in two places and never set anywhere**,
so it could never fire. Now:
- a **real** pyramid add rejected/failed at the broker sets the lock + fires a Telegram/UI danger alert,
- further adds on that basket are blocked until it closes,
- the lock **clears automatically** when the basket goes flat or a new UTC day starts.
A protected winner no longer keeps retrying a failing add into the spread.

## P2 — Lot caps now reconcile (raising Max Lot actually does something)
Two fixes to the cap-coupling that made `Max Lot` a near-dead knob:
- **`Final add = Max Lot (pressure leg)` toggle** (Settings → 9). **ON** (default, unchanged
  behaviour) = the final add jumps straight to Max Lot (0.01→0.02→0.03→**0.05**). **OFF** = every add
  climbs by Lot Step, capped at Max Lot, no surprise jump. The jump is now *visible and your choice*,
  not a hidden quirk.
- **`maxTotalLots` auto-fits the ladder.** Raise Max Lot or Max Adds and the basket lot cap moves with
  them (so the final add isn't silently vetoed) — unless you set `maxTotalLots` yourself. The
  stack-risk % and total-exposure % caps stay put as the *real* governors. Settings shows the live
  "fully-pressed basket reaches **N lots**" total.

## P3 — One source of truth for the first-add profit floor
The app-level pre-gate used 0.75R while the engine used 0.80R — so at 0.78R one passed and the other
blocked. The pre-gate now reads the engine's `minProfitRFirstAdd`; they can't disagree.

## P5 — Per-add risk is now stop-distance aware
Add risk used to scale with lot size only (`risk × lot_ratio`), assuming every add's stop sat at the
same distance as the base trade. Now it scales with **both** lot size **and** the add's own stop
distance: an add placed behind nearby structure (tighter stop ≈ current ATR) is correctly counted as
*less* risk, a wider add as *more*. Falls back to the old approximation when stop distances aren't
available. This makes the stack-risk cap honest.

## Verified
- Engine + app compile and import; all five behaviours unit-checked (ladder shape both ways, cap
  auto-fit + user-override, SL-distance risk up/down, failed-add block, unified threshold).
- Settings card renders the new toggle + live basket total; clean and responsive at 390/1280, no
  page overflow; fonts/weights match the existing design.
- Signal generation, profit protection (BE/partials/trailing) and the recovery monitor are untouched.
