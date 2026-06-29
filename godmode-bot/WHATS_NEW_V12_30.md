# GodMode V12.30 — P0 safety & security patch (from the institutional audit)

Implements the four verified P0 findings from the V12.29 audit. These move the safety/security grades
from C+ toward A-.

## 1. MT5 institutional pre-flight (before every live order)
`mt5_bridge._preflight()` now runs before every `order_send` (execute / close / modify):
- **Adaptive filling mode** — picks the broker's supported mode (FOK → IOC → RETURN) from the symbol's
  bitmask instead of the old hardcoded IOC (which some brokers reject outright).
- **Stop/freeze-level validation** — pushes SL/TP outside the broker's minimum stop distance.
- **Margin pre-check** — `order_calc_margin` vs free margin; blocks with a clear message if short.
- **`order_check`** — the broker's own pre-trade validation; a hard rejection blocks the send.
Each order result now carries a `preflight` block for telemetry.

## 2. GET endpoints locked down
When a server API key is configured (i.e. you've exposed the bot for LAN/mobile), **every `/api/`
request — reads included — now requires the key.** Previously only writes were protected, so account,
trades and settings were readable by anyone on the network. The static app shell still loads so you can
enter the key; a banner now prompts for it. Local-only users (no key set) are unaffected.

## 3. Seeded memory quarantined from live decisions
The performance DB's sample/seed rows are now flagged and **excluded from the stats that feed live
confidence calibration and strategy ranking** (`memory.stats(live_only=True)`). Demo seed data still
populates the UI on first run, but it can no longer fake a live edge. Existing databases are migrated.

## 4. Explicit truth flags
`/api/status` now returns `dataSource` (`live_mt5` / `synthetic_demo` / `offline`) and `tradingAllowed`
(true only when connected + live + market open + kill-switch clear), with a `tradingBlockedReason`.
Synthetic data can never report `tradingAllowed: true`.

Verified: GET endpoints 401 without the key / 200 with it · app shell still loads · seed rows excluded
from live stats · status flags correct · UI clean and responsive at 360/390/1280.
