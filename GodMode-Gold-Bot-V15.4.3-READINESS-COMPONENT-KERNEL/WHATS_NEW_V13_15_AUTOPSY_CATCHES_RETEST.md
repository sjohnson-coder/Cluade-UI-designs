# GodMode Gold Bot V13.15 — Missed-Move Autopsy actually catches the misses now

## Why it was blank (three real holes)
The autopsy lived INSIDE _fast_sniper_signal_watch and had three bugs that made your exact
screenshot invisible:
  1. It EXCLUDED armed-retest setups (`and not fast.get("armedRetest")`). Your missed spike said
     "WATCH RETEST" — i.e. armedRetest=True — so it was skipped. But a retest that never fills IS
     a missed move. That alone blanked the screenshot case.
  2. It sat AFTER an `open_positions -> return` guard: nothing logged while any trade was open.
  3. It only ran when the alert function ran, which itself returns early on market-closed etc.

## Fix: standalone _missed_move_autopsy(), main loop, every tick
Now logs a missed move whenever displacement clears the bar and the bot did NOT end up in a trade,
INCLUDING:
  • armed-retest setups that never filled (tagged "Armed retest ... never filled")
  • spikes skipped because a position was already open (tagged so you know it was capacity, not the gate)
Does NOT log when: the trade was actually taken, a bracket armed on the coil (handled), or the
move was below the floor. Detection floor lowered to catch strong ALIGNED pumps too (0.85x bar),
not only counter-HTF ones.

## Verified 5/5
  1. Armed-retest 1.48 ATR (the screenshot) -> LOGGED (was blank)   2. Hard-veto spike -> logged
  3. Trade taken -> not logged   4. Bracket armed -> not logged   5. Below floor -> not logged
Cost: below-floor early-out is ~free in the 1s loop.

## Note on the "what could have been" column
A freshly-logged miss shows in the card immediately with verdict "SCORING…" for up to 60 min
(it needs future candles to measure what the move actually did). The ROW is visible instantly;
only the dollar figure waits for the lookahead window. That is by design, not a blank.

## Validation
Boot clean. endpoints failing: NONE. Autopsy 5/5 cases. Full regression green.
