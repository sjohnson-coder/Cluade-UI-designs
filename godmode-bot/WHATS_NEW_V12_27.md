# GodMode V12.27 — Auto-pilot strategy discovery + range candidate + link-based news

## 1. Auto-discover & install (opt-in auto-pilot)
When **no enabled strategy fits** the current market, the bot can now run the Strategy Lab itself,
**auto-install the best candidate that beats your edge out-of-sample**, and send a **Telegram alert
with Uninstall / Keep buttons** — so you don't miss a setup while you're at work.

- **Settings → 12e → Auto-discover & install** (OFF by default; cooldown configurable).
- Telegram buttons work via a lightweight getUpdates poller (no webhook, nothing exposed). Fallback
  text commands: **`/uninstall`** and **`/keep`**.
- **Guardrails (can't force a losing trade):** never during a news blackout, never stacks a second
  install, cooldown-throttled, and it **only installs a candidate the Lab validates** as beating your
  current edge out-of-sample. If nothing beats your edge, it stays flat and tells you — it never
  loosens discipline to manufacture a chop trade.

## 2. New "Range Compression Breakout" Lab candidate
A chop/range-regime candidate that **does NOT fade the range** (fading loses). It sits ready and only
fires on a fresh, sized directional leg breaking OUT of the compression — lower efficiency floor so it
can engage as the range resolves, tight spread cap, scout size. Like every candidate it's back/forward-
tested first and only installs if it beats your edge. This gives the multi-strategy scan and the
auto-pilot something regime-appropriate to select in ranges.

## 3. Live news/macro by LINK (no hosting, no JSON authoring)
You can just paste a **link** — the feed fields fetch a URL for you.
- **One-click free calendar:** Settings → 12c has a **"Use free ForexFactory calendar link"** button
  that fills in `nfs.faireconomy.media/ff_calendar_thisweek.json` — that single link powers the
  high-impact USD news blackout (FOMC/CPI/NFP). No signup, no hosting.
- **DXY / US10Y macro:** paste a free quote link (e.g. financialmodelingprep.com or twelvedata.com)
  with `?apikey=YOUR_KEY`; the fetcher reads JSON *or* CSV automatically.

## 4. Strategy Scan panel: reasons now wrap
The "Why blocked" column wraps fully instead of truncating off the card edge, so every gate reason is
readable.
