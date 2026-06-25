# GodMode V12.3 — Fix: held losers past the floor + trading chop

Your screenshots showed two SELLs closing at -1.24R and -0.93R with "fast-fail floor
-0.50R; AI recovery 60", inside a tight 3979-3987 chop range. Two real bugs + a root
cause, all fixed:

## 1) The fast-fail floor was being ignored (the -1.24R losses)
When the recovery monitor said RECOVER but **dynamic SL was OFF** (the default), the
code HELD the loser with no stop change and no floor — so it bled past -0.50R until a
later NEUTRAL read cut it at -1.24R. That's "the AI widened the SL then fast-failed it":
it held without actually capping anything.

FIX: the hard fast-fail floor now **always** cuts at your configured level UNLESS
dynamic SL is enabled AND has placed a real, risk-capped stop. So:
- Dynamic SL OFF (default): RECOVER can no longer hold past the floor → loss capped at
  ~-0.5R.
- Dynamic SL ON: the AI widens the stop ONCE to a level capped by your max-risk %, and
  the trade rides to that capped stop — bounded either way. No more -1.24R surprises.

## 2) It was trading chop (the repeated fast-fails)
The de-gating let it enter a tight sideways range, where every trade fast-fails. Added a
**Kaufman efficiency-ratio filter** (net move ÷ path length over 20 bars): below the
threshold the market is ranging → **no entries** ("Choppy/range market" block). Verified:
the exact 3979-3987 chop reads 0.09 efficiency and is now blocked; a real trend reads ~1.0
and trades normally. Thresholds scale with strictness (relaxed 0.24 → sniper 0.42).

## 3) The recovery monitor gave false RECOVER in chop
In a flat range the EMAs look "aligned", so the monitor wrongly said RECOVER and held
losers. It now **caps the recovery score below the hold threshold when efficiency is low**
→ verdict CUT in chop (verified: chop → CUT, genuine trend → RECOVER). So even an open
trade that drifts into chop is cut, not held.

Net effect: far fewer trades (no chop), losers capped at the floor, and the recovery
monitor only holds in genuine trends. The post-loss cooldown + chop filter together also
stop the immediate re-entry you saw.

Backend-only change; no settings to update (the chop threshold follows your AI Strictness
mode — use Strict/Sniper for an even tighter chop filter).
