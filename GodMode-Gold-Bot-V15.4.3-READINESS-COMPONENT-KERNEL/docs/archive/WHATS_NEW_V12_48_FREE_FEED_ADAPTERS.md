# V12.48 — Free Feed Adapters & Macro/News Parser Fix

This build fixes the live Market News and Macro feed failures users saw when FMP endpoints were restricted or Alpha Vantage returned a non-standard response.

## Added

- Free **Yahoo Finance RSS** market-news adapter with XML/RSS parsing.
- Free **Yahoo DXY chart** adapter support (`chart.result[0].meta.regularMarketPrice`).
- Free **FRED DGS10 CSV** support for US10Y.
- Better Alpha Vantage error handling for `Information`, `Note`, and `Error Message` responses.
- API-key placeholder replacement: URLs containing `apikey=YOUR_KEY` or `apikey=demo` are now corrected when a real key is entered in Settings.
- New Settings buttons:
  - Use free Yahoo market-news RSS
  - Use free DXY + US10Y macro templates

## Recommended free setup

Economic calendar URL:
`https://nfs.faireconomy.media/ff_calendar_thisweek.json`

Market news URL:
`https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F,DX-Y.NYB,%5ETNX&region=US&lang=en-US`

DXY URL:
`https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=1d&interval=5m`

US10Y URL:
`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10`

Leave all four API key fields blank for this free setup.
