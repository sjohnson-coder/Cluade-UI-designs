# GodMode Gold Bot V12.76 — UI Truth, Version Epoch, News Resilience

## 1. Why none of the new features appeared (root cause)

The bot serves `frontend/dist`; all UI work lives in `frontend/src`. **The shipped `dist`
bundle was compiled on July 7 — before every change of the last several releases.** Purge
buttons, CSV/PDF export, the AI audit panel, the skip-reasons panel: all present in source,
none compiled. The backend was correct the whole time; the browser was running old code.

Fixed structurally so it can never happen silently again:
- **`GET /api/system/build-status`** compares the newest `src/**.tsx|ts|css` mtime against the
  bundle mtime and reports staleness with the exact offending file and timestamps.
- On startup the bot **prints a loud banner** if the bundle is stale.
- `REBUILD_UI_FIRST.txt` at the project root explains the one-time fix.

Run once: `cd frontend && npm install && npm run build`, restart, hard-refresh (Ctrl+F5).

## 2. Only trades from THIS bot version count (automatic)

`_is_bot_record()` matches on magic number **or** the `GODMODE_` comment prefix — both shared
by every past version — so each new build silently adopted old engines' trades into analytics,
probability calibration, the AI coach and the loss governors.

Now: on the **first boot of a new version** the bot stamps a data-epoch at "now". Only trades
taken by the current engine onward are counted. Nothing is deleted on the broker; open
positions untouched. Same-version reboots never move the epoch. Opt out with
`GODMODE_KEEP_HISTORY_ON_UPGRADE=1`. Manual purge (V12.75, Settings → 12z) still available.

## 3. News feed "keeps disconnecting" (real bug, fixed)

On **any** fetch exception the calendar did `self._cache=[]; self._cache_at=now` — it cached
the failure. One transient blip wiped good events, reported `error_or_empty`, and **silently
dropped news-blackout protection** until the TTL expired.

Now a failed refresh keeps the last-known-good events, does not stamp the cache time (so the
next call retries immediately), and reports `status: "live_stale"` with the error. Blackout
protection stays active. Only a cold start with no cache ever returns empty.

## 4. Strategies tab was static — now live

The tab hardcoded `'M15'` (so switching execution to M5 changed nothing on screen) and the
"Why AI Chose This Strategy" card was **fake text** with a hardcoded `ProgressBar value={87}`.

`/api/strategies` now serves, per strategy: the **real execution timeframe** from settings, the
**live rank score** and regime/session fit from the same ranking the router uses each bar,
`isSelected` (picked this bar), live win rate vs catalog estimate (clearly labelled), live net
P&L, live trade count, and an honest **PROVEN (≥20) / LEARNING (≥5) / UNPROVEN** evidence badge
so a 3-trade 100% win rate can never look like an edge. Rows are sorted by rank score. The
Strategies page was rewritten to render all of it, including a real "why chosen" breakdown.

## Speed
Boot **0.086s**. `/api/signals` unchanged. The strategy enrichment reuses the already-cached
decision — no extra engine work, no added latency on the entry path.

## Validation
Version-epoch: auto-fires on upgrade, hides prior-version trades, does **not** move on a
same-version reboot, env opt-out honoured. Build detector correctly flags the real stale
bundle. News: transient failure preserves events + blackout and reports `live_stale`; cold
start honestly reports empty. Strategies: returns `M5` after switching timeframe, evidence
badges correct. Full V12.67–76 regression green. py_compile clean.
