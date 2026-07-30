# GodMode Gold Bot V12.75 — Frontend Crash Fix + Database Purge

## 1. The frontend crash (root cause found and fixed)

`TradingViewChart.tsx` rendered `<div id={containerId}>` through React, then imperatively did
`el.innerHTML = ''` and let TradingView inject an iframe into that same node. React's virtual
DOM never knew. On unmount (i.e. every time you navigate away from Signals) React called
`removeChild` on a node TradingView had already replaced →
**`NotFoundError: Failed to execute 'removeChild' on 'Node'`** → blank page.

Fixed properly:
- React now owns only an outer host div. The widget's container is created imperatively as a
  child that React never renders and never tries to reconcile.
- Cleanup actually destroys the widget (`widgetRef.current.remove()`) and clears the host node,
  instead of only flipping a `cancelled` flag and leaking the widget on every timeframe change.
- Bonus: the R/R display divided by zero when `entry === sl` (rendered literal "Infinity") and
  assumed `tp2` always exists — scout/fast-lane signals only carry `tp1`. Now guarded, falls back
  to tp1, and renders nothing if the number isn't finite.

## 2. Old trades kept coming back (root cause found and fixed)

`_is_bot_record()` claims a broker deal as the bot's if `magic == GODMODE_MAGIC` **or** the
comment starts with `GODMODE_`. Every past version of the bot used the same magic and prefix,
so a 365-day history pull re-adopted trades from engines that no longer exist — polluting
analytics, probability calibration, the AI coach's diagnosis, and the win/loss governors.

**New: Data Epoch + Purge (Settings → 12z).**
- `POST /api/data/purge` with `scope=history|memory|journal|all` and `confirm=true`.
- Purging writes a cutoff timestamp. All broker deals *before* it are hidden from **every**
  read path at once — filtered at the single choke point (`_enrich_history`), which also means
  purged trades can never re-enter the learning path.
- **Nothing on your broker account is touched.** No positions closed, no deals deleted, settings
  untouched. Undated rows are never hidden.
- `GET /api/data/epoch` reports whether a purge is active and since when.
- Four buttons in Settings: Purge Trade History / Learned Memory / Decision Journal / Everything,
  each behind a confirm dialog. Recommended after any major upgrade.

## 3. Speed (verified, not assumed)
- Boot: **0.124s** (budget 0.30s) — unchanged; the epoch is one disk read at startup.
- Epoch filter: parsed dates are memoised onto the row after first touch →
  **33.8ms → 1.39ms per 5000 rows (24× faster, 0.28µs/row)**. Zero measurable cost.
- `/api/signals`: 3.81ms. The entry/decision hot path is untouched by this release.

## Validation
Purge: blocked without `confirm`; hides pre-cutoff trades; keeps post-cutoff and undated ones;
`_enrich_history` drops purged rows before analytics *and* before learning; epoch survives
restart; status endpoint correct. Memoisation verified for both correctness and 24× speedup.
Full V12.67–75 regression green: secret-safe save, rollback, signals list guarantee, pure
settings read, audit scoreboard, repaired fast-fail clock, range-fade crash-block, journal
export. py_compile clean across all modules.

## Rebuild note
Backend fixes (purge, epoch, endpoints) are live on restart. The **crash fix and the Purge
buttons are frontend source changes** — run `cd frontend && npm install && npm run build` to
get them. Until then you can purge via `POST /api/data/purge {"scope":"all","confirm":true}`.
