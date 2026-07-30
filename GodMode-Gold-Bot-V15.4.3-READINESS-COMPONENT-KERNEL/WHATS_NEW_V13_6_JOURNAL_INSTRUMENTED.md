# GodMode Gold Bot V13.6 — The journal can now explain itself (0/8 -> 8/8)

## Why this mattered
I told you the highest-value change (cutting losers earlier) was UNTESTABLE, because your journal
had no excursion data. That was true — and it was a bug, not a design limit. Fixed.

## THREE real bugs found

### 1. Every context column exported BLANK (0/200 in your journal)
_vetting_journal_rows used trade_context.get(ticket) — a STRICT lookup. MT5 closes a trade under
a different deal id than the order id recorded at entry, so it missed on essentially every trade.
sl, confidence, session, quality, entryReason: all blank.
A fuzzy match() (exact ticket -> then symbol/side/price/time scoring) ALREADY existed for exactly
this. The journal just never called it. It does now.

### 2. MAE/MFE was captured but never exported — and merge() couldn't reach it
Your bot has recorded mfeR/maeR/riskBasis/beMoved on EVERY close since V12.80. They were never
in the CSV. Worse: merge() wrote them into _data only, while match() returns objects from the
_recent list — so for any trade resolved by fuzzy match (i.e. nearly all of them) the excursion
was invisible anyway. merge() now keeps both views in sync.
NEW COLUMNS: maeR, mfeR, riskBasis, beMoved, checksSeen.
**maeR is the one that matters**: worst R the trade went against you before resolving. With it,
"would a tighter stop have killed this winner?" becomes measurable instead of a guess.

### 3. Exit labels read exactly backwards
130 winners said "Stop loss hit"; 68 losers said "Closed by bot". MT5 reports DEAL_REASON_SL for
ANY stop fill — including a TRAILING/BE stop closing in PROFIT. The label now uses the trade's
P&L: profit -> "Trailing/BE stop (profit)", loss -> "Stop loss hit". Unknown P&L keeps the old
conservative label.

## Verified end-to-end (not just "it compiles")
Simulated the exact failure — a trade closing under a DIFFERENT ticket than its entry:
    strategy/confidence/session/quality/sl/entryReason/maeR/mfeR = 8/8 POPULATED  (was 0/8)
    exitReason = "Trailing/BE stop (profit)" on a winning stop
Two bugs were caught BY that test, after the code already compiled:
  • _epoch_of silently returned None for every real timestamp — app.py never imported datetime,
    and my bare `except` swallowed the NameError. Exactly the silent-failure class that caused
    the blank columns in the first place.
  • The excursion merge/_recent desync above.
I also caught my own bad test (it used "entryPrice" where the real entry path writes "entry") —
the production schema was correct; my test was wrong.

## What to do now
1. Run the bot. New closes get fully instrumented rows.
2. After ~30-50 trades, export the journal and send it to me.
3. THEN I can answer the loss-cap question with data: for every winner, maeR tells us whether a
   tighter stop would have killed it. That converts the biggest open question in this system from
   opinion into arithmetic.
Old trades cannot be back-filled — that context was never stored. This starts from now.

## Validation
Boot fast. endpoints failing: NONE. Full regression green. All V13.x work intact.
