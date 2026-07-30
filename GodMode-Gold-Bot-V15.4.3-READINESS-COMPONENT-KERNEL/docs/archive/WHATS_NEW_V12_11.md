# GodMode V12.11 — AI Strategy Lab (self-improving, evidence-based)

This is the foundation of the "AI agent that scouts and tests better strategies" you described —
built the safe, honest way. **Analytics → Strategy Lab.**

## What it does
The agent back- and forward-tests a **library of candidate trading STYLES** against **your own MT5
history** and **head-to-head with your current live config**, then recommends an upgrade **only when
a candidate genuinely beats your setup out-of-sample**. Click **🧠 Run Strategy Lab** and it:

1. Backtests your **current config** (the baseline) over your history with realistic costs.
2. Backtests **every candidate** over the **same** history (each candidate is the real engine tuned
   to a different style — e.g. *Tight Trend-Rider, Aggressive Scout, Sniper Quality-Only, London/NY
   Breakout, Strict Chop-Avoider, Balanced+*).
3. Shows a **head-to-head table**: each candidate's expectancy, **± vs your baseline**, profit factor,
   win rate, % of walk-forward folds positive, and trade count.
4. If a candidate clears a real margin **and** holds up out-of-sample **and** doesn't worsen profit
   factor, it raises a **Recommended Upgrade** with the **back/forward-test evidence and the reason
   it's better**, plus a one-click **Install**.

When a better strategy is found it also fires a **notification + top-bar alert + sound + Telegram
message** prompting you to review and install.

## "Cross-references your live & past trades"
Because each candidate is replayed over **your real history with the real engine**, the comparison
*is* the cross-reference: it shows whether that style would have produced better outcomes than your
current config did over the same market — exactly what you asked for.

## Install shows the evidence
Clicking Install displays the candidate's back/forward results (R/trade, profit factor, % folds
positive, trade count) and its thesis, then applies the profile to your live engine and **persists
it** (survives restart). Nothing is ever auto-applied — you decide, with the numbers in front of you.

## The honest part (and how it's safe)
True *autonomous internet code-writing* isn't safe — it means running arbitrary generated code on
your account. So candidates come from a **curated, expandable library** of proven Gold styles, and
**everything is proven on your data and approved by you before it trades**. The pipeline already
accepts external candidates of the same shape (`POST /api/lab/add-candidates`) — a **trusted strategy
feed** (a URL you control, like the macro feeds) or an **AI generator** (Claude API, bounded to a
safe rule grammar) can be plugged in next to widen the pool, with the same backtest-gate + your
approval protecting you. (Tell me which of those two you want and I'll wire it.)

## Also: "vet all strategies against the live chart"
The engine **already** ranks your strategies by live-chart fit every cycle and picks the best for
each forecast — and the new **Decisions journal (V12.9)** now shows that choice and its reasoning live.

## API
`GET /api/lab/candidates` · `POST /api/lab/run` · `GET /api/lab/status` · `POST /api/lab/install` ·
`POST /api/lab/add-candidates`

## Validation
Backend compiles ✓ · frontend builds ✓ · Strategy Lab tab verified responsive on mobile in a real
browser ✓ · **8 simulation suites pass** — including a dedicated lab suite proving head-to-head
candidate testing, **the live engine config is always restored** after a run, the recommendation
gate (withholds a marginal candidate, recommends a genuine OOS winner), and external-candidate
ingestion (dedup + validation).
