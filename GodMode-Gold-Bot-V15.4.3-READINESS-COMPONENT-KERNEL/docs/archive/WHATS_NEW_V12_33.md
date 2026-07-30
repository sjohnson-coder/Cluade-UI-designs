# GodMode V12.33 — One-click Efficiency Sweep (edit your costs, then test)

V12.32 let you **set** the trend-efficiency (chop) floor per mode. V12.33 lets you **find the right number on
your own data** — at the exact broker costs you type in — before you commit it.

## What it does
**Analytics → Backtest → "🧪 Efficiency sweep"** replays the SAME cost-aware engine over the SAME candles at
a range of trend-efficiency floors (0.18 · 0.24 · 0.30 · 0.36 · 0.42) and shows one comparison table:

| efficiency | trades | expectancyR | winRate | profitFactor | maxDrawdownR | oos | verdict |

The floor with the highest expectancy is flagged **◀ best**. That's your sweet-spot for the active mode —
copy it into **Settings → 4 → Trend-efficiency by mode**.

## Edit the cost before running (the headline)
The sweep uses the **Spread / Commission / Slippage** inputs already on the Backtest tab — so you edit your
real broker economics first, then sweep. Tighten the floor and trades drop but quality rises; loosen it and
you take more (choppier) tape. The table makes the trades-vs-expectancy trade-off explicit **at your costs**,
not at an optimistic default.

## Honest by design
- Runs on **your real MT5 history** when MT5 is connected; otherwise it clearly labels the result
  **synthetic / illustrative only** (numbers vary run-to-run on synthetic data — don't tune on them).
- It **never touches live trading**. The live strictness config is snapshotted before the sweep and
  restored in a `finally` block, so the engine you trade with is byte-for-byte unchanged afterwards.
- Verdicts use the same GO / CAUTION / LOW SAMPLE / NO-GO scale as Validate My Edge.

## Notes
- Runs as a background job (survives tab switches / reloads via the job store), with a progress bar per floor.
- New endpoint: `POST /api/backtest/efficiency-sweep-async` → `{jobId}`.
- UI verified clean and responsive at 360 / 390 / 1280 px — the results table scrolls within its own
  container on mobile (same pattern as the other backtest tables); no page-level overflow. Fonts, weights,
  Tag colors and card styling match the existing Analytics design exactly.
