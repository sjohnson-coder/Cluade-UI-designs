# GodMode Gold Bot V12.40 — Audit Fix

This patch fixes two critical issues found during the V12.39 deep audit:

1. Auto-entry used the MT5 market snapshot side (`WAIT`) instead of the decision-engine side (`BUY`/`SELL`). In semi-auto mode this prevented Telegram approvals from being queued; in full-auto mode it could be interpreted as SELL. Orders now use the approved decision side only.
2. Volatility-normalized sizing referenced an undefined `symbol` variable, which could crash the auto-trade tick exactly when a valid setup reached execution. `symbol` is now defined from the approved decision/market settings before sizing.

Additional safety:
- Telegram queued payloads are forced to a valid BUY/SELL side.
- Telegram execution blocks invalid sides.
- MT5 execution now rejects any side that is not BUY or SELL instead of treating unknown values as SELL.
