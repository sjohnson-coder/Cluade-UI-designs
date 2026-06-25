# Final MT5 Auto-Connect + Premium UI Functional Fix

## Fixed
- Removed the fake/local address bar from the top of every page.
- Added backend startup MT5 auto-connect. If MetaTrader 5 is already running and logged in, the backend attempts to attach automatically when the bot starts.
- Added `/api/mt5/auto-connect` for manual re-trigger from Settings.
- Restored dark theme by adding final dark-mode CSS variables after the late light-theme overrides.
- Added date filters to the Trades page.
- Strategy configuration card now closes automatically after a successful save.
- Analytics uses MT5 account currency from the backend instead of a hard-coded pound sign.
- Analytics “View Full Report” is now separated from the notes text.
- Restored premium ivory/white/gold card styling, sidebar width, topbar height, spacing, borders and responsive breakpoints.
- Upgraded live chart styling with a cleaner responsive premium chart shell and live price badge.
- Disabled unnecessary page/card animations and kept only subtle hover/focus transitions.

## Runtime behaviour
- Live MT5 data appears only when the MetaTrader5 Python bridge can attach to your running/logged-in MT5 terminal.
- Live order execution still requires Live Trading ON and Auto Trading ON.
- Dry-run remains the safe default unless you deliberately switch live mode on in Settings.

## Tested
- Python backend compile: PASS
- FastAPI key GET endpoints: PASS
- FastAPI key POST endpoints: PASS
- Frontend TypeScript/Vite production build: PASS
