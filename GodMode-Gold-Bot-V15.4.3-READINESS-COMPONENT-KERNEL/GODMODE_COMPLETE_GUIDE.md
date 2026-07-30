# GodMode Gold Bot V14.1.23 Complete Start Guide

## Use these files

For the first installation, use `2_INSTALL_EA_AND_START_GODMODE.bat`.
For normal daily startup after the EA has been installed, use `START_GODMODE.bat` or `start_all.bat`.
For EA diagnosis, use `CHECK_TICK_GUARD.bat`.

The other files are source code, support tools, compatibility launchers, documentation and tests. They are not separate applications that must all be installed.

## First installation

1. Close old GodMode backend windows and remove older Tick Guard EAs from MT5 charts.
2. Extract V14.1.23 into a new folder with normal write permission, such as `C:\Trading\GodMode-V14.1.23`.
3. Open and log in to the exact broker MT5 terminal.
4. Run `2_INSTALL_EA_AND_START_GODMODE.bat`.
5. Refresh MT5 Expert Advisors and attach `GodModeTickGuard` to one XAUUSD chart.
6. Enable **Allow Algo Trading** in the EA dialog and enable the global MT5 Algo Trading toolbar button.
7. Run `CHECK_TICK_GUARD.bat` and require a PASS result.
8. In the dashboard, open Health Center and wait for all runtime components to receive fresh heartbeats.

## Why V14.1.22 showed degraded readiness

V14.1.22 exposed several independent issues:

- Windows rejected directory-handle `fsync` after an atomic JSON file replacement. The file had already committed, but the warning made persistence appear broken.
- The older EA heartbeat used broker-server time, while Python validated UTC epoch time. A broker two hours ahead produced a false stale-heartbeat failure.
- On machines with multiple MT5 terminals, the installer could copy the EA and configure the control path for the wrong terminal profile.
- The normal desktop build was gated by an enterprise evidence certificate requiring externally signed evidence files, so a local installation could never complete it.
- A normal close-reconciliation throttle used `StopIteration`, which was logged as a subsystem failure.

V14.1.23 corrects each path while retaining fail-closed live order admission.

## Local runtime attestation

The normal desktop live gate continuously verifies:

- MT5 is connected and permits trading.
- The exact V14.1.23 Tick Guard heartbeat is fresh.
- The heartbeat matches the bot magic number, comment prefix and symbol.
- Event-loop, trade-protection and broker-reconciliation heartbeats are healthy.
- There are no unresolved broker commands.
- The runtime data directory is writable.

When these checks pass, Health Center reports **Local Live Runtime Attestation: OK**. This is the correct operating certificate for a local desktop installation. The separate enterprise evidence mode remains available for formal audited deployments.

## Troubleshooting Tick Guard

Run `CHECK_TICK_GUARD.bat`. Follow the exact failure it prints:

- **Heartbeat file does not exist:** attach the newly compiled EA, enable Algo Trading and confirm the chart is receiving ticks.
- **Wrong build:** remove the old EA, recompile V14.1.23 and attach the new `.ex5`.
- **Wrong terminal path:** keep the intended MT5 terminal open, rerun `COMPILE_TICK_GUARD_V14_1_23.bat`, then reattach the EA.
- **Magic, prefix or symbol mismatch:** make the EA inputs match the Settings page.
- **Stale heartbeat:** confirm the market/chart is receiving ticks and the EA smile/status icon is active. The timer also writes heartbeats, so a completely absent update normally indicates the EA is not running.

## Safety state

The release ships with Live Trading OFF, Auto Trading OFF and Dry Run ON. Turn on Live Trading and Auto Trading only after MT5 and Tick Guard are both verified. Live order entry can still be correctly blocked by market closure, broker restrictions, kill switch, unresolved execution outcomes, validation policy or unhealthy protection loops.
