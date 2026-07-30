# GodMode Gold Bot V13.14 — Walk-forward button fixed; backtest honesty documented

## Why the walk-forward button did nothing
Two bugs:
1. DUPLICATE api method — I had added a second walkForward() that collided with an older one.
2. THE KILLER: it was a BLOCKING POST with a 9-second frontend timeout. A real walk-forward runs
   5+ full backtests over 6000 bars — WAY over 9s. The request aborted, fell back to {ok:false}
   with no message, and the card rendered nothing. That's the "click, no results, no progress".

## Fix: async job + progress bar (same system the main backtest already uses)
New POST /api/backtest/walk-forward-async returns a jobId immediately; the card polls it via the
existing jobStore/useJob system and shows the JobBar progress ("backtest window N", 0→100%, ETA,
Stop button). Verified end-to-end: job starts, progresses to 100, returns a real verdict.
Also removed the duplicate api method.

## "Backtest shows walk-forward in ITS results" — that's a DIFFERENT thing (working as intended)
The main Backtest already runs a lightweight fold-split of its OWN trades and shows a
"Walk-Forward Folds" table — that is in-sample fold consistency, not the full optimize-on-A /
validate-on-B harness. The dedicated Walk-Forward card is the real out-of-sample optimizer. Both
are legit; they answer different questions. (Naming overlap was the confusion.)

## "Not sure the backtest is right" — I audited it. Here is the honest verdict.
GOOD (audited, correct):
  • NO lookahead — the engine only sees candles up to and including the current bar; HTF via
    bisect on timestamp so it cannot peek at future H1/H4/D1 bars.
  • CONSERVATIVE fills — stop checked BEFORE take-profit within the same bar.
  • REAL costs — spread + commission + slippage×2 (both fills), correct for scalping.
THE CAVEAT (now shown in the result's "assumptions"):
  • The backtest models entry -> fixed SL/TP ladder -> break-even-after-TP1 -> max-hold. It does
    NOT replicate your LIVE exits: 5-min fast-fail, trailing stop, ratcheting profit-lock, or the
    new noise floor. So backtest P&L will NOT equal live P&L. Read it as "is the ENTRY any good",
    not "what will I make". This is almost certainly why the numbers felt off — the backtest can't
    reflect the exact exit changes we have been shipping.

## Validation
Async WFO: start -> progress 0..100 -> real verdict, proven. endpoints failing: NONE. Backtest
audit findings documented in-product. Frontend braces balanced, blocking method removed.
