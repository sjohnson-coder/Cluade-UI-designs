# V12.38 — News Dashboard + Feed Links

Added:

1. Dashboard **Live News & Calendar** card.
2. `/api/feeds/status` now reports economic calendar, market news, DXY, US10Y and macro status.
3. `/api/feeds/news/live` for live headline/sentiment feed checks.
4. `/api/news/status` for one-shot calendar + news status.
5. Settings now includes **Market news URL** and **Market news API key**.
6. Provider buttons added for ForexFactory calendar, Alpha Vantage news template, and FMP economic calendar template.
7. Economic calendar display no longer invents fake CPI/FOMC events when no URL is configured.

Risk note: news feeds reduce avoidable event risk, but they do not prove edge. Continue using the validation lock before live auto-trading.
