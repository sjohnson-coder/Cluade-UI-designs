# V12.51 — Fast Signal Watchdog / Retest Alert Fix

This patch fixes the issue where the bot only sent a Market Open Telegram message during a fast XAUUSD move and did not send a trade/retest signal.

## Fixed

- Added a low-latency Fast Sniper Signal Watchdog that runs from the fast backend loop.
- Fast Sniper TAKE setups now generate Telegram alerts even when the normal WAIT forecast engine is silent.
- Semi-auto live mode now queues TAKE / SCOUT approval immediately from the fast lane.
- Auto mode remains fastest: when live/auto/dry-run-off are enabled, the entry path can fire without waiting for Telegram approval.
- Hot M5 momentum spikes now send a no-chase / watch-retest alert instead of going silent.
- Fast sniper/retest alert settings added to Settings → Telegram Alerts.

## Why this matters

The old WAIT forecast system used the normal decision engine and a slow forecast interval. It could miss Fast Sniper states because the fast lane lived in the execution loop. V12.51 separates fast signal alerts from generic wait forecasts.

