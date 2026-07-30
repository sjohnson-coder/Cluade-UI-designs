# V14.1.15 Verification Report

## Local outcome

V14.1.15 passes every automated check available in this macOS workspace and is
packaged with a fail-closed certification workflow. This is not, by itself,
authorization for unattended live trading.

| Requirement | Result |
|---|---|
| Clean V14.1.14 baseline | PASS — 187 tests before this remediation |
| Full V14.1.15 backend regression suite | PASS — 203 tests under the resolved release dependencies |
| Focused V14.1.15 broker-admission suite | PASS — 16 tests |
| Python syntax compilation | PASS — 55 files |
| TypeScript correctness | PASS — `tsc --noEmit` |
| Production dashboard build | PASS — Vite 8.1.0 |
| Rendered Dashboard/Trades/Analytics navigation | PASS |
| Browser JavaScript error log | PASS — zero errors |
| UI theme retention | PASS — compiled CSS SHA-256 unchanged |
| Python dependency advisory audit | PASS — no known vulnerabilities in the exact resolved production/test environment |
| Frontend production dependency advisory audit | PASS — no known vulnerabilities |
| Release archive checksum/safe-extract verifier | PASS — pristine extraction, identity, settings, original UI hash, and every release-file checksum |
| Windows MetaEditor compilation | INCOMPLETE — unavailable on macOS |
| Target-broker lifecycle drills | INCOMPLETE |
| Demo-forward soak | INCOMPLETE |

## Locally exercised protection scenarios

- Fresh trade-mode query on consecutive entries, including a FULL-to-CLOSEONLY
  broker transition.
- FULL, LONGONLY, SHORTONLY, CLOSEONLY, DISABLED, missing, and unknown
  trade-mode admission outcomes.
- CLOSEONLY permits a position-reducing DEAL but blocks market and pending
  entries.
- Market tick exceptions, gateway exceptions, malformed responses, and missing
  `open` values fail closed before `order_send`.
- Retcode 10044 from `order_check` and `order_send` is classified
  `BROKER_CLOSE_ONLY`; the next attempt is locally suppressed by cooldown.
- Pending entries require a valid protective stop and run shared broker
  preflight.
- BUY/SELL retained-peak floor under a loose BREATHING request.
- Chart-like SELL reaches more than +2.8R and retains more than +1.4R on
  retracement in deterministic bid/ask replay.
- Stop distance/side validation and stale-decision rejection.
- Broker mutation readback, retry, unknown-outcome, and per-ticket isolation.
- Atomic-state failure preserves the prior valid protection state.
- Burst concurrent evaluation rejects without submitting a leg.
- Telegram group command rejects the wrong/missing human user ID.
- Sustained lag requires three breaches; recovery requires two healthy samples.
- Missing, expired, incomplete, and wrong-build certifications reject.
- Telegram validation override cannot bypass any immutable live-entry gate.
- Missing event-loop telemetry fails closed before the first watchdog sample.
- Certified live mode requires fresh Tick Guard attestation even with no path.
- Dry-run is never reported as permission to send live MT5 orders.
- Post-commit directory-sync failure cannot falsely report an uncommitted state.
- Signed certification rejects tampered, stale, missing, unsafe, or hash-mismatched
  evidence.
- Every production HTTPS call routes through DNS pinning, connected-peer
  validation, proxy isolation, redirect revalidation, and response bounds.
- The release extractor rejects POSIX/Windows traversal, duplicate members,
  symlinks, special/encrypted files, oversized expansion, and suspicious ratios.

## Mandatory exact-build certification gates

1. Run `COMPILE_TICK_GUARD_V14_1_15.bat` on the target Windows machine and save
   a zero-error MetaEditor log plus the `.ex5` SHA-256.
2. Attach the EA to the broker's XAUUSD symbol and verify fresh heartbeat,
   build identity, magic, comment prefix, symbol mapping, control path, BE,
   trailing, BREATH, CUT, expiry, and hard floor.
3. On demo, exercise BUY/SELL open/readback, manual Telegram BUY/SELL
   confirmation, `/be`, `/trail`, protected burst success, mid-batch rejection,
   partial fill, unknown result/reconciliation, close, and restart.
4. Stop Python with a winner and loser open. Confirm broker SL/TP and Tick Guard
   remain effective and no new risk enters.
5. Test stop/freeze distance, tick size/value/currency, min/step/max lot, margin,
   filling modes, netting/hedging, symbol suffix, gaps, news spread, and rollover.
6. Verify HTTPS remote access with a strong API key, authorization failures,
   certificate renewal, DNS changes, backup restore, and incident rollback.
7. Complete a representative multi-week demo soak. Define thresholds before the
   run for uptime, p95/p99 loop lag, API latency, rejection/partial-fill rate,
   slippage, peak giveback, drawdown, orphaned commands, and alert delay.
8. Place each completed artifact below `backend/data/evidence/`, populate
   `live_certification.template.json` with its relative path, observation time,
   and passed state, set a private 32+ byte `GODMODE_CERTIFICATION_HMAC_KEY`,
   then run `SIGN_LIVE_CERTIFICATION.py`. The signer hashes every artifact,
   applies a short expiry, signs the exact-build manifest, self-verifies it, and
   installs `backend/data/live_certification.json`.

## Grade

- Source safety implementation and local automated verification: **A+**.
- Packaged release integrity after pristine ZIP verification: **A+**.
- Original UI styling and compiled CSS retention: **A+**.
- Broker-admission transparency and fail-closed behavior: **A+**.
- Unattended live-production certification now: **NOT CERTIFIED**.
- Unattended live-production grade after every target gate passes for this
  exact unmodified build: **A+ eligible**.

The grade is engineering/readiness evidence, not expected profitability.
