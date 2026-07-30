# V13.50 Audit Remediation

Implemented release-blocking fixes from the V13.49 audit: closed SQLite connections, leased execution commands, explicit execution lifecycle, serialized multi-target orders, fail-closed Telegram sizing, broker-confirmed Dynamic SL breathing state, fresh expiring EA directives, EA-side profitable-stop invariants, authenticated exports, longer endpoint-aware UI timeouts, stale-data metadata, root test configuration, and version/build alignment.

The MT5 guard must be recompiled and must report version 1.20. Live broker validation remains mandatory on demo because MetaTrader is unavailable in the build environment.
