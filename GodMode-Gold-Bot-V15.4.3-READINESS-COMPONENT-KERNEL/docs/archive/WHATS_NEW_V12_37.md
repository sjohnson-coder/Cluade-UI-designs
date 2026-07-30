# GodMode Gold Bot V12.37 — Validation + Telegram Semi‑Auto Trader Upgrade

This build upgrades V12.36 from an advanced scanner/auto-bot into a safer semi-auto trading assistant.

## 1. Telegram semi-auto trader
When the decision engine finds an executable BUY/SELL setup, the bot now sends Telegram approval buttons instead of firing automatically by default:

- ✅ TAKE — send the full approved setup to MT5.
- 🔒 SCOUT — send the setup at reduced size where broker minimum lot allows.
- ❌ SKIP — mark the setup as skipped; no MT5 order is sent.
- 🛑 Kill Auto — immediately disables auto-entry and engages the kill switch.

Useful Telegram commands:

- `/positions` — show open bot positions with Close / Move SL to BE buttons.
- `/kill` — emergency stop from your phone.
- `/help` — show Telegram controls.

Default mode is now `execution.mode = semi_auto` and `telegram.semiAutoEnabled = true`.

## 2. Hard validation lock before live execution
Live orders are now blocked until the bot passes real MT5-history validation.

Default unlock requirements:

- Real MT5 history, not synthetic demo candles.
- At least 40 validation trades.
- Profit factor ≥ 1.30.
- Expectancy ≥ +0.10R.
- Walk-forward consistency ≥ 70%.

Run **Backtest > Validate** after connecting MT5. The result is saved in `backend/data/validation_gate.json` and exposed at `/api/validation/status`.

## 3. Neutral strategy priors
The strategy ranking no longer trusts catalog win-rate numbers as proven edge.

- 0–29 live bot trades: neutral prior.
- 30–99 trades: blended live result + neutral prior.
- 100+ trades: real live memory can dominate.

This prevents an unproven strategy from ranking as “GodMode” just because its static catalog says 68–72%.

## 4. Real broker execution memory
Every live order/close/modify now records:

- requested price,
- filled price,
- slippage in price units,
- latency in ms,
- retcode/rejection status.

Recent execution memory is stored at `backend/data/execution_memory.jsonl` and used to grade broker execution quality.

## 5. Crash-safe multi-target option
When volume is large enough to split safely, the bot can place separate broker-managed TP1–TP4 child orders, so TP exits survive a Python/server crash.

For 0.01 lot trading, the bot keeps the safer single broker SL/TP runner because broker minimum lot usually prevents safe splitting.

## 6. Improved safety visibility
The action matrix now includes:

- validation status,
- broker execution quality,
- validation gate reason when locked.

## Important
This version was syntax-checked and import-tested in the sandbox, but it cannot be live-tested against your MT5 terminal here. Start with dry-run/demo and confirm Telegram buttons, validation lock, MT5 connection, and broker fills before using live funds.
