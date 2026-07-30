# GodMode Gold Bot V12.47 — Execution Mode, Feed Sync & MT5 PnL Fix

## Fixed

### 1. Auto / Semi-auto switching
- Added a single authoritative execution mode: `execution.mode`.
- Dashboard Settings → Execution Control now has Auto / Semi-auto buttons.
- Telegram commands added:
  - `/auto` — switch to automatic execution
  - `/semi` — switch back to Telegram approval mode
  - `/mode` — show/change mode
- Telegram quick controls also include Auto Mode / Semi-Auto buttons.
- Fixed a legacy conflict where `telegram.semiAutoEnabled=true` could silently keep the bot in semi-auto even when `execution.mode=auto`.

### 2. Telegram timing
- Auto mode now bypasses Telegram TAKE/SCOUT approval delays when enabled.
- Semi-auto remains available for manual confirmation, but it is now explicit.

### 3. Telegram/MT5 PnL alignment
- Open-position PnL now uses MT5 floating position profit plus booked entry costs when available.
- Closed-trade history already reconstructs MT5 deals using profit + commission + swap; this remains the broker-truth source.
- Open positions expose `pnlGross`, `entryCosts`, `pnlUsd`, and `pnlSource` for easier debugging.

### 4. News/calendar/macro feeds
- Fixed a backend bug where Settings → Data Feeds refreshed old objects but not the actual dashboard `live_calendar` and `macro_feed` objects.
- Economic calendar, DXY, US10Y, and market-news URLs now apply immediately after Save & Apply Feeds.
- Feed errors are now visible in status detail instead of silently returning empty.
- API keys are appended as `apikey=` query parameters for retail APIs such as FMP and Alpha Vantage.
- Added an FMP DXY + US10Y template button in Settings.

## Notes
- The free ForexFactory JSON link can power live USD blackout checks, but it is not a historical backtesting news database.
- FMP economic calendar and quote endpoints require a valid FMP API key.
- Alpha Vantage news requires a valid Alpha Vantage API key and is rate-limited on free plans.
