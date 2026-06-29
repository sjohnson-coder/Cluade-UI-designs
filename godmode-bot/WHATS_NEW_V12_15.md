# GodMode V12.15 — Range awareness + background backtests with a progress bar

## 1) Range awareness — stop buying tops / selling bottoms of a sideways range
This is the fix for what you saw all day: in a choppy range (3983–4052), the bot kept signalling
**BUYs at the range highs** — the worst place to buy. They were correctly filtered out yesterday by
the efficiency/RSI guards, but now there's a dedicated, cleaner filter at the source.

**How it works:** the engine measures where price sits in its recent range (0 = bottom, 1 = top).
When the market is a confirmed **sideways range** (low efficiency + a meaningful width) and price is
near an extreme, it:
- **BUY near the top → blocked** ("price near the TOP of a sideways range … don't buy the top"),
- **SELL near the bottom → blocked** ("… don't sell the bottom").

Crucially it **never fires in a real trend** — a genuine efficient trend is excluded, so a trend
*pullback* near the highs is still a good buy (verified in tests: range-top buy at efficiency 0.14 is
blocked; trend buy at efficiency 0.52 is allowed). The skip shows a **clear reason** in the Decisions
journal and the Telegram forecast.

**Optional FADE mode** (off by default, Settings → 4): instead of just skipping the extreme, *trade
the other way* — sell the top / buy the bottom of the range (mean-reversion). It's the aggressive
version; **validate it in the Backtest tab before using it live.**

**Settings → 4. AI Strictness:** Range awareness (on), Fade range extremes (off), Range top/bottom
block thresholds (0.78 / 0.22, tunable).

## 2) Background backtests with a progress bar
Validate My Edge, Run Backtest, and Run Strategy Lab no longer **freeze the page**. They now run as
**background jobs**:
- click once and a **progress bar** appears showing the live stage — *"Replaying bar 12,400 / 60,000
  · 37 trades so far"*, then *"Computing metrics, walk-forward folds & verdict…"* — with a **% and an
  ETA** ("~2 min left");
- the page **stays fully interactive** — you can switch tabs and keep working while it runs;
- the Strategy Lab bar even names the candidate being tested ("Testing Aggressive Scout 3/7 …").

Under the hood: new async endpoints (`/api/backtest/validate-async`, `/api/backtest/run-async`,
`/api/lab/run-async`) start a job and return a `jobId`; the UI polls `/api/jobs/{id}` for progress.
The heavy replay runs in a worker thread so the API never blocks. (The original synchronous
endpoints still exist.)

## Validation
Backend compiles ✓ · frontend builds ✓ · **10 simulation suites pass** (incl. a new range-awareness
suite: blocks the range-top buy, allows the trend buy, fades when enabled). Background job + progress
verified end-to-end (0→100% with live stages) and the progress bar confirmed in a real browser with
the page staying interactive during the run.
