# V13.50 Final Verification

## Completed verification

- All backend Python files parsed and compiled.
- Root-level pytest command completed: 7 tests passed.
- Execution ledger lease recovery tested.
- ACKNOWLEDGED orders are no longer falsely labelled FILLED.
- Broker-confirmed deals are labelled FILLED.
- SQLite connections now close deterministically after every operation.
- Multi-target order paths are routed through the serialized durable gateway.
- Telegram sizing failures now block execution rather than silently falling back.
- Dynamic SL breathing state is committed only after a successful broker modification.
- Failed SL modification clears pending breathing ownership.
- BREATH directives are published only with a confirmed stop.
- HOLD, CUT and BREATH directives now include creation time, expiry, build ID and sequence.
- MT5 Guard 1.20 rejects stale directives and unsafe breathing stops.
- Frontend export requests now include API-key authentication.
- Cached API fallback now includes stale age and triggers a visible global warning.
- Frontend request limits were increased to reduce false offline states.
- Frontend package declarations were aligned with the lock file.
- Static assertions confirmed only the centralized multi-target implementation directly calls the bridge.

## Environment limitations

The release environment did not contain a Windows MetaTrader 5 terminal, MetaEditor, broker account or live tick stream. Therefore MQL5 compilation, broker order fills, freeze-level rejection behaviour and real reconnect reconciliation must still be validated on a demo terminal before live use.

The frontend dependency installation could not complete within the build environment timeout, so a fresh Vite source build was not independently reproduced here. The included existing frontend distribution remains in the package, while the updated source must be rebuilt on the target machine using `npm ci && npm run build`.
