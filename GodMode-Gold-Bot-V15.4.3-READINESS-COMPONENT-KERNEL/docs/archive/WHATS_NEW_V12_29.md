# GodMode V12.29 — Four alpha/realism upgrades + full responsive/style audit

## The four upgrades you asked for ("build all")

1. **Tick-style slippage in the backtest.** Backtest & Validate now charge a per-fill **slippage** on
   BOTH entry and exit (×2), on top of spread + commission — so scalping/M5–M15 results are honest
   about the fill you actually get. New "Slippage/fill" input on the Backtest tab; shown in the cost
   line. Set it to your broker's typical slippage for a faithful result.

2. **Learned per-session strategy memory.** The performance store now tracks every strategy's win-rate
   **per session** (London / NY / Asia). The strategy picker prefers a strategy's *in-session* win-rate
   once it has ≥5 samples there — so it adapts to what actually works in each session, not just overall.

3. **Cross-asset hard filter (DXY / US10Y).** Opt-in (Settings → 4): when a **live** DXY/yields feed
   shows a clear gold bias, the bot won't take a trade that fights it (no buying gold when the dollar/
   yields say down). Only acts when a feed is genuinely live — no feed, no filter.

4. **Enhanced regime classifier.** Regime detection now blends **ADX trend strength** + a **volatility
   percentile** + Kaufman efficiency + the HTF stack into one label *and a 0–100 confidence score*
   (shown on the Regime card). The AI Agent intel grid now shows **Trend Strength (ADX)** and
   **Volatility %ile**. Deterministic and explainable — not a black box.

## Full UI audit (responsive + style consistency)
- Swept all 9 routes × widths 360/390/768/1280 — **zero page overflow** everywhere; tables scroll
  inside their wrappers as designed.
- **Fixed** two narrow-screen (360px) overflows: a regression where long checklist values (e.g.
  "MetaTrader5 package missing") couldn't wrap, and long URLs/JSON in help text. Long `code` now wraps;
  section-header tags wrap below the title on small screens.
- All new controls reuse the existing components (Row / ToggleSwitch / NumberInput / IntelCell), so
  font family, size and weight match the original design exactly.
