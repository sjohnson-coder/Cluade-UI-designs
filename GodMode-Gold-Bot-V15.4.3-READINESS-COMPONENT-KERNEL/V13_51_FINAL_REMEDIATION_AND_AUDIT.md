# GodMode V13.51.0 Full Transactional Remediation and Independent Re-Audit

## Release verdict

V13.51.0 corrects the release-blocking defects identified in the two V13.50 audits. Backend compilation, route generation, expanded regression tests and static transaction-path scans pass. Live broker behaviour still requires demo verification because MetaTrader 5 and a broker terminal are unavailable in the build environment.

## Critical corrections completed

1. ACKNOWLEDGED and UNKNOWN executions remain blocked until explicit reconciliation. They cannot be retried when a lease expires.
2. MT5 nested result objects are normalised before FILLED, PARTIAL or ACKNOWLEDGED classification.
3. Every broker mutation now uses the same process lock and durable ledger: open, multi-target open, close, partial close, SL modification, TP modification, pending-stop placement and pending cancellation.
4. Broker mutations require position or order readback. Inconclusive outcomes become UNKNOWN and block subsequent live actions.
5. Live execution is blocked whenever unresolved UNKNOWN or ACKNOWLEDGED commands exist.
6. MT5 preflight now fails closed when symbol information, margin calculation or order_check is unavailable.
7. Price normalisation uses broker tick size, stops level and freeze level rather than fixed two-decimal assumptions.
8. Breakout sizing no longer falls back silently to 0.01 lots after a sizing exception.
9. EA control directives now include engine instance, sequence and immutable initial risk.
10. Tick Guard 1.30 validates engine prefix, rejects older sequences, supports fresh engine-instance transitions, checks every hard-floor close result and preserves original R after stop changes.
11. The EA replay implementation was retested and corrected so equal current sequences remain valid during repeated file reads; only older sequences are rejected.
12. UI mutation requests are blocked unless a confirmed live backend response has established LIVE state. Stale, offline and authentication-required states disable the page controls and cannot be dismissed.
13. FastAPI startup handlers were consolidated into one lifespan owner with deterministic cancellation and MT5 shutdown.
14. Root pytest discovery now includes backend and Dynamic SL suites.

## Verification

- Python compileall: PASS
- Root pytest: 14 PASS
- Dynamic SL tests included: PASS
- FastAPI OpenAPI generation: PASS
- Registered routes: 175
- Duplicate method/path routes: 0
- Backend direct MT5 mutations outside designated gateways: 0
- Execution ledger unknown-outcome retry test: PASS
- Nested MT5 confirmation normalisation test: PASS
- Stable mutation idempotency test: PASS
- FastAPI deprecated startup warnings: removed
- EA static engine/sequence/original-risk checks: PASS

## Critical re-audit observations

No further deterministic code defect was found in the corrected transaction, ledger, Dynamic SL ownership or UI stale-state paths during static and automated verification.

The project still contains broad exception handling in optional feeds, chart rendering, historical reporting and compatibility fallbacks. Those paths no longer control the central broker transaction gateway. They should continue to be reduced module by module, but they are not permitted to manufacture a successful broker result.

The frontend source changes could not be rebuilt in this Linux environment because npm dependency installation was unavailable. The Windows launcher already rebuilds the frontend when source is newer. Run INSTALL_GODMODE.bat on the target machine with Node installed, or run `npm ci && npm run build` in `frontend` before live use. Do not use an older dist bundle with the V13.51 backend.

MetaEditor compilation and broker tests remain environment dependent. Compile GodModeTickGuard.mq5 and confirm version 1.30.

## Mandatory demo acceptance sequence

1. Start the backend and confirm `/api/runtime/health` is healthy.
2. Confirm the UI reports LIVE and controls remain disabled when the backend is stopped.
3. Place one 0.01 BUY and one 0.01 SELL.
4. Verify each ledger record includes broker order/deal/position identity.
5. Interrupt the backend during a demo submission and verify the command becomes UNKNOWN and cannot be retried until reconciled.
6. Test SL, TP, partial close and full close readback.
7. Trigger one profitable BREATH event and confirm the EA respects the stop for the full heartbeat window.
8. Restart Python and verify the EA accepts the new engine instance but rejects an older sequence.
9. Test one pending breakout bracket and OCO cancellation.
10. Keep live trading disabled unless every acceptance item passes.

## Further performance improvements recommended

These are performance research additions, not release-blocking bug fixes:

- Shadow-policy logging for tighter stop, breathing stop, unchanged stop, burst and no-burst counterfactuals.
- A calibrated continuation model and a separate retracement-quantile model.
- Probability calibration monitoring using reliability curves and Brier score.
- Uncertainty abstention during regime changes or stale feature inputs.
- Campaign-level locking shared by burst and pyramid.
- Live broker cost distributions by session, spread, slippage, commission and latency.
- Walk-forward validation, untouched holdout data and backtest-overfitting controls.
- Minimum-lot canary releases with automatic rollback on duplicate commands, unknown outcomes, rejection spikes or drawdown anomalies.
