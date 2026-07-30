# GodMode Gold Bot V13.8 — the 5-minute wall, and permission to catch the spikes

## THE TRAP I ALMOST SHIPPED (read this one)
Setting fastFailNoProgressMinutes = 5 would have done NOTHING. The no-progress exit requires:
    trade_age >= fastFailMinSeconds  AND  trade_age >= fastFailNoProgressMinutes * 60
With fastFailMinSeconds = 600, the binding constraint was max(600, 300) = 10 MINUTES. Your 5-min
setting would have been silently capped — and a migration guard at line 596 SNAPPED any value
below 300 back to 600, so it would have re-broken itself on every restart.
Both gates now move together. Verified EFFECTIVE cut = 300s = 5 min, and 300 now sticks.

## 1. The 5-minute wall (the single biggest number in your data)
    UNDER 5 min: 149 trades  net +15.97
    OVER  5 min:  51 trades  net -67.02
Avg win is flat across every bucket (+0.75 -> +1.87 -> +1.77 -> +1.59). Avg loss DOUBLES after
5 min (-2.1 -> -2.6 -> -5.2 -> -5.4). Time does not kill your winners; it grows your losers.
    fastFailMinSeconds        600 -> 300
    fastFailNoProgressMinutes  25 -> 5
Cuts ONLY trades that never peaked and are already red at 5 min. Your winners resolve in ~4 min,
so this cannot touch them.

## 2. I WAS WRONG ABOUT Fsmms — and did NOT disable it
I recommended killing Fsmms. Then I decoded it: **Fsmms = "Fast Sniper M5/M15 Momentum Shift" —
your Fast Sniper lane's CORE entry.** Disabling it would have amputated your primary entry engine.
And it is not even a bleeder:
    Fsmms under 5min: 33 trades  net  +4.13
    Fsmms over  5min:  9 trades  net -16.18
Fsmms is PROFITABLE under 5 minutes. Nine long-held trades create its entire -12.05. Same wall.
Change 1 fixes it without disabling anything. Nothing was amputated.

## 3. THE SPIKE ANSWER: breakoutRequireHtfAlign True -> False
Your screenshots proved the real cause: all 7 trades SELL, every spike UP. On a bearish-HTF day
every engine is sell-only — the rallies were not slow to catch, they were FORBIDDEN. No amount of
latency work would have taken one of them.
A pre-positioned STOP order is the ONE counter-HTF mechanism that defends itself: price must come
to OUR level, and stop distance is fixed BEFORE entry. Every counter-trend disaster in your
history (July-8 fade, reversal scouts) was a MARKET order into a move already running with risk
defined after the fact. This has neither property.
Loosened for breakout brackets ONLY. Reversal scouts stay OFF. The HTF gate on the sniper lane is
untouched.
Also: breakoutStopEnabled now ships True (you had already flipped it; a fresh install would not).

## 4. Burst demo-only is now account-TYPE aware
demoOnlyUntilValidated checked `liveTradingEnabled and not dryRun` — true on a DEMO account too,
so burst was silently blocked on demo: the one place it is meant to prove itself. It now checks
the real MT5 account type, exactly like breakout-STOP already did. Runs on demo, self-blocks on
real money.
breakoutStopDemoOnly back to True: costs nothing on your demo (reads demo=True and arms normally)
and auto-guards the day you point this at a live account.

## Invariants — nothing regressed
exhaustion guard ON | strong-momentum ON | reversal scouts OFF | burst risk model account_pct |
sniper HTF gate untouched | coach can still tune fastFailNoProgressMinutes (verified: set to 6).
Boot 0.117s. endpoints failing: NONE. Full regression green.

## What happens next
Run it. Two things to watch, both now measurable:
  • Does the -67 over-5-min bucket shrink? (change 1)
  • Do counter-HTF brackets pay or bleed? (change 3)
maeR/mfeR are recording on every close since V13.7. Send the journal after 30-50 trades and both
questions get answered with arithmetic. If the brackets bleed, flip breakoutRequireHtfAlign back —
it is one setting in /tools -> Pump & Dump Engine.

## Honest caveat
My 5-min model is a linear pro-rata approximation of what cutting early would have done. Real
fills will not match it exactly. The DIRECTION is unambiguous across every bucket and every
strategy — that is why this ships. The magnitude is not a promise.
