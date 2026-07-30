# GodMode Gold Bot V13.7 — maeR bug fixed, news OFF root-caused (again, properly), marker faster

## 1. YOUR JOURNAL PROVED V13.6 WAS HALF-BROKEN — fixed
Good news from your upload:
  • exitReason is FIXED: 134 winners now correctly read "Trailing/BE stop (profit)". The
    backwards labels are gone.
  • context columns WORK on new trades: the last 3 trades (the only ones closed after V13.6)
    have strategy/confidence/session/quality/sl/entryReason populated. The other 197 are
    pre-fix — their context was never stored and cannot be back-filled. Expected.

BAD news: **maeR/mfeR were 0/200 — blank even on the 3 NEW rows.** My V13.6 fix did not work.

ROOT CAUSE: the excursion capture lived INSIDE `if match and not already:`, but
`POSITION_PROTECTION_STATE.pop(gone)` runs for EVERY closed position, unconditionally. So on any
close where that guard failed — close already cached, or no matching row in `closed` yet — the
protection state was DESTROYED before mfeR/maeR were ever saved. Permanently lost.

FIXED: capture moved OUT of the guard, to immediately before the pop. Unconditional. Verified
against the exact failing path: maeR=-0.42, mfeR=1.85, riskBasis, beMoved all survive now.

## 2. NEWS SHOWING OFF — the real cause this time
V12.99.3 fixed the backend (861ms -> ~25ms warm, confirmed still fast). The remaining bug was in
the FRONTEND, and it was worse than latency:

  • request() used a flat 2800ms GET timeout. /api/feeds/status hits LIVE upstream feeds, so on
    a real network a slow-but-working feed blew that budget.
  • On ANY failure it fell back to a default object whose values are literally
    {status:'not_configured'} — so the UI ASSERTED "not configured" when all it actually knew
    was "the request failed". A configured, working feed therefore rendered OFF.

FIXED:
  • /api/feeds and /api/news now get an 8000ms budget; everything else keeps the snappy 2.8s.
  • The fallback no longer lies: it returns {unreachable:true, status:'unknown'}.
  • The News card distinguishes the three states honestly — LIVE / CHECK / OFF, and now '…'
    (amber) when the backend is simply unreachable, instead of falsely claiming OFF.

## 3. PRICE MARKER STILL LAGGY — found what V13.5 missed
V13.5 made the engine PUSH the trades cache every ~1s while a position is open, but left the
MARKET cache lazy. The marker rides PRICE. So you had a fresh trade sitting on a stale price —
the first request after expiry still returned the OLD value while refreshing in the background.

FIXED:
  • The engine now pushes BOTH caches (market + trades) every loop while a position is open.
  • Backend hot path measured: _live_market 0.96ms, _live_trades 0.18ms — essentially free.
  • Since the backend is that cheap, the browser poll was the real constraint: Dashboard
    1500ms -> 800ms and Trades tab 1500ms -> 1000ms WHILE A TRADE IS OPEN (unchanged when flat,
    so nothing is hammered for no reason).

    Worst-case marker age: ~2.5s -> ~1.8s, and it is now genuinely continuous rather than
    stale-then-jump.

## What to do
Run it. New closes now write maeR. After ~30-50 trades send the journal and I can finally answer
the loss-cap question with arithmetic instead of opinion: for every winner, maeR says whether a
tighter stop would have killed it.

## Validation
Boot 0.091s. endpoints failing: NONE. Full regression green. Frontend swept for the
duplicate/use-before-declare class — Dashboard/Trades/api.ts all clean, braces balanced.
