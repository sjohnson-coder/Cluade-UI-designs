# GodMode V12.31 — Broker-cost calibration + No-Trade conflict-report fixes

## Broker-cost calibration (set your real costs once)
The Backtest tab now has a **Slippage/fill** input and a **"💾 Save as my broker costs"** button.
Punch in your broker's real spread + commission + slippage once and:
- every **Validate / Backtest auto-loads them** (so the GO/NO-GO verdict reflects YOUR economics, not an
  optimistic default), and
- the live cost gate uses the same commission.
Stored in `settings.brokerCosts`. This is the honest way to see exactly where your edge turns positive
as the spread drops.

## No-Trade / Standby conflict report — addressed
Most of that report's top recommendations were already shipped in V12.25–V12.26; this adds the rest and
makes the intent explicit in code:

- **No-Trade is fallback-only (now explicit).** The strategy carries `executable: False` /
  `fallbackOnly: True` metadata, and the multi-strategy scan (V12.26) already selects the best *real*
  strategy that passes its own gates — No-Trade is resolved *only* when every real strategy fails or a
  universal safety veto fires. It never "competes for selection" (the report's main fear, which was true
  in the pre-V12.26 build).
- **Strategy-scan audit trail in Telegram.** The "blocked preview" alert now lists each strategy and why
  it was held (e.g. "HTF Trend: ✗ chop 0.07 < 0.24"), plus an explicit **"Order sent to MT5: NO"** and
  "Final action: WAIT" — so you can see on your phone that the bot scanned *all* strategies and isn't
  stuck. (The AI Agent "Strategy Scan" panel already showed this in the UI.)
- **Explicit lifecycle state.** Every decision now reports `lifecycleState`
  (FORECAST → SCANNING → BLOCKED / TRIGGERED), shown on the AI Agent Decision card — separating a
  *forecast bias* from an *executable trade*.
- **Forecast ≠ trade** wording (from V12.25) reinforced.

Verified: lifecycle = BLOCKED on chop, No-Trade metadata present, broker costs persist + auto-load,
UI clean and responsive at 360/390/1280/1600.
