# V14.1.23 Release Notes

Build: `V14.1.25-RUNTIME-BRIDGE-PROTECTION-FIX`

## Corrected failures

1. Windows atomic JSON persistence no longer attempts unsupported directory-handle `fsync`. File flush, atomic replacement and JSON read-back remain enforced.
2. Tick Guard heartbeat and control freshness now use UTC in both Python and MQL5.
3. EA installation prioritises the connected MT5 terminal and its exact `MQL5\Files` directory.
4. Stale imported terminal paths no longer override a fresher heartbeat from the active terminal.
5. Normal desktop live admission uses continuous local runtime attestation. The formal HMAC evidence certificate remains available through `enterprise_evidence` mode.
6. Close reconciliation no longer throws `StopIteration` for normal throttle control.
7. Startup and `CHECK_TICK_GUARD.bat` provide exact terminal, heartbeat and identity diagnostics.
8. Production frontend assets are cache-busted for V14.1.23 and retain the global sans-serif UI.

## Required operator action

The V14.1.23 EA must be compiled and attached. An older Tick Guard cannot satisfy the exact-build gate.

Run `2_INSTALL_EA_AND_START_GODMODE.bat`, attach the newly compiled EA to XAUUSD, enable Algo Trading, then run `CHECK_TICK_GUARD.bat`.
