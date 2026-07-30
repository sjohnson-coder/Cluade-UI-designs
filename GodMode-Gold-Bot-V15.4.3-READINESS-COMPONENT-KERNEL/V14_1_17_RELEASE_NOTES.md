# GodMode Gold Bot V14.1.17 — Silent Bugs Fix

V14.1.17 is built from V14.1.16 (which itself renamed BUILD_ID away from V14.1.15
without a full cascade). This release closes the drift and repairs a family of
silent errors that combined into two visible symptoms:

- "Saved settings does not apply, keeps reverting"
- "Unattended live certification is incomplete; live entries remain locked"

## Root causes fixed

### 1. Version drift across the certification chain (root cause of the cert banner)

The runtime `BUILD_ID` had moved to `V14.1.16-LIVE-FLAG-SAFETY-FIX` but
`SIGN_LIVE_CERTIFICATION.py`, `VERIFY_RELEASE.py`, `live_certification.template.json`,
`RELEASE_MANIFEST.json`, the shipped `backend/data/settings.json`, the operator
`GODMODE_SETTINGS_*.json`, and the Tick Guard EA all still asserted
`V14.1.15-BROKER-ADMISSION-HARDENED`. Because the certification gate requires
an exact-build match (`payload.buildId == BUILD_ID`), no cert the operator could
sign would ever pass — the banner was permanent by construction.

V14.1.17 permanently ends this class of drift:

- `SIGN_LIVE_CERTIFICATION.py` now reads `BUILD_ID` from `backend/app.py` at
  runtime (`_read_backend_build_id()`). Renames of `BUILD_ID` cannot desync it.
- `VERIFY_RELEASE.py` derives `EXPECTED_BUILD` and `EXPECTED_VERSION` the same way.
- `backend/tests/test_v1416_consolidation.py::test_release_identity_is_coherent`
  now asserts coherence between `BUILD_ID` and `APP_VERSION` rather than a
  literal string — the previous literal was one release stale on arrival.
- Every remaining literal (`V14.1.16-LIVE-FLAG-SAFETY-FIX`, `V14.1.15-...`) was
  bulk-retagged to `V14.1.17-SILENT-BUGS-FIX` across app, frontend, EA,
  tests, cert template, manifest, and packaged settings.

### 2. Silent load-time floor clamps rewriting user-tuned settings (root cause of "keeps reverting")

Two load-time clamps in `_load_settings()` ran on *every* startup, silently
overwriting saved user values that fell below hard-coded floors:

- `trading.tradeManagement.fastFailMinSeconds < 300` → forced to `300` every load.
- `protectedBurst.burstFastFailSeconds < 180` → forced to `200` every load.

Both looked to save (receipt OK, disk file written), then a bot restart quietly
lifted them back. Now:

- The `fastFailMinSeconds` clamp is folded into the existing one-shot
  `v13.8.1-fastfail-spike` migration marker. User values are preserved.
- The `burstFastFailSeconds` clamp becomes a one-shot `v14.1.17-burst-clamp-once`
  migration, logs when it acts, and never fires again after the first run.

### 3. `_sync_validation_settings` asymmetric authority

The old sync always let `validation.enabled` win over `execution.validationLockEnabled`.
Any config or UI wiring only the legacy field got silently reverted on save.
V14.1.17 makes the sync symmetric:

- Whichever field is present in the payload wins.
- If both present and disagree, the canonical (`validation.enabled`) wins AND logs.
- Neither present → fail-closed (both True).

Unit-verified across all six truth-table cases.

### 4. `/api/execution/mode` GET returned a partial `settings` blob

Same anti-pattern that V12.67 fixed on `/api/mt5/live-mode`. A UI that splatted
this two-key slice over full state would silently drop every other field. Field
renamed to `settingsSlice` so no client can mistake it.

### 5. `execution.requireLiveCertification` was a hidden knob

The only way to disable the unattended-cert requirement was hand-editing
`backend/data/settings.json`. Demo and dev operators had no path off the
"certification incomplete" banner. Added a toggle in Settings → section 3b
"Validation Lock & Live Unlock".

## What still stands

- Every other V14.1.15 hardening: broker admission gate, Telegram TAKE/SCOUT
  scope, Tick Guard heartbeat requirement, event-loop watchdog, atomic JSON
  replacement with mandatory readback, HMAC-SHA256 cert schema V2, deterministic
  Dynamic SL state machine.
- `SETTINGS_LOCK`-scoped save with tmp-file replace and read-back verification.
- All V13/V14 migration markers preserved and idempotent.

## Verification

- Python: `ast.parse` clean on `backend/app.py`, `SIGN_LIVE_CERTIFICATION.py`,
  `VERIFY_RELEASE.py`.
- Frontend: `npm run build` clean; `tsc --noEmit` clean.
- Build ID visible in `frontend/dist/assets/index-*.js`; new UI toggle visible
  in `Settings-*.js`.
- `_sync_validation_settings` unit-run across 6 truth-table cases: correct.
- Service imports clean under a stubbed `MetaTrader5`.
