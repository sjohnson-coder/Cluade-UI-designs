# GodMode V13.52.0 — Final Critical Remediation and Verification

## Scope completed

- Authoritative `/api/readiness` and `/api/liveness` endpoints.
- UI can enter LIVE only from readiness and only when frontend/backend build IDs match.
- API-key recovery remains interactive on Settings while all trading mutations remain blocked.
- Stale `SUBMITTING` commands become `UNKNOWN`; they are never retried blindly.
- Automatic conservative broker reconciliation worker checks positions and active/history orders.
- Manual reconciliation no longer accepts an arbitrary terminal status.
- Partial closes require measured pre/post volume reduction within broker volume-step tolerance.
- Pending placement/cancellation require active-order or order-history evidence.
- Multi-target baskets use durable child commands with stable child execution IDs.
- Process-level single-instance lock prevents two backend processes owning one bot data directory.
- MT5 bridge IPC lock now includes pending-order and reconciliation query methods.
- Tick Guard 1.40 uses one heartbeat setting, broker tick size, stop level and freeze level.
- BREATH invariants are revalidated after distance adjustment and quantisation.
- CUT and stop modifications perform post-request position readback.
- Global UI error and unhandled-promise handlers force DEGRADED state.

## Verification performed

- Python compilation: PASS.
- Root pytest: 20 PASS.
- FastAPI OpenAPI generation: PASS.
- API paths generated: 163.
- Readiness and liveness routes present: PASS.
- Direct broker mutation scan: only designated serialized gateway functions call mutation methods.
- Version consistency in source: V13.52 / Tick Guard 1.40.
- Dynamic SL regression suite included in root test discovery: PASS.

## Important engineering truth

No trading system can be certified as absolutely bug-free by static analysis or unit tests. The following require the target Windows/MetaTrader/broker environment and therefore remain mandatory acceptance tests:

- MetaEditor compilation of the EA.
- Clean frontend dependency installation and production build.
- Live MT5 order/deal/history readback.
- Broker-specific stop/freeze and tick-size behaviour.
- Partial fills, delayed acknowledgements and terminal disconnects.
- Netting and hedging account behaviour.
- Multi-day soak, process-kill and restart reconciliation testing.

Run the included demo acceptance sequence before live trading. Keep auto trading disabled until readiness reports `ready: true` and all broker tests pass.
