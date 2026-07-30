# GodMode Gold Bot V12.87 — Best-of-Both Merge (shallow retest kept, dangers caged)

## What this is
Your V12.84 base + the GOOD parts of ChatGPT's V12.86, with its risky part disabled and its
regressions removed. Nothing you had was lost; the useful new capability was kept.

## KEPT from ChatGPT's build (the good stuff)
1. **Shallow-retest continuation** — the fix for your Sunday 45pt staircase. Retest zone widened
   from 25-62% to 12-58%, and the leg is now anchored to the LOCAL pre-breakout base instead of
   the furthest 12-candle extreme, so shallow 15-25% pullbacks in strong grinds now qualify.
   PROVEN: a 19% pullback (below the old 25% floor) now fires a continuation entry.
2. **Safety guards that make shallow entries honest** (not looser — stricter): min 2 bars after
   arming, trigger candle capped at 1.10 ATR (won't "retest-enter" on another spike), a
   counter-pullback is required, and an overshoot cap rejects a 74% collapse masquerading as a
   retest. A two-candle rejection confirm is allowed.
3. **Fresh-break range override** in the decision engine: a genuine fresh directional break
   (efficiency >= 0.38 or leg >= 0.90 ATR in-side) is no longer misread as sideways range and
   blocked at the edge.

## CAGED (shipped OFF by default)
4. **Reversal SCOUTS** — ChatGPT enabled a new COUNTER-TREND entry type that bypasses the HTF
   hard veto and gets a confidence bonus. Your worst historical losers are counter-trend-shaped
   and the base edge isn't proven to ~50 trades yet, so this ships DISABLED (both in settings and
   in code defaults). The logic is present and correct; flip
   automation.fastSniperReversalEnabled = true ONLY after the base is proven, and test it as ONE
   change in isolation.

## RESTORED (ChatGPT's build had regressed these — they were built on V12.83, before your fixes)
5. **News browser-UA fix** — their fetches still identified as GodModeGoldBot/1.0, so your
   "error or empty" bug was BACK. All feed fetches use a browser UA again.
6. **/api/news/test + "Test News Feeds Now"** button restored.
7. **Loud block alerts** — their watcher rewrite PROMISED a "FILLED or BLOCKED/REJECTED" message
   that did not exist in their code (you'd wait forever). Your real V12.84 behaviour is restored:
   the AUTO alert runs the tick and reports ORDER SENT + ticket, or the exact blocking gate.

## NOT ported (deliberately)
8. **Protected Burst campaign layer** (one-batch-per-impulse, re-entry guard, adaptive sizing,
   basket stops). Burst is default-OFF dormant code; porting its campaign refinements correctly
   is a separate, larger merge that belongs to a dedicated burst-validation release, not a
   philosophy-fix build. Available to port when you decide to validate burst.

## Does it defeat the bot's purpose?
No. The core discipline is intact: it still NEVER buys the spike candle; it still enters the
second leg on a rejection close; HTF veto, governor, repeat-guard, loss-feedback all unchanged.
It just accepts politer, shallower second legs — which is exactly what you asked for after the
staircase days. The one philosophy violation ChatGPT introduced (counter-trend reversals) is off.

## Validation
Boot 0.151s. Shallow 19% retest fires correctly (and waits through the 2-bar guard first).
Reversal confirmed inert by default, opt-in flips cleanly. News UA browser on all fetches,
news-test endpoint live, loud blocks present. Full V12.67-87 regression green.

## After upgrading
Run UPGRADE_HELPER_COPY_MY_SETTINGS.bat, start bot. You should see more retest entries fire on
grind days. Reversals stay off until you choose. /tools -> Test News Feeds Now to confirm news.
