# GodMode V12.14 — Install fix, AI 429 handling, Risk-page fixes, full-screen tabs, icons

Fixes the issues from your screenshots. (One bigger item — running backtests in the background with
a progress bar — is the dedicated next step; everything else here is done.)

## 1) Strategy Lab "Install" now actually works
Before, installing a candidate quietly changed your config but **didn't show anywhere**. Now Install:
- **adds the strategy to your Strategies page** (it appears as "Active tuning (Strategy Lab)",
  enabled, with its backtested win-rate/expectancy) — so you can see it like your other strategies;
- **applies its tuning to the live engine** (this is what changes how trades are judged);
- **persists** it, so it survives a restart;
- the **Install button turns into "✓ installed"** and only one Lab tuning is active at a time.

> Honest note from your run: your **current config tested at ≈ −0.03R** over 2.5 years (slightly
> negative after costs), and the candidates were only marginally better with low out-of-sample
> consistency. That's the tool telling the truth — **don't trade real size until Validate My Edge
> shows a real GO.** See the new guide (`GUIDE_NEW_TABS_AND_FEEDS.md`) for how to hunt a better config.

## 2) AI generator: 429 handled + clearer errors
"Too Many Requests (429)" now **auto-retries with backoff** (2s, 4s). If it's still rate-limited you
get a plain message: *"…rate-limited even after retries — your key is throttled or out of credits,
wait a minute or check your plan."* A bad key now says *"rejected the API key (401) — check it in
Settings."* So you'll always know whether it's a key problem, a credit problem, or just a busy moment.

## 3) Risk page fixes
- **"View All"** (Live Warnings & Alerts) now works — it expands to show recent system alerts &
  notifications (toggles to "Hide").
- **Refresh** now gives visible feedback (spinner + "Refreshing…" + a confirmation).
- **Margin Health ring** — the percentage is now **perfectly centered inside the ring** (it was
  overlapping/covered before).

## 4) Full-screen result tabs
Decisions, Backtest, and Strategy Lab now use the **full page width** (they were squeezed into ~2/3
because of an empty side-panel column). Tables are wider and scroll horizontally on small screens,
so you see far more detail.

## 5) Better icons
Replaced the emoji on **Validate My Edge** (gauge), **Run Strategy Lab** (flask), **Generate with
AI** (sparkles) and **Fetch feed** (rss) with clean line icons matching the rest of the UI.

## 6) New guide: `GUIDE_NEW_TABS_AND_FEEDS.md`
- How to use the Decisions / Backtest / Strategy Lab tabs effectively.
- **Exactly how to get the DXY / US10Y / economic-calendar feeds**: the precise JSON shape the bot
  expects, free providers whose output it already parses (Financial Modeling Prep, Twelve Data,
  Alpha Vantage, calendar APIs), example URLs, and how to verify via `/api/feeds/status`.

## Validation
Backend compiles ✓ · frontend builds ✓ · install→strategy flow verified end-to-end (registers,
persists, replaces, shows in Strategies page) ✓ · 429 retry/backoff unit-tested ✓ · Risk margin ring
centering + full-width confirmed in a real browser ✓ · all 9 simulation suites still pass.

## Coming next (the one remaining item)
**Background backtests with a progress bar** — so Validate / Run Backtest / Strategy Lab run without
freezing the page, you can navigate away, and a bar shows how much data is processed and ETA. That's
a focused build I'll do next so it's done properly.
