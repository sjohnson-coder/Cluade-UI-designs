# GodMode V12.2 — Win-streak lot ladder + faster trailing + full pyramid settings

## Why your lot never scaled
A setting `firstEntryLotMode = "base_lot_only"` forced 0.01 on EVERY trade. Replaced with
a real **win-streak lot ladder** (what you actually described):
- First trade = **Base Lot**.
- Each consecutive **WIN** scales the next trade by **Lot Step**, up to **Max Lot**
  (e.g. 0.01 → 0.02 → 0.03 → 0.04 → 0.05).
- Any **loss resets to Base Lot**.
Toggle + Base/Step/Max are in **Settings → 9. Lot Scaling & Pyramid**. On by default.

This is different from **pyramiding** (which ADDS lots to an already-open winning trade).
Both are now fully exposed in card 9.

## Faster trailing (protect more profit)
Lowered the DEFAULTS: break-even **0.8R → 0.4R**, trailing start **1.0R → 0.5R**, trail
distance **1.2 → 1.0 ATR**, and it tightens further as profit grows.

IMPORTANT: your saved settings.json keeps your OLD values (0.8 / 1.0), so the new defaults
won't apply to you automatically. **Set them in Settings → 5c:**
- Break-even at R → **0.4**
- Trailing Starts at R → **0.5**
- Trail ATR Multiplier → **1.0** (lower = tighter = locks more)

## Full pyramid settings (Settings → 9)
Now editable: pyramiding enabled, max adds, **min recent wins to add**, min profit R for
add 1 / add 2, min confidence for add 1 / add 2, max spread — plus the lot ladder.

## Note on pyramiding starting
Pyramid adds need: base trade **in profit + at break-even**, a **fresh continuation
signal**, and **≥1 recent win** (anti-martingale). With the faster break-even (0.4R) the
"protected" condition is met sooner, so adds can trigger more readily. If you want adds to
fire easier, lower "Min Profit Add 1 (R)" and "Min Confidence Add 1 (%)" in card 9.
