# V14.1.10 Verification Report

## Outcome

The supplied V14.1.9 archive was not release-ready. Its own checksum file
failed for eight files, its release identity was mixed with V14.1.8, and the
baseline backend suite had nine failures. The remediated V14.1.10 source passes
all checks available in this macOS workspace.

No finite static test campaign can prove software “bug free,” and no backtest
can guarantee profit. Target-broker Windows MT5 validation remains mandatory.

## Evidence matrix

| Requirement | Result | Evidence |
|---|---|---|
| Backend regressions | PASS | 119 passed, 0 failed in 16.45 seconds |
| Python byte compilation | PASS | `compileall` completed without error |
| Undefined Python names | PASS | `pyflakes` completed without findings |
| TypeScript correctness | PASS | `tsc --noEmit` |
| Production dashboard build | PASS | Vite 8.1.0, 2,181 modules transformed |
| UI style retention | PASS | Theme CSS SHA-256 unchanged |
| Frontend/backend API coverage | PASS | 112 active frontend paths matched registered backend routes |
| Backend dependency audit | PASS | No known vulnerabilities found |
| Frontend production dependency audit | PASS | No known vulnerabilities found |
| Local API smoke | PASS | Health, liveness, readiness, redacted settings, OpenAPI: HTTP 200 |
| Settings secret redaction | PASS | Smoke response returned blank secret fields; regression-covered |
| Live/auto defaults | PASS | Both disabled in shipped settings |
| Windows MetaEditor compile | INCONCLUSIVE | Windows MT5/MetaEditor unavailable in this workspace |
| Target broker behaviour | INCONCLUSIVE | Requires the user's broker symbol, stops level, fill policy, spread and account mode |
| Demo-forward soak | INCONCLUSIVE | Not performed; requires elapsed market time |

The production JavaScript bundle is approximately 1.04 MB (286.53 KB gzip).
Vite reports a non-blocking chunk-size warning; this affects initial-load
performance, not order correctness.

## Protection behaviour verified in code/tests

- Profit protection ratchets monotonically: a protected stop is not loosened by
  later routine trailing decisions.
- Recovery widening is deterministic, limited by configured risk/extra-R,
  capped in count, subject to cooldown, and rejected during news/dirty-market,
  broken-structure, or weak-recovery conditions.
- Cross-ticket state is isolated.
- Stop mutations are serialized and known-stale decisions are rejected directly
  before broker submission.
- Manual break-even/trailing, automatic dynamic SL, recovery decisions, and TP
  protection carry the expected current stop/target into the mutation gateway.
- Each TP partial has a durable idempotency identity.
- Multi-target and pyramiding entries use server-authoritative geometry,
  protection, margin, exposure, and risk gates.

These checks materially reduce the risk of the retracement failure described by
the supplied chart, but they do not establish perfect execution. The Python
manager only acts while the service and MT5 connection are alive; Tick Guard is
the independent terminal-side layer and must be compiled and attested.

## Mandatory go-live gates

1. On the target Windows machine, run
   `COMPILE_TICK_GUARD_V14_1_10.bat`; require MetaEditor to report zero errors
   and confirm `GodModeTickGuard.ex5` exists.
2. Attach the EA to the broker's actual XAUUSD chart and configure the shared
   MQL5 Files path. Enable `requireTickGuardForLive` only after the heartbeat is
   visible; readiness must then block if that heartbeat becomes stale.
3. Use a demo account to verify BUY and SELL initial SL/TP, BE, trailing,
   bounded widening, fast-cut, TP partials, reconnect/restart recovery,
   duplicate command idempotency, and Telegram confirmation.
4. Simulate a backend stop and an MT5 disconnect while positions are open.
   Confirm the independent emergency floor remains active and all new entries
   fail closed.
5. Test the broker's minimum stop/freeze distance, lot step, minimum volume,
   maximum volume, filling mode, netting/hedging behaviour, weekend market
   state, and high-spread rejection.
6. Complete at least two to four weeks of demo-forward observation across news,
   London/US overlap, rollover, gaps, and network interruption. Compare fills,
   slippage, maximum adverse excursion, profit giveback, and drawdown against
   the chosen limits.
7. Only then enable live trading at the broker minimum size. Do not enable
   unattended live use while any readiness reason is present.

## Grade

- Source implementation and automated verification: **A- (92/100)**.
- Live-production certification today: **C / INCONCLUSIVE**, because the
  Windows EA compile, broker-specific integration, failure drills, and demo soak
  are still outstanding.
- Overall release-readiness grade: **B+ (87/100), conditional**.

This grade measures engineering readiness, not expected trading returns.
