# GodMode V8 — Intelligence Upgrade

This build closes the bot's feedback loop and adds true adaptive intelligence on top
of the existing deterministic decision engine. Below is exactly what changed and why,
mapped to the issues raised.

## The core problem that was fixed
Previously the bot computed a *selected strategy* but, at execution time, stamped the
MT5 comment with only the **entry type** (`GODMODE_auto_fire`). The real strategy was
discarded, the AI never recorded closed trades, and Analytics/Journal/Top-Strategies
grouped by the useless comment fragment. Three wires are now connected:
**record → attribute → learn → adapt.**

---

## What changed (file by file)

### New backend modules
- **`backend/services/trade_context.py`** — persistent `ticket → entry-context` store.
  Stamps a short, reversible strategy **code** into the 31-char MT5 comment
  (e.g. `GODMODE_LiqSweepOB_A`) and records the full strategy name, entry reason,
  confidence, session, regime, entry/SL at order time. Legacy entry-type comments are
  correctly *not* treated as strategies.
- **`backend/services/ai_reviewer.py`** — Claude-powered post-trade reviewer. Reads each
  closed trade's context and returns `{aiScore, summary, lesson, improvement, adjustment}`.
  Uses the Anthropic Messages API when `ANTHROPIC_API_KEY` is set (default model
  `claude-haiku-4-5-20251001`, override via `GODMODE_AI_REVIEW_MODEL`); otherwise falls
  back to a deterministic local reviewer so it **always works** with zero extra installs.

### Decision engine (`decision_engine.py`)
- **True HTF bias** from real **H4 + D1** candles (`_htf_bias`), added as a 1.30-weight
  scored factor and a gate (counter-HTF trades are blocked in sniper mode, flagged otherwise).
- **Performance-weighted ensemble selector** (`_rank_strategies`): every enabled strategy
  is scored for the current bar (regime fit × live win-rate × expectancy × session fit) and
  the best is chosen. The full ranked list is returned as `strategyCandidates`.
- **Calibration feedback** (`_apply_calibration`): confidence is nudged toward the *realised*
  win-rate for its bucket once ≥8 live samples exist — the calibration table is no longer
  cosmetic.
- Richer, human-readable `reason` including HTF bias and the management plan.

### MT5 bridge (`mt5_bridge.py`)
- Deeper history: **M15 500, H1 300, + new H4 200 & D1 200** (was 250/100, no H4/D1).
- **Exit-reason classifier** from the MT5 deal reason code → "Take profit hit",
  "Stop loss hit", "Closed manually", etc.

### API (`app.py`)
- **Learning loop**: every closed bot trade is now recorded into performance memory and
  reviewed by the AI — idempotent per ticket, real-data only (never demo).
- **Strategy attribution**: auto/manual/signal/execute orders stamp the real strategy and
  store entry context; closed trades are enriched with strategy + readable reason + R-multiple.
- **Top Strategies** now group by real strategy and emit both key styles, fixing the empty
  Dashboard card and the `GODMODE_sign/scou/auto_fir` fragments in Analytics.
- **`/api/strategies`** returns live-computed win-rate / sample size per strategy.
- **Signals** now return the primary signal **plus the ensemble leaderboard** so "Featured
  High-Confidence Signals" shows multiple real strategies.
- **Risk**: session caps + spread guard are now persisted/editable fields.
- New endpoints: `/api/ai/trade-review/{ticket}`, `/api/ai/review-summary`.

### Frontend
- **Dashboard**: fixed the Top-Strategies key mismatch (no more blank card), fixed the H1
  alignment bug, added a **Higher-Timeframe Bias (H4·D1)** card.
- **Risk**: the rule toggles now **save**, and **Session Risk Caps are editable & persisted**.
- **Signals**: Featured cards label the Top Pick vs ensemble Candidates.
- **Journal/Trades/Analytics**: now show the real strategy, a readable reason, and AI notes.

---

## How to turn on the Claude reviewer (optional)
In `backend/.env` set:
```
ANTHROPIC_API_KEY=sk-ant-...
GODMODE_AI_REVIEW_MODEL=claude-haiku-4-5-20251001   # or claude-sonnet-4-6 / claude-opus-4-8
```
Without a key the local fallback reviewer runs automatically.

## Note on the candle-depth / HTF answer
250 M15 candles was adequate for the M15 indicators but thin for EMA-200 and had **no**
true higher-timeframe context. This build pulls 500×M15, 300×H1, 200×H4 and 200×D1 and
computes a real daily/H4 bias used in both scoring and gating.
