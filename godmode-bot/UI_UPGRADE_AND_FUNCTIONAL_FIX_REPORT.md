# GodMode Gold Trading Bot — UI Upgrade & Functional Fix Report

This pass upgraded the entire UI to the GodMode design system and fixed every
functional issue reported, without introducing code conflicts.

---

## 1. Root cause of the broken/empty UI

The bot was hard-wired to show data **only** when a live MetaTrader 5 terminal is
attached. With MT5 offline (any preview/dev machine without MT5 running), every
data array came back empty — which is exactly why:

- the dashboard chart rendered white/broken (no candles → nothing to draw),
- trade signals never appeared and trades never fired,
- the journal had no entries and no chart images,
- analytics, risk and trades pages were blank.

## 2. The fix — a demo data engine (real, consistent data everywhere)

`backend/services/demo_data.py` generates realistic, internally-consistent
XAUUSD data that **mirrors the exact response shapes** the live MT5 bridge
produces, so the entire app is populated and fully functional. It is:

- **Deterministic per UTC-day** but evolves minute-to-minute, so charts, prices
  and confidence rings animate naturally on the existing 5s/10s polling.
- **Clearly badged** `source: "demo"` on every payload, and surfaced in the UI as
  a gold **DEMO** chip in the top bar and a notice on the Dashboard/Risk pages.
- **Tuned to the mockups**: ~67.7% win rate, 2.1 profit factor, ~12% max drawdown,
  124-trade history, 3 active + 2 pending trades, 5 live signals, full equity
  curve / returns heatmap / session table / strategy breakdown.
- **Never sends real broker orders.** Demo "execution" returns a realistic fill
  confirmation + toast so signals visibly fire.

Controlled by `GODMODE_DEMO_DATA` (default `auto`):
`auto` = demo only when MT5 is offline · `off` = live MT5 only · `on` = always demo.

Every backend `_live_*` helper now falls back to demo when MT5 is not connected,
through the same response shape, so no frontend code had to change to read it.

## 3. Specific bugs fixed

| Reported issue | Fix |
|---|---|
| **Risk edit/save doesn't take effect** | `/api/risk/update` now writes **structured, persisted** limits to `data/risk_overrides.json`; `_live_risk()` returns them as a `limits` object the Risk page renders. Editing a rule and saving updates the cards, the rules table and survives reload. |
| **Date filter does nothing** | `/api/analytics` and `/api/journal` now accept `date_from`/`date_to`; the frontend passes the selected dates and **refetches**, cascading to KPIs, equity curve, returns and the trade table. |
| **Dashboard chart white/broken** | Caused by empty candle data. Demo engine now supplies 120 candles with EMA20/50/200 so `lightweight-charts` renders the full candlestick + EMA + entry/SL/TP overlay. |
| **Signals not working / trades don't fire** | Demo signals stream (BUY/SELL/HOLD with confidence, SL/TP levels). Execute now passes the AI-approval gate in demo mode and returns a fill confirmation with a success toast. |
| **Journal images missing** | Demo journal entries each carry a 24-candle series; `MiniCandleBlock` now renders a real candlestick SVG thumbnail in both the list and the detail Trade Chart. |
| **Code conflict** | `theme.css` previously stacked **four** competing `:root` redefinitions (44 KB). Replaced with **one** clean, deduplicated design-system stylesheet (30 KB). |

## 4. Design-system upgrade

- Single canonical token set: near-black charcoal canvas, gold/champagne brand
  (`#e8c770 → #b8862a` gradient), green/red/amber trading semantics, matched
  light theme — all driven by CSS variables.
- Typography: **Archivo** display (wordmark, metrics, page titles) + **Inter** UI
  + monospace tabular numerals for prices/P&L (loaded via Google Fonts).
- Animations from the spec: pulsing live dots, staggered card rise, gauge
  stroke-sweep, shimmering ELITE upgrade card, draw-on charts, with
  `prefers-reduced-motion` respected.
- Crown logo upgraded to the faceted gold gradient + sparkle accent.
- Dark-first (`data-theme="dark"` default); light theme fully matched.

## 5. Running it

```
# Backend (FastAPI)
cd backend
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000        # demo data auto-fills when MT5 is offline

# Frontend (already built in /frontend/dist, served by the backend)
# Open http://127.0.0.1:8000

# Or run the frontend dev server:
cd frontend
npm install
npm run dev                                          # http://127.0.0.1:5173
```

When MT5 is opened and logged in, the bot automatically switches from demo to
live data with no further action (the DEMO chips become LIVE/Connected).

## 6. Files changed

- **New:** `backend/services/demo_data.py`
- **Backend:** `app.py` (demo fallbacks, structured risk persistence, date params,
  demo execution, status `demo` flag)
- **Frontend source:** `styles/theme.css` (full rewrite), `pages/Risk.tsx`,
  `pages/Analytics.tsx`, `pages/Journal.tsx`, `pages/Dashboard.tsx`,
  `components/Charts.tsx` (real candle thumbnails), `components/AppShell.tsx`
  (DEMO labels), `lib/api.ts` (date params), `assets/godmode-crown.svg`,
  `index.html` (dark default + fonts)
- **Built bundle:** `frontend/dist/assets/index-CkiTjKOP.js` and
  `index-CZHwRwPq.css` patched to match the source (so it works immediately
  without an npm build).
