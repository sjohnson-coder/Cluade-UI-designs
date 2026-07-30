# GodMode Gold Bot V13.0 — Living neural core + Economic Calendar restored

## 1. The AI image is now alive (and it MEANS something)
The dashboard's Adaptive Strategy Engine card held a STATIC svg — it told you nothing about
whether the AI was actually running. Replaced with `NeuralBrain`, a real-time canvas render in
champagne bronze:
  • slow breath pulse            -> the engine is running
  • charge packets with comet tails travelling the synapses -> "electric waves flowing through"
  • expanding heartbeat ring, drifting rotation, per-node shimmer -> it is alive
CRUCIALLY the motion is bound to REAL state, not decoration:
    active = market closed ? 0.12 : (decision === TAKE_TRADE ? 1.0 : 0.4)
So it visibly surges when the engine is deciding and goes near-dormant when the market is shut.
Anatomy is generated from a seeded RNG, so the brain never re-rolls between loads.

Performance (you asked for fast loading throughout): ONE canvas, ONE rAF loop, DPR capped at 2,
auto-pauses via IntersectionObserver when scrolled off-screen and on tab-hide, and honours
prefers-reduced-motion by drawing a single static frame.

## 2. Economic Calendar UI — restored
The calendar data was live at /api/feeds/economic-calendar/live the whole time; there was simply
NO UI mounted for it. You only ever saw a one-line "next high-impact USD" on the dashboard.
New panel, mounted on the Dashboard next to the news card:
  • Leads with the only question that matters: "am I about to get run over?" — blackout state
    loud, countdown to the next high-impact USD print second, event list quiet below.
  • Impact encoded as a bronze weight bar (scans in one pass) rather than a traffic-light row.
  • Shows forecast/previous where the feed provides them.
  • NEVER fabricates: unconfigured says "not configured", live-but-empty says so (normal at
    weekends), fetch errors are shown verbatim. Built against the feed's real shape
    {id,title,currency,impact,timeUtc,actual,forecast,previous}.

## HONEST STATUS — what I did NOT do
  • **TradingView-grade chart rebuild: NOT DONE.** You asked for this twice now. It is a
    substantial rebuild (there is already a TradingViewChart.tsx + LiveChart.tsx to reconcile),
    and doing it badly in the same pass as two new components would be worse than not doing it.
    It is the next version, on its own.
  • Daily/Weekly AI Review + Rollback buttons — still not investigated.
  • "Applied" + Revert state on Recommended Actions — still pending.
  • "Ensure every function works perfectly / no hidden config" — I cannot honestly claim this.
    V12.99 closed all 33 known settings gaps and V12.99.2 fixed the apply whitelist, but I have
    not audited every button in the app end-to-end.

## BUILD RISK — read this
There is NO npm/node_modules in my sandbox, so I could NOT typecheck or compile these two new
React components. I mitigated what I could: verified no leftover `aiNode` import, balanced
braces, confirmed Card/SectionTitle/Tag signatures (incl. Tag's 'amber' colour), and swapped my
icons to `CalendarDays`/`ShieldCheck` — which the existing Dashboard already imports and are
therefore proven present — instead of the unverifiable CalendarClock/ShieldAlert.
If the build errors, send me the exact message and I'll fix it immediately.

## Validation
Boot 0.299s. Calendar endpoint returns real shape. feeds_status warm ~115ms (was 861ms).
Full regression green. V12.99.2/.3 fixes intact. No defaults changed.
