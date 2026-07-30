# GodMode Gold Bot V15.0.7 Release Notes

**Build:** `V15.0.7-DETERMINISTIC-PROTECTION-HARDENED`

V15.0.7 is a focused protection-determinism and missed-move-analysis release. It preserves the existing entry strategy and dashboard styling.

## Deterministic stop ownership

- Python is the sole automated stop-policy decision owner.
- The exact-build `GodModeTickGuard` is the sole automated broker-side SL actuator while a fresh policy directive exists.
- Tick Guard executes `HOLD`, `CUT`, `PROTECT`, `RECOVER` and `BREATH` directives on MT5 ticks.
- Its local break-even, trail and hard-floor rules run only when the Python policy owner is stale or absent.
- Python no longer performs automated `MODIFY_SL` mutations from the open-trade management loop.

## Breathing and winner protection

- `BREATH` is rejected unless MT5 readback proves that the current broker SL already protects profit.
- The proposed breathing SL must remain profitable and legal under the broker stop/freeze rules.
- The V14 winner wrapper cannot activate below `protectStartAtr`; an already armed position remains armed after activation.
- Broker-confirmed `PROTECT` and `BREATH` transitions are persisted immediately.

## Deterministic timing and recovery state

- Recovery confirmation, cut confirmation, cooldown, grace and maximum hold now use elapsed monotonic seconds.
- Epoch anchors allow timers to survive a backend process restart.
- Trade age is reconstructed from `openTimeMsc`, `openTimestamp`, numeric `openTime`, or the broker UTC open-time string.
- Peak distance and peak R are persisted immediately whenever a new high-water mark is observed.
- Broker-confirmed SL changes are persisted immediately rather than waiting for the periodic checkpoint.

## Live ATR fail-closed policy

A synthetic `8.0` ATR is no longer used for risk-changing decisions. A valid positive live ATR is required for:

- Dynamic recovery widening.
- Staged pyramiding.
- Protected Burst continuation and sizing.
- Post-loss same-direction re-entry proof.
- Repeat-setup ATR displacement checks.
- Live AI recovery-monitor output.

Missing ATR blocks the risk-changing action and records a runtime-health reason.

## Missed-move replay

- Events are identified by symbol, side, timeframe and the completed pump-candle epoch.
- Legacy duplicate observations within ten seconds are consolidated without five-minute bucket artefacts.
- Entry begins at the first executable quote after the blocked decision: BUY ask or SELL bid.
- Replay uses chronological MT5 ticks: BUY exits at bid and SELL exits at ask.
- Best favourable movement and adverse movement before the best point retain their actual exit prices and timestamps.
- The 0.01-lot counterfactual uses MT5 `order_calc_profit` when available, with an explicitly labelled XAU price-distance fallback only when broker calculation is unavailable.

## MT5 bridge additions

- Market snapshots expose `tickTime` and `tickTimeMsc`.
- Open positions expose `openTimestamp` and `openTimeMsc`.
- `copy_ticks_range` provides sorted bid/ask tick replay.

## Safe release defaults

- Live Trading: OFF.
- Auto Trading: OFF.
- Dry Run: ON.
- Deployment mode: `LIVE_RESTRICTED`.
- Maximum open positions: 1.
- Maximum restricted volume: 0.01.
- Complex entries: disabled.
- Exact-build Tick Guard: required for live operation.

## Required Windows validation

The included MQL5 source must be compiled in MetaEditor with zero errors and attached to the active XAUUSD chart. Static Linux verification cannot compile `.mq5` to `.ex5` or prove broker-specific fills, stop/freeze behaviour, slippage, terminal restarts or network recovery. Complete those checks on an MT5 demo account before live use.
