# GodMode V13.48.1 Three-Phase Stability Upgrade

## Phase 1: Immediate safety
- Corrected canonical backend version and build ID.
- Made MT5 connectivity flags truthful; demo data no longer reports MT5 connected.
- Changed the example live configuration to disable demo fallback by default.
- Added a serialized execution gateway for manual, auto, Telegram, burst and pyramid order paths.
- Added durable SQLite idempotency and execution transaction journaling.
- Added runtime health endpoints and structured rotating logs.
- Preserved atomic settings writes and added visible settings-load failure telemetry.

## Phase 2: Stability refactor
- Introduced `services/runtime_safety.py` as a dedicated reliability service.
- Centralized execution serialization and duplicate suppression.
- Hardened performance-memory SQLite with WAL, busy timeout and serialized writes.
- Separated dependency installation from normal startup.
- Pinned frontend dependencies and added mandatory TypeScript checking before builds.
- Existing route-level React crash recovery remains enabled.

## Phase 3: Verification
- Added automated tests for execution idempotency, runtime health, version truth, connectivity truth and atomic settings persistence.
- Added `/api/execution/ledger` and `/api/runtime/health` diagnostic endpoints.
- Added deterministic build metadata for support and rollback checks.

## Operational rule
Run `INSTALL_GODMODE.bat` once after extracting the build. Use `start_backend.bat` for normal starts. Keep live trading disabled until MT5 connection, broker symbol settings and minimum-lot dry-run checks have been reviewed.
