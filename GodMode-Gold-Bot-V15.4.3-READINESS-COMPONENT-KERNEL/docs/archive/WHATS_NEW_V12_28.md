# GodMode V12.28 — Multi-timeframe Validate + one-click H1 research preset

## What "trade on H1/H4" actually means
The bot makes its entry decisions on a **primary timeframe** (Settings → 5. Trading Defaults →
Timeframe; default M15). Setting it to **H1** means the engine reads **H1 candles** for signals,
structure and stops — so it genuinely *trades on H1*: far fewer, larger setups, wider structural
stops, longer holds. (It still reads H1/H4/D1 as higher-timeframe *context* regardless.)

Why it matters: on H1 a trade's stop might be ~15–25 points vs ~4–6 on M15, so your fixed spread
(0.24) drops from ~5–7% of risk to ~1–1.5%. **Cost stops eating the edge** — the single biggest lever
from the edge diagnosis, without inventing any new signal.

## Validate now runs at the selected timeframe (was hardcoded M15)
- The Backtest tab has a **Timeframe** selector (M5/M15/H1/H4). Backtest & **Validate My Edge** now
  pull history and replay the engine **at that timeframe** (previously always M15), with a sensible
  ~2-year sample auto-sized per timeframe. The verdict and result line show which timeframe was tested.

## One-click "Research preset: H1 + news"
A button in the Backtest tab that sets the timeframe to **H1** and applies the free ForexFactory news
link, so you can **Validate the higher-timeframe + cross-asset version against your own history without
hand-tuning**. It is **research only — it does NOT change live trading.** If (and only if) Validate
returns **GO**, switch live by setting Settings → 5. Trading Defaults → Timeframe = H1.

This is the honest path: prove the H1 edge on your history first, then trade it — instead of flipping
live blind.
