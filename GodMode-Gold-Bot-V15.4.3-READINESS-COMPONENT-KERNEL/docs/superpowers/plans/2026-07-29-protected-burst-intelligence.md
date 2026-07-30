# Protected Burst Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a distinct V15.3.2 Protected Burst release that fires one immediate two-to-three-leg batch only when the base trade is approaching the real deterministic break-even arm point, probability and continuation remain strong across consecutive scans, and the fully rounded basket fits a strict account-risk budget.

**Architecture:** Add a focused Burst policy module for account classification, BE-arm progress, sustained-evidence tracking, basket-risk validation, lifecycle classification, and gate tracing. Keep MT5 execution in `backend/app.py`, but make it consume one preflight result before any leg is submitted. Expose a read-only status endpoint and a live dashboard card that polls cached Burst state without invoking trading analysis.

**Tech Stack:** Python 3, FastAPI, MetaTrader5 bridge, pytest, React 18/TypeScript source, production JavaScript overlay, CSS.

## Global Constraints

- Release identity must be exactly `V15.3.2-NONBLOCKING-RUNTIME-RECOVERY`.
- Immediate batches contain two legs at the normal Burst threshold and three legs only at the strong threshold.
- No sequential drip-feed adds are introduced.
- Telegram Burst state must use the same resolved configuration as the execution path.
- The complete batch must be risk-valid after broker minimum/step rounding before the first order is sent.
- A failed order in an otherwise accepted atomic batch must trigger rollback of already accepted Burst legs when rollback is enabled.
- Dashboard status is read-only and must not call MT5 or strategy evaluation.
- Burst probe legs cannot widen, breathe, pyramid, or inherit normal runner permissions until promoted.
- Existing base-entry, Early Intent, Qualified Peak Runner, validation-lock, broker-admission, and Tick Guard safety remain authoritative.

---

### Task 1: MT5 account trade-mode truth

**Files:**
- Modify: `backend/services/mt5_bridge.py`
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Produces: `account_snapshot()` fields `accountTradeMode`, `accountTradeModeName`, `accountType`, `demo`, `contest`, and `real`.

- [ ] Write failing tests for DEMO, CONTEST, REAL, and unknown account trade modes.
- [ ] Run the focused tests and confirm failures are due to missing fields.
- [ ] Extract `account_info.trade_mode` using MetaTrader5 account constants and return normalized fields.
- [ ] Run the focused tests and confirm all account-mode cases pass.

### Task 2: Pure Burst policy and sustained evidence

**Files:**
- Create: `backend/services/protected_burst_v153.py`
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Produces: `compute_be_arm_progress(...)`, `update_sustained_evidence(...)`, `classify_burst_lifecycle(...)`, `evaluate_rounded_basket_risk(...)`, and `build_gate(...)`.

- [ ] Write failing tests for deterministic BE-arm progress using AI Dynamic SL, launch phase, and legacy BE settings.
- [ ] Write failing tests requiring three consecutive stable scans and resetting on direction change, stale scan, or excessive score deterioration.
- [ ] Write failing tests for two-leg and three-leg batch selection.
- [ ] Write failing tests proving broker rounding cannot push aggregate risk above the Burst budget.
- [ ] Write failing tests for `BURST_PROBE`, `BURST_CONFIRMED`, `BURST_RUNNER`, and `BURST_DEFENSIVE` transitions.
- [ ] Implement the minimal pure policy functions and rerun the focused tests.

### Task 3: Burst defaults, resolver, gate trace, and status endpoint

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/data/settings.json`
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Produces: `_protected_burst_status_snapshot()` and `GET /api/trading-modes/protected-burst/status`.

- [ ] Write failing tests that Telegram, toggles, GET status, and execution all resolve the same Burst defaults.
- [ ] Write failing tests that dashboard status reports every evaluated gate, account type, sustained scans, BE progress, batch size, projected risk, and current blocker.
- [ ] Adopt Claude's resolver correction in Telegram and toggle responses.
- [ ] Materialize one canonical configuration with aligned backend/frontend defaults.
- [ ] Add cached Burst runtime trace storage and the read-only status endpoint.
- [ ] Confirm status retrieval performs no MT5 fetch or strategy evaluation.

### Task 4: Replace the early-arm shortcut with real deterministic BE progress

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Consumes: `compute_be_arm_progress(...)`.

- [ ] Write a failing test where the old cost-buffer formula would arm Burst at 0.20 points but the real deterministic arm is not close.
- [ ] Write a failing test where the base trade reaches 85% of the actual deterministic arm and becomes eligible.
- [ ] Replace the cost-buffer calculation with the policy result and include the complete BE calculation in the trace.
- [ ] Verify an already broker-protected base leg reports 100% progress.

### Task 5: Sustained probability and immediate adaptive batch

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Consumes: `update_sustained_evidence(...)`.

- [ ] Write failing tests showing one strong scan cannot fire.
- [ ] Write failing tests showing three stable scans fire two legs.
- [ ] Write failing tests showing strong sustained confidence and continuation fire three legs.
- [ ] Persist evidence per campaign and direction in bounded runtime state.
- [ ] Reset evidence on opposition, excessive deterioration, timeout, new campaign, or completed batch.

### Task 6: Transactional basket-risk preflight and atomic execution

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Consumes: `evaluate_rounded_basket_risk(...)`.
- Produces: preflight rows containing final lot, stop, projected loss, and order payload.

- [ ] Write failing tests showing minimum-lot rounding can exceed the total Burst budget.
- [ ] Write failing tests proving no order is submitted when the final basket is over budget.
- [ ] Write failing tests proving all legs are preflighted before the first submission.
- [ ] Write failing tests proving a partial execution failure closes accepted Burst legs when atomic rollback is enabled.
- [ ] Pass the Burst risk percentage into every `_safe_entry_lot` call and independently sum broker-native projected losses.
- [ ] Reject incomplete two-leg or three-leg plans before execution.

### Task 7: Strict Burst lifecycle and management

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/services/deterministic_exit_intelligence.py` only if required by an existing public interface
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Consumes: `classify_burst_lifecycle(...)`.
- Persists: `burstStage`, `burstContinuationScore`, `burstPromotionReason`, `burstCampaignId`.

- [ ] Write failing tests that a new Burst leg starts as `BURST_PROBE`.
- [ ] Write failing tests that Burst probes cannot widen, breathe, pyramid, or use normal runner management.
- [ ] Write failing tests for stricter probe fast-fail, early BE, and tight trail thresholds.
- [ ] Write failing tests for one-way promotion to `BURST_CONFIRMED` and `BURST_RUNNER`.
- [ ] Write failing tests that deteriorating confirmed legs become `BURST_DEFENSIVE`.
- [ ] Integrate lifecycle state into the existing management loop without changing normal or Early Intent trades.

### Task 8: Live dashboard Burst gate trace

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/styles/theme.css`
- Create: `frontend/dist/burst-live-v1530.js`
- Create: `frontend/dist/burst-live-v1530.css`
- Modify: `frontend/dist/index.html`
- Test: `backend/tests/test_v1530_protected_burst_intelligence.py`

**Interfaces:**
- Consumes: `GET /api/trading-modes/protected-burst/status`.

- [ ] Add API client method and typed dashboard source integration.
- [ ] Add a Dashboard card at the existing live-engine anchor.
- [ ] Display account type, status, BE progress, sustained scans, confidence, continuation, projected risk, batch size, campaign, and every gate.
- [ ] Add pulse, scan, armed, blocked, and firing animations while respecting reduced-motion preferences.
- [ ] Add a production overlay for the packaged `dist` dashboard and version its assets.
- [ ] Align Settings defaults and expose the new sustained-evidence, strong-batch, atomic rollback, and lifecycle controls.
- [ ] Add static contract tests proving the endpoint and production assets are wired.

### Task 9: Release identity and verification

**Files:**
- Modify: all release-identity files discovered by exact search
- Create: `V15.3.2_DONE_AND_VERIFICATION.md`
- Modify: `RELEASE_MANIFEST.json`
- Regenerate: `SHA256SUMS.txt`

**Interfaces:**
- Produces: `GodMode-Gold-Bot-V15.3.2-NONBLOCKING-RUNTIME-RECOVERY.zip` and checksum.

- [ ] Replace backend, frontend, launcher, verifier, settings, Tick Guard, documentation, and asset build IDs.
- [ ] Run focused V15.3.2 tests.
- [ ] Run Python compilation.
- [ ] Run the complete backend test suite.
- [ ] Run JavaScript syntax checks and TypeScript transpilation checks.
- [ ] Run runtime release verification.
- [ ] Extract the final ZIP into a clean folder and repeat the complete backend suite and release verification.
- [ ] Verify ZIP CRC, manifest hashes, no runtime databases/logs/caches, and exact release identity.
