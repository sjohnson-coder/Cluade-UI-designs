# GodMode V12.22 — Real background jobs, Journal fixes, responsive top bar, Mac support

A big usability pass addressing everything in your last report.

## 1) Backtests & Strategy Lab now TRULY run in the background (with a Stop button)
Before, the progress bar lived inside the tab, so switching tabs lost it (the server job kept running,
but the UI couldn't see it). Now a **module-level job store** owns the run:
- Start a Backtest / Validate / Strategy Lab job, then **switch tabs or pages freely** — come back and
  the **live progress bar is still there**, and the **result appears even if you were away** when it
  finished.
- Every run has a **■ Stop** button (new `POST /api/jobs/{id}/cancel`) — the job ends cleanly within a
  step.

## 2) Journal page — fixed and finished
- **New Journal Entry** now works: a form (date, symbol, side, outcome, PnL, strategy, session,
  lessons, what-I'll-do-differently, notes). Saved to disk (`POST /api/journal/entry`) and shown next
  to the bot's auto trade-journal entries — survives restarts.
- **Date range** now has **Date From *and* Date To** (was start-only).
- **Search** matches the app styling (icon inside a proper field) and filters entries live as you type.
- Dead "More Filters" / placeholder controls removed.

## 3) Top bar is responsive again (incl. zoomed-out Chrome)
Adding the "Market" chip had crowded the bar. At ≤1720px (and when you zoom out) the bar now
**condenses into one clean row** instead of wrapping/distorting: the non-functional search box is
dropped, status chips compact, the theme toggle becomes icons; and the lowest-priority chips (Session,
Spread) drop first on mid widths. Verified across 360 → 1920px and at 90%-zoom-equivalent widths.

## 4) Analytics → Trades: pagination
The Trades tab is now paginated (15/page, First/Prev/Next/Last) so long histories stay usable.

## 5) Run it on a Mac (iMac/MacBook) — one-click, like Windows
- **`START_HERE_MAC.command`** — double-click to start (sets up Python + deps the first time, opens the
  dashboard). **`start_backend_mobile_mac.command`** for phone/LAN access.
- **`RUN_ON_MAC.md`** explains setup *and* the honest limitation: MetaTrader 5's Python API is
  **Windows-only**, so live MT5 trading needs Windows. On a Mac the dashboard/analytics/backtests run
  in demo mode — best practice is to run the bot on a Windows PC/VPS and view it on the iMac via the
  secure remote access (Settings → 13 + Tailscale).
- Shipped as **two zips**: a Windows zip and a Mac zip (with the Mac one-click launchers).

## 6) Full manual
**`GODMODE_COMPLETE_GUIDE.md`** — every page/button explained, the testing workflow (Validate → demo →
live), why-it's-not-trading reasons, and a safe go-live checklist.

## Validation
Backend compiles · frontend builds · background job start→cancel verified live ("Stopped by you") ·
journal entry POST verified · responsive sweep across 11 widths × 11 pages.
