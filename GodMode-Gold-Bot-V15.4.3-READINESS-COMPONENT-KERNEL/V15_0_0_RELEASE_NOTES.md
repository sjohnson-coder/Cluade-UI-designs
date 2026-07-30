# GodMode Gold Bot V15.0.0 — Enterprise Intelligence

V15 adds ten coordinated intelligence and runtime capabilities while preserving all V14.1.25 safety gates and Windows/MT5 workflows.

## Delivered

1. Multi-state regime intelligence and strategy suitability.
2. Multi-horizon calibrated probability forecasts for continuation, reversal, recovery, TP-before-SL, BE-first, fast-fail, Burst success and invalidation.
3. Broker-specific rolling spread, slippage, latency and fill-quality intelligence.
4. Missed-opportunity registration, replay, outcome classification and gate-pressure reporting.
5. Deterministic adaptive exit policy with hard-invalidation precedence, profit-floor ratcheting, time decay and asymmetric-loss control.
6. Burst expected-value evaluation with complete pass/fail gate trace.
7. Continuous calibration contracts and hybrid model governance with shadow requirements, approval queue and rollback.
8. Free-only external-context adapters with cache, stale state and failure isolation.
9. Explainable decisions with reason contributions, confidence, uncertainty and blockers.
10. Central V15 runtime state manager with serialised updates, revisioning, secret redaction and atomic Windows-safe persistence.

## Safety position

V15 runs as a governed intelligence layer. It does not bypass or replace the existing live-trading admission, risk, Tick Guard, broker, certification, kill-switch or reconciliation gates. Material model and policy changes require approval.

## New API

- `GET /api/v15/overview`
- `POST /api/v15/evaluate`
- `GET /api/v15/health`
- missed-opportunity registration/resolution endpoints
- governance candidate/approval/rollback endpoints
- free external-context read/refresh endpoints

## UI

The AI Agent page includes a V15 Enterprise Intelligence panel showing health, regime, probabilities, deterministic exit recommendation, expected MFE/MAE and Burst gate trace.
