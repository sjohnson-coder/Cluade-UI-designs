# GodMode V15 Enterprise Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver ten integrated, testable intelligence and runtime upgrades that improve risk-adjusted decisions without bypassing existing live-trading safety.

**Architecture:** Add a focused `backend/services/v15` package and a single orchestrator, then expose read-only/control APIs and minimal dashboard panels. Existing execution remains authoritative; V15 recommendations are advisory until governed promotion explicitly enables an adapter.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic-compatible dictionaries/dataclasses, SQLite/JSONL persistence already used by the project, React 18, TypeScript, Vite, pytest.

## Global Constraints
- Free data only; no paid service is required.
- Local-first operation; external data failure cannot stop safe core operation.
- Optimise risk-adjusted return, not raw win rate.
- Hybrid governance: low-risk calibration may auto-promote; material changes require approval.
- Preserve all V14.1.25 execution gates, UI styling, launchers, Tick Guard, Telegram, and manual controls.
- No production code before a failing test.

---

### Task 1: Typed V15 contracts and runtime state manager
**Files:** Create `backend/services/v15/contracts.py`, `backend/services/v15/runtime_state.py`, `backend/tests/test_v15_runtime_state.py`.
**Produces:** `RuntimeStateManager`, immutable report dictionaries, monotonic revisions, health snapshots, atomic persistence and one-owner command publication.
- [ ] Write failing tests for revision monotonicity, concurrent updates, secret redaction, Windows replace fallback, and command ownership.
- [ ] Run focused tests and confirm failure because modules do not exist.
- [ ] Implement minimal contracts and state manager.
- [ ] Run focused tests and full runtime-safety tests.

### Task 2: Regime and broker intelligence
**Files:** Create `regime_engine.py`, `broker_engine.py`, and `test_v15_regime_broker.py`.
**Produces:** `RegimeAssessment assess_regime(snapshot)` and `BrokerProfile update_broker(telemetry)`.
- [ ] Write failing deterministic tests for trend/compression/expansion/news/transition and spread/slippage/latency session profiles.
- [ ] Implement transparent rolling classifiers.
- [ ] Verify bounds, determinism, and persistence-ready output.

### Task 3: Multi-horizon calibrated probability engine
**Files:** Create `probability_engine.py`, `calibration.py`, and `test_v15_probability.py`.
**Produces:** `ProbabilityForecast forecast(features, regime, broker)` and Brier/reliability metrics.
- [ ] Write failing tests for all required horizons, probability bounds, uncertainty growth, calibration, MFE/MAE, and hold time.
- [ ] Implement deterministic logistic scorecards plus empirical calibration.
- [ ] Verify no NaN/inf and stable reason contributions.

### Task 4: Missed opportunity and counterfactual learning
**Files:** Create `missed_opportunity.py`, `test_v15_missed_opportunity.py`.
**Produces:** rejected-signal registration, candle replay, outcome classification, gate-attribution and threshold-pressure summaries.
- [ ] Write failing lifecycle tests.
- [ ] Implement append-only tracking and replay.
- [ ] Verify profitable misses, correct rejects, ambiguous cases, and expiry.

### Task 5: Adaptive exit intelligence
**Files:** Create `exit_engine.py`, `test_v15_exit_engine.py`.
**Produces:** deterministic `ExitRecommendation` for hold, BE, trail, tighten, fast-fail, and close.
- [ ] Write failing tests for hard invalidation, profit-floor preservation, recovery timeout, asymmetric loss control, and regime-aware trailing.
- [ ] Implement priority-ordered deterministic policy.
- [ ] Verify fast-fail cannot be postponed by an optimistic recovery score after hard invalidation.

### Task 6: Burst intelligence with complete gate trace
**Files:** Create `burst_engine.py`, `test_v15_burst_engine.py`.
**Produces:** expected-value decision, risk contribution, and every pass/fail gate.
- [ ] Write failing tests for protected-floor, exposure, extension, broker quality, cooldown, continuation, and bridge readiness.
- [ ] Implement evaluator and trace.
- [ ] Verify blocked decisions always contain actionable reasons.

### Task 7: Free macro/news context
**Files:** Create `external_context.py`, `test_v15_external_context.py`.
**Produces:** provider adapters, cache, rate limits, stale/failure status and normalised risk context.
- [ ] Write failing tests using local XML/JSON fixtures for RSS, GDELT-like, FRED-like and official-release formats.
- [ ] Implement standard-library parsers and safe HTTP integration.
- [ ] Verify all-provider failure returns neutral/high-uncertainty context, not an exception.

### Task 8: Governance, walk-forward evaluation and rollback
**Files:** Create `governance.py`, `test_v15_governance.py`.
**Produces:** candidate creation, risk-adjusted scoring, auto-promotion rules, approval queue, shadow requirement and rollback.
- [ ] Write failing promotion/rejection/approval/rollback tests.
- [ ] Implement composite objective and immutable audit trail.
- [ ] Verify material changes never auto-promote.

### Task 9: Explainability and orchestrator
**Files:** Create `explainability.py`, `orchestrator.py`, `test_v15_orchestrator.py`.
**Produces:** one `DecisionIntelligenceReport` containing all ten upgrade outputs, reason codes, contributions, confidence and health.
- [ ] Write failing end-to-end orchestration tests.
- [ ] Implement isolated composition and graceful partial failure.
- [ ] Verify deterministic IDs and complete audit events.

### Task 10: FastAPI integration and runtime adapters
**Files:** Modify `backend/app.py`; create `backend/tests/test_v15_api.py`.
**Produces:** `/api/v15/overview`, `/forecast`, `/regime`, `/broker`, `/exit`, `/burst`, `/missed`, `/calibration`, `/governance`, `/external-context`, `/health`, and shadow-evaluation endpoints.
- [ ] Write failing API contract and origin/security tests.
- [ ] Add singleton orchestrator and endpoints without weakening middleware.
- [ ] Verify Telegram persistence and manual/MT5 regressions remain green.

### Task 11: Dashboard integration
**Files:** Modify `frontend/src/pages/AIAgent.tsx`, `frontend/src/pages/Health.tsx`, `frontend/src/lib/api.ts`; add `frontend/src/components/V15Intelligence.tsx`.
**Produces:** probability matrix, regime, exit, Burst gate trace, calibration, missed opportunities, external freshness and subsystem health.
- [ ] Add typed API client and component tests/build checks.
- [ ] Implement panels using existing UI primitives and sans-serif design.
- [ ] Build production assets and verify no inline-script/CSP regression.

### Task 12: Release verification and packaging
**Files:** Update version metadata, release notes, launch verification, manifest and checksums.
**Produces:** clean V15 ZIP, report, checksum.
- [ ] Run focused and full pytest suites.
- [ ] Compile all Python files and build frontend.
- [ ] Run release verifier on a pristine extracted copy.
- [ ] Remove runtime artefacts and package immutable files only.
