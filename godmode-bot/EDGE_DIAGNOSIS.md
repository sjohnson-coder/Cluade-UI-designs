# Why the live expectancy is negative — diagnosis & the honest path forward

You asked me to dig into the negative expectancy and improve the win probability. I ran the numbers
hard, using **your own data** from the screenshots plus controlled tests. Here is the truth, the
evidence, and what actually can (and cannot) move the needle.

## The numbers (yours)
- **Live, 200 trades:** win **53.5%**, profit factor **0.7**, expectancy **−0.67 USD**.
- **Strategy Lab on your real MT5 history (60,000 candles, 2023→2026):** every candidate is negative —
  current config **−0.046R**, best (London/NY) **−0.028R**, none positive; win rate ~48–49%.

## What that math means
Profit factor 0.7 at 53.5% win ⇒ **average win ≈ 0.61 × average loss**. Your winners are too small
relative to your losers. But the deeper number is this:

> **Cost per trade ≈ (spread + commission) / risk = (0.37 + 0.07) / ~10 ≈ 0.044R.**
> Your backtest deficit is **−0.046R**. They are almost identical.

**Your signal is roughly break-even *before costs*; the trading costs are what make it lose.** That is
the single most important sentence in this document.

## What I tested (and ruled out)
1. **Is it the exit structure?** No. I re-ran the *same* entries on choppy gold-like data with five
   exit profiles. The **current exit (bank 25% at 1R, break-even after TP1) was the BEST** (+0.13R).
   "Let winners run" was far *worse* (−0.18R) — in chop the winners don't run, they reverse. So the
   exit is already right; do not "let it run".
2. **Is it entry strictness?** No. Your Lab already swept relaxed → sniper, efficiency, R:R,
   confluence. **None reached positive** (best −0.028R). Tightening just reduces the bleed.
3. **Is it a cost-aware skip gate?** Not a real fix. Skipping high-cost trades either changes almost
   nothing or blocks ~everything — it can't turn a zero-edge signal positive.
4. **Cost sensitivity is linear and real:** spread 0.10 → cost 0.017R; spread 0.37 → 0.044R; spread
   0.50 → 0.057R. On a break-even-gross signal, that *is* the whole result.

**Conclusion: no parameter tweak inside the current signal creates an edge that isn't there.** This is
why every Lab candidate is negative — they all trade the same break-even signal and pay the same costs.

## What actually moves the needle (in order of impact)
1. **Cut your spread — this is the #1 lever.** 0.37 is wide for gold. A tighter-spread / ECN / raw
   account (gold spreads of 0.10–0.20 during London/NY) removes **~0.025–0.03R per trade** — enough to
   flip a break-even signal slightly positive. This is a **broker/account change**, not code. It will
   do more than any setting in this app.
2. **Trade far fewer, only A+ setups in prime hours.** Fewer trades = less cumulative cost bleed, and
   concentrating on the best London/NY setups raises the average edge per trade above the cost hurdle.
   I've added a concentrated **"Prime Quality"** config for you to install and re-Validate.
3. **Adaptive cost discipline (new in the engine).** The spread gate is now **volatility-aware**: it
   tolerates a wider spread only when the expected move (ATR) is big enough to pay for it, and tightens
   automatically when the market is quiet (where cost dominates). This stops the worst edge-to-cost
   trades. (It reduces trade count; it does not invent edge.)
4. **Re-Validate after the broker/config change.** If **Validate My Edge** still shows NO-GO on real
   history, accept the honest result.

## The honest bottom line
On **M15 XAUUSD with a 0.37 spread**, this signal is a **break-even coin-flip that loses to costs.** No
code change I can make manufactures a real edge — and I won't pretend otherwise. Your realistic options:
- **Get the spread down** (better broker) and re-Validate — the most likely route to positive.
- **Be ruthlessly selective** (Prime Quality, prime sessions only) and accept far fewer trades.
- **Treat it as a research/demo tool** until Validate shows a genuine GO; consider testing a different
  timeframe or instrument where the signal shows more directional edge.

Do **not** trade real size while Validate says NO-GO. The kindest thing I can tell you is the true
thing: chasing more settings on a break-even-minus-costs signal will keep producing −0.04R.
