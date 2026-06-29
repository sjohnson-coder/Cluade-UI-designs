# GodMode V12 — Trade-management lifecycle, rich alerts, hedge/scalp, backtest verdict

Addresses your latest report point by point.

## "Install matplotlib for chart alerts" — what it meant
That text was the app telling you **matplotlib isn't installed**, which is exactly why
your Telegram had **no chart images**. Two fixes: `start_backend.bat` now installs
requirements (incl. matplotlib) on launch, and the AI-Agent note is reworded to say so
clearly. After updating, run once: `pip install -r backend/requirements.txt`.

## Backtest card was broken → fixed
The inputs were collapsing because `.form-row` is a 2-column grid that doesn't survive
inside a flex row. Rebuilt the control row with robust markup — bars/spread/commission
boxes and the toggle now render properly.

## What the backtest result means + does it auto-improve
Your real-data run (608 trades, PF **1.04**, expectancy **+0.023R**, OOS consistency
**50%**, folds flipping −0.06 / −0.11 / +0.17) means: **the strategies are essentially
break-even after costs and inconsistent out-of-sample — no reliable edge as currently
configured.** The result now prints a plain **Verdict** ("No edge yet / Refine first /
Worth trading") so you don't have to interpret the numbers.

It does **not** silently change the bot. **Optimize Weights** only fits + applies new
factor weights *if out-of-sample improves* — yours said "did not improve," so it correctly
changed nothing (forcing it would overfit). The honest takeaway from PF 1.04: the problem
is **strategy quality, not weights** — use **"Disable no-edge"** to switch off the
DISABLE-verdict strategies (your London Open Breakout / Asian Range looked like the
drag) and re-test. The optimizer can only sharpen a real edge; it can't manufacture one.

## Trailing / TP1-TP4 / TP-push / pyramid / lot-scaling now actually work
These were partly cosmetic before. Fixed:
- **Entries now carry the REAL structural SL + a broker TP at TP2** (was a fixed
  placeholder), so the trade actually targets the plan.
- **TP1-TP4 partial closes** execute in the management loop (closes 25% at each level
  when lot size allows; at 0.01 lots it can't slice, so it locks BE + trails the single
  position and tells you). Stable R basis fixed so R stays correct after break-even.
- **TP Push** now *actually extends the broker TP* to TP4 on a clean runner (was just a
  notification).
- **Pyramid lot-scaling** now uses the pyramiding engine's next-add size (was always base
  lot). New toggles: Settings → 5c (TP1-TP4 partials, TP Push).
- Note: management only runs when **Live Trading is ON and connected** — in dry-run it
  won't trail/partial. Trailing needs the trade to reach its start-R; fast-fail won't pre-empt
  a recovering trade now (V9 monitor).

## Rich Telegram alerts (entry + close)
- **Trade-open** alert now sends side, entry, SL, **TP1-TP4**, confidence, strategy,
  brief reason **and a chart** (needs matplotlib).
- **Trade-closed** alert sends exit, PnL, R-multiple, reason + chart.
(The bare "WAIT / lots" message was already removed in V9.)

## Hedge / scalp mode
Settings → 5e → **Hedge / scalp mode**. On a **RETAIL_HEDGING** MT5 account only, a fresh
HIGH-QUALITY setup (STANDARD/SNIPER) can open as an **independent scalp** alongside an
existing trade (instead of a pyramid add), capped by "Max concurrent scalps", with the
same strict BE / trailing / fast-fail protection. It's gated on account type so it can
never net-off your open position on a non-hedging account.

## Files
- `backend/app.py` — TP1-4 partials + TP-push, stable R basis, rich entry/close alerts,
  real SL/TP on entry, pyramid lot-scaling, hedge/scalp logic, new settings.
- `backend/services/mt5_bridge.py` — `is_hedging()`.
- `backend/services/backtest_engine.py` — edge **assessment / verdict**.
- `backend/services/trade_context.py` — scalp entry type; saves TP1-4.
- `frontend` — Backtest card fix + verdict banner, AI-Agent matplotlib note, new settings
  (bundle rebuilt). `start_backend.bat` installs requirements.
