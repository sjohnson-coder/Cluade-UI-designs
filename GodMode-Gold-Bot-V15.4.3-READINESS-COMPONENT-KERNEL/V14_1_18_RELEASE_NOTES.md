# GodMode Gold Bot V14.1.18 A+ Settings Hardening

V14.1.18 repairs the configuration reset, stale-save and silent runtime-divergence paths found in V14.1.17.

## Corrected

- Settings are revision-controlled. Stale browser writes return a conflict instead of overwriting newer toggles.
- Live Trading, Auto Trading, execution mode, Protected Burst, Pyramiding, MT5 connection configuration, imports and rollbacks use one atomic transaction path.
- Failed commits restore the prior settings file, in-memory state and MT5 execution state.
- Corrupt settings are quarantined and restored from a validated last-known-good copy. The restored copy is written back to the primary file immediately.
- The Settings page no longer displays default values when the backend request fails, times out or answers with the wrong build ID.
- Critical switches require JSON booleans. Malformed sections, non-finite numbers, unsafe ranges and unsupported enum values are rejected before runtime mutation.
- A synchronous UI operation guard prevents Save & Apply from racing Live or Auto toggle requests.
- Timed-out MT5 jobs are isolated by work lane and run on daemon workers, so one stuck native call cannot starve unrelated trading operations or prevent shutdown.
- Macro feeds use TTL caching, single-flight requests, stale-last-good fallback and HTTP 429 exponential backoff.
- Launchers verify the exact V14.1.18 backend process on port 8000 before opening the dashboard.
- Legacy settings writers now use the same lock and transactional save path.
- The expensive phantom-configuration regression scan was made deterministic, reducing the complete suite from intermittent stalls to a clean exit.

## Packaged safety state

Live Trading and Auto Trading are OFF. Dry Run is ON. Live certification remains required. Windows MetaEditor compilation, target broker readback drills and demo forward-soak evidence are still required before unattended live trading.
