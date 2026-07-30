# GodMode Gold Bot V12.69 — Fast Boot + Log Rotation + Full User Guide

## Startup speed
- matplotlib (chart renderer) is now imported lazily on first chart render instead of at
  boot. Measured backend startup: **1.96s → 0.10s** (~95% faster module load). First
  Telegram chart pays the ~1.2s once; every boot pays nothing.
- Append-only .jsonl logs (decision journal, execution memory) are auto-rotated at boot
  when they exceed 4MB, keeping the newest entries. Prevents the slow creeping startup
  lag and memory growth after weeks of live running.

## Docs
- New `USER_GUIDE_RUN_AND_MANAGE.md` — plain-English: first-time setup, the 3-rung safety
  ladder to go live, AI connection for BOTH Claude and OpenAI, auditor rollout order,
  5-minute daily routine, common mistakes, phone access, FAQ.

## Confirmed behaviours (asked & verified)
- OpenAI API fully supported (coach + auditor, incl. image blocks) alongside Claude.
- With NO AI connected the bot runs 100% normally — AI layers fail-open/skip.
- The Entry Auditor assists live, in real time, inside the entry path (engine approve →
  AI audit → veto/downgrade/SL-tighten → order), not in the tick loop.

## Validation
- py_compile all modules passes; full regression suite (secret-preserving save, rollback,
  signals list guarantee, pure settings read, auditor default-off, chart helper safe with
  MT5 disconnected) passes; chart render verified working after lazy-load refactor;
  rotation verified (200k-line file → newest 5k kept, order preserved).
