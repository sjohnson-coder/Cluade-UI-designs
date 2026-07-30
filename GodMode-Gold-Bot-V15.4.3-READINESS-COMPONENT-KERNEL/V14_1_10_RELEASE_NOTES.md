# GodMode Gold Bot V14.1.10 — Enterprise Remediation

V14.1.10 is a defensive remediation of the supplied Claude V14.1.9 archive. It
keeps the existing dashboard theme and trading workflow while fixing confirmed
live-path, protection, readiness, security, and release-integrity defects.

## Critical fixes

- Isolated dynamic-stop recovery state per ticket. A winner/recovery decision
  from one position can no longer leak into the next position managed in the
  same cycle.
- Added stable, unique execution identities for every scheduled TP partial so
  TP2/TP3/TP4 cannot be incorrectly replayed from a cached TP1 result.
- Revalidated optional `expectedCurrentSl` and `expectedCurrentTp` under the
  central mutation lock immediately before an MT5 stop mutation. Known-stale
  stop decisions now fail closed.
- Routed multi-target orders through the same protected-entry validation and
  risk-capped sizing gate as standard entries.
- Rebuilt pyramiding execution around broker/account/position state collected
  by the server. Client-supplied claims about profit, break-even, risk, margin,
  side, price, and protection are no longer trusted.
- Made live risk sizing and pyramiding decision defaults fail closed when
  authoritative inputs are missing.
- Fixed the startup decision-cache lock imbalance and the spread sampler's
  handling of unavailable quotes.

## Operator controls

- Telegram `/buy` and `/sell` commands queue a manual order and require an
  explicit confirmation button.
- Telegram `/be <ticket>` and `/trail <ticket>` remain available for
  authenticated manual protection of open positions.
- UI manual trade, break-even, trailing, partial-close, close, standard-entry,
  multi-target, and pyramiding calls use the real protected backend routes.
- Automatic/live execution remains disabled by default.

## Security and readiness

- `/api/settings` redacts the MT5 password, Telegram bot token, AI-provider key,
  market-data keys, and strategy-lab feed key.
- Backend readiness is shown separately from live-trading readiness. A healthy
  API no longer implies that MT5 execution is armed.
- Python dependencies were upgraded to remove the known vulnerabilities in the
  supplied archive. Production frontend and backend dependency audits report no
  known vulnerabilities at packaging time.
- The supplied archive's mixed V14.1.8/V14.1.9 identity and stale checksums were
  replaced by a single V14.1.10 identity and newly generated checksums.

## UI compatibility

The theme stylesheet is unchanged:

`3610baecb6d1b438999d081ebb79b9806c4add01c1888fdcd2a7a4d563667545`

The only visible addition is a status banner that distinguishes “backend
ready” from “live trading armed” and displays the backend's reasons/warnings.

## Important live-use boundary

This package is not a promise of profit and is not yet certified for unattended
live trading. `GodModeTickGuard.mq5` is source-only in this package because
MetaEditor/MT5 is Windows-specific. Compile it on the target terminal, confirm
zero errors, verify heartbeat and stop updates, then complete the demo-forward
gates in `V14_1_10_VERIFICATION_REPORT.md`.
