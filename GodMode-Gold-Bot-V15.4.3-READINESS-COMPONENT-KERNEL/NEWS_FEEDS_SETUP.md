# GodMode News Feed Setup — V12.38

The dashboard now has a **Live News & Calendar** card. It shows whether the news integration is actually working.

## Recommended links

### 1. Free economic calendar / news blackout
Paste this into **Settings → Data Feeds → Economic calendar URL**:

```text
https://nfs.faireconomy.media/ff_calendar_thisweek.json
```

This powers the high-impact USD blackout window for CPI, NFP, FOMC and other red-folder USD events.

### 2. FMP economic calendar API
Official docs:

```text
https://site.financialmodelingprep.com/developer/docs/stable/economics-calendar
```

Template endpoint:

```text
https://financialmodelingprep.com/stable/economic-calendar
```

Put your key in **Calendar API key** or append `?apikey=YOUR_KEY`.

### 3. Alpha Vantage market news & sentiment
Official docs:

```text
https://www.alphavantage.co/documentation/#news-sentiment
```

Paste this into **Market news URL**:

```text
https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=economy_macro,economy_monetary,financial_markets&sort=LATEST&limit=20
```

Put your Alpha Vantage key in **Market news API key**.

### 4. Trading Economics calendar
Official docs:

```text
https://tradingeconomics.com/api/calendar.aspx
```

Use this if you have a Trading Economics API key and want a more institutional calendar feed.

## Dashboard colours

- **Green LIVE**: feed is configured and returning parseable events/headlines.
- **Amber CHECK**: URL/key is set but the feed returned empty/error.
- **Red OFF**: no feed configured.

Economic calendar blackouts can block new entries. Market-news headlines are dashboard/context only by default.
