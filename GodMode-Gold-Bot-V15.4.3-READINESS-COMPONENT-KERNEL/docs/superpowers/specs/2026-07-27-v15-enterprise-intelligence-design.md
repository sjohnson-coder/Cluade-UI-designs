# GodMode V15 Enterprise Intelligence Design

## Objective
Build ten coordinated upgrades on top of V14.1.25 while preserving the existing dashboard, strategies, MT5 safety gates, Tick Guard, Telegram, manual trading, and Windows launch workflow. The optimisation objective is risk-adjusted return. Data is local-first and free-only: MT5 history/live data, the bot journal, FRED-compatible public data, GDELT, RSS, and official central-bank publications. External data must never be a single point of failure.

## Architecture
V15 adds a bounded `backend/services/v15` package behind a single `GodModeV15Orchestrator`. Existing execution remains authoritative; V15 produces calibrated forecasts, recommendations, diagnostics, and governed candidate changes. No model may bypass live safety, broker, Tick Guard, certification, risk, or kill-switch gates.

The orchestrator owns ten independently testable units:

1. **Regime Intelligence**: multi-state regime classification and strategy suitability.
2. **Multi-Horizon Probability**: continuation, reversal, recovery, TP-before-SL, BE-first, fast-fail, Burst success, invalidation, MFE, MAE, and holding-time forecasts.
3. **Broker Intelligence**: rolling spread, slippage, latency, fill quality, freeze/rejection and session profiles.
4. **Missed Opportunity Learning**: shadow lifecycle for every rejected signal and counterfactual outcome classification.
5. **Adaptive Exit Intelligence**: deterministic BE, trailing, fast-fail, tighten, hold, and exit recommendations from calibrated evidence.
6. **Burst Intelligence**: expected-value and gate-trace evaluation for protected add-on entries.
7. **Continuous Calibration and Governance**: Brier/reliability metrics, walk-forward candidate evaluation, low-risk auto-promotion, approval-required material changes, and rollback.
8. **Free Macro and News Intelligence**: cached, rate-limited RSS/GDELT/FRED-compatible adapters with stale-data and failure isolation.
9. **Explainability**: reason codes, contribution values, confidence, uncertainty, thresholds, and complete decision traces.
10. **Runtime State Manager**: one in-process authority for subsystem state, command sequencing, snapshots, health, and atomic persistence. MT5 CSV remains only as the EA transport boundary and is written by one owner.

## Data Flow
Market snapshots, strategy context, broker telemetry, journal outcomes, and free external context enter the orchestrator. Engines emit typed results. The orchestrator composes a `DecisionIntelligenceReport`, persists an append-only audit event, updates health, and exposes read-only API snapshots. Existing execution code may consume recommendations only through explicit adapters and remains guarded by existing safety checks.

## Model Strategy
V15 uses deterministic calibrated ensembles rather than promising impossible prediction. Initial models are transparent scorecards with Platt-style/logistic calibration and rolling empirical priors. They can run without scientific packages. Historical training and walk-forward evaluation operate locally. Future model families can implement the same interfaces.

## Governance
- Low-risk calibration-only updates may auto-promote after walk-forward, drawdown, calibration, stability, sample-size, and rollback checks.
- Material changes to entry thresholds, exit policy, Burst, risk, sizing, session controls, or feature sets require user approval.
- Every candidate retains its baseline, metrics, dataset window, reason, checksum, status, and rollback pointer.
- Shadow mode is mandatory before live promotion.

## Free Data Policy
No paid dependency is required. Providers are optional and degrade safely. Core trading remains operational with external data unavailable. Cached data includes source, fetched time, event time, freshness, parse status, and error reason.

## Runtime and Persistence
The state manager serialises writes, maintains monotonic revisions, uses atomic file replacement with Windows retry/fallback, redacts secrets, and provides health state. Only the command publisher owns `godmode_control.csv`. Telegram credentials retain secure persisted status and are never cleared by masked frontend payloads.

## API and UI
Add `/api/v15/*` endpoints for overview, forecast, regime, broker, exits, Burst trace, missed opportunities, calibration, governance, external context, explainability, health, and shadow evaluation. Extend AI Agent and Health pages with V15 summaries without changing the approved visual language.

## Safety
- No V15 recommendation directly places a trade.
- Manual and automated execution still require all existing admission gates.
- Invalid, stale, low-sample, or out-of-distribution forecasts increase uncertainty and reduce permission.
- Missing news never authorises a trade.
- Fast-fail uses hard invalidation overrides so a weak recovery score cannot postpone exit indefinitely.

## Testing
Use TDD for every engine. Tests cover calibration bounds, deterministic output, regime transitions, counterfactual outcomes, asymmetric exit protection, Burst gate traces, free-provider failure isolation, state concurrency, Windows replace failures, governance promotion/rollback, API contracts, and regression against the existing suite.

## Release Acceptance
- Existing V14.1.25 tests remain green.
- New V15 focused tests pass.
- All Python compiles.
- Frontend production build succeeds.
- Release manifest and ZIP integrity pass.
- No caches, logs, databases, credentials, or virtual environments are packaged.
