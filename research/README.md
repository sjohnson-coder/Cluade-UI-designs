# XAUUSD structural research

An 11.7-year study of gold's intraday structure, built to answer one question: is there a
repeatable, exploitable pattern in how XAUUSD moves?

**Short answer:** not in direction — in the clock. See [FINDINGS.md](FINDINGS.md) for the
full result, or `docs/gold-clock-report.html` for the illustrated version.

## Layout

| Path | What it is |
|---|---|
| `data_pipeline.py` | Downloads 4.08M M1 bars from HistData, fixes the timezone, writes `m1.parquet` / `daily.parquet` |
| `analysis.py` | Every exhibit in the report — volatility clock, session drift, cost sensitivity, news windows |
| `backtest_engine.py` | Bar-by-bar sweep-and-reclaim and breakout models, with costs charged |
| `FINDINGS.md` | The written result |
| `viz_data.json` | Pre-computed series behind the report's charts |
| `../bot/session_overlay.py` | Reference implementation of the one strategy that survived |
| `../bot/XAUUSDSessionOverlay.mq5` | The same logic as a MetaTrader 5 EA |

## Running it

```bash
pip install pandas numpy scipy pyarrow
cd research
python data_pipeline.py     # ~40MB of zips, a few minutes
python analysis.py          # reproduces every number in FINDINGS.md
python backtest_engine.py   # the SMC audit
```

`data_pipeline.py` ends by re-running `verify_timezone()`, which asserts that the
NFP volatility spike lands at 08:30 in both winter and summer. If that assertion fails, the
data has been re-normalised upstream and **every session-level result below is invalid** until
the conversion is fixed.

## Two traps this code exists to avoid

**The timezone.** HistData documents its export as "EST without DST". It isn't — the stamps
are New York local time *with* DST. Trusting the docs shifts every summer observation by an
hour and smears each session boundary across two hours for eight months a year.

**The reopen print.** The strongest anomaly in the raw data — 18:00 NY, t = 7.75 — is a stale
quote. 42.8% of it comes from a single minute. Every candidate edge here is tested with the
boundary bar excluded, and that one check killed the best-looking result in the study.

## Result in one table

| | Buy & hold | Session overlay (1.5 / 0.5 / 0.0) |
|---|--:|--:|
| Return p.a. | 7.69% | **11.43%** |
| Volatility | 15.6% | 11.3% |
| Sharpe | 0.55 | **1.02** |
| Max drawdown | −28.3% | −18.3% |
| Hours exposed | 23 | 14 |

Viable at a round-trip cost below ~$0.35/oz (CME GC futures), dead above it (retail CFD).
Cost is the binding constraint, not the signal.

**Research, not investment advice.**
