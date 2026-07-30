# GodMode Gold Bot V14.1.18 Verification Report

## Release identity

- Version: `14.1.18`
- Build: `V14.1.18-A-PLUS-SETTINGS-HARDENED`
- Input archive SHA-256: `bcc4bf96e354adc6c9f9ba7007b04d9e1b46f7260b87e8d0073b181b578dd188`
- UI CSS SHA-256: `75e99bee29d6a9b89a12da77e6b56873c260dc148b54acacc7a434ea21b3c968`

## Confirmed remediations

1. Revision-controlled settings prevent stale Save & Apply requests from overwriting a newer Live or Auto toggle.
2. Settings failures no longer render an undisclosed default configuration in the dashboard.
3. Toggle endpoints report real failures and restore the prior UI state.
4. Corrupt settings are quarantined and recovered from a validated last-known-good file without destructive default overwrite.
5. Settings schema, boolean, enum, finite-number and safety-range validation run before mutation.
6. Disk-write or runtime-apply failures roll back disk, in-memory settings and MT5 execution state.
7. Launchers reject an old or unrelated backend already occupying port 8000.
8. Timed-out MT5 workers cannot hold a global worker lock or block interpreter shutdown.
9. Macro feeds are cached and back off after HTTP 429 responses.
10. Legacy settings mutation routes use the shared settings lock and transactional writer.

## Fresh verification

- Python compilation: PASS
- Focused V14.1.18 hardening suite: `10 passed`
- Complete automated suite: `215 passed in 3.33s`
- Frontend TypeScript source syntax through TypeScript transpilation: PASS
- Packaged production JavaScript syntax through `node --check`: PASS
- Settings API validation smoke: PASS, malformed nested settings return HTTP 422
- Settings concurrency regression: PASS, only one writer with a shared revision can commit
- Corrupt-primary recovery regression: PASS
- Disk-failure rollback regression: PASS
- Worker timeout isolation regression: PASS
- Macro cache and 429 backoff regression: PASS
- Release tree verification: PASS
- Pristine safe-extracted ZIP verification: PASS

## Scope boundary

This environment does not provide Windows MetaTrader 5, the target broker account, MetaEditor or elapsed market-session time. Therefore the source and packaged release can be graded A+ for the repaired configuration and local automated verification, but unattended live trading is deliberately **NOT CERTIFIED**. The bot remains fail-closed until exact-build Tick Guard compilation, broker readback/failure drills, demo soak evidence and signed live certification are completed on the target Windows machine.
