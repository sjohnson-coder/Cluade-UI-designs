# GodMode Gold Bot V13.10 — See every missed move, why, and what it would have paid

## You were right: I built the autopsy and gave you no way to read it
V13.9 wrote `missed_pump` rows to decision_journal.jsonl. Reaching them meant grepping a file on
disk. Worse — I checked how those rows actually rendered in the existing Analytics journal:

    type    : close        <- WRONG, a miss is not a close
    what    : "Closed #"   <- a phantom closed trade with no ticket
    detail  : ""           <- THE BLOCKING REASON WAS DROPPED ENTIRELY
    (no filter chip, so you could not even isolate them)

So the one field that answers "why did it miss?" was silently thrown away by the table. Fixed.

## NEW: Dashboard card — "Missed Moves — Autopsy"
Sits under the News card. For each missed move: side, price, time, the exact blocking reason, and
the displacement in ATR. Plus a verdict per row and running totals.

## NEW: WHAT COULD HAVE BEEN — measured, not guessed
New endpoint `/api/journal/missed-pumps` replays the REAL M5 candles after each miss and computes,
in the direction the bot wanted to trade:
  • couldHaveMadeUsd — peak the trade would have reached (MFE)
  • worstFirstUsd    — worst it would have gone against you BEFORE that peak (MAE)
  • verdict          — REAL MISS / WOULD HAVE HURT FIRST / MARGINAL / NOT WORTH IT / SCORING…

**The honesty rule: upside alone lies.** A move that ran +6 but first dumped -4 would have been
stopped out before it paid — that is NOT free money and is NOT counted. Only "REAL MISS" (big
upside, small drawdown first) is totalled. Verified with a deliberate test case: a +10.4 move that
first went -28.2 against correctly scores `would_have_hurt_first` and is excluded from the total.
On XAUUSD 0.01 lot a $1 price move = $1 P&L, so the price delta IS the dollar figure — verified
against your own MT5 history (sell 0.01, 3976.46 -> 3976.22 = +0.24).
Misses younger than the 60m lookahead are marked SCORING… rather than judged on partial data.

## FIXED: Analytics -> Decision Log
  • New "Missed pumps" filter chip
  • Red "missed" badge (was mislabelled gold "close")
  • what    -> "MISSED BUY 1.62 ATR"  (was "Closed #")
  • detail  -> the actual blocking reason  (was blank)
  • outcome -> "@ 3972.40"

## How to read it
  • Card empty while pumps happen  -> the bot is TAKING them, not missing them. Good.
  • Rows saying REAL MISS          -> read `Blocked by`. That names the exact gate to argue with.
  • Rows saying WOULD HAVE HURT FIRST -> the bot was RIGHT to skip. This is the column that stops
    us "fixing" misses that were never opportunities.

## Validation
Boot 0.082s. endpoints failing: NONE. Scoring math verified against a production-shaped candle
series (peak/dip matched exactly). Empty-state safe. Frontend swept for the duplicate/
use-before-declare class that broke your build before — Dashboard/Analytics/api.ts clean, braces
balanced, and the card reuses WifiOff (already imported) rather than risk a new icon import.
