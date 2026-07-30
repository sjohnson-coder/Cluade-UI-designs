# GodMode Gold Bot V12.58 — UI Freeze Watchdog + MT5 IPC Stabilisation

This build targets the issue where the dashboard and other pages start spinning/freezing after the bot has been running for hours, and buttons stop responding in real time.

## Root cause addressed

The bot was doing several slow operations at the same time:

- Dashboard refresh calling live market, trades and analytics.
- AppShell/top bar calling status, notifications and market snapshot.
- Auto-trading loop calling entry, management and signal watchdog.
- Telegram command loop and protected burst controls calling MT5.
- Trade history/analytics repeatedly reading MT5 history.

MetaTrader5 Python IPC can become unstable or slow when many threads hit the terminal at the same time. The old async background loop also called blocking MT5 work directly, meaning a slow MT5 operation could starve the FastAPI event loop and make pages/buttons appear frozen.

## Fixes added

### 1. MT5 IPC serialization
All broker-facing MT5Bridge calls are now serialized with a re-entrant lock. This prevents dashboard polling, trade management, Telegram controls and burst/pyramid actions from fighting each other inside the MT5 Python bridge.

### 2. Background loop no longer blocks the web server
Auto-entry, AI Dynamic SL management and fast sniper signal watchdog now run in worker threads with timeouts. If MT5 becomes slow, the web UI stays responsive and the slow operation is recorded in heartbeat state.

### 3. Dashboard stale-cache fallback
Dashboard, decision and trade refreshes now return the last good snapshot immediately if a refresh is already in progress. This avoids the repeated “rolling loader” problem when returning to Dashboard from another page.

### 4. Trade refresh cache
Closed trade history is now cached briefly. The bot no longer reloads 90 days of MT5 history on every dashboard/trades/analytics refresh cycle.

### 5. Frontend request timeout + cache fallback
The browser now aborts GET requests after a short timeout and shows cached data instead of spinning indefinitely. POST/action requests also have a timeout so buttons do not remain stuck forever.

### 6. Local rate limit increased
The local dashboard rate limit has been increased so normal UI polling does not accidentally throttle the app.

## Important note

This does not change trading strategy logic, AI Dynamic SL, protected burst, loss-feedback governor, or config library logic. It is a runtime stability/performance upgrade.

## Recommended use

After installing this build:

1. Close the old terminal.
2. Close any old browser tabs using the bot.
3. Start the bot fresh from the new folder.
4. Open only one dashboard tab initially.
5. Let it run for several hours and watch whether pages/buttons remain responsive.

