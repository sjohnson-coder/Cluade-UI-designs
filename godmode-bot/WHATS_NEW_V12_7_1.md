# GodMode V12.7.1 — Chart data integrity (the "candles don't match" fix)

Follow-up to V12.7, targeting your M15 screenshot where the Telegram chart still didn't match.

## What was actually wrong
The candle OHLC the bot draws **is** real MT5 data — but the alert chart was sourced through
`_live_market()`, which **silently falls back to synthetic DEMO candles whenever the bot isn't
connected to MT5** at that moment. So if a forecast/alert fired during any disconnect, it drew
**fake candles** that look nothing like your real XAUUSD — exactly the mismatch you saw.

(The times were never the issue: MT5 returns candle time in **broker/server time**, and the axis
reproduces that, so it already lines up with your platform. The old caption just mislabeled it "UTC".)

## The fix
1. **Alert charts now draw REAL connected MT5 candles only** — the synthetic demo fallback is removed
   from the alert path. If MT5 isn't connected, the alert sends **text-only** (no misleading chart)
   and says *"No chart = MT5 not connected."* A live alert can no longer show fake candles.
2. **Exact OHLC stamped on every chart** — e.g. `O4032.66 H4035.16 L4031.28 C4031.84`. This must
   equal your MT5's last M15 candle readout (top-left of your chart). If it matches, the data is
   correct and any visual difference is just window/zoom; if it doesn't, you're disconnected or on
   a different symbol — now you can tell instantly.
3. **Date + server-time axis** — ticks now read `06/25 09:43` (broker/server time, matching your
   platform) so you can align it bar-for-bar.
4. Caption corrected: *"real MT5 {TF} candles, server-time axis (matches your platform)."*

## How to verify (30 seconds)
1. Make sure the dashboard shows **MT5: Connected** (Settings → 2). If it's offline, that was the
   cause — the bot was drawing demo candles.
2. On the next alert, compare the **O/H/L/C printed on the chart** to the O/H/L/C at the top of your
   MT5 **M15** chart. They should be identical.
3. If you get a **text-only** alert with "MT5 not connected", reconnect MT5 — charts return
   automatically once live.

Backend compiles ✓ · time/OHLC label logic unit-tested ✓ · no frontend change.
