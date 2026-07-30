# GodMode Gold Bot V13.1 — TradingView-grade chart, live-trade-only markers

## The chart rebuild (finally, on its own version as promised)

### Realtime tick — the tape now moves
The old chart called setData() (full series rewrite) on every poll. Now the forming candle is
pushed through series.update(), the way a real tape ticks. Full reloads only happen on
timeframe switch or data gaps. Everything anchored to price moves smoothly, live.

### Markers ONLY when a trade is live — and they MOVE with price
  • The historical WIN/LOSS confetti and "AI bias" arrows are GONE. The chart shows the market,
    and decorates it only with the position you actually hold.
  • While a trade is open: one entry arrow at your fill, plus ENTRY/SL/TP price lines built from
    the REAL position fields (entryPrice/sl/tp) — never fabricated. They vanish on close.
  • Price lines are persistent handles updated in place (applyOptions) — they GLIDE when trade
    management moves your SL/TP; the old chart destroyed and re-created them every poll (blink).
  • NEW: a live P&L badge rides the current price line (repositioned via priceToCoordinate on
    every tick and pane resize): direction + lots + live +/-USD, green in profit, red in
    drawdown. This is the marker that moves in realtime as price moves.

### TradingView furniture
  • Timeframe switcher M1/M5/M15/M30/H1/H4/D1 — backed by a NEW endpoint
    GET /api/market/candles?tf=&count= (per-TF cache: 2s on M1/M5, 20s higher; clamped 50..1500)
    so switching TF never touches your global trading timeframe and costs ~1.6ms warm on repeat.
  • Volume histogram in its own scale margin.
  • OHLC legend following the crosshair, champagne-bronze crosshair labels, price precision 0.01,
    right-offset breathing room, theme-reactive without remounting.

## Engineering notes
  • Chart is created ONCE; candles, lines, markers, badge all update in place. No remount, no
    white flash.
  • Stale-closure hazard fixed properly: the badge reads the live trade through a ref, so the
    resize/range subscriptions captured at creation always see current state.
  • Dashboard now passes liveTrade explicitly; markers/lines are gated on ticket presence.

## BUILD RISK — same honesty as V13.0
No npm in my sandbox: these React changes are NOT compiled/typechecked. Mitigations: brace
balance verified on both edited files, imports limited to lightweight-charts 4.2 public API
(createChart/addCandlestickSeries/addHistogramSeries/createPriceLine/IPriceLine — all v4), no
new icon imports, backend endpoint fully tested. If the build errors, send the exact message.

## Validation
Boot 0.093s. /api/market/candles: M5/H1 ok, bad TF falls back to M15, count clamped, cache hit
1.6ms. Full backend regression green. All V12.99.x + V13.0 fixes intact. No defaults changed.
