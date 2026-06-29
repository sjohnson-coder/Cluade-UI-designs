# GodMode V12.32 — Trend efficiency exposed (per-mode chop filter)

You can now **manage the trend-efficiency (chop) threshold** directly — the exact number behind the
"Choppy/range market: trend efficiency 0.20 < 0.24" block.

**Settings → 4. AI Strictness → "Min Trend Efficiency per mode (chop filter)"** — one value per strict
mode (Relaxed / Balanced / Strict / Sniper), editable. The value for your **active** mode applies live;
the rest are remembered for when you switch (same pattern as the per-mode confluence control).

- **Lower it** (e.g. Relaxed 0.24 → 0.18) to trade choppier tape — more trades, more whipsaw risk.
- **Raise it** to take only clean trends.
- Below ~0.18 you're trading near-random noise — backtest first.

Engine reads `ai.efficiencyByMode`; the active mode's value drives the chop gate (and `minEfficiencyRatio`
still overrides if set). Defaults unchanged: Relaxed 0.24 · Balanced 0.30 · Strict 0.36 · Sniper 0.42.
