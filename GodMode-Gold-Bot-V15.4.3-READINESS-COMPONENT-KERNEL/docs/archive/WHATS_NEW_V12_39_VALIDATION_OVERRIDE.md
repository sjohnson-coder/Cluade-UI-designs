# GodMode Gold Bot V12.39 — Validation Lock Settings Override

## Added

- New **Settings → 3b. Validation Lock & Live Unlock** card.
- You can now switch the validation lock ON/OFF from the dashboard.
- You can configure the validation pass rules directly in Settings:
  - minimum validation trades,
  - minimum profit factor,
  - minimum expectancy in R,
  - minimum out-of-sample/walk-forward consistency,
  - require real MT5 history,
  - allow Telegram TAKE/SCOUT manual override.

## Safety behaviour

- **Validation Lock ON**: live MT5 execution is blocked until Backtest → Validate passes.
- **Validation Lock OFF**: live/semi-auto execution can proceed without validation proof. Use this only for demo testing or when you accept the risk manually.
- **Allow Telegram Manual Override ON**: Telegram TAKE/SCOUT can bypass validation, while fully automatic entries remain blocked.

## Backend hardening

- `validation.enabled` and legacy `execution.validationLockEnabled` are now kept in sync.
- Old `settings.json` files from earlier builds will not silently conflict with the new toggle.
