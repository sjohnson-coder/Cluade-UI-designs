# GodMode Gold Bot V14.1.15 — Broker Admission Hardening

V14.1.15 is built from the checksum-verified V14.1.14 release. It preserves the
existing light/navy/gold dashboard styling while hardening stop ownership,
outbound networking, burst concurrency, persistence, runtime responsiveness,
Telegram authorization, release identity, and operator transparency.

## V14.1.15 broker-admission remediation

- Every live market or pending entry performs a fresh MT5 `symbol_info` query
  and enforces `trade_mode` before `order_check` or `order_send`.
- `FULL`, `LONGONLY`, `SHORTONLY`, `CLOSEONLY`, and `DISABLED` are handled
  explicitly. A missing or unknown value fails closed.
- Direction restrictions are enforced for BUY/SELL market and pending orders.
  Position-reducing closes remain allowed in `CLOSEONLY`; SL/TP protection
  changes are not incorrectly treated as new exposure.
- Market-state exceptions, missing ticks, malformed responses, and all missing
  `open` fields now fail closed. The last execution boundary independently
  rechecks market state, so manual, Telegram, auto, burst, pyramid, and
  multi-target entries share the same behavior.
- MT5 retcode `10044` is classified as `BROKER_CLOSE_ONLY`, surfaced with
  structured telemetry, and starts a symbol-scoped cooldown. Retries during the
  cooldown are rejected locally without another broker entry submission.
- Pending-stop entries now use the same broker preflight and require a
  directionally valid broker-side protective stop.
- Broker status exposes the active close-only cooldown, its origin, expiry, and
  retry-after period for operator transparency.

## V14.1.15 live-control remediation

- Telegram TAKE/SCOUT override can bypass only the strategy-validation result.
  Unresolved broker outcomes, protection health, event-loop health, Tick Guard,
  and exact-build certification remain immutable live-entry gates.
- Certified live execution now requires a configured, fresh, exact-build Tick
  Guard heartbeat even when an imported configuration leaves the explicit
  `requireTickGuardForLive` compatibility flag off.
- A missing first event-loop watchdog sample fails closed; live entries cannot
  slip through the startup interval before latency telemetry exists.
- Health and status APIs distinguish `DRY_RUN`, `LIVE`, and `DISABLED`; dry-run
  is never displayed as permission to place real MT5 orders.
- Atomic JSON replacement treats unsupported post-commit directory fsync as a
  degraded durability warning, performs mandatory readback, and does not falsely
  report that an already committed generation failed.
- Live certification is schema V2: HMAC-SHA256 signed, trusted-issuer bound,
  limited to seven days, requires recent observations, confines evidence paths,
  and verifies a unique SHA-256-matched artifact for every gate.
- `SIGN_LIVE_CERTIFICATION.py` hashes and signs completed evidence without
  writing the signing key into the certificate.

## Dynamic SL and winner protection

- The deterministic V14 state machine now owns the retained-peak floor. A loose,
  stale, or defective caller-supplied stop cannot bypass the configured maximum
  giveback, including during a controlled BREATHING state.
- BUY and SELL breathing decisions are covered by mirrored regression tests.
- A quote-by-quote production Dynamic-SL replay accepts caller, CSV, or MT5
  bid/ask sequences and reports every state, stop, locked R, peak R, giveback,
  and exit. Synthetic input is explicitly marked and is not proof-eligible.
- A chart-like SELL regression reaches more than +2.8R, retraces, and is stopped
  with more than +1.4R retained instead of returning to break-even.
- Every live position now exposes the deterministic state, reason codes,
  current/peak/locked/giveback R, recovery score, breath count, decision age,
  and broker-protection status in the existing Trades UI.

## Burst and execution reliability

- Protected Burst evaluation is single-flight. Background, API, and Telegram
  triggers cannot evaluate the same campaign concurrently.
- Stable campaign/leg execution identities and the durable execution ledger
  remain authoritative for retry deduplication.
- The batch response now distinguishes requested, attempted, accepted,
  complete, and partial legs. A broker rejection stops subsequent legs and
  activates the existing failed-batch lock.
- Unresolved or unknown broker outcomes, stale trade protection, sustained
  event-loop lag, a missing watchdog sample, missing Tick Guard attestation, incomplete live
  certification, and failed strategy validation all block new live entries.

## Runtime, persistence, and remote safety

- The event loop has a hysteresis watchdog. Three sustained lag breaches pause
  new entries; two healthy observations recover without flapping.
- Protection and shared JSON state use same-directory temporary files, file
  flush/fsync, atomic replace, best-effort directory fsync, and mandatory JSON
  readback. A failed replace preserves the last good state; unsupported
  post-commit directory sync cannot masquerade as a failed commit.
- Every production outbound HTTPS path connects to the exact public IP address
  that was DNS-validated, while preserving hostname TLS/SNI verification. The
  connected peer is checked for exact address match and public scope.
- Redirects are re-resolved and re-pinned; cross-origin authorization/cookie
  headers are removed; proxy environment variables are not used; response size,
  timeout, redirect count, and scheme remain bounded.
- Invalid `Content-Length` headers are treated as unknown length and are still
  protected by the bounded read.

## Telegram, UI, and transparency

- Manual `/buy` and `/sell` remain confirmation-gated and require a protective
  SL. `/be <ticket>`, `/trail <ticket>`, `/positions`, `/burst_now`, and `/kill`
  remain available.
- Private chats remain compatible. Group/supergroup/channel commands now
  require both the configured chat ID and `telegram.allowedUserId`.
- Analytics no longer displays hardcoded claims about strong performance,
  London-session superiority, confidence thresholds, or strategy leadership.
  Empty/low samples are shown as insufficient evidence.
- Broker execution quality identifies each component source. A configured
  spread is no longer labeled as live execution evidence.
- The legacy tick endpoint is truthfully labeled as a sample strategy scaffold.
  Production entry-strategy tick backtesting is not claimed.
- The existing compiled CSS remains byte-identical:
  `62ddb63df0e1e45f69f7ad8883f430f859942af01d232a520556d6c9c9ea5845`.
- The exact resolved Python production/test environment and the frontend
  production dependency set reported no known advisories on 2026-07-25.

## Important boundary

No finite test suite can prove a trading system bug-free, prevent broker gaps
or slippage, or prove future profitability. V14.1.15 therefore defaults to
`execution.requireLiveCertification=true` and fails closed until the exact
build has complete target-machine evidence. See
`V14_1_15_VERIFICATION_REPORT.md`.
