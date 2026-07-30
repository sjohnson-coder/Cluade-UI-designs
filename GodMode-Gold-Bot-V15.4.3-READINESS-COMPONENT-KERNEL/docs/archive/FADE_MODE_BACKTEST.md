# Range-filter FADE mode — backtest verdict

**Question:** the V12.15 range filter can do two things at a sideways-range extreme — **BLOCK**
(skip the trade, the default) or **FADE** (trade the *other* way, i.e. mean-revert: sell the top /
buy the bottom). FADE ships **off**. Should it be on?

**Answer: No. Keep FADE off.** Fading the extremes turns a strong-edge configuration into a
marginal one. This was the expected result for a trend-following Gold bot, now confirmed with a
head-to-head backtest, and it's why FADE was shipped disabled.

## How it was tested
Identical method to **Validate My Edge** (same cost-aware walk-forward engine, same 12 live
strategies, spread 0.25 + commission 0.07, 6 folds), run at the realistic **balanced + scout**
strictness most users run. Three configurations were replayed over the **same** candle series so
the only variable is the range policy:

1. **Range OFF** — the range filter disabled entirely (control).
2. **BASELINE** — range filter on, extremes **blocked** (current default).
3. **FADE** — range filter on, extremes **mean-reverted** (the option under test).

Faded counter-trades are tagged at the moment of entry, so their standalone performance is
measured directly.

> **Data caveat (important):** MT5 isn't connected in this environment, so the replay runs on a
> synthetic Gold M15 series built to contain both clean trend legs and genuine sideways ranges.
> The **absolute** numbers (e.g. an apparent "strong" edge) are inflated by clean synthetic
> trends and are **not** a real-money edge claim. What's valid here is the **relative** comparison
> on identical bars: BASELINE vs FADE. The real edge verdict still comes from running Validate My
> Edge on your own cached MT5 history.

## Results

### Preliminary — 6,000 M15 bars
| Config | Trades | Expectancy R | PF | Win % | Total R | Edge |
|---|---:|---:|---:|---:|---:|---|
| Range OFF (control) | 589 | 0.245 | 1.44 | 47.0 | 144.5 | strong |
| **BASELINE (block)** | 585 | **0.206** | 1.36 | 46.2 | 120.4 | **strong** |
| **FADE (mean-revert)** | 666 | **0.080** | 1.13 | 42.3 | 53.3 | **marginal** |

- Turning FADE on cut expectancy **0.206R → 0.080R** and downgraded the edge **strong → marginal**.
- The **85 faded counter-trades** stood alone at **−0.73R each, 19% win rate** — they are pure bleed.

### Confirmation — 36,000 M15 bars (≈1.5 years)
| Config | Trades | Expectancy R | PF | Win % | Total R | Max DD R | OOS % | Edge |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Range OFF (control) | 3,585 | 0.24 | 1.43 | 46.6 | 862.0 | 37.8 | 100 | strong |
| **BASELINE (block)** | 3,636 | **0.19** | 1.33 | 45.6 | 692.4 | 36.8 | 100 | **strong** |
| **FADE (mean-revert)** | 4,296 | **0.04** | 1.06 | 41.0 | 171.5 | **85.5** | 83 | **none** |

The larger sample makes the verdict harsher, not softer:
- Expectancy **0.19R → 0.04R**; edge **strong → none**; total return **692R → 172R** (**−521R**).
- **Max drawdown more than doubles: 36.8R → 85.5R.** FADE adds losers in clusters (it fires during
  the same ranging stretch), so the equity damage compounds.
- The **662 faded counter-trades** again stand alone at **−0.73R, 18% win** — *identical* to the
  6k sample's −0.73R / 19%. That stability across independent samples means this is a real,
  repeatable effect, not a draw of the dice.

## Why FADE loses
The bot is a **trend-following** Gold engine. The signals that survive its gates near a range top
are usually momentum/structure still pointing **with** the prior trend. Selling into that (the FADE)
fights the very thing the bot is good at — and because ranges come in stretches, the bad fades
cluster together and balloon the drawdown. The range filter's value is the **BLOCK** — it stops you
*buying the top* of chop — not flipping into a counter-trade. Mean-reversion is a different strategy
with its own entry/exit logic, not a one-line inversion of a trend signal.

> On this clean-trend synthetic data the BLOCK costs a little vs no filter at all (0.24R → 0.19R,
> drawdown unchanged, OOS still 100%) because synthetic trends rarely punish "buying the top." On
> **real** Gold chop that's exactly the trade that hurts, so the BLOCK is cheap insurance — keep it
> on. FADE, by contrast, is harmful in every sample.

## Recommendation
- **Leave "Fade range extremes" OFF** (Settings → 4). This backtest confirms the shipped default.
- Keep **Range awareness ON** (the BLOCK) — it's the protective half and costs little.
- If you ever want to trade mean-reversion deliberately, build it as its **own** strategy in the
  Strategy Lab (with its own backtest gate), rather than as a fade toggle on the trend engine.
