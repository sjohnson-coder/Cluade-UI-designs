# V12.56 — Dynamic SL UI clarity, visible rollback, dashboard performance

## Why this build exists
V12.55 added the AI Performance Coach and config library, but the UI still showed separate Break-even, Trailing and TP Push controls in a way that made it look like three systems were fighting the new AI Dynamic SL.

## Changes

### 1. Unified AI Dynamic SL settings
Settings → 5c is now renamed to **AI Dynamic SL — Unified Profit Protection**.

The main visible controls are now:
- AI Dynamic SL Master
- Protect starts at ATR
- Minimum locked profit fraction
- Maximum giveback fraction
- Recovery room
- Recovery room ATR
- Runner / TP push allowed

The old BE / trailing controls are now hidden under **Advanced legacy fallback values**. They remain only as compatibility / broker-side safety fallback values.

### 2. Dashboard wording fixed
The dashboard Trade Management card now shows:
- AI Dynamic SL
- Protected Floor

instead of making the user think classic BE and trailing are the primary controllers.

### 3. Visible rollback button in Settings
Settings → 12f now has a visible button:

**Rollback Last AI Fix / Import**

This uses the existing rollback snapshot saved before:
- Apply Fix
- config profile apply
- config import

### 4. Dashboard loading / lag reduction
The dashboard now:
- loads cached dashboard data immediately
- fetches dashboard first
- defers feed and strategy refreshes briefly
- refreshes dashboard every 4 seconds instead of 2.5 seconds
- refreshes feeds every 45 seconds
- refreshes strategies every 90 seconds
- caches expensive backend analytics aggregation for 20 seconds
- increases backend dashboard cache TTL to 4 seconds

This reduces the long reload feeling when returning to Dashboard from another page.

### 5. API provider guidance
OpenAI and Claude both work through official API endpoints. OpenAI uses the Responses API and Claude uses the Messages API. The bot still keeps AI in advisory mode only: it can recommend safe setting changes, but cannot place trades or write code.

## Notes
- Use OpenAI if you already have a working key and want speed/cost flexibility.
- Use Claude if you prefer more verbose reasoning and strategy critique.
- Either provider can be effective as long as the bot sends structured trade statistics and receives whitelisted setting patches only.
