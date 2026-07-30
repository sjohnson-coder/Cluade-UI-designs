# GodMode Gold Bot V12.98 — The pump/dump settings are now VISIBLE and editable

## My bug — not your build
You were right. V12.93-97 added the backend config for breakout-stop, strong-momentum
continuation and the exhaustion guard, and they are LIVE and working — but I never added UI
fields for them. Settings.tsx hand-codes every field, so keys with no field simply don't render.
No rebuild would have shown them, because the fields didn't exist.

## Fixed in TWO places
1. **/tools -> "Pump & Dump Engine" button (works immediately, NO npm build needed).**
   Backend-rendered HTML, so it's always fresh. Toggles + numeric fields for:
   - Breakout-STOP entries (+ demo-only safety)
   - Strong-momentum continuation (+ min displacement, max stretch)
   - Exhaustion guard (+ stretch trigger)
   - Shallow retest floor
   Each has a plain-English explanation of what it does. Saves instantly via /api/settings.
2. **React Settings page** — new "Pump & Dump Engine (V12.93-97)" subsection under the Fast
   Sniper Lane block with all of the above plus breakout range/base-candles/expiry and the
   exhaustion RSI levels. Appears after the auto-build runs (V12.96).

## To turn on the feature you actually wanted
/tools -> "Pump & Dump Engine" -> **Breakout-STOP entries: ON** (leave Demo only: ON).
That is the mechanism that catches the ramp into a pump instead of entering at the tail.

## Verified
Panel renders and exposes all keys; GET /api/settings returns them; toggling via the panel's
save path flips the live value both ways. Boot 0.076s. Full V12.67-98 regression green.
Defaults unchanged: breakout OFF+demo, strong-momentum ON, exhaustion guard ON, reversal OFF,
burst ON+demo+risk-sized.
