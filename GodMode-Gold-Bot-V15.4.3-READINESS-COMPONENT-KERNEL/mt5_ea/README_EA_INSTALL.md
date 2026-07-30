# GodModeTickGuard V15.4.3

GodModeTickGuard is the broker-side SL actuator for `V15.4.3-READINESS-COMPONENT-KERNEL`. Python owns the deterministic protection policy; this EA applies its fresh HOLD, CUT, PROTECT, RECOVER and BREATH directives on every MT5 tick. Local break-even, trailing and hard-floor logic runs only as a conservative fallback when the Python owner is stale or absent.

## Recommended installation

1. Open the exact MetaTrader 5 terminal and log in to the account used by the bot.
2. Remove every older GodModeTickGuard from all charts.
3. Run `2_INSTALL_EA_AND_START_GODMODE.bat`.
4. In MT5, press `Ctrl+N`, right-click **Expert Advisors**, and select **Refresh**.
5. Attach `GodModeTickGuard` to one active XAUUSD chart.
6. Tick **Allow Algo Trading** and keep the MT5 toolbar **Algo Trading** button green.
7. Keep these EA inputs matched to the bot Settings page:
   - `MagicNumber = 20250525`, unless deliberately changed in the bot.
   - `CommentPrefix = GODMODE_`, unless deliberately changed in the bot.
   - `ExpectedEngineBuild = V15.4.3-READINESS-COMPONENT-KERNEL`.
8. Run `CHECK_TICK_GUARD.bat` and require a PASS result.

A successful check confirms a fresh exact-build heartbeat from the same terminal, magic number, prefix and symbol used by the backend.

## Manual installation

1. Run `COMPILE_TICK_GUARD_V15_0_8.bat`.
2. When MetaEditor cannot be found automatically, open MT5 and select **File > Open Data Folder**.
3. Open `MQL5\Experts\GodModeTickGuard.mq5` in MetaEditor and press `F7`.
4. Confirm MetaEditor reports **0 errors** and creates `GodModeTickGuard.ex5` beside the source.
5. Return to MT5, refresh Expert Advisors and attach the EA to XAUUSD.
6. Run `CHECK_TICK_GUARD.bat`.

## Included protection

- Exact-build Python policy ownership while directives are fresh
- Tick-level HOLD, CUT, PROTECT, RECOVER and BREATH actuation
- BREATH rejection until the broker SL is already profitable
- PROTECT rejection below the configured ATR threshold
- Fallback break-even, ATR trailing and emergency hard floor only when the owner is stale
- UTC exact-build heartbeat
- Magic-number, comment-prefix and symbol isolation

The `.mq5` source alone provides no live protection. The compiled `.ex5` must be attached to a chart and continuously producing a fresh heartbeat.
