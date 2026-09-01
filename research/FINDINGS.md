# XAUUSD structural research — findings

**Sample:** 4,077,891 M1 bars · 3,006 trading sessions · 2015-01-02 → 2026-08-28 (11.7 years)
**Source:** HistData.com free 1-minute XAUUSD bid bars
**Strategies tested:** 64 configurations · **survived cost + out-of-sample + artifact audit:** 1

---

## Headline

There is no exploitable loophole in XAUUSD's **direction**. Yesterday's return explains
0.018% of the variance in today's. Every classic Smart Money / ICT liquidity model tested
here came out at or below break-even before costs and negative after them. News direction
is a coin flip. The largest statistical anomaly in the raw data is a stale price print.

There *is* an exploitable loophole in XAUUSD's **clock**. Volatility is ~3,160× more
forecastable than direction, and gold's entire risk-adjusted return over 11.7 years was
earned while Asia was awake and given back while New York traded. Re-weighting exposure by
session — predicting no prices at all — takes the Sharpe ratio from 0.55 to 1.02 and the
maximum drawdown from −28.3% to −18.3% on identical bars.

---

## 1. Win rate is a dial, not an edge

One setup (fade a sweep of the Asian high in the London killzone), 1,107 trades, entry rule
and sample held fixed. Only the target changes:

| Target | Win rate | Expectancy | Total | Profit factor |
|--------|---------:|-----------:|------:|--------------:|
| 0.25 R | 76.2% | −0.129 R | −142.8 R | 0.44 |
| 0.50 R | 66.7% | −0.125 R | −138.6 R | 0.67 |
| 1.00 R | 51.2% | −0.101 R | −111.9 R | 0.82 |
| 2.00 R | 35.5% | −0.088 R | −97.0 R | 0.88 |
| 5.00 R | 24.2% | −0.104 R | −114.5 R | 0.88 |

At a 0.05 R target with **zero** cost, the same setup posts a **94.4% win rate** —
1,045 wins, 62 losses, net **−9.7 R**.

A win rate quoted without expectancy, profit factor and max drawdown is the one number
that can be set to anything.

---

## 2. Method: two things that must be right

### Timezone

HistData documents its export as "EST, no DST". It is not — the stamps are **New York local
time with DST**. Proof: NFP (08:30 ET by definition) and the London PM fix (15:00 London)
both land on the same stamp in January and July. Taking the docs at face value shifts every
summer observation by an hour and destroys all session-level results.
`data_pipeline.verify_timezone()` re-runs this check.

### The reopen artifact

Scanning all 24 hours for drift, 18:00 NY (session reopen) dominates: **+2.87 bp, 60.5% hit
rate, t = 7.75**, worth $2,131/oz over the sample. It is not real:

- **42.8%** of the effect comes from the **single first print** of the session
- **61.2%** from the first five minutes
- No other hour shows this concentration — the artifact is isolated to the reopen

Excluding that print drops it to t = 2.66, and a $0.30 spread turns it negative. The same
trap has been documented independently in GDX overnight drift, where a 30%+ annualised
anomaly largely evaporated under minute-level execution.

**Rule:** any edge concentrated in the first or last print of a session is a data artifact
until proven otherwise.

### Test discipline

- Costs always charged ($0.35/oz standard; $0.10–$1.00 sensitivity sweep)
- Stops/targets walked bar-by-bar on M1 — no favourable intrabar assumptions
- IS 2015–2021 / OOS 2022–2026; a sign flip is failure, not a regime story
- Causal thresholds only (one promising FOMC result died when made causal)
- Returns in bp/ATR, never dollars — gold went $1,184 → $4,572 in-sample

---

## 3. What does not work

### Smart Money Concepts — 20 variants, all negative

Sweep-and-reclaim of Asian high/low and previous-day high/low, across London killzone,
NY killzone, NY AM and silver-bullet windows, at 2 R:

| Window | Level faded | n | Win | Expectancy | PF |
|--------|-------------|--:|----:|-----------:|---:|
| Silver bullet 10:00–11:00 | prev-day low | 335 | 41.8% | −0.026 R | 0.95 |
| NY killzone 07:00–10:00 | prev-day high | 512 | 39.1% | −0.037 R | 0.94 |
| London killzone 02:00–05:00 | prev-day high | 392 | 36.7% | −0.057 R | 0.92 |
| London killzone 02:00–05:00 | Asian high | 1,107 | 35.5% | −0.088 R | 0.88 |
| London killzone 02:00–05:00 | Asian low | 1,021 | 32.3% | −0.176 R | 0.77 |

**Diagnosis, which matters more than the verdict:** at zero cost these are roughly
break-even (PF 1.06–1.11). The pattern isn't random — it's too small to pay for itself.
A reclaim entry sits close to the swept extreme, so the stop is tight (median **$3.05**,
0.14 ATR). A $0.35 spread against a $3.05 stop is **11.5% of risk on every trade**.
Tightening stops for "better R:R" makes this strictly worse.

### News direction

- NFP 08:30–08:35 window: median range **$8.23** vs **$1.07** quiet = **7.7×**, and
  **35.1%** of the entire day's range in five minutes
- Does the first 5-minute impulse hold to the close? **50.4%** on NFP days, 48.9% otherwise

The volatility is completely reliable. The direction is a coin flip taken at the widest
spread of the day.

**Look-ahead warning:** days with a large 14:00 spike initially showed 57.7% continuation.
Rebuilt with a *causal* trailing threshold: t = −0.08, IS +0.027 / OOS −0.059. It was
look-ahead bias.

### Rejection log

| Hypothesis | Result | Verdict |
|---|---|---|
| Judas swing (fade first Asian-range sweep) | High-first 50.5% / low-first 47.9%; opposite side later taken 40–44% | No bias |
| PDH/PDL sweep & failure | PDH swept 50.4% of days, closes back below 48.6% of those | No bias |
| Opening-range breakout 08:00–11:00 | Best −0.002 R; IS −0.027 / OOS +0.035 sign flip | Unstable |
| Breakout + 50d trend filter | +0.025 R, PF 1.09 — 74 trades/yr × 0.025 R | Too thin |
| Daily trend following (Donchian 20/55, MA crosses) | All four flipped sign IS→OOS; best +2.4 R total | Unstable |
| 26-condition scan for NY direction | Strongest \|t\| = 2.49 across 26 tests | Null |
| Weekend gap fade | 97% fill, but median gap $0.33 < spread | Untradeable |

Buy-and-hold (CAGR 12.0%, max DD −26.6%) beat every timing system tested.

---

## 4. What is real

### Volatility is forecastable; direction is not

| Measure | R² |
|---|---:|
| Yesterday's ATR14 → today's true range | **0.563** |
| Yesterday's return → today's return | **0.00018** |
| Ratio | **3,160×** |

True-range autocorrelation is +0.80 at 1-day lag; returns are +0.013.

### The clock

Share of the average day's range by NY hour — **08:00–11:00 carries 21.9% in three hours**.
**~30%** of session highs and **31%** of session lows form between 08:00 and 12:00 NY —
four hours out of twenty-three, at 1.8× proportional share.

### The session asymmetry — the core finding

Session drift, reopen print excluded:

| Window | n | Mean | Up% | t | p | Sharpe |
|---|--:|-----:|----:|--:|--:|-------:|
| Asia 18:05–02:00 | 2,914 | **+2.59 bp** | 51.8% | **3.00** | **0.0027** | 0.88 |
| London 02:00–08:00 | 2,955 | +0.56 bp | 50.6% | 0.66 | 0.51 | 0.19 |
| NY AM 08:00–12:00 | 2,934 | +0.45 bp | 50.4% | 0.40 | 0.69 | 0.12 |
| NY PM 12:00–16:58 | 2,655 | −0.79 bp | 48.9% | −1.09 | 0.27 | −0.34 |

Holding gold in one session only:

| Exposure | Market hours | Return p.a. | Vol | Sharpe | Max DD |
|---|--:|--:|--:|--:|--:|
| Buy & hold (all sessions) | 23 | 7.69% | 15.6% | 0.55 | −28.3% |
| **Asia only 18:05–02:00** | 8 | 6.95% | 7.1% | **0.98** | −13.2% |
| London only 02:00–08:00 | 6 | 1.80% | 6.5% | 0.31 | −21.8% |
| **New York only 08:00–17:00** | 9 | **−0.98%** | 11.4% | **−0.03** | −30.8% |

The 08:00–12:00 NY window spans 60.7% of the average daily range and delivers none of the
return. Asia spans 48% and delivers all of it.

Robustness: Asia drift positive in **10 of 12** calendar years; by thirds +2.74 / +0.74 /
+4.55 bp. 2018 and 2022 were negative.

**Why this is credible beyond the backtest:** the overnight drift is one of the most durable
anomalies in finance. The NY Fed attributes it to dealer inventory management — intermediaries
absorb order imbalances into the close and are paid for carrying that risk through illiquid
hours. Gold has the same dealer structure and the same Asia→West handoff.

### Calendar

- **Friday is the strongest day**: +0.086% mean, 55.7% positive, t = 1.95
- Monday flattest at 50.5%
- Weekly high forms Friday 27.4%; Sunday+Monday produce 33.7% of weekly lows
- Strongest months: Jan +3.8%, Dec +2.2%, Aug +1.9%, Oct +1.7%. Negative: Jun, Sep, Nov
- Monthly sample is only 11–12 observations — a tiebreaker, not a signal

### The volatility regime shift

| Year | ADR | % of price |
|---|--:|--:|
| 2018 | $12.31 | 0.97% |
| 2021 | $23.93 | 1.33% |
| 2024 | $33.17 | 1.38% |
| 2025 | $60.85 | 1.73% |
| 2026 | $128.47 | 2.78% |

**Every threshold in a gold bot must be a multiple of ATR, never dollars or pips.** A $30
stop was 2.4 average daily ranges in 2018 and is 0.23 of one in 2026 — the same code
silently mutated from a swing system into a scalper. This is the most common cause of a
gold EA that "stopped working."

---

## 5. The construction that survived

| Construction (Asia / London / NY weights) | Return p.a. | Vol | Sharpe | Max DD |
|---|--:|--:|--:|--:|
| Buy & hold, flat 1× | 7.69% | 15.6% | 0.55 | −28.3% |
| Overlay 1.0 / 0.5 / 0.25 | 7.80% | 8.6% | 0.92 | −13.7% |
| **Overlay 1.5 / 0.5 / 0.0** | **11.43%** | 11.3% | **1.02** | −18.3% |

Comparable return to holding gold outright, at 72% of the volatility, drawdown 10 points
shallower, and **zero exposure during the most violent nine hours of the day**.

### Cost is the entire question

Gross Asian drift is 2.59 bp/session (~$0.57/oz). A typical retail XAUUSD spread is 2–4 bp.

| Venue | Round trip | Net/session | Annualised | Verdict |
|---|--:|--:|--:|---|
| CME GC futures (1 tick + comm.) | $0.10 | +1.98 bp | +5.00% | **Viable** |
| GC futures, wider fill | $0.20 | +1.38 bp | +3.47% | **Viable** |
| Tight ECN CFD | $0.30 | +0.77 bp | +1.95% | Marginal |
| Typical retail CFD | $0.50 | −0.43 bp | −1.09% | **Dead** |
| Wide retail CFD | $1.00 | −3.45 bp | −8.70% | **Dead** |

**Build this on CME gold futures (GC, or MGC at 10 oz), not a retail CFD.** If a CFD is the
only option, verify a sub-$0.30 average spread on your own fills during 18:00–02:00 — spreads
widen precisely at the rollover this strategy trades into. The lower-turnover overlay is the
better answer: it adjusts weight rather than round-tripping the position nightly.

---

## 6. Implementation

See `bot/session_overlay.py` and `bot/XAUUSDSessionOverlay.mq5`.

1. **Clock, NY time with DST.** Asia 18:05–02:00 ×1.5, London 02:00–08:00 ×0.5, NY
   08:00–17:00 ×0.0, flat 17:00–18:05. Entry at 18:05, never 18:00.
2. **Volatility-targeted size.** notional = equity × weight × min(target_vol / realised_20d, 1.5)
3. **Spread gate.** Above $0.35/oz, never increase exposure. Reducing risk always allowed.
4. **Trend filter.** Flat below the 200-day MA (optional — costs return, cuts the tail).
5. **Flat before the weekend.** Friday 15:00 NY.
6. **Hard per-session stop** at 2% of equity.

### Three things that will silently break it

- **Broker server time ≠ New York time.** Most MT5 brokers run GMT+2/+3 on *European* DST.
  The EA converts through GMT and applies the US rule; its DST routine was verified against
  105,192 hourly stamps (2015–2026) with zero mismatches.
- **Swap/financing.** The Asian window straddles the rollover where swap is charged. A
  −$3/lot/night swap against $0.57/oz of edge is not a rounding error.
- **Backtest on your own broker's ticks.** This edge lives inside a margin narrow enough
  that feed differences matter.

---

## 7. What would make this wrong

- **The Asian drift is real but not large.** t = 3.00 over 2,914 sessions — and negative in
  2018 and 2022. A two-year losing stretch is inside normal behaviour, so you cannot tell a
  bad run from a dead edge quickly. Decide the abandonment rule in advance.
- **The sample is one regime.** 2015–2026 is a secular bull market ($1,184 → $4,572; 2025
  alone +51.7%). Long-side results, the 200d filter and the Asia drift may partly express
  that trend. A genuine bear decade is the real test.
- **Volatility regime shift.** ADR went 10× within the sample. ATR-normalisation is the
  defence, but another doubling changes fill quality in ways backtests miss.
- **Crowding.** The overnight drift is well documented and increasingly traded.
- **Costs are the binding constraint and can change.** The strategy sits 1–2 bp above
  break-even. Monitor realised cost as a live risk metric, not a setup parameter.
- **Single instrument, single data feed.** Nothing here is validated on a second vendor's ticks.

---

## On "manipulating" the market

Nothing here involves influencing the price of gold, and nothing here would work if it tried.
The structure described is a *liquidity and inventory* pattern — dealers being paid to carry
risk through illiquid hours — that you join rather than create. The edge comes from being on
the right side of the clock, in size you can afford, at a cost low enough to keep it.

---

## Sources

1. Quantum Algo / LuxAlgo — SMC backtesting surveys; no rigorous public study establishes
   standalone profitability.
2. Kohli, R. — *Day-of-the-week effect and January effect examined in gold and silver metals.*
3. Yu, H-C. et al. — *Weekday effects on gold: Tokyo, London, and New York markets.*
4. Haghani, Ragulin & Dewey — *Night Moves: Is the Overnight Drift the Grandmother of All
   Market Anomalies?* SSRN.
5. Boyarchenko, Larsen & Whelan — *The Overnight Drift*, NY Fed Staff Report 917.
6. QuantPedia — *Dangers of Relying on OHLC Prices: Overnight Drift in GDX ETF.*
7. SSGA *Gold 2026 Outlook*; Goldman Sachs and J.P. Morgan on central-bank demand and real yields.
8. Price data: HistData.com free 1-minute XAUUSD bars, 2015-01 → 2026-08.

**This is research, not investment advice.** Leveraged gold trading can lose more than the
capital committed. The edge documented here is small enough that ordinary execution
differences can erase it.
