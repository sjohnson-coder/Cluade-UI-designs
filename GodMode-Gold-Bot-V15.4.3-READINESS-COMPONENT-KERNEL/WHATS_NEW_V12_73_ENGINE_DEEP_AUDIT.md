# GodMode Gold Bot V12.73 — Deep Engine Audit (thinking & decision bugs)

A full audit of the decision engine, feature computation, regime classifier, impulse-retest
detector, SL/BE logic, lot sizing and streak governors — running simulations against the
July-8 dump to catch the *same class* of bug as the 45-second guillotine. Four real
decision-logic errors found and fixed; several subsystems audited and confirmed sound.

## Fixed

**1. Regime mislabelled a crash as "Strong Bullish Trend".**
The trend-direction flag was `structureBullish OR computedSide==BUY`. `structureBullish`
can stay true for hours after the last bullish break of structure — so during the $60
breakdown the label read "Strong Bullish Trend" while price was in freefall. Direction is
now taken from what is moving NOW: current computed side → short-window efficiency
direction → structure bool only as last resort. Simulation of the dump bottom now returns
computedSide SELL / bias SELL (was BUY).

**2. Range-fade could counter-trade a fresh crash.**
A window containing old chop + a new waterfall looks like a huge low-efficiency "range"
with price at the "bottom" — and FADE flipped the correct SELL into *buying the bottom of
the crash*. Two new vetoes downgrade FADE to BLOCK: (a) recent short-window efficiency
pointing into the extreme = fresh impulse, not a range; (b) D1+H4 both opposing the fade
direction = never mean-revert against the higher-timeframe river. Simulation confirms the
crash bottom now BLOCKs instead of FADE-buying.

**3. Impulse-retest confirmation read the still-forming candle.**
Pullback/rejection were judged on `closes[-1]` (the live, unclosed candle), which flickers
green/red mid-bar so an "ARMED→CONFIRMED" flip could appear and vanish within a minute.
Now judged on the last CLOSED candle (`[-2]`), matching how the armed-retest tracker and
every real trader reads confirmations.

**4. HTF hard veto** (carried from V12.72, re-simulated here) blocks any entry where D1 and
H4 both oppose the side — the direct guard against the July-8 "bias SELL but BUY fired".

## Audited and confirmed CORRECT (no change needed)
- **R-multiple math**: risk basis is captured once from entry→original SL and reused, so R
  stays correct after the stop moves to break-even. Verified.
- **SL/BE modification**: monotonic — the stop only tightens, except a bounded in-profit
  recovery-room loosen that can never drop below the break-even/locked-profit floor. Sound.
- **Lot risk ceiling**: correct constant-$ risk math (equity × risk% ÷ loss-per-lot),
  clamped to broker min/step/max. Note: default `firstEntryLotMode=base_lot_only` keeps
  first entries at base lot (harmless at 0.01; revisit if you raise size/risk%).
- **Win/loss streak governor**: win streak resets to 0 on any loss; loss streak resets on
  any win; a scratch (pnl 0) counts as neither. Correct.
- **bid/ask**: entries use ask for BUY / bid for SELL; closes use the opposite. Correct.

## Simulations run
Reconstructed the July-8 session as real candles (45 bars chop → $60 waterfall) with
bearish H4/D1. Verified: engine reads SELL at the bottom (not bullish BUY); HTF veto fires
on the contradiction BUY; fast-fail holds a flat 45s/10-min trade, cuts a 26-min red one,
never cuts a winner; range-fade BLOCKs instead of buying the crash bottom. Full V12.67-73
regression (secret-safe save, rollback, signals, pure read, spread gate, auditor,
scoreboard, clock) passes. py_compile clean.

## Expectation
Combined with V12.72's clock repair, the bot should stop manufacturing loss streaks and
stop taking counter-trend entries at the worst location. Fewer, better-located trades held
for real time. Judge on expectancy over the next sessions, not trade count.
