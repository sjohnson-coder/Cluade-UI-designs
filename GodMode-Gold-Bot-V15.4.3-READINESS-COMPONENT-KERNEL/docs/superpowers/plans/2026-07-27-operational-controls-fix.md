# V15.0.5 Operational Controls Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable validation-lock, auto-trading, Telegram test/recap, and manual-trigger operation while preserving the bot's visual design and adopting the reference Inter + Archivo typography.

**Architecture:** Keep the backend as the authoritative safety gate and settings transaction owner. Add focused control endpoints with truthful results, remove the frontend's stale readiness race from execution requests, expose actionable pre-live state, and rebuild the production frontend from source so source and deployed code are identical.

**Tech Stack:** Python 3, FastAPI, pytest, React 18, TypeScript, Vite, MT5 bridge, Telegram Bot API.

## Global Constraints

- Preserve all immutable broker, risk, reconciliation, Tick Guard, and live-certification gates.
- A disabled strategy-validation lock must not disable hard safety gates.
- Do not embed or distribute font binaries; use the reference Google Fonts import for Inter and Archivo.
- Production `frontend/dist` must be rebuilt from the corrected TypeScript source.
- All control APIs must return truthful success/failure and actionable blocker details.
- Default operation remains fail-closed and non-live.

---

### Task 1: Establish regression tests for control failures

**Files:**
- Create: `backend/tests/test_v1504_operational_controls.py`
- Modify: `tests/test_release_integrity.py`

- [ ] Add failing tests for validation-lock atomic toggling and field synchronisation.
- [ ] Add failing tests proving Telegram recap reports disabled, missing credentials, and send failure truthfully.
- [ ] Add failing tests proving a successful Telegram recap reports success only after a real send result.
- [ ] Add failing tests for manual-trigger validation override while preserving hard safety gates.
- [ ] Add release tests for V15.0.5 build identifiers, no stale V14 production strings, and Inter + Archivo typography.
- [ ] Run focused tests and confirm expected failures.

### Task 2: Repair backend operational controls

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/services/prelive_safety.py` only if required by a reproduced failure.

- [ ] Add an atomic `/api/settings/validation-lock` endpoint that updates both validation fields through the verified settings transaction.
- [ ] Return the authoritative validation state and revision in the response.
- [ ] Refactor recap and forecast send functions to return structured send results.
- [ ] Make `/api/telegram/recap` return a non-2xx truthful failure when disabled, credentials are missing, or Telegram rejects the send.
- [ ] Keep the test-alert endpoint independent of notification suppression and return Telegram's diagnostic message.
- [ ] Remove false hard-gate failures caused solely by an uninitialised protection heartbeat when there are no positions requiring protection, without weakening protection for open positions.
- [ ] Run focused backend tests to green.

### Task 3: Repair frontend control wiring

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/pages/Trades.tsx` only where blocker reporting is incomplete.
- Modify: `frontend/index.html`
- Modify: `frontend/src/styles/theme.css`

- [ ] Add API methods for immediate validation-lock updates and pre-live status refresh.
- [ ] Replace the frontend-only execution refusal with a fresh readiness/build/auth transport check, then let the backend return authoritative trade blockers.
- [ ] Make validation-lock toggle transactional with rollback and user-visible backend result.
- [ ] Make Live and Auto controls show the precise backend blocker rather than a generic success/failure state.
- [ ] Make Telegram test and recap buttons surface disabled/credential/send errors and refresh saved state.
- [ ] Apply Inter to body/control text and Archivo to display/value typography using the reference font import.
- [ ] Keep existing colours, spacing, card geometry, and responsive layout unchanged.

### Task 4: Rebuild and verify production frontend

**Files:**
- Regenerate: `frontend/dist/**`

- [ ] Install existing locked dependencies without dependency upgrades.
- [ ] Run TypeScript typecheck.
- [ ] Build production assets from corrected source.
- [ ] Verify production bundles contain V15.0.5 and no stale V14.1.22/V14.1.23 control copy.
- [ ] Verify production HTML imports Inter and Archivo only.

### Task 5: Deep regression and release hardening

**Files:**
- Modify: version/release metadata files required by the verifier.
- Create: `V15_0_5_RELEASE_NOTES.md`
- Create: `V15_0_5_VERIFICATION_REPORT.md`
- Regenerate: `SHA256SUMS.txt`

- [ ] Update backend, frontend, launcher, manifest, and verifier build identifiers consistently.
- [ ] Run full pytest suite.
- [ ] Run Python compileall.
- [ ] Run frontend typecheck and production build.
- [ ] Run JavaScript syntax checks on generated bundles.
- [ ] Run release verifier against a pristine copied tree.
- [ ] Package ZIP, verify archive integrity, and generate SHA-256 checksum.
