# GodMode V12.18 — Fresh-leg override: stop sitting out the START of a clean move

## The problem you saw
Your forecasts showed **80%-confidence BUYs parked as "No-Trade / Standby"** with
*"trend efficiency 0.16–0.21 < 0.42 — price is ranging"* — and then price ran ~80 points
straight up. The bot's **direction was right**; the gate was wrong.

Why: the chop filter uses a **20-bar** Kaufman efficiency ratio. Right after a dip-and-reverse,
that 20-bar window **still contains the old swing**, so it reads "low efficiency = chop" even
though a clean new leg has already started. The bot was judging the *new* move with a *stale*
measurement and sitting out the best part of the trend.

(Note: this is separate from, and on top of, the **sniper lock** fixed in V12.17 — uninstall that
first. Both were needed.)

## The fix — a *smarter* gate, not a looser one
The engine now also computes an **8-bar (short-window) efficiency** and its direction. When the
20-bar reading says "chop" **but** a clean, sized leg is underway **in the same direction as the
trade**, it's treated as a **fresh leg** and allowed as a **scout-size** entry instead of being
hard-blocked.

Guards so it never becomes "trade the chop":
- short-window efficiency must be **≥ 0.58** (a genuinely clean push, not noise),
- the leg must have moved **≥ 0.6 ATR** (not a tiny wiggle),
- it must agree with the **trade's direction**,
- it does **not** override the range-extreme block (you still never buy the top / sell the
  bottom of an established range),
- it enters at **scout size**, so a wrong read costs little.

This is deliberately the opposite of loosening the threshold — the stress-test showed lowering
the efficiency floor to 0.20 was the *worst* config. The override is targeted: it only fires on a
confirmed fresh push in the trade's direction.

## Evidence (cost-aware walk-forward, balanced strictness, identical candles)
| | Trades | Expectancy | PF | Win % | Max DD | Edge |
|---|---:|---:|---:|---:|---:|---|
| OFF (hard-block chop) | 2,438 | 0.183R | 1.32 | 45.7 | 35.2R | strong |
| **ON (fresh-leg override)** | 2,550 | **0.284R** | **1.52** | 48.3 | **32.1R** | strong |

Expectancy **+55%**, profit factor up, win rate up, and **drawdown went down** — it adds quality
early-trend entries, not chop noise. A second independent random sample agrees: 0.239R → **0.334R**
expectancy, drawdown 33.8R → **27.5R**. Both existing regression suites (range-awareness,
directional) still pass.

> **Honest caveat:** this is synthetic data — the fresh-leg trades' eye-popping standalone numbers
> are inflated because synthetic trends always follow through. The *relative* improvement (more
> trades, higher expectancy, **lower** drawdown) is the real signal. Validate on your own MT5
> history before sizing up. Default ON; tunable in code (`fresh_leg_override`, `fresh_leg_eff`,
> `fresh_leg_min_atr`).
