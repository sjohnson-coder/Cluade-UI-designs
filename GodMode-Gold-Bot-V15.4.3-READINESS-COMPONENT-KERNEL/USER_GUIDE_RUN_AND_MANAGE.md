# HOW TO RUN & MANAGE THE GODMODE GOLD BOT — Plain-English Guide (V12.69)

Read this once, top to bottom. Fifteen minutes now saves you hours later.

---

## PART 1 — What this bot actually is (30 seconds)

A rules-based XAUUSD (gold) scalping engine that reads your MT5 broker's live candles,
scores every potential setup against ~12 confluence factors (structure, order blocks,
RSI/MACD, higher-timeframe alignment, session, spread, news, macro), and only fires when
enough factors agree. It then manages the trade itself: break-even, dynamic trailing stop,
partial take-profits, fast-fail on dead trades, and optional pyramiding on winners.

The AI (Claude or OpenAI) is an **optional layer on top** — a coach that reviews results
and an auditor that second-opinions each entry. **The bot fully works without any AI
connected.** No key = those features quietly stay off; everything else runs.

---

## PART 2 — First-time setup (do once)

1. **Install MetaTrader 5** on this Windows PC and log into your broker account. Leave
   MT5 running. (The bot talks to your logged-in terminal — no separate broker password
   needed in most cases.)
2. **Install Python 3.10+** from python.org. During install, tick "Add Python to PATH".
3. **Unzip the bot** anywhere (e.g. `C:\GodModeBot`).
4. **Double-click `1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat`.** First run installs the
   backend packages (needs internet once), then opens the dashboard at
   `http://127.0.0.1:8000`. Later runs start in a couple of seconds.
5. In the dashboard go to **Settings → 2. MT5 Connection → "Auto-detect Running MT5"**.
   The status chip at the top should turn green.

That's it. The bot is now watching the market in **DRY RUN** (paper) mode — it evaluates
everything but sends no real orders.

---

## PART 3 — The safety ladder (how to go live WITHOUT losing money to a bug)

The bot has three locks stacked on purpose. Go up the ladder in order:

**Rung 1 — Dry run (default).** Watch the Dashboard and Signals pages for a few days.
Check the AI Agent page: is the bot's reasoning sensible? Are skip reasons legitimate?

**Rung 2 — Validate.** Go to the Backtest tab and run **Backtest → Validate** on your own
broker history. The Validation Lock (Settings → 3b) keeps live orders blocked until your
strategy passes your minimum trades / profit factor / expectancy rules **on your own data**.
Don't lower these thresholds to "make it pass" — that defeats the whole point.

**Rung 3 — Demo live, then small real.** Flip **Live Trading ON + Auto Trading ON**
(Settings → 3) on a demo account first. Run at least a week. Then real account at the
minimum lot (0.01) with Risk per Trade at 0.25–0.5%.

**Semi-auto vs Auto (Settings → 3, Execution Mode):**
- **Semi-auto (default, recommended to start):** every approved setup is sent to your
  Telegram with TAKE / SCOUT / SKIP buttons. You are the final trigger.
- **Auto:** approved setups fire straight to MT5. Only after you trust the verdicts.

**The panic buttons:** Risk page → Emergency Kill Switch stops everything instantly.
Telegram `/panic` does the same from your phone.

---

## PART 4 — Connecting the AI (optional, recommended)

**Works with BOTH Claude (Anthropic) and OpenAI — your choice.**

1. Get a key: Claude → console.anthropic.com → API Keys (`sk-ant-…`), or
   OpenAI → platform.openai.com → API Keys (`sk-…`).
2. Settings → **12d. AI Provider**: pick provider, paste key, set model
   (e.g. `claude-sonnet-4-6` or `gpt-4o`), click **Save + Test AI Connection**.
3. What the AI now does:
   - **AI Performance Coach** (AI Agent page): reads your closed trades AND the live
     skip/block stream, tells you in plain English what's hurting results, and proposes
     one-gate-at-a-time setting fixes. Every fix is whitelisted, clamped, and creates a
     rollback snapshot before applying.
   - **AI Entry Auditor** (Settings → 12d-2): one call per candidate entry, WITH a chart
     image of your real candles. It can veto a contextually bad entry, downgrade it to
     scout size, or tighten the stop to its invalidation level. It can never create trades.
     **Note:** chart-vision works on both providers; Claude is recommended for chart reads.
4. **Auditor rollout order:** use "Save + Preview Audit on Current Setup" a few times →
   enable with veto power OFF (downgrade-only) on demo → watch the Verdict Log on the AI
   Agent page vs actual outcomes for a few days → then enable veto power.
5. **If the AI service is ever down:** the audit is skipped and the engine's own decision
   stands (fail-open). The bot never stops trading because an API had a bad day — unless
   you deliberately turn on "Fail-closed".

**Cost reality:** roughly one AI call per actual trade plus on-demand reviews. With a
small model this is pennies per day.

---

## PART 5 — Daily management routine (5 minutes)

1. **Glance at the top bar**: MT5 chip green, Market OPEN, spread sane (<0.35 typical).
2. **Dashboard**: open P&L, today's trades, any risk warnings.
3. **AI Agent page**: read the "Why the bot skipped setups" panel. A healthy sniper bot
   skips MOST setups — that's discipline, not malfunction. Worry only when ONE reason
   dominates (>50% of skips) for days; then read the coach's suggestion about it.
4. **Once a week**: run a **Weekly AI Review** (AI Agent page). Apply at most ONE
   suggested fix, then let it run a week before touching anything else. One change at a
   time is the only way to know what worked.
5. **Telegram** is your remote control: `/status`, `/mode`, `/auto`, `/semi`,
   `/burst_on`/`/burst_off`, `/pyramid_on`/`/pyramid_off`, `/panic`.

## Things people get wrong (please don't)

- **Don't chase volume.** "The bot barely trades" usually means the market is chop and
  the bot is correctly flat. Loosening three filters at once to force trades is how
  accounts die.
- **Don't run two copies** of the backend at once (two .bat windows) — they'll fight over
  the same MT5 terminal and settings file.
- **Don't edit settings.json by hand while the bot is running.** Use the dashboard; it
  saves atomically and creates rollback snapshots.
- **Made a mess of settings?** Settings → 12f → **"Rollback Last Save / AI Fix / Import"**
  restores the previous state. Export your config after any setup you like.
- **Blank page after an update?** Hard-refresh the browser once (Ctrl+F5). V12.67+ serves
  the shell uncached so this should no longer happen, but old tabs may need one refresh.
- **Password fields showing empty is NORMAL** — secrets are masked for display. Saving
  with an empty field keeps the stored secret (fixed in V12.67).

## Phone access

Same Wi-Fi: run `start_backend_mobile.bat`, open `http://YOUR-PC-IP:8000` on the phone.
Anywhere: install free Tailscale on PC + phone, open `http://<PC-Tailscale-IP>:8000`.
Secure it: set `GODMODE_API_KEY` on the PC and enter the same key in Settings → 13.

---

## PART 6 — Quick answers

**Does it work without any AI?** Yes, completely. The trading engine is deterministic
rules — AI is an optional coach/auditor layer. No key = those panels just say "not
configured" and everything else runs.

**Is the AI real-time / does it improve live decisions?** Yes — the Entry Auditor runs
inside the live entry path: engine approves → AI audits in ~2–8 seconds → veto/downgrade/
stop-tighten applies → THEN the order (or Telegram approval card) goes out. It is not
in the tick loop (that would add cost and latency for nothing); it fires exactly when a
decision is about to become a trade, which is the only moment a second opinion matters.

**Which is better, Claude or OpenAI?** Both fully supported for coach and auditor. For
the chart-image reads Claude is recommended; for text-only auditing either is fine.

**What if my PC crashes mid-trade?** Broker-side SL/TP are always on the order, so the
broker protects the position even with the app dead. Restart the bot; it reconciles open
positions and resumes management.
