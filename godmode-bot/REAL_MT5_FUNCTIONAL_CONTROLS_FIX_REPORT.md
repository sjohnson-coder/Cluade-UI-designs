# GodMode Gold Trading Bot — Real MT5 Functional Controls Fix

This build fixes the UI/backend disconnects reported after the real-data build.

## Fixed

- Removed the fake `app.godmodegoldbot.com` browser-bar branding.
- Added real MT5 connection controls in Settings:
  - Auto-connect to currently running/logged-in MT5 terminal.
  - Optional terminal path.
  - Optional login/server/password manual login.
  - Refresh/connect buttons.
- Added runtime switches:
  - Dry Run switch.
  - Live Trading switch.
  - GodMode Auto Trading switch.
  - AI Approval Gate switch.
- Settings now persist to `backend/data/settings.json` at runtime.
- Live execution requires both Live Trading ON and Auto Trading ON.
- Export buttons now open real export endpoints.
- Filter buttons now open real UI filter panels.
- Strategy Configure now opens an editable panel and saves to backend strategy state.
- Live management controls now call real backend endpoints.
- Refresh buttons now reload real backend state.
- API Documentation button opens `/docs` and displays required/optional API keys.
- Telegram Test button now calls Telegram API and validates token/chat ID.
- Removed unnecessary page/card hover animations for smoother UI.
- Improved spacing, wrapping, responsiveness, table overflow and card alignment.
- Pyramiding no longer generates a fake/demo plan when there is no active GodMode bot trade.
- Forward reports and daily AI review no longer generate fake performance if no real bot history exists.

## Required keys

For basic MT5 connection: none if MT5 is already open and logged in.

Optional:
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for Telegram alerts.
- `GODMODE_API_KEY` and `VITE_GODMODE_API_KEY` for local API protection.
- Macro/news feed URLs/keys for DXY, US10Y and economic calendar integrations.

## Safety

The package ships with no saved `settings.json`, so default execution starts in dry-run mode.
