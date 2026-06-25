# GodMode — Using the new tabs + setting up data feeds

## Part A — How to use the new tabs

### Analytics → Decisions  (the "why did it / didn't it trade" log)
Every entry decision the bot makes (TAKE or SKIP) is logged with the exact confidence and the
**blocking reason**, plus every management action (break-even, trail, recovery-room, fast-fail,
partials) and every close. Filter with the chips (All / Entries / Management / Closes).
**Use it to answer "why didn't it trade that move?"** — find the SKIP row and read the reason
(e.g. "Confidence 68% below threshold 72%", "Choppy/range: efficiency 0.21 < 0.28").

### Analytics → Backtest  (does my CURRENT config work?)
- **Validate My Edge** — replays the real engine over ~2 years of your MT5 history and gives a
  plain-English **GO / CAUTION / NO-GO**. Run this first.
- **Run Backtest** — the detailed per-strategy + walk-forward breakdown.
- **Optimize Weights** — fits the confidence-factor weights to your data (out-of-sample gated).

### Analytics → Strategy Lab  (find a BETTER config)
- **Run Strategy Lab** — back/forward-tests a library of trading STYLES against your history and
  shows each one's expectancy **vs your current config**.
- **Generate with AI** — your Claude/ChatGPT proposes new styles (needs a key in Settings → 12d).
- **Fetch feed** — pulls styles from your trusted feed URL (Settings → 12e).
- A candidate is **recommended** only if it beats your config out-of-sample. Click **Install** and
  it (a) applies that tuning to the live engine and (b) **shows up in your Strategies page** as the
  "Active tuning (Strategy Lab)". The Install button turns into **✓ installed**.

> Important reality check: when you ran the Lab, your **current config showed ≈ −0.03R expectancy**
> over 2.5 years — i.e. slightly negative after costs — and the candidates were only marginally
> better with low out-of-sample consistency. That's the tool doing its job: **it's telling you the
> bot doesn't yet have a proven edge on your data.** Don't size up on real money until Validate My
> Edge shows a genuine GO. Use the Lab + Optimize Weights to search for a config that does.

---

## Part B — Setting up the data feeds (DXY / US10Y / Economic calendar)

These are **optional**. Left blank, the bot runs **neutral** (no macro tilt, no news blocking) — it
never invents a bias. Add them to give the engine a real macro read + high-impact news blackouts.

### What JSON the bot expects
- **DXY feed URL** → a JSON object with a price and a % change. The parser accepts any of these key
  names: `value`/`price`/`close`/`last`/`rate` for the level, and
  `changePct`/`changePercent`/`changesPercentage`/`change` for the %:
  ```json
  { "value": 104.2, "changePct": -0.18 }
  ```
- **US10Y feed URL** → same shape (it also accepts `changeBp` for basis-point change):
  ```json
  { "value": 4.28, "changePct": -0.04 }
  ```
- **Economic calendar URL** → a JSON array (or `{ "events": [...] }`) of events; each needs a time,
  an impact, and a currency:
  ```json
  [ { "time": "2026-06-25T18:00:00Z", "impact": "high", "currency": "USD", "title": "FOMC" } ]
  ```
  The bot only blackout-blocks around **high-impact USD** events.

### Free providers whose output the bot already parses
> Sign up (free tier), get an API key, and paste the **full URL including your key** into the field.
> The "Feed API key" boxes are optional (use them only if your provider wants a Bearer/`apikey`).

- **Financial Modeling Prep** (financialmodelingprep.com) — free quote endpoints return
  `price` + `changesPercentage`, which the parser reads directly:
  - DXY: `https://financialmodelingprep.com/api/v3/quote/DX-Y.NYB?apikey=YOUR_KEY`
  - US10Y: `https://financialmodelingprep.com/api/v3/quote/%5ETNX?apikey=YOUR_KEY`
- **Twelve Data** (twelvedata.com) — `/quote` returns `close` + `percent_change` (rename to
  `changePct` if needed via their params), e.g.
  `https://api.twelvedata.com/quote?symbol=DXY&apikey=YOUR_KEY`
- **Alpha Vantage** (alphavantage.co) — free `GLOBAL_QUOTE` returns a `change percent` field.
- **Economic calendar**: a ForexFactory-compatible JSON mirror (search "forex factory json
  calendar"), or a free economic-calendar API (e.g. Finnhub `/calendar/economic`, Trading Economics
  free tier). It must return events with a time + impact + currency as above.

### If a provider's shape doesn't match
If a feed returns a different JSON shape than above, point the field at a tiny personal proxy (a
Cloudflare Worker / small script) that reshapes it to `{ "value": ..., "changePct": ... }`. The
bot deliberately doesn't hard-code any one paid provider so you stay in control of the source.

### How to confirm it's working
After saving, open `http://<your-bot>/api/feeds/status` (or the dashboard) — it shows each feed as
**live** or **not_configured**, so you can see immediately whether your URL is being read.
