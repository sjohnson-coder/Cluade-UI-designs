# GodMode Gold Bot V13.55.1 Protection Hotfix

Build: `V13.55.1-PRODUCTION-PROTECTION-HOTFIX`

V13.55.1 keeps the V13.55 UI and trading architecture, but repairs the protection path that could leave a profitable trade unmanaged by Python. Live and automatic trading remain disabled by default.

## Protection corrections

- Fixed an unconditional protection-loop crash: counter-trend variables are now initialized before the conditional time-stop and fast-fail branches use them.
- Isolated every position-management pass. Bad data on one ticket is reported and blocks new live entries, but no longer prevents the other open tickets from being protected.
- Made protection health a live-entry prerequisite. A skipped, timed-out, stale, or failed protection cycle fails readiness and blocks new positions.
- Scheduled open-position protection before scanners and new-entry work.
- Persisted each trade's maximum favourable excursion before downstream decisions. The winner floor is calculated from the stored peak, so a restart, broker rejection, or retracement cannot erase the high-water mark.
- Legalized peak-derived stops against the current broker tick, stops level, and freeze level. If the ideal floor has already been crossed, the bot requests the best currently legal profitable stop; it never crosses the entry price.
- Broker-confirmed SL/TP values—not stale preflight values—now drive state, alerts, and readback.
- Known broker rejections and failures can retry the same protective command. Uncertain submission outcomes remain locked until broker reconciliation.
- Uncertain mutation rows retain the exact MT5 request after preflight adjustment, allowing restart reconciliation to compare with the price actually submitted.
- Repaired the armed-retest exception and made retest state consume only after a complete decision exists.
- Removed duplicate reversal defaults that silently replaced the stricter production values.

## Deterministic dynamic-SL behavior

- Bot-created trades still require a broker-side initial SL.
- With packaged defaults, winner protection arms at the first of: `0.55 ATR`, `0.9R`, `3.0` price points, or a confirmed manual BE/trail command.
- The high-water mark is monotonic. The normal winner floor retains at least `62%` of peak price excursion and can only ratchet further into profit.
- Recovery breathing can loosen a previously tightened winner stop only to the retained-profit floor. It cannot return a protected winner to loss.
- Underwater widening remains recovery-gated and capped by account risk, `0.35R` extra distance, two widenings, cooldowns, expiry, invalidation, and news hard-cut rules.
- Time stop, fast-fail, invalidation, broker SL, and the tick-level EA remain independent cut layers.

These are deterministic safeguards, not a promise of profit or perfect fills. Gaps, slippage, terminal downtime, and broker rejection can still exceed a requested price. The fresh Tick Guard gate reduces the period in which Python alone would own protection.

## Manual control

- Telegram-confirmed `/buy` and `/sell` use the same sizing, SL, validation, identity, and broker-readback gateway as UI entries.
- `/be <ticket>` arms break-even protection.
- `/trail <ticket>` now persists as an ongoing trailing instruction after the first broker-confirmed stop move.
- UI/Telegram controls intentionally manage only positions carrying the configured GodMode magic/comment ownership stamp. A trade opened directly in MT5 is not silently adopted.

## Tick Guard attestation

New live entries require a heartbeat no older than 20 seconds from the matching EA. The heartbeat must match:

- build `V13.55.1-PRODUCTION-PROTECTION-HOTFIX`;
- magic number;
- comment prefix;
- configured trading symbol.

The Windows installer and compile helper no longer accept an old `.ex5` as proof of a successful compile.

## Verification boundary

Python tests, syntax/static checks, TypeScript, and the optimized frontend bundle are verified in this package. MT5/MetaEditor compilation, broker-specific stop behavior, disconnect recovery, and demo soak require the target Windows terminal and are deliberately left as mandatory release gates. Complete [V13_55_1_VERIFICATION_REPORT.md](V13_55_1_VERIFICATION_REPORT.md) before enabling live money.
