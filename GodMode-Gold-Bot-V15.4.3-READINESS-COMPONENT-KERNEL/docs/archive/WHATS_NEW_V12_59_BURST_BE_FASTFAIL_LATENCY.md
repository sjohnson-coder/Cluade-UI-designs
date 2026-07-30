# V12.59 — Burst BE Trigger + Fast-Fail + Latency Guard

## Why Burst did not fire on the first protected trade
The previous protected-burst monitor was blocked by the global auto-entry cooldown. After the base trade opened, `lastFire` activated the normal cooldown, so the burst monitor could miss the exact moment the base trade first reached BE/protected floor. Burst then evaluated later, sometimes only after a second trade or later loop.

## Fixes
- Protected Burst now bypasses the normal entry cooldown when a bot position is already open.
- BE/protected floor can now trigger by actual XAUUSD points, default `0.30`, not only R/ATR.
- When AI Dynamic SL first locks a trade, it flags Burst for immediate evaluation.
- Burst default confidence reduced from 84% to 76% so strong live setups like 76.2% do not wait unnecessarily.
- Burst recovery threshold reduced from 72 to 62 to allow continuation adds while still blocking weak recovery.
- Manual Telegram batch confirmation defaults OFF; Telegram can still turn Burst ON/OFF and manage modes.
- Burst batch cooldown reduced to 8s, not 45s.
- Burst requires base leg to be protected and at least +0.30 points in profit.
- Burst legs use faster fail protection: 45s and -0.30R default.
- Heavy closed-trade reconciliation is throttled to reduce MT5/UI lag.

## Safety
This is still Protected Burst, not zero-loss martingale. Pyramiding remains OFF when Burst is ON. Burst only adds after the base basket has a protected floor and continuation probability remains valid.
