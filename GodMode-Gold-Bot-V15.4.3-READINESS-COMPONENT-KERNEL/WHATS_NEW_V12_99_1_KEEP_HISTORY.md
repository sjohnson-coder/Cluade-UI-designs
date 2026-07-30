# GodMode Gold Bot V12.99.1 — Trade history now survives upgrades automatically

## The problem
Every version bump printed "New engine version detected. Trade history reset: only trades from
this version onward will be counted." You are trying to accumulate a ~50-trade validation base —
but we have shipped ~15 versions in three days, so the count kept resetting to zero. The data
needed to answer "does breakout-stop pay?" and "did entries move earlier?" was being wiped by the
very upgrades meant to improve things.

## Fixed — no action needed from you
`set GODMODE_KEEP_HISTORY_ON_UPGRADE=1` is now baked into EVERY launcher:
  1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat, 2_INSTALL_EA_AND_START_GODMODE.bat,
  START_HERE_NO_NPM_REQUIRED.bat, start_all.bat, start_backend.bat, start_backend_mobile.bat,
  DEV_START_BACKEND_WITH_RELOAD_ONLY.bat
Just start the bot the way you normally do. History now carries across every future upgrade.

## Verified
Simulated an upgrade both ways:
- WITHOUT the var: "New engine version detected ... Trade history reset" (the old behaviour)
- WITH the var: silent, no reset, history preserved
The patch is confirmed present in all 7 launchers.

## If you ever start the bot another way
- PowerShell:  $env:GODMODE_KEEP_HISTORY_ON_UPGRADE=1 ; then start the bot in the same window
- CMD:         set GODMODE_KEEP_HISTORY_ON_UPGRADE=1  ; then start the bot in the same window
- Permanent (survives reboots): Windows Search -> "Edit the system environment variables" ->
  Environment Variables -> New (User variables) -> Name: GODMODE_KEEP_HISTORY_ON_UPGRADE,
  Value: 1 -> OK. Restart the terminal.
The variable must be set in the SAME window/session that launches the bot — that is why baking it
into the .bat is the reliable route.

## Note on the reset that already happened
This preserves history from now on; it cannot recover counts already reset by earlier upgrades.
Your broker-side deal history in MT5 is untouched — this only affects which trades the engine
attributes to itself for its own stats.

Everything else unchanged from V12.99 (all 33 settings visible, 0 gaps).
