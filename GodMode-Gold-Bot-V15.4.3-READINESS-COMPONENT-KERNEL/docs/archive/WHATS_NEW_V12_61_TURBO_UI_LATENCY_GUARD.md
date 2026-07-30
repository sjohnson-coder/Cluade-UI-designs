# V12.61 — Turbo UI Latency Guard

Focus: make the dashboard/pages/buttons stay responsive after long live sessions.

## Fixes

- Added Turbo UI cache: Dashboard/Trades/Analytics/Account/Market endpoints now return the last good snapshot instantly and refresh in a daemon background thread when stale.
- Removed the heaviest Burst-mode lag source: open positions no longer call MT5 history once per position. Entry commission/swap approximation is now batch-cached.
- Dashboard no longer waits for long-history analytics before painting. Analytics refreshes independently in the background.
- Trade history live UI now uses a shorter recent-history window; deep Analytics still handles deeper history separately.
- Frontend GET timeout reduced so a slow local endpoint cannot leave the app spinner frozen for a long time.
- Startup warms account, market, trade, analytics and dashboard caches in background without blocking the API.

## Expected behaviour

- Page switches should show cached data immediately.
- Buttons should respond quickly even if MT5 IPC is slow.
- Data may briefly show `stale: true` while a background refresh is running, but the UI should not freeze.
- Trading logic is not changed. Burst lot ladder and BE/fast-fail behaviour from V12.60 remain intact.
