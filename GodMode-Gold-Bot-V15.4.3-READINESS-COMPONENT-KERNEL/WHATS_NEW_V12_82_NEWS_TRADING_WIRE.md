# GodMode Gold Bot V12.82 — News Now TRULY Gates Trades (the real root cause)

## Your question first: is the review unified?
Yes. The V12.80 trade-review engine feeds INTO the V12.81 "Recommended Actions" panel on the
AI Agent page — it is the first source merged in, not a separate button. (It also has a card on
/tools, but that is only the no-rebuild fallback view, not a second apply surface.)

## Why news kept "going off" — the actual root cause (found this time)
There are THREE separate economic-calendar objects in the bot:
1. `live_calendar` (EconomicCalendarAPI) — the DISPLAY feed (dashboard News card).
2. `calendar` (EconomicCalendar) — a module-level instance.
3. `decision_engine.calendar` (EconomicCalendar) — **the ONLY one that actually blocks trades.**

V12.77 added `configure()` and wired it — but ONLY to `live_calendar` (the display one).
The trading calendar (`decision_engine.calendar`) is a DIFFERENT class that resolved its URL
from **environment variables only** and had no `configure()` at all. So your Settings 12c URL
reached the dashboard feed but NEVER reached the calendar that gates entries. Result: news could
show "configured" on screen while the trading news-blackout was permanently blank — displayed,
never in use. That is exactly the disconnect you described.

### Fix
- Added `configure(url, before, after)` to the `EconomicCalendar` class in
  `services/market_intelligence.py`; its `url` now prefers the settings override, falls back to env.
- `_apply_runtime_settings()` now configures ALL THREE calendars (display, module, and
  `decision_engine.calendar`) from `dataFeeds.economicCalendarUrl`, using signature inspection so
  each class gets only the args it accepts.
- Blackout windows (before/after minutes) from Settings now apply to the trading calendar too.

### Proven end-to-end (not assumed)
Test: save a URL in Settings -> `decision_engine.calendar.url` is set (was always blank) ->
inject a high-impact USD event -> the decision engine returns
**"High-impact news blackout — no entries allowed"** and the trade is gated. News now
influences trades, it does not just display.

## Why the dashboard dot kept flickering to red "off"
The display status returned `error_or_empty` (red) whenever the feed had zero events RIGHT NOW —
which is normal on weekends / market-closed (your screenshots show Market CLOSED). A configured,
reachable, simply-quiet feed was being painted as "off".

### Fix
New `live_quiet` status + an `active` flag: when the calendar is configured and not in a hard
fetch-error state, the dashboard dot is GREEN regardless of whether events exist this instant.
`error_or_empty` is now reserved for an actual fetch failure. No more weekend flicker.

## Speed / safety
Boot 0.081s. `/api/signals` unchanged. Only feed-config and status logic touched; entry hot path
untouched. Full V12.67-82 regression green (unified recs, review engine + whitelist, secret-safe
save, epoch, governor, signals, audit scoreboard).

NOTE: rebuild the frontend (`cd frontend && npm install && npm run build`) to see the green dot
change; the backend gating works immediately regardless of the bundle.
