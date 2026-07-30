# V15.0.3 Pre-Live Safety Hardened

This release adds an independent fail-closed pre-trade supervisor while preserving the audited V14 visual CSS.

## Safety additions
- Deployment modes: SHADOW, DEMO, LIVE_RESTRICTED and LIVE_FULL.
- Default release mode is LIVE_RESTRICTED, dry-run enabled, live and automatic trading disabled.
- Exact pre-submit checks for MT5 connectivity, trade permission, runtime readiness, reconciliation, live market source, tick freshness, spread, symbol, daily loss, consecutive losses, open-position count and equity drawdown.
- Restricted mode caps volume at 0.01 lot and disables Burst, Pyramid and multi-target entries by default.
- Every admission decision is durably journalled to `backend/data/pretrade_snapshots.jsonl` at runtime.
- Existing close, emergency-close and protective mutation paths remain available even when entry gates are locked.
- `/api/prelive/status` exposes the active mode, limits and supervisor health.

No strategy thresholds or V14 CSS styling were changed.
