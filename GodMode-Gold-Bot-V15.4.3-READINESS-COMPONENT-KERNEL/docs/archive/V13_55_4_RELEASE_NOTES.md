# GodMode Gold Bot V13.55.4

## Dynamic SL unification
- AI Dynamic SL is the sole winning-stop owner while enabled. Legacy BE/trailing remain fallback-only when the master is off.
- Maximum giveback now controls peak-profit lock directly; legacy `profitLockFraction` no longer overrides it.
- TP extension requires the Dynamic SL continuation score and no invalidation.
- Position management uses Bid for BUY and Ask for SELL.
- SL/TP prices are normalized to broker tick size and digits.
- Widening risk uses MT5 `order_calc_profit` first, then live tick value/tick size fallback.
- Cached recovery decisions are rejected when stale, wrong-symbol, or wrong-direction.
- RECOVER widening and non-structural CUT require consecutive confirmation.
- Protection-state read/write failures are reported to logs and runtime health.

## UI
- Existing visual styling is unchanged.
- Legacy BE/trailing controls are hidden in source while AI Dynamic SL is enabled.

## Tick Guard status
The `.mq5` source is included. A compiled `.ex5` is not included because MetaEditor is unavailable in the build environment. Tick Guard must be compiled on the target Windows/MT5 machine. The manifest marks tick-level protection incomplete until this is done.

## Verification
- Python compile: passed
- Backend tests: 58 passed
- Frontend source updated. Clean Vite rebuild could not be completed because the package registry returned repeated HTTP 503 responses. Existing `dist` is retained, so the backend corrections are usable, but the conditional UI hiding change requires running `REBUILD_DASHBOARD.bat` on a machine with npm access.
