# GodMode Gold Bot — Complete Guide (every function + how to test for productive trades)

This is the full manual: what each page/button does, and the exact testing workflow to go from
"installed" to "trading with a proven edge". Read the **Quick Start** and the **Golden Workflow**
first; the rest is reference.

---

## 0) Quick Start
1. **Start it.** Windows: double-click `START_HERE_NO_NPM_REQUIRED.bat`. Mac: double-click
   `START_HERE_MAC.command` (see `RUN_ON_MAC.md`). The dashboard opens at `http://127.0.0.1:8000`.
2. **Connect MT5** (Windows, live trading): open MetaTrader 5, log in, then in the bot go
   **Settings → 2. MT5 Connection → Auto-detect Running MT5**. The top bar "MT5" chip turns green.
3. **Stay in Dry Run** until you've validated an edge (below). Live trading is a deliberate switch.

> The top bar always shows: Live Connection, MT5, **Market (OPEN/CLOSED)**, Session, and Spread. When
> **Market = CLOSED** (weekends) the bot stands down and won't signal — that's expected.

---

## 1) The Golden Workflow (do this in order)
**The bot will not make money just by running it. Prove an edge first.**

1. **Cache history in MT5.** On your MT5 XAUUSD M15 chart, scroll *far* back (months) so MT5 stores
   the candles the bot will replay.
2. **Validate My Edge** (Analytics → Backtest → *Validate My Edge*). This replays the real engine over
   ~2 years of *your* MT5 history and returns **GO / CAUTION / NO-GO** with expectancy, profit factor,
   win rate and out-of-sample fold consistency.
   - **NO-GO / CAUTION** → do **not** trade live yet. Refine (below), don't size up.
   - **GO** → continue to step 3.
3. **Forward-test on DEMO** for 2–4 weeks. Watch it trade in real time with no money at risk.
4. **Go live small.** Only after demo matches the backtest: Settings → turn **Live Trading** on, start
   at the **minimum** risk %, and scale up *only* as live results track the backtest.

If Validate says NO-GO, use **Strategy Lab** and **Optimize Weights** (below) to search for a better
configuration — then re-Validate. Never skip straight to live.

---

## 2) Pages & every function

### Dashboard
The live command center. Shows the current signal (BUY/SELL/WAIT/**CLOSED**), confidence ring, the
"Why this trade?" confluence checklist, the active strategy the router picked, account, open trades,
and a market-closed banner on weekends. **Refresh** re-pulls now (it also auto-refreshes).

### Signals
Real-time signal stream + a detailed inspector (entry, SL, TP1–4, confidence, confluence checklist,
execution readiness). **Execute Signal** sends the selected trade to MT5 (respects AI approval and all
gates). Filters: pair, session, strategy, confidence, status.

### Strategies
Your strategy arsenal. Each card shows win rate, expectancy, max DD, regime and sessions. Toggle a
strategy on/off (the router only picks from enabled ones). **Configure Strategy** edits its name, min
confidence and risk %. Installed Strategy-Lab strategies appear here too (see Strategy Lab).

### Trades
Live open trades, pending orders, and closed history with management controls (close, partial, etc.).
KPIs across the top (Net PnL, open PnL, win rate, profit factor, expectancy).

### AI Agent
The autonomous loop status + heartbeat (why it traded / didn't, each cycle), circuit breakers, and
recovery monitor. This is where you see the bot "thinking" live.

### Risk
The Risk Management Center: max daily loss, max drawdown, risk per trade, max open risk, exposure caps,
loss-streak limit, news filter, circuit breaker, spread cap, session caps. Live warnings & alerts, and
a margin-health ring. Edit a limit → **Save**. These are hard guardrails the engine respects.

### Analytics (tabs)
- **Overview / Performance** — equity curve, drawdown, returns heatmap, execution quality, KPIs.
- **Trades** — your bot-only trade sample, **paginated** (15/page).
- **Strategies** — per-strategy net PnL / win rate; expectancy-vs-winrate scatter.
- **Decisions** — the *Decision & Management Journal*: a timestamped log of **why** the bot did or
  didn't trade, and every management action. The answer to "why didn't it take X?".
- **Backtest** — the engine room (see Testing, below).
- **Strategy Lab** — the self-improving strategy finder (see Testing, below).
- **Risk / Reports / Custom** — risk visuals, full JSON report, custom date-range views.
- The date pickers + **Refresh / Export** apply to the whole page.

### Journal
Your trading journal. **New Journal Entry** opens a form (date, symbol, side, outcome, PnL, strategy,
session, lessons, what-I'll-do-differently, notes) — saved to disk and shown alongside the bot's
auto trade-journal. Filter by **Date From / Date To**, Outcome, Strategy, Symbol, and **search** the
text of every entry. The summary tiles compute win rate, total PnL, best/worst trade.

### Settings (numbered cards)
1. **Appearance** — theme, density, sound. 2. **MT5 Connection** — auto-detect / manual login.
3. **Trading** — symbol, risk %, order type, sessions. 4. **AI Strictness** — relaxed/balanced/strict/
**sniper** presets + confidence, R:R, efficiency, **Range awareness**, **Fade range extremes** (leave
OFF — it loses), **Fresh-leg override** behaviour. 5–6. **Management / Automation** — break-even,
trailing, fast-fail, pyramiding, cooldowns, recovery monitor, vol-normalized sizing. 7. **Telegram** —
token, chat ID, chart images, WAIT forecast, daily/weekly recap (+ the new **Market Open/Closed**
updates). 8. **Risk note**, 12c. **Data Feeds** (DXY/US10Y/calendar URLs), 12d. **AI Strategy
Generator** (Claude/ChatGPT key), 12e. **Strategy Lab feed & schedule**, **13. Mobile & Remote
Access** (API key + Tailscale), **14. Save & Apply** (persist everything).

---

## 3) Testing for productive trades (the core of the bot)

### Validate My Edge  (Analytics → Backtest)
The single most important button. Replays the **real decision engine** over your MT5 history with
costs (spread + commission) and walk-forward folds, then gives **GO / CAUTION / NO-GO**. A real GO
needs **positive expectancy after costs AND consistent out-of-sample folds**. Runs in the background —
you'll see a progress bar with a **Stop** button, and you can switch tabs/pages while it runs.

### Run Backtest  (Analytics → Backtest)
Same engine, but you choose the bar count and the **spread/commission** — set these to your broker's
real XAUUSD costs. Gives overall expectancy/PF/DD, **per-strategy** verdicts (KEEP/REFINE/DISABLE),
and the walk-forward folds. Use **"Disable no-edge"** to switch off strategies that don't earn their
keep. Also background + Stop.

### Optimize Weights  (Analytics → Backtest)
Trains the engine's confidence-factor weights on part of your history and validates on the rest
(anti-overfit shrinkage). Toggle **"Apply if improved"** to persist a genuinely better weighting.
**Reset Weights** restores the hand-set defaults.

### Strategy Lab  (Analytics → Strategy Lab)
The self-improving finder. It back- and forward-tests a library of candidate trading **styles**
against *your* data and head-to-head with your current config, and only **recommends** an upgrade
that genuinely beats you out-of-sample. **Generate with AI** (needs a Claude/ChatGPT key in Settings
12d) proposes new candidate styles — fully validated/clamped, never code. **Fetch feed** pulls from a
trusted URL you control. **Install** adds the winner as a real strategy in your rotation **with its own
gates — it does NOT rewrite your global strictness** (and **Uninstall & revert** removes it). Runs in
the background with a Stop button. *Autonomy is "AI recommends, you approve" — nothing installs itself.*

### Decisions journal  (Analytics → Decisions)
After any session, this tells you exactly **why** the bot stood down (spread too wide, choppy/range,
low confidence, news blackout, etc.) — so you can fix the real blocker instead of guessing.

---

## 4) Why "it's not trading" (and what to do)
The bot is built to **wait for quality**. Common, *correct* reasons it stands down — all visible in
"Why this trade?" / Decisions:
- **Market CLOSED** (weekend) — it resumes Sunday ~22:00 UTC.
- **Spread too wide** — e.g. `spread 0.37 > 0.35 threshold`. Trade during London/NY when spreads
  tighten, or raise the cap in Risk if your broker runs wider (carefully).
- **Choppy/range** or **price at the top/bottom of a range** — it's avoiding the worst entries.
- **Confidence below threshold** — if you installed the "Sniper Quality" Lab tuning it clamped you to
  85%+; **Analytics → Strategy Lab → Uninstall & revert** to return to balanced.
- **News blackout** — high-impact USD news window.

If you want *more* trades: Settings → 4 → use **balanced** (not sniper), keep scout entries on. If you
want *fewer/higher-quality*: use strict/sniper. Always re-**Validate** after changing strictness.

---

## 5) Safe go-live checklist
- [ ] Cached ≥1 year of M15 history in MT5.
- [ ] **Validate My Edge = GO** (positive expectancy after costs + consistent folds).
- [ ] Forward-tested on **demo** 2–4 weeks; live-like results match the backtest.
- [ ] Risk per trade at the **minimum**; Risk page caps set; circuit breaker on.
- [ ] Telegram alerts on so you're notified of every entry/close + daily summary.
- [ ] Only then: Settings → Live Trading ON, Auto Trading ON. Scale up slowly.

> Reality check: a backtest on synthetic data (MT5 not connected) is illustrative only. The real
> verdict is **Validate on your own MT5 history**. Don't size up on hope.
