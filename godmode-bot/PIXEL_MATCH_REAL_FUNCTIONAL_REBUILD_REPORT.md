# GodMode Gold Trading Bot — Pixel-Match Real Functional UI Rebuild

## Scope
This build restores the GodMode premium mockup design system while preserving the live MT5/backend functionality added in previous versions.

## UI rebuild completed
- Removed browser/address-bar frame from the actual app shell.
- Restored fixed 240px sidebar, 72px top header, compact premium cards, gold/green/red accents, thin borders, clean Inter/SF typography, white light theme and deep navy dark theme.
- Added SVG-style GodMode crown/logo treatment and AI node graphic in the dashboard strategy engine card.
- Light theme background is now white, not cream-heavy.
- Dark theme follows the deep navy/gold mockup language.
- Added responsive tablet/mobile layout protection.

## Functionality preserved/extended
- MT5 auto-connect backend remains active on startup.
- Settings live/dry-run/auto-trading switches remain connected to backend settings.
- Manual trade trigger remains wired to POST /api/trades/manual-trigger.
- Auto trading check remains wired to POST /api/auto-trading/tick.
- Trade close/modify/live management actions remain wired.
- Export buttons use /api/export.
- Telegram test remains wired to /api/telegram/test.
- API docs button opens backend API documentation information.
- Strategy configure save now calls /api/strategy/configure and closes the configuration card.
- Dashboard strategy engine now populates from enabled strategies in the Strategies tab.
- Strategies page now displays all strategies as cards.
- Analytics uses account currency from MT5 where available.
- Journal displays bot-only MT5 history and does not invent manual/demo trades.

## Live data policy
The UI no longer pretends that fake broker/account data is live. If MT5 is unavailable or there is no bot-only history, the UI shows waiting/empty states. Strategy catalogue/configuration data is still shown because it is bot configuration, not market/account data.

## Tests
- Frontend TypeScript build: PASS
- Vite production build: PASS
- Backend Python compile: PASS
- FastAPI smoke tests: PASS
- Manual trade endpoint dry-run validation: PASS
- Auto-trading tick guard: PASS
