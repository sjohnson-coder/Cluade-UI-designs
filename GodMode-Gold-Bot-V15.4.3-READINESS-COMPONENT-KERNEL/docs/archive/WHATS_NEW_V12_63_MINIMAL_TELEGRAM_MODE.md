# V12.63 — Minimal Telegram Mode

This build reduces Telegram noise and keeps only useful/actionable messages.

## New default Telegram behaviour

Minimal Mode is ON by default. Telegram now prioritises:

- executable trade approvals / trade fired / trade sent
- trade closed alerts
- rejected order / broker failure alerts
- Protected Burst events
- risk / emergency / kill-switch alerts
- AI optimisation / strategy coach alerts
- daily and weekly recaps
- direct command replies, e.g. `/positions`, `/mode`, `/auto`, `/semi`

## Suppressed by default

- WAIT forecast / preview alerts
- Fast Sniper retest/no-chase watchlist alerts
- momentum spike watch alerts
- market-open heartbeat messages
- BE / trailing / TP-push chatter
- repeated duplicate messages
- automatic separate “Quick controls” messages after every signal

## New Settings controls

Settings → Telegram Alerts now includes:

- Minimal Useful Messages Only
- Trade Entry / Exit Alerts
- Burst Alerts
- Risk / Emergency Alerts
- BE / Trailing / TP Chatter
- Watchlist / Retest Noise
- Market Open / Close
- Auto-send Control Buttons
- Duplicate cooldown seconds

## Why this helps

Telegram now behaves more like a command/control panel instead of a constant feed. Useful events still arrive, but repeated scanning updates and management chatter stay in the dashboard/journal.
