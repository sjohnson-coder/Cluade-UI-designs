# GodMode Pixel-Match Functional Fix 2

This patch applies the supplied CSS/design system as final overrides and fixes the functional issues reported after live testing.

## UI and CSS fixes
- Applied a stricter premium dashboard style system matching the provided dark/light mockup prompt.
- Restored deep navy/gold dark mode and clean ivory-white light mode tokens.
- Tightened sidebar width, topbar height, card radius, borders, button styling, tags, tables, rings, charts and responsive behaviour.
- Improved dashboard chart container sizing and added a safe chart fallback so the chart panel never renders blank silently.
- Added journal crown/logo treatment to entry rows and detail heading.
- Improved table wrapping at mobile widths while keeping compact desktop rows.

## Trading/functional fixes
- Trades tabs now actually switch the visible trade tables: All, Active, Pending, Closed, Canceled.
- Trade timeline now appears only when an active GodMode bot trade exists.
- Timeline events reveal progressively only when TP/BE/trailing conditions are reached.
- Live management card no longer shows fake trade-management values when there is no active trade.
- Close trade endpoint now caches just-closed trade requests immediately so the closed-trades history updates faster while MT5 history synchronizes.
- Modify/close actions now emit notifications.
- Signals endpoint now returns real trade-plan levels from the AI decision: entry, SL, TP1-TP4, RR, reason.
- Signal AI reason rendering bug fixed.
- Risk edit buttons now open a real editable risk panel and save to `/api/risk/update`.
- Analytics tabs now switch actual page sections and date range filters work locally against bot-only history.

## Tests
- Frontend TypeScript build: PASS
- Vite production build: PASS
- Backend Python compile: PASS
- FastAPI smoke endpoints: PASS
- Auto-trade heartbeat/check: PASS
- Risk update endpoint: PASS

## Note
True pixel-perfect browser rendering can still vary by screen size, zoom and OS font smoothing, but this version uses the supplied design-system CSS as the final global override.
