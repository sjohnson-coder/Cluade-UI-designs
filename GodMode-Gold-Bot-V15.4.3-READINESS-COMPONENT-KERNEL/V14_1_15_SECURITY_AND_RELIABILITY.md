# V14.1.15 Security and Reliability Remediation

## Validated remediations

| Area | Prior failure mode | V14.1.15 control |
|---|---|---|
| MT5 trade mode | Entries could reach the broker without enforcing the symbol's current permission mode | Fresh `symbol_info.trade_mode` enforcement immediately before every market and pending entry |
| Direction restrictions | LONGONLY/SHORTONLY could reject after local approval | BUY/SELL admission matrix fails closed for market and pending order types |
| Close-only operation | Entry retries could continue while the broker allowed closes only | CLOSEONLY blocks new exposure but preserves position-reducing closes |
| Market-state failure | Exceptions and missing fields could be interpreted as open | Exceptions, missing ticks, malformed responses, and absent state all fail closed at the execution boundary |
| Broker retcode 10044 | Close-only rejection was generic and could be retried repeatedly | Structured `BROKER_CLOSE_ONLY` classification and symbol-scoped cooldown suppress broker hammering |
| Pending entries | Pending stops bypassed shared broker preflight | Same trade-mode, margin, stop-distance, `order_check`, market-state, and protective-SL controls as market entries |
| Outbound feeds | DNS validated once, then the HTTP stack resolved again | DNS result is pinned to the TCP socket; TLS still verifies the hostname |
| Other outbound HTTPS | Telegram/AI fixed endpoints bypassed the pinned transport | Every production HTTPS call now uses the same pinned, bounded, no-proxy transport |
| Connected peer | A rebound/private peer was not checked after connect | Exact public peer/IP equality check before TLS |
| Response parsing | Malformed `Content-Length` raised unexpectedly | Invalid length is ignored; bounded streaming read remains authoritative |
| Dynamic SL | Caller-supplied BREATHING stop could undercut retained peak | Peak-retention floor enforced inside the pure state machine |
| Protection recovery | Direct JSON overwrite could truncate restart state | Durable atomic JSON replace with readback |
| UI responsiveness | A sustained event-loop stall was not an entry gate | Hysteresis lag watchdog blocks new live risk |
| Burst concurrency | Scanner and Telegram could evaluate together | Non-blocking single-flight burst evaluation lock |
| Burst reporting | Partial/short batches were ambiguous | Requested/attempted/accepted/partial/complete fields |
| Telegram groups | Matching chat ID authorized any group member | Matching configured human user ID also required |
| Performance UI | Static “strong/best/optimal” claims | Evidence-derived values or explicit insufficient sample |
| Execution score | Configured spread labeled live | Per-component provenance and mixed-source label |
| Tick research | Sample scaffold advertised as real production backtester | False capability removed; production exit replay separately exposed |
| Live release | Unverified installation could look production-ready | Exact-build, expiring, all-gates live certification lock |
| Telegram override | Validation override bypassed every combined execution gate | Override is scoped to strategy validation; immutable gates always run |
| Tick Guard | Certification did not make the EA continuously mandatory | Certified live mode requires a configured fresh exact-build heartbeat |
| Startup latency | Missing first event-loop sample passed the execution gate | Missing or stale watchdog telemetry fails closed |
| Dry-run transparency | Simulation could display “Orders can be placed” | APIs and UI explicitly report DRY RUN and deny live-trading permission |
| Atomic commit reporting | Directory fsync could raise after replacement committed | Mandatory readback plus degraded durability warning reflects committed state |
| Certification evidence | Non-empty evidence strings could self-assert A+ | Trusted issuer, HMAC, bounded TTL/age, safe paths, and artifact SHA-256 verification |
| Release extraction | POSIX-only traversal checks missed Windows separators/duplicates | Portable path normalization, duplicate/symlink/special/encrypted/size/ratio rejection |
| Dependency advisories | Old temporary test harness contained obsolete packages | Exact V14.1.15 environment rebuilt; pytest moved to 9.0.3; Python and frontend production audits clean on 2026-07-25 |

## Safety invariants

- A live OPEN requires an SL, valid risk sizing, stable execution identity, and
  broker readback.
- Every risk-increasing market or pending entry requires a fresh, recognized,
  direction-compatible MT5 symbol trade mode.
- Market state is explicit and open, or the entry is denied.
- A broker close-only result cannot trigger rapid repeat entry submissions.
- Routine stop changes cannot increase risk. BREATH widening requires fresh
  internal authorization, remains on the profit side, respects the retained
  peak floor, and is cash-risk capped.
- Unknown/acknowledged broker outcomes are not retried blindly.
- One position's continuation evidence cannot affect another ticket.
- Failed per-position management is isolated; other tickets continue.
- Existing broker SL/TP remains the protection layer when new entries are
  paused by health or certification gates.
- Manual and Telegram actions can never bypass reconciliation, protection,
  event-loop, Tick Guard, or exact-build certification gates.

## Residual risks requiring target evidence

- MetaEditor/MQL5 compilation and `.ex5` behavior cannot be verified on macOS.
- Broker stop/freeze levels, tick values, filling modes, partial fills, symbol
  suffixes, gaps, rollover, netting/hedging, and terminal IPC vary by broker.
- An application watchdog cannot protect against machine power loss, broker
  rejection, network partitions, or market gaps beyond the broker-held SL.
- Demo-forward soak requires elapsed market time and representative regimes.

These residuals are mandatory certification gates, not assumed successes.
