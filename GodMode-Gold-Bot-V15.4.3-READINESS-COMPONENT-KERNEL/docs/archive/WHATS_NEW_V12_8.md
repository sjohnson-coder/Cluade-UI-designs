# GodMode V12.8 — Validate My Edge (the truth-teller) + anti-overfit guardrails

This is the phase I've said matters most before risking real money: **proof of edge on your own
data**, plus a guardrail so the learning can't overfit.

---

## 1) One-click "Validate My Edge"
**Analytics → Backtest → 🎯 Validate My Edge.** It replays the **real decision engine** bar-by-bar
over up to **~2 years of your actual MT5 M15 history** with realistic Gold costs (spread +
commission), runs a 6-fold walk-forward, and returns a plain-English verdict:

- **GO (demo-forward first)** — positive expectancy after costs with consistent folds.
- **CAUTION** — barely above costs / inconsistent folds; refine before sizing up.
- **NO-GO** — no reliable edge as configured; don't trade live as-is.
- **INCONCLUSIVE** — too few trades; load more history and re-run.
- **NO-GO (test data)** — MT5 wasn't connected, so it ran on synthetic candles (not a real verdict).

The verdict card shows expectancy (R/trade), profit factor, win rate, max drawdown, the date span,
% of walk-forward folds positive, and a **deploy checklist**:
1. Validate on real MT5 history (GO needs positive expectancy **and** consistent folds).
2. Forward-test on a **demo** account 2–4 weeks before any real money.
3. Start live at the **minimum** risk % and scale **only** after live matches the backtest.

It's deliberately **conservative** (assumes SL-before-TP within a bar, no exit slippage, news not
modeled), so a GO here is a genuinely hard bar to clear.

> **History tip:** scroll your MT5 M15 chart far back first (and raise *Tools → Options → Charts →
> Max bars in chart*) so the terminal has the history cached — otherwise the bot can only replay
> what MT5 will give it. The card tells you the exact span it actually tested.

## 2) Backtest now uses real multi-year history
The replay cap was raised from ~6 weeks to **up to ~3.4 years** of M15 bars, so the validation has
enough sample to mean something (a few dozen trades isn't proof — hundreds is).

## 3) Anti-overfit guardrail on learned weights
When you optimize the confidence-factor weights, each learned weight is now **shrunk toward neutral
(1.0)** by a **learning rate (default 0.5)** — so even an out-of-sample-approved fit only moves a
factor **halfway** to its in-sample optimum. This stops a noisy correlation on a smallish sample
from swinging a factor's influence too hard (Bayesian shrinkage toward the prior). The optimizer
still **refuses to apply** unless out-of-sample actually improves, and weights stay clamped to
[0.3, 1.8]. The factor table now also shows the raw (un-shrunk) weight for transparency.

---

## How to use it (recommended flow)
1. Connect MT5, scroll the M15 chart back a year or two.
2. **Validate My Edge.** If it's **NO-GO/CAUTION**, the engine/strategy mix needs work before live —
   use "Disable no-edge" on the per-strategy table and re-validate.
3. If **GO**, optimize weights (Apply if improved), demo-forward 2–4 weeks, then go live at min risk.

## Validation
Backend compiles ✓ · frontend builds ✓ · **5 simulation suites pass** (directional, profit
protection, volatility sizing, live-feed neutrality, and this validation phase — 709-trade replay
producing a coherent GO verdict + shrinkage pulling weights from 0.193→0.112 toward neutral).

> Synthetic numbers in the test are inflated by clean generated trends — that's expected. The whole
> point of this tool is that **only your real MT5 history gives the real number.**
