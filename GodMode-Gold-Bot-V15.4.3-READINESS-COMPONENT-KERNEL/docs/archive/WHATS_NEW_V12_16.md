# GodMode V12.16 — Responsive QA: zero horizontal scroll, phone → monitor

A focused layout-quality pass. **No trading logic changed.** It guarantees every page and
every new tab fits its screen with **no horizontal scrollbar**, from a 360px phone up to a
1920px monitor — verified by an automated sweep, not by eye.

## What was broken (all pre-existing)
1. **Laptops (≈1366–1700px):** the top bar + page header were one non-wrapping row, so on a
   1440px laptop the status chips and buttons ran past the right edge and forced the whole app
   to scroll sideways.
2. **Phones — Signals / Trades / Strategies / Risk / Journal:** these pages use a *main column +
   side panel* grid. When it collapsed to a single column on smaller screens it used CSS `1fr`,
   which is really `minmax(auto,1fr)` — and `auto` refuses to shrink below the widest content in
   the column (a 12-column history table, a long strategy description). So the single "column"
   inflated to ~1000–1200px and dragged the entire page — including the side panel's full-width
   buttons — into horizontal scroll, on every phone width.
3. **Phones — Analytics overview:** the weekly-returns grid (`ReturnsHeatmap`) used fixed `1fr`
   columns that wouldn't shrink below `10.27%`, bloating to ~394px inside a 390px screen.
4. **Narrow phones (≤360px) — Settings:** a long system-status value (the MetaTrader5 module
   line) was `white-space:nowrap` and spilled ~10px past the edge.

## The fixes
- **Top bar / page header now wrap** at ≤1720px — only when the controls genuinely don't fit, so
  wide desktops are untouched.
- **Every main+side layout now collapses with `minmax(0,1fr)`** instead of `1fr`
  (`.layout-right`, `.responsive-two`, `.analytics-layout`, `.risk-layout`, `.journal-layout`,
  dashboard). The column can now shrink to the screen, and wide tables scroll **inside their own
  card** (intended) instead of stretching the page.
- **Returns grid collapses cleanly** — `minmax(40px,64px) repeat(5,minmax(0,1fr))` with
  `min-width:0` cells.
- **Long status values wrap** instead of forcing width.

## Validation
Backend compiles ✓ · frontend builds ✓ · automated overflow sweep across
**9 widths (360 / 390 / 768 / 1024 / 1180 / 1366 / 1440 / 1536 / 1920) × 11 page+tab
combinations** (Dashboard, Analytics, Decisions, Backtest, Strategy Lab, Risk, Settings,
Signals, Trades, Strategies, Journal) — **no genuine page overflow anywhere.** Wide data tables
still scroll horizontally inside their card on a phone, which is the intended behaviour.
