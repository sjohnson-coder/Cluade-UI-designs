# GodMode Gold Bot V12.43 — Feed Persistence + Capital-Aware Lot Guard

## Fixed

### Live News & Calendar persistence
- Dashboard feed state now persists through page navigation using backend cache + browser localStorage.
- Feed status no longer flashes OFF when you leave Dashboard and return.
- `/api/feeds/status` now re-syncs Settings → Data Feeds into runtime environment every call.
- Last-known-good economic calendar, market news, and macro states are cached and returned as `stale: true` during temporary API empties/errors instead of being wiped.

### Economic calendar parser
- More robust parsing for ForexFactory-style JSON, FMP-style JSON, and generic event arrays.
- Supports more field names: `title/event/name/indicator/release`, `currency/country/Country`, `date/time/datetime/timestamp/releaseDate`.
- Handles ISO strings, UTC strings, common date-time formats, and seconds/ms timestamps.

### Macro feed parser
- More robust parser for quote APIs with nested `data`, `results`, `quote`, `values`, or `historical` arrays.
- Reads common quote fields: `price`, `value`, `close`, `last`, `rate` and percentage fields such as `changesPercentage`, `changePct`, `regularMarketChangePercent`.

### Dashboard card location and responsiveness
- Moved **Live News & Calendar** out of the cramped right-side column.
- It now sits under **Analytics Overview / Top Strategies**, giving it much more width.
- Added responsive layout for smaller screens.

### Performance / lag reduction
- Dashboard no longer makes a second separate live-news request every 5 seconds.
- The News card now uses `/api/feeds/status`, which already includes market-news status and latest headline.
- This reduces repeated API calls and MT5/UI polling pressure.

### Lot-scaling safety
- Added a central `safe_entry_lot` governor used by auto entries and Telegram TAKE/SCOUT.
- First-entry sizing now respects:
  - `baseLot`
  - `lotStep`
  - `maxLot`
  - `maxTotalLots`
  - broker min/step/max volume
  - account equity and configured `riskPerTrade`
  - actual entry-to-SL distance
- Default `ai.firstEntryLotMode = base_lot_only` is now respected.
- This prevents accidental jumps like `0.01 → 1.42 lots` when volatility sizing sees a tight stop.
- Telegram approvals are clamped again at execution time, so old pending approvals cannot bypass the safety cap.

## How to use
1. Go to **Settings → 12c. Data Feeds**.
2. Paste your calendar/news/macro links.
3. Click **Save & Test feeds** or the main **Save & Apply** button.
4. Go back to Dashboard. The wider News card should remain stable/persistent.
5. Check `/api/feeds/status` if a feed says CHECK — it will show the reason/detail.

## Notes
- Blank feeds remain neutral and do not block trades.
- If a feed was recently live but temporarily fails, the UI shows a cached live state instead of flickering OFF.
- Economic calendar blackout remains the only default news hard-block. Market headlines are informational unless you add a sentiment hard filter.
