# GodMode Gold Bot — V15.4.3 Sustained Burst Intelligence

**Current release:** `V15.4.3-READINESS-COMPONENT-KERNEL`

V15.4.3 upgrades Protected Burst from a loosely observed simultaneous batch into a fully gated, sustained-confidence execution subsystem while retaining the V15.2.9 Qualified Peak Runner and deterministic trade-management stack.

Key changes:

- Uses MT5 `trade_mode` to identify demo, contest and real accounts accurately.
- Retains Claude's resolved Telegram Burst ON/OFF state correction.
- Fires an immediate two-leg or three-leg batch after every gate is satisfied.
- Arms against the real deterministic break-even threshold rather than an approximate spread buffer.
- Requires confidence and continuation to remain qualified across several scans before submission.
- Recalculates complete basket risk after broker minimum/step lot rounding.
- Preflights every leg and rolls the batch back if atomic execution fails partway through.
- Gives Burst legs independent `BURST_PROBE`, `BURST_CONFIRMED`, `BURST_RUNNER` and `BURST_DEFENSIVE` management states.
- Applies stricter Burst stop-loss, break-even, trailing and fast-fail rules without weakening the base trade.
- Adds a live dashboard trace showing every passed, waiting and failed Burst gate.
- Uses a distinct backend, frontend, launcher, Telegram and Tick Guard build identity.

Start here:

1. Extract the release into a new folder.
2. Close every previous GodMode backend command window.
3. Run `START_GODMODE.bat`.
4. Run `VERIFY_ACTIVE_BUILD.bat` and require `PASS` for `V15.4.3-READINESS-COMPONENT-KERNEL`.
5. Compile and attach the supplied Tick Guard before live certification.
6. Keep validation lock active during demo forward testing.
7. Review the Protected Burst card on the dashboard before permitting complex entries.

The packaged release is deliberately disarmed and `LIVE_RESTRICTED`. Protected Burst will remain blocked until certification and complex-entry permissions are explicitly satisfied.

See `V15.4.3_DONE_AND_VERIFICATION.md` for the complete Definition of Done, risk boundaries and verification evidence.

---

# GodMode Gold Bot V14.1.15 — Broker Admission Hardened


> **V14.1.15 broker-admission and enterprise live hardening**
>
> Start with [V14_1_15_RELEASE_NOTES.md](V14_1_15_RELEASE_NOTES.md), review
> [V14_1_15_SECURITY_AND_RELIABILITY.md](V14_1_15_SECURITY_AND_RELIABILITY.md), then complete the
> target-machine gates in [V14_1_15_VERIFICATION_REPORT.md](V14_1_15_VERIFICATION_REPORT.md).
> Telegram manual trading, break-even, and trailing commands are documented in
> [TELEGRAM_MANUAL_CONTROLS_V13_55_1.md](TELEGRAM_MANUAL_CONTROLS_V13_55_1.md).
> Live trading remains disabled by default. V14.1.15 also defaults to a
> build-bound unattended-live certification lock: target Windows/MT5, broker,
> failure-drill, TLS, backup/restore, and demo-soak evidence must all pass before
> a live entry can be approved.

## V12.46 update — Multi-Timeframe Sniper Bias Matrix

The fast sniper lane now uses M5 as the trigger, M15 as the setup context, and cached M30/H1/H4/D1 bias scoring as the higher-timeframe guard. This keeps entries fast without trading M1/tick noise or fighting strong H4/D1 direction.

# GodMode Gold Trading Bot — Premium Dashboard Redesign

This package upgrades the bot into a modern full-stack dashboard:

- FastAPI backend with all UI-facing endpoints
- React 18 + TypeScript + Vite frontend
- Soft luxury light mode and deep navy/gold dark mode
- Persistent instant theme switching
- Dashboard, Signals, Strategies, Trades, Risk, AI Agent, Analytics, Journal, Settings pages
- Mock data fallback when real MT5/backend data is unavailable
- Safe trade-action endpoints with live trading disabled by default

## Run Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open API docs:

```txt
http://127.0.0.1:8000/docs
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```txt
http://127.0.0.1:5173
```

## Change API Base URL

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Live MT5 Safety

Live order sending is disabled by default. `/api/trades/execute` returns a dry-run response unless this environment variable is explicitly enabled:

```env
GODMODE_ENABLE_LIVE_TRADING=true
```

Only enable this on a demo account after broker-specific validation is added and tested.

## Added Backend Endpoints

```txt
GET  /api/status
GET  /api/account
GET  /api/market/snapshot
GET  /api/dashboard
GET  /api/signals
GET  /api/strategies
GET  /api/trades
GET  /api/trades/active
GET  /api/trades/pending
GET  /api/trades/history
GET  /api/risk
GET  /api/analytics
GET  /api/journal
GET  /api/settings
GET  /api/ai/decision
GET  /api/strategy/arsenal
GET  /api/all

POST /api/trades/execute
POST /api/trades/execute-multi-target
POST /api/trades/close
POST /api/trades/modify
POST /api/settings
POST /api/strategy/enable
POST /api/strategy/disable
POST /api/risk/update
```

## What Is Included

The frontend includes reusable components for the app shell, sidebar, topbar, cards, metrics, gauges, progress bars, tags, tables, market chart overlays, strategy cards, signal details, risk panels, journal entries, and settings controls.

The backend includes a safe MT5 bridge stub plus realistic data services so the UI works even before connecting to a live terminal.


## GodMode AI Decision Engine Upgrade

The upgraded backend includes `services/decision_engine.py`, a deterministic gold-trading decision layer that scores market regime fit, strategy historical edge, current confluence, spread/execution quality, volatility fitness, session context, risk/reward potential, and skip discipline. It exposes `/api/ai/decision` and `/api/strategy/arsenal`. This is intentionally deterministic and auditable; any external LLM should be used for explanation, research, and optimization review, not raw autonomous order execution.

## TP1–TP4 Support

The backend supports TP1, TP2, TP3, and TP4 in the data model and the UI. `/api/trades/execute-multi-target` returns a safe dry-run plan by default and, when live mode is explicitly enabled, can split a trade into child positions for partial target management.

## Institutional Intelligence Upgrade Added

This version adds backend modules and API endpoints for:

- Walk-forward backtesting
- Monte Carlo testing
- Strategy-by-strategy performance memory
- Session-specific win-rate memory
- Spread/slippage memory
- Economic calendar and news blackout filter
- DXY / US10Y / macro gold-bias awareness fallback layer
- Gold volatility regime detection
- Trade replay engine
- Probability calibration from recorded outcomes
- Live trade-management decision engine for TP1-TP4
- Post-trade auto-journaling
- Broker execution quality scoring
- Overfitting guard
- Emergency kill switch
- 11-strategy institutional XAUUSD arsenal
- Deterministic trader-question decision logic

New endpoints include:

```txt
GET  /api/market/intelligence
GET  /api/calendar/economic
GET  /api/macro/gold-context
GET  /api/market/volatility-regime
GET  /api/news/blackout
GET  /api/memory/performance
POST /api/memory/record-trade
POST /api/journal/auto
POST /api/backtest/walk-forward
POST /api/backtest/monte-carlo
GET  /api/replay/trade/{trade_id}
GET  /api/calibration/probability
POST /api/trades/manage-live
GET  /api/broker/execution-quality
GET  /api/overfitting/guard
GET  /api/emergency/kill-switch
POST /api/emergency/kill-switch
POST /api/emergency/reset
POST /api/trades/execute-multi-target
```

The decision engine is deterministic and auditable. External AI should be used as a supervisor/reviewer, not as the direct order trigger.


## AI-Controlled Pyramiding Upgrade

Added backend and UI support for AI-controlled pyramiding, Hold, Break-even, Trailing, TP Push and TP1–TP4 runner management. New endpoints: /api/ai/super-intelligence, /api/pyramiding/plan, /api/pyramiding/execute, /api/trade-management/status, /api/ui/feature-map. The system is deterministic and auditable, but true 90%+ live performance still requires real data feeds, walk-forward testing and demo-forward validation.


## REAL FEEDS AND EXECUTION UPGRADE

Added provider-ready live integrations and institutional execution modules:

- Real economic calendar adapter with blackout window logic
- DXY feed adapter
- US10Y/yields feed adapter
- MT5/CSV tick-data backtester
- Broker-specific tick-value lot sizing
- TP1–TP4 partial-close endpoint
- MT5 trailing-stop modifier endpoint
- AI pyramid execution with exposure validation
- Trade screenshot/chart replay storage
- Strategy versioning and parameter version tracking
- Forward-test report generator
- Daily AI performance review

Live trading remains dry-run safe unless `GODMODE_ENABLE_LIVE_TRADING=true`. Real external data requires setting the relevant `GODMODE_*_URL` and key variables in `.env`.


## FINAL_UI_INTERACTION_AUDIT

This version removes the cream/oval background from the new feature sections and forces them to inherit the same white dashboard surface and dark-mode variables as the original pages. The global theme toggle applies to every page and every newly added feature card.

A global ActionCenter now gives every visible button/switch immediate feedback and routes important controls to safe backend hooks where available. Live trading actions remain dry-run/safety-gated unless `GODMODE_ENABLE_LIVE_TRADING=true` is explicitly set.

## Latest Upgrade: Protected Aggressive Lot-Scaling Pyramid

The pyramiding engine has been upgraded from reduced-size add-ons to protected aggressive lot scaling. It now supports a base lot such as `0.01`, then Add 1 at `0.02`, Add 2 at `0.03`, and a final capped max-lot add from settings.

This mode is still protected by strict controls: break-even plus costs, two-win streak gate, profit-buffer funding, no-news gate, spread/slippage checks, broker execution score, structure validity, margin floor, total lot cap, stack risk cap, exposure cap, and fast guard.

New API endpoints:

- `GET /api/pyramiding/settings`
- `POST /api/pyramiding/settings`

See `PYRAMIDING_PROTECTED_LOT_SCALING_UPGRADE.md` for the exact rules.

## V12.45 Low-Latency Sniper Lane
Added M15-context / M5-trigger fast lane, faster Telegram approval buttons, faster callback polling, and /api/fast-sniper/status. See WHATS_NEW_V12_45_LOW_LATENCY_SNIPER_LANE.md.

## V12.47 note
This build adds explicit Auto/Semi-auto execution mode switching from both Settings and Telegram, fixes feed settings persistence into the actual live feed objects, and aligns Telegram/open-trade PnL more closely with MT5 broker PnL by including booked entry costs when available.
