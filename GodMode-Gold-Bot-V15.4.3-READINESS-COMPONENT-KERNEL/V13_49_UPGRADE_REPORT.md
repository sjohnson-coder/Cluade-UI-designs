# GodMode V13.49 Deterministic Dynamic SL Upgrade

## Mandatory installation step

Recompile and attach `mt5_ea/GodModeTickGuard.mq5` version 1.10. The old EA does not understand the new `BREATH` ownership directive and can immediately undo a Python-selected breathing stop.

## Corrected defects

- Fixed Protected Burst calling `assess_recovery()` with invalid arguments and reading a nonexistent `score` key.
- Protected Burst now uses an open-position continuation score rather than treating entry confidence as the sole add-on probability.
- Burst analysis failures are logged, exposed through runtime health, and block safely with an explicit error.
- Telegram button renamed to `Evaluate Burst Now` because hard safety gates remain active.
- Dynamic SL now uses a deterministic continuation assessment and a structure/ATR-aware protected-profit stop.
- A breathing stop can only operate after profit protection, never crosses the entry to a loss, has a maximum count, cooldown and expiry.
- Python publishes `BREATH,ticket,stop,expiry` ownership to the MT5 guard.
- MT5 guard version 1.10 suspends its own BE/trailing during an active BREATH window while retaining the broker stop.
- MT5 guard now logs failed CUT, stop modification and broker retcodes.
- Python logs failed Dynamic SL modifications and displays a danger alert instead of silently continuing.
- Existing exact legacy settings are migrated once to runner-aware defaults without replacing customised values.
- Application version and API build identity updated to 13.49.0.

## New runner defaults

- Minimum retained peak fraction: 30%
- Maximum giveback fraction: 65%
- Minimum locked profit: 0.05R plus costs
- Continuation score to breathe: 70
- Maximum breathing events: 2
- Breathing expiry: 330 seconds
- Burst entry-quality safety floor: 68
- Burst continuation threshold: 72

These are initial deterministic controls and should be validated on demo before live capital is used.

## Verification completed

- Full Python compilation passed.
- Eight targeted regression tests passed.
- App import and route registration passed.
- Source scan confirmed removal of the broken Protected Burst recovery call.

## Live validation still required

This environment cannot compile MQL5 or connect to the user's Windows MT5 terminal and broker. Before live use:

1. Compile `GodModeTickGuard.mq5` in MetaEditor with zero errors.
2. Attach it to one XAUUSD chart and verify version 1.10 in the Experts log.
3. Configure `automation.mql5ControlFilePath` to the terminal's MQL5 Files folder.
4. Run on demo and confirm the control file contains a `BREATH` row when a protected winner approaches its stop.
5. Confirm the EA does not re-tighten the stop before the BREATH expiry.
6. Confirm a rejected stop modification appears in the dashboard and `backend/data/logs/godmode.log`.
