# GodMode V12.35 — Lag fix (MT5 snapshot caching + non-blocking feeds)

You reported the bot lagging. I profiled it and found two causes — both fixed here. No behaviour
changes, no settings to touch; it's pure performance.

## Cause 1 (the big one): every poll re-fetched 4 timeframes from MT5
`market_snapshot()` pulls **tick + symbol info + M15 + H1 + H4 + D1** — about **1,200 candles over 7 MT5
calls** — and it ran with **no caching**. Meanwhile the UI polls several endpoints that each call it
*every 5 seconds*: the topbar (status + market), and on the AI Agent page the action-matrix **and**
market-snapshot fire together via `Promise.all`. With live trading on, the 3-second auto-protection loop
adds another. So each cycle fired **3–4 independent 7-call multi-timeframe fetches** at the MT5 terminal
— that's the lag.

**Fix:** a 2.5-second snapshot cache in the MT5 bridge. All the near-simultaneous polls in one cycle now
share **one** fetch.
- Verified: a burst of 4 snapshot calls dropped from **4 full fetches → 1** (16 `copy_rates` IPC → 4).
- TTL is deliberately 2.5s — **shorter than the 3s protection loop**, so trade management *always*
  refetches fresh data and never acts on a stale price. Order fills already re-read the live tick at
  execution, so nothing about entries/exits gets staler.
- Cache auto-clears on connect / disconnect / Refresh, so reconnecting shows live data instantly.
- Override with `GODMODE_SNAPSHOT_TTL=0` to disable (or a larger number for even less MT5 load).

## Cause 2: a slow news/macro URL could freeze a poll for up to 8s
The economic-calendar and DXY/US10Y feeds refreshed **inline** on the request thread (8s timeout each).
With the free ForexFactory link you added, every ~5 min one decision/poll could block up to 8s while it
refreshed — a periodic freeze.

**Fix:** both feeds now refresh on a **daemon thread** and return the last-good (or neutral) value
**immediately**. Verified: a deliberately-slow feed that used to block 8s now returns in **0 ms**, and the
cache warms in the background a moment later. The 5-/10-minute cache and cache-on-failure behaviour are
unchanged.

## Net effect
With MT5 connected, MT5 round-trips per 5-second cycle drop by roughly **60–75%**, and no request can be
blocked by a slow feed. Signal generation, profit protection, recovery monitor and the pyramid logic are
all untouched — they just run on a snapshot that's at most 2.5s old.
