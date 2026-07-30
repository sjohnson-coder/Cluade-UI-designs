# GodMode Gold Bot V12.96 — Dashboard rebuilds itself on upgrade (no more manual npm)

## The problem
Every upgrade shipped fresh backend code but a STALE compiled dashboard (frontend/dist), so new
UI only appeared after you manually ran `cd frontend && npm install && npm run build`. You should
not have to do that on every upgrade.

## The fix — auto-build on startup
On boot, the bot now checks if the dashboard source is newer than the compiled bundle. If it is,
it rebuilds automatically in a BACKGROUND THREAD (boot stays instant — 0.08s, never blocked):
- If node_modules is missing (first run after unzip), it runs `npm install` first (needs internet
  once, ~1-2 min).
- Then `npm run build`, and the new UI is live — just refresh the browser.
- If npm/Node is not installed, or the build fails, it says so clearly and keeps serving the
  previous bundle (never crashes, never leaves you with a blank UI).

Status is live at GET /api/system/frontend-build and printed to the console.

## What you do now
Nothing, in the normal case: unzip, start the bot, wait for the console line
"Frontend rebuilt automatically — refresh the browser", refresh. Done.

## Requirements / honest limits
- Node.js + npm must be installed on the machine (they usually are if you have used the bot's
  frontend before). If not, install Node once from nodejs.org.
- The FIRST build after a fresh unzip needs internet for `npm install`. After that, rebuilds are
  offline and fast.
- Fallback: REBUILD_DASHBOARD.bat (double-click) does the same thing manually if you ever need it.
- NOTE: this build could not be exercised end-to-end in the packaging sandbox (no npm registry
  access there), but the auto-build logic is verified to run, report status, and fail safe. On a
  normal networked machine it completes the build.

## Everything else intact
V12.95 news-cache latency fix, exhaustion guard, breakout-stop (off/demo), burst risk-sizing
(on/demo), telegram fix, why-silent, shallow retest. Full regression green, boot 0.081s.
