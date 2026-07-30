# GodMode Gold Bot V15.0.5 Verification Report

## Release identity

- Version: `15.0.5`
- Build: `V15.0.5-OPERATIONAL-CONTROLS-FIX`
- Default state: live OFF, Auto OFF, dry-run ON, `LIVE_RESTRICTED`
- Tick Guard source property: `15.004`

## Automated verification

- Backend regression suite: **294 passed, 0 failed**.
- Python backend compilation: passed.
- Release utility compilation: passed.
- TypeScript/TSX syntax transpilation: passed for **29 source files**.
- Deployed JavaScript syntax: passed for **29 files**.
- JSON parsing: passed for all packaged JSON files inspected before staging.
- Deployed HTML asset references: passed.
- Deployed JavaScript relative-import integrity: passed.
- Route/OpenAPI integrity: **199 route-method pairs**, **188 operation IDs**, no duplicates.
- Root and backend packaged settings equality: passed.
- Safe packaged defaults: passed.
- Reference typography: Inter + Archivo present; no font binaries included.
- Release manifest inventory, SHA-256 list, pristine ZIP and compressed-data integrity: verified during final packaging.

## Regression coverage added

The V15.0.5 tests exercise immediate Validation Lock persistence, settings-revision conflicts, authoritative Live/Auto blockers, first-entry protection readiness, open-position protection enforcement, manual-trigger routing, frontend readiness refresh, Telegram Bot API envelope failures, Markdown retry, failed-send dedupe recovery, recap/forecast delivery truth, WAIT cooldown truth, scheduled recap success latching, current deployed assets, release identity and manifest completeness.

## Environment boundaries

A fresh Vite dependency installation/build could not be completed in this environment because the npm package gateway returned HTTP 503. The existing production bundle was patched to match source and was checked through source transpilation, deployed-JavaScript syntax, asset-reference integrity, import integrity and regression tests.

Real Telegram delivery requires the user's bot token/chat ID and network access. Real MT5 order placement, broker retcodes, slippage and Tick Guard behaviour require the Windows terminal and broker demo account. Those external runtime integrations are not represented as locally certified by this report.
