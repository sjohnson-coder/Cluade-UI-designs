# GodMode Gold Bot V12.77 — The Missing Feed Wire, Import Fix, Backend Tools Page

## 1. News / DXY / US10Y stayed "not_configured" no matter what you saved (root cause)

`_apply_runtime_settings()` pushed settings into the MT5 bridge and the decision engine —
and **never touched the data feeds.** The feed objects resolved their URL from a property
that read **environment variables only**:

    @property
    def url(self):
        return os.getenv('GODMODE_ECONOMIC_CALENDAR_URL','') or os.getenv('ECONOMIC_CALENDAR_URL','')

So a calendar URL saved in Settings 12c was written to `settings.json` and consulted by
nobody. MacroFeed even carried a comment claiming Settings URLs "take effect at runtime" —
an intention that was never wired.

**Fixed.** `EconomicCalendarAPI`, `MarketNewsAPI` and `MacroFeed` now take a `configure()`
call; Settings override env (env still works headless). `_apply_runtime_settings()` pushes
`dataFeeds.*` on every save, and a changed URL force-refreshes the feed immediately instead
of waiting out the 5-minute TTL. Verified: saving a calendar URL flips `configured` to true
on the same request.

## 2. "Import config did nothing"

`allowed_roots` in `/api/config/import` was missing **`aiAuditor`** and **`mt5Connection`** —
both of which `/api/config/export` writes. Importing your own export silently discarded them.
Both are now importable (secrets still protected: a masked empty password never overwrites a
stored one). Import now returns `appliedSections` and `ignoredSections` and refuses to claim
success when nothing matched.

## 3. Purge and exports without a rebuild — `GET /tools`

The compiled dashboard can lag the source, which is what hid these controls. There is now a
self-contained page served straight from the backend at **http://127.0.0.1:8000/tools** —
no npm, no build. It provides Purge (history / memory / journal / everything), CSV and PDF
journal download, a data-epoch readout, and live diagnostics links. It shows the stale-build
banner when relevant.

## 4. Still true from V12.76
Only trades from the current engine version are counted (auto data-epoch on upgrade; opt out
with `GODMODE_KEEP_HISTORY_ON_UPGRADE=1`). Stale-bundle detection warns on startup.

## Speed
Boot **0.103s**. `/api/signals` unchanged. `configure()` is a string compare per save — the
entry/decision hot path is untouched.

## Validation
Saving `dataFeeds.economicCalendarUrl` reaches the live feed and flips `configured`; market
news and DXY/US10Y overrides applied. Settings persist across `_apply_runtime_settings()` and
to disk (revert test). Import applies 18 sections including `aiAuditor`, ignoring only `meta`
and `security`. `/tools` renders with all controls and the safety note. Full V12.67–77
regression green. py_compile clean.
