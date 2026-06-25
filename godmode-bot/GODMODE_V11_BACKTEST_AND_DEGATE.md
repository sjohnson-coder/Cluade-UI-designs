# GodMode V11 — Cost-aware backtest/optimizer + de-gating (trade regularly)

Two things in this release: the validation harness you asked for, and a fix for the
bot being over-gated (barely trading).

## 1) Cost-aware backtest + walk-forward + weight optimizer
`backend/services/backtest_engine.py` replays the REAL decision engine bar-by-bar over
historical M15 candles (H1/H4/D1 resampled on the fly, lookahead-free), simulates each
trade with the engine's own TP1–TP4 + break-even plan, and charges spread + commission
on every trade. Output:
- Per-strategy edge: expectancy (R), profit factor, win rate, max drawdown (R), sample
  size, and a **KEEP / MARGINAL / DISABLE / FLAG_LOW_SAMPLE** verdict.
- Walk-forward folds + an out-of-sample consistency %.
- A **factor-weight optimizer** that measures how predictive each confidence factor
  actually is of cost-adjusted R (correlation on in-sample trades), turns that into
  weights, validates on a held-out slice, and only applies them if out-of-sample
  improves (it refuses to overfit). Applied weights persist to `data/factor_weights.json`
  and the engine uses them live (`_score_factors`).

Validated: the simulation P&L/cost math is exact (a partial-then-BE trade returns
+0.675R and a straight stop −1.025R to the penny), and the full harness runs end-to-end.

**Use it:** Analytics → **Backtest** tab → set your broker's real spread/commission →
**Run Backtest**. Then **Optimize Weights** (toggle "Apply if improved" to push them
live). "Disable no-edge" turns off strategies the test flags DISABLE.

New endpoints: `/api/backtest/run`, `/api/backtest/optimize-weights`,
`/api/backtest/weights[/reset]`, `/api/backtest/apply-verdicts`.
Note: a real edge measurement needs MT5 connected (real candles). With MT5 offline it
runs on synthetic data and says so — numbers are illustrative only.

## 2) De-gating — the bot now trades quality setups regularly
You were right that it was over-gated (one cluster in the morning, then nothing). The
engine had too many *hard* vetoes stacked on top of each other. Backtested, **balanced
mode took 0 trades** before this change. Fixes:
- **Pullback entries are no longer rejected.** The engine used to require a perfect M15
  EMA stack, which un-stacks during the exact OTE/pullback it wants. It now derives a
  *weak* direction from EMA-50 slope and takes the pullback as a **scout** entry when it
  agrees with the H4/D1 bias (instead of vetoing it).
- **Over-extension is graded**, not a single veto: a mild stretch is a scout flag; only a
  genuine chase (> 4.2 ATR from EMA-50) is blocked.
- **RSI is soft, not a hard veto**, unless truly extreme (>80 / <20) AND fighting the
  higher-timeframe bias — RSI can ride >70 in a real trend.
- **Looser, genuinely-balanced presets** (lower confidence/confluence/session floors).

After de-gating, **balanced mode takes ~90 trades** over the same backtest window with the
protections that matter still intact (news, spread, kill-switch, no-pyramid-into-loser,
counter-bias RSI extremes, no-structure chop, confidence floor, repeat-setup guard,
post-loss cooldown). Dial it with Settings → AI Strictness (relaxed ↔ sniper).

## Files
- `backend/services/backtest_engine.py` (new)
- `backend/services/decision_engine.py` — weak-alignment direction, graded gates,
  retuned presets, learnable factor weights, backtest session/news hooks.
- `backend/app.py` — backtest endpoints + candle source + factor-weight persistence.
- `frontend/src/pages/Analytics.tsx` + `lib/api.ts` — Backtest tab (bundle rebuilt).
