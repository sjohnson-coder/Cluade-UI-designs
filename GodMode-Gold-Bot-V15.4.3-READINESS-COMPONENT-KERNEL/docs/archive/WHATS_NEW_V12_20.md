# GodMode V12.20 — Market-closed awareness (Telegram open/close + no wait-signals when closed)

The bot now knows when the XAUUSD market is closed and behaves accordingly — in the UI and on Telegram.

## What's new
**1. The bot knows when the market is closed.**
Spot gold trades ~24/5, so "closed" = the weekend (Friday 21:00 → Sunday ~22:00 UTC), detected by a
timezone-safe UTC schedule and, when MT5 is connected, confirmed by **live tick-staleness** (no new
tick for 5+ minutes also flags an intraday halt / the daily break). Source of truth:
`mt5_bridge.market_open()`.

**2. The UI displays "Market Closed".**
- A **"Market: CLOSED"** chip (red) in the top bar, always visible.
- A **"Market Closed"** banner on the Dashboard with the reason ("Weekend — reopens Sunday ~22:00
  UTC") and a standby note.
- The main signal reads **"CLOSED — standby"** instead of WAIT.

**3. Telegram open/close updates.**
- On the market **closing for the day**, a **🔴 Market Closed** message is sent that **includes the
  daily trade summary** (Net PnL, win rate, PF, trades, max DD, expectancy + equity image).
- On the market **reopening**, a **🟢 Market Open** message is sent.
- These fire once, on the actual open↔closed transition (never on startup).

**4. No WAIT/forecast spam while closed.**
The throttled "Forecast — waiting for trigger" Telegram signals are **suppressed whenever the market
is closed** — you'll only get the closed summary and, later, the open notice.

**5. No entries while closed.**
With the market closed the decision is `MARKET_CLOSED`, so the auto-trade tick stands down (no new
entries). Open trades remain protected by their broker SL.

## Notes
- All gated on your existing Telegram toggle — nothing sends unless Telegram is enabled.
- The weekend schedule is UTC and conservative; tick-staleness makes it broker-exact when connected.

## Validation
Backend compiles · frontend builds · schedule verified for Sat/Sun/Fri/midweek boundaries ·
transition state machine verified (silent on startup, fires once per open↔close, no repeats) ·
`/api/status` and the Dashboard both report **CLOSED** live (weekend) · UI confirmed in a real
browser (top-bar chip + banner + "CLOSED" signal).
