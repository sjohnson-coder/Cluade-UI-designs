# GodMode V12.7 — Directional Fix (takes BUYS again), Honest Charts & Live Feeds

This release treats every concern from your screenshots (IMG_5918–5921), without omission.

---

## 1) THE BIG ONE: "it only takes SELLs, never BUYs" — fixed
Your screenshots showed a strong XAUUSD **uptrend** (3980 → 4045) and the bot printing **BUY**
forecasts (4015–4032) that all would have won — yet every one was **blocked at 65–68%
confidence vs the 72% threshold** and labelled *"No-Trade / Standby Strategy."*

**Root cause (a systematic short bias in trends):** the bot measured "lateness" and
"over-extension" as distance from the **lagging EMA-50**. In a strong rally price is naturally
far above EMA-50, so:
- the **timing score collapsed to ~20** (out of 95) for buys, and
- **over-extension** flagged the buy as "chasing" → scout/blocked,

while a counter-trend **sell** (price near the EMA after a dip) scored high on both. So the bot
**faded every rally and took only shorts** — exactly what you saw.

**The fix — trend-aware entries.** When price is in a confirmed trend (slow **EMA-50 rising/falling
≥ 0.35 ATR over 10 bars**, price on the trend side, side matches), the bot now:
- anchors "lateness" and over-extension to **EMA-20** (the pullback anchor a trend hugs), not the
  lagging EMA-50 — so a trend pullback isn't punished as a chase;
- gives **partial pullback credit** to trend continuation (so it doesn't sit out the whole move
  waiting for a deep retrace that never comes);
- treats an **elevated RSI as "manage tightly," not a veto** (RSI rides 70–85 in real trends; only
  a true parabolic >88, or RSI fighting the higher-timeframe bias, hard-blocks now);
- **classifies efficient trends correctly** so a real trend strategy is selected instead of Standby.

**Proven in simulation** (drives the real engine on a reconstructed version of your chart): the
trend BUY now returns **TAKE_TRADE · BUY · 78% confidence · STANDARD · "Liquidity Sweep + OB
Retest"** — where before it was skipped < 72%. Chop is still rejected (the change is gated on a
genuine trend; the choppy-range hard-block is untouched), so this does **not** reopen the
range-trading problem.

> This is symmetric: in a **downtrend** the bot now rides trend-aligned **sells** the same way.

## 2) Hedge mode "didn't trade the buys" — same root cause, now fixed
Your forecasts were **flat** (no open position), so hedge mode (which only adds a 2nd position
*alongside an open one*) was never even in play — and the hedge scalp requires **STANDARD/SNIPER**
quality, which the over-extension penalty was denying your buys (they were SCOUT). With the gate
fixed, trend buys now reach STANDARD, so **both** first entries **and** hedge scalps fire on them.
Hedge mode has no buy/sell restriction — it takes whatever side the engine computes.

## 3) Telegram chart candles "don't match my chart" — fixed
The chart plotted **real** MT5 candles but: (a) it had **no timeframe label** and (b) **no time
axis**, and the bot trades **M15** while your platform screenshot is **M5** — so they could never
line up. Now every chart:
- is **titled with the timeframe** (e.g. `XAUUSD · M15  BUY`),
- has a **real UTC time axis** drawn from the candle timestamps (so you can align it bar-for-bar),
- carries a caption: *"Chart is M15 (the timeframe the bot trades) — set your platform to M15 to
  match the candles,"*
- and is **watermarked "DEMO DATA"** if the feed is ever synthetic/disconnected, so a non-live
  image is never mistaken for your broker's.

Set your MT5 chart to **M15** and the candles will match the alert.

## 4) Live macro & news feeds — real, not a hidden stub
The macro/intermarket model and the economic-calendar news gate are now **fully configurable and
honest**:
- Unconfigured, macro is **genuinely NEUTRAL** (the old display feed silently injected a constant
  *bullish-gold* tilt — that hardcoded stub is gone; it now contributes **no tilt** with a small
  neutral dead-band), and the news gate **doesn't invent blackouts**.
- Add your own endpoints in **Settings → 12c. Data Feeds**: DXY, US10Y and a ForexFactory-style
  economic-calendar URL (+ optional keys). Configuring once now drives **both** the decision engine
  and the display feeds (the two used different env-var names before — unified).
- Live/stub status is exposed at **`/api/feeds/status`**. Changes take effect immediately on Save.

---

## Settings added
- **12c. Data Feeds (Live Macro & News)** — DXY / US10Y / economic-calendar URLs + keys.

## Validation
Backend compiles ✓ · frontend builds ✓ · **4 simulation suites pass** (directional, profit
protection, volatility sizing, live-feeds neutrality). No contradiction with chop protection,
fast-fail, smart protection, sizing, pyramiding, or hedge mode.

### Tuning notes (Settings)
- If you want even more trend participation, lower **AI → Scout/Standard Confidence %**.
- The trend relaxation is intentionally gated on a real trend; in chop the strict gates remain.
