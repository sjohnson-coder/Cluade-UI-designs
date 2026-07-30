# GodMode Gold Bot V15.0.7 Verification Report

**Version:** `15.0.7`  
**Build:** `V15.0.7-DETERMINISTIC-PROTECTION-HARDENED`  
**Verification date:** 2026-07-28

## Scope verified

This verification covers the deterministic-protection changes requested for V15.0.7:

- BREATH requires a broker-confirmed profitable stop.
- The V14 winner wrapper remains inactive below the configured protection threshold.
- Python owns automated stop policy; Tick Guard is the automated broker-side SL actuator while its exact-build directive is fresh.
- Recovery confirmation, cut confirmation, cooldown, grace and hold limits use elapsed time rather than loop counts.
- Peak changes and broker-confirmed SL changes are persisted immediately.
- Position age is reconstructed from broker open timestamps.
- Risk-changing decisions fail closed without a valid live ATR.
- Missed-move analysis starts at the first executable quote, uses chronological bid/ask ticks and deduplicates stable market events.

## Automated evidence

- Backend regression suite: **327 passed, 0 failed** (`PYTHONPATH=. pytest -q`).
- Python compilation: **passed** (`python -m compileall -q backend`).
- Frontend source syntax: **29 TypeScript/TSX files transpiled with 0 syntax errors** using the installed TypeScript compiler API.
- Deployed frontend syntax: **29 JavaScript assets passed** `node --check`.
- Deployed asset imports: **85 relative imports resolved, 0 missing**.
- JSON validation: **40 JSON documents parsed successfully** in the development tree before release filtering.
- FastAPI routes: **196 method/path combinations, 0 duplicates**.
- OpenAPI operation IDs: **189 generated, 0 duplicates**.
- Packaged settings contract: safely disarmed, `LIVE_RESTRICTED`, exact build identity, Tick Guard required, elapsed-time fields present and legacy check-count fields absent.
- Settings schema defence: release verification now rejects unknown top-level settings sections before packaging.
- UI theme CSS SHA-256 preserved: `c3dce76e509c74fce7430187c5874a4dea61f1bc3f67eea65bc42ac99ab636f1`.

## Safety invariants checked

- The automated open-trade manager contains no direct `MODIFY_SL` broker mutation.
- Manual break-even and manual trail controls remain explicit user-triggered exceptions.
- Tick Guard rejects BREATH when MT5 does not confirm a profitable existing stop.
- Tick Guard rejects PROTECT below the configured ATR threshold unless a profitable broker stop is already present.
- Tick Guard rejects RECOVER when ATR is unavailable or the requested risk exceeds the configured cap.
- Fresh Tick Guard ownership suppresses competing local fallback protection rules.
- Missing live ATR blocks protected burst additions, staged pyramid additions, post-loss same-direction re-entry and repeat-entry displacement checks.
- Missed-move P/L uses broker `order_calc_profit` when available and labels the fallback when it is not.

## Environment limitation

A complete `tsc --noEmit` dependency-aware frontend type-check could not be performed because the extracted release workspace does not include `node_modules`, and dependency installation was unavailable in this environment. The packaged production JavaScript and all TypeScript/TSX source files were nevertheless syntax-checked as described above.

The MQL5 source cannot be compiled into an `.ex5` file in this Linux environment. Compile `mt5_ea/GodModeTickGuard.mq5` in Windows MetaEditor and complete MT5 demo-account failure testing before live deployment. Static verification cannot prove broker-specific stop/freeze responses, fills, slippage, terminal restarts or network recovery.
