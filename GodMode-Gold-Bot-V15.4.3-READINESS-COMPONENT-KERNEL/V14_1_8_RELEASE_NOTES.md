# V14.1.8 Performance & Rate-Limit Hardened

- Non-blocking, single-flight calendar and market-news refresh.
- Exponential 429/outage backoff (5–30 minutes) with last-known-good cache.
- News/calendar TTL raised to 15 minutes.
- Frontend polling reduced and suspended while the tab is hidden.
- Dashboard active-trade polling changed from 800ms to 1.8s.
- Production startup no longer runs npm/Vite builds unless GODMODE_AUTO_BUILD_FRONTEND=1.
- Network timeout reduced to 4 seconds for optional external feeds.
