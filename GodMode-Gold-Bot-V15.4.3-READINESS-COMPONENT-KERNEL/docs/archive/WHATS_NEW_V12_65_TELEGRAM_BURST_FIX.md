# GodMode V12.65 — Telegram Burst + Live Stability Fix

## Fixed: white screen after saving settings
The live start scripts no longer run Uvicorn with `--reload`. In previous builds, saving `backend/data/settings.json` triggered the development reloader, restarting the API/UI server and causing the dashboard to briefly go blank or stay white if MT5 startup/auto-connect took time.

Use the normal launchers for live trading:
- `1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat`
- `start_backend.bat`
- `2_INSTALL_EA_AND_START_GODMODE.bat`

A separate `DEV_START_BACKEND_WITH_RELOAD_ONLY.bat` is included for code development only.

## Fixed: Telegram approvals not always visible
- TAKE / SCOUT / SKIP buttons are no longer suppressed by Minimal Telegram mode.
- If a semi-auto executable setup is queued locally but Telegram delivery fails, the heartbeat now reports the Telegram failure instead of silently assuming the phone received the buttons.
- Pending approvals can resend after a short gap if the first Telegram delivery failed or was not confirmed.

## Fixed: real trade alerts being deduped
The 90-second Telegram duplicate filter no longer suppresses real broker events such as:
- Trade fired
- Trade sent
- Scout sent
- Order not sent
- Trade closed / close failed

This prevents repeated same-direction entries or exits from silently missing Telegram updates.

## Added: Manual Telegram Burst button
Telegram position/control panels now include:
- `⚡ Fire Burst Now`
- `/burst_now` command

This authorises one protected-burst batch immediately, but it does **not** bypass safety. The normal safety gates still check MT5 connection, live/auto switches, open base position, BE/protected floor, spread, confidence, recovery score, exposure caps, cooldown, validation lock and market conditions.

## Improved: Loss-feedback governor
The bot still blocks revenge re-entries after a loss, but it now allows a genuine fresh impulse after one same-direction loss when all of these are true:
- price has moved strongly away from the failed exit,
- EMA reclaim is present,
- the setup is not SCOUT,
- confidence is still acceptable,
- only one same-direction loss is in the recent loss window.

This addresses the case where the chart visibly shows a clean continuation edge but the old governor was stuck at Proof 4/5 and kept skipping.
