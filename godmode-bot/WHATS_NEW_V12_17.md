# GodMode V12.17 — Strategy-Lab installs are now reversible (and the "sniper lock" fix)

## What was wrong (this is why your bot sat out winning trades)
Installing a Strategy-Lab candidate **silently rewrote your global AI strictness** (mode,
confidence thresholds, min R/R, efficiency gate) and there was **no way to undo it**. You had the
**"Sniper Quality-Only"** profile installed, which put the whole bot into **sniper mode**:
`standardConfidence 85`, `minRiskReward 2.0`, `minEfficiencyRatio 0.45`, scout entries **off**.

That is exactly why the forecasts showed **80%-confidence BUYs parked as "No-Trade / Standby"** — an
80% / 1.8R / efficiency-0.2 setup can't clear an 85% / 2.0R / 0.45-efficiency gate. A stress-test
backtest makes it stark: **sniper took 0 trades over ~188 days** of the same data where balanced/strict
traded profitably. The bot wasn't broken — it was clamped shut by a tuning you couldn't see or remove.

## The fix
- **Uninstall & revert.** Strategy Lab now has an **Uninstall** button (next to "Active tuning", and in
  the candidates table). It removes the installed strategy **and restores the exact strictness you had
  before installing it**.
- **Installs are now reversible by design.** Each install snapshots your pre-install strictness first,
  so revert is exact. Chained installs keep your original baseline.
- **You're never stuck.** If a tuning was installed *before* this update (so there's no snapshot — your
  case), Uninstall restores the **safe default** (balanced + scout entries, efficiency 0.30, R/R 1.5).
- Endpoint: `POST /api/lab/uninstall`.

**Do this first after updating:** open **Analytics → Strategy Lab → Uninstall** to drop the sniper
tuning and get back to balanced. Your 80% setups will be eligible again.

## Important context (read this)
Removing the sniper lock is the right fix, but note from the same stress-test: **loosening the
efficiency gate did NOT help** (efficiency 0.20 was the *worst* config; a tighter 0.45 with sane
confidence was the *best*). So the cure for "it skips chop" is **not** "trade everything" — it's
getting off the broken sniper clamp, plus a smarter (not looser) efficiency check. The deeper
"trade ranges safely / multi-strategy router" redesign is proposed separately for your sign-off.

## Validation
Backend imports ✓ · frontend builds ✓ · install→uninstall round-trip restores the snapshot exactly ✓ ·
pre-existing-install fallback restores clean balanced (eff 0.30, R/R 1.5, scout on) ✓ · live API test:
install "Sniper Quality-Only" → mode sniper, then uninstall → **mode balanced, take 72** ✓.
