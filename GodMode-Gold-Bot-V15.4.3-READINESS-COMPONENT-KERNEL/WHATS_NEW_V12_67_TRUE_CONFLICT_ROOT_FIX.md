# GodMode Gold Bot V12.67 — True Conflict Root-Cause Fix + AI Intelligence Upgrade

V12.66 patched the *symptoms*. V12.67 fixes the actual *root causes* that were still
making settings roll back, and makes the AI agent genuinely useful instead of decorative.

---

## The real reason settings kept "rolling back" (now fixed)

The dashboard was **silently wiping your MT5 password on every Save**, and Config Import
was wiping **every** secret (Telegram token + all API keys).

Why: `GET /api/settings` masks secrets to `""` before sending them to the browser (correct,
for safety). But the Settings page holds that whole object and posts **all of it** back when
you press Save. The backend's deep-merge then wrote the empty `""` straight over your real
stored password. Everything looked fine in the session — until you restarted, MT5 could no
longer log in, and the config looked like it had "reverted."

**Fix:** an empty value on any known secret field now means *"keep what's stored"*, never
*"erase it"*. A real new secret still overwrites normally. Proven with unit + end-to-end tests.

Secret paths protected: `mt5Connection.password`, `telegram.botToken`, `aiProvider.apiKey`,
and all `dataFeeds.*Key` / `strategyLab.feedKey`.

## Other conflicts fixed

1. **`GET /api/settings` was not a pure read.** Every page load called
   `_apply_runtime_settings()` and wrote the live MT5 status object into the global settings
   dict, re-pushing credentials to the MT5 bridge. Reads are now side-effect-free; runtime
   status is attached only to the response copy.

2. **Live/Auto-trading toggles returned the full settings blob.** The Settings page replaces
   its entire form whenever a response carries `settings`, so flipping a toggle **threw away
   every unsaved edit you had typed** — the exact "my edits keep reverting" feeling. Those
   endpoints no longer return `settings`; the toggle is still persisted, the UI keeps your edits.

3. **Save could time out and report failure while actually succeeding.** Each Save takes a
   rollback snapshot, and the snapshot was recomputing full MT5 analytics (slow). On a slow
   history read the request blew past the browser's timeout — the save completed but the UI
   said "Save failed" and reloaded old values. Snapshots now use a warm metrics cache and are
   instant. The whole save is also wrapped in one re-entrant lock so background tasks, Telegram
   commands and AI-coach applies can no longer half-apply on top of each other.

4. **Rollback now always has something to roll back to.** If the recorded snapshot pointer was
   missing or stale, rollback used to dead-end with an error. It now falls back to the newest
   snapshot on disk — which is what "undo my last change" should do.

5. **Signals tab going blank.** Belt-and-braces on top of V12.66's error boundary:
   `GET /api/signals` can now never return a non-array or a 500 — any internal failure degrades
   to an empty list, so the page renders "waiting for setup" instead of white.

6. **`index.html` is served `no-store`.** A browser caching the old app shell after a rebuild
   would load a deleted JS bundle = pure blank page. The shell is never cached now.

---

## AI agent is now actually intelligent

Before, the AI panel mostly restated numbers. Now:

- **The coach reads the live decision/block stream, not just closed trades.** It sees *why*
  the bot skipped setups over the last 48h (2d) / 7d — the dominant block reason, the fire
  rate (took vs skipped), and the BUY/SELL split.

- **It produces plain-English coaching suggestions**, e.g.:
  - "'trend efficiency 0.20 < 0.30 (chop)' caused 62% of skips. If backtests confirm the chop
    filter is too tight for current volatility, lower the active-mode efficiency floor by 0.02
    and re-validate — otherwise the market simply isn't trending and staying flat is correct."
  - "Strategy 'London Liquidity Sweep' is carrying the edge (71% win). Protect it: don't loosen
    global filters in ways that dilute its setups."
  - "SELL trades are only winning 28% — the bot may be fighting the higher-timeframe trend.
    Enable/verify the H4-D1 hard veto and the DXY/US10Y cross-asset filter."

- **A new "Why the bot skipped setups" panel** on the AI Agent page shows the fire rate and a
  ranked table of skip reasons, so you can see at a glance whether you're over-filtered.

- When you connect a Claude/OpenAI key (Settings 12d), the same block-stream is fed to the LLM
  with an upgraded prompt that demands one-gate-at-a-time, plain-language, safe setting patches.
  Every suggested change is still whitelisted, clamped, and snapshotted before applying.

- The safe-patch whitelist + clamps were extended to cover efficiency floors, confluence,
  chop and extension knobs, so the coach's suggestions are actually applyable via "Apply Fix".

---

## Rebuild note (important)

The dashboard bundle in `frontend/dist` already contains the V12.66 crash-safety (error
boundary + signal normalisation). The new **"Why the bot skipped setups" panel** is a source
change in `frontend/src/pages/AIAgent.tsx`. To see it in the UI, rebuild the frontend on your
machine:

```
cd frontend
npm install
npm run build
```

All the **backend** fixes (the ones that actually stop settings rolling back and make the AI
coach intelligent) are live immediately with no rebuild — just restart the backend with
`1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat`.

## Validation performed

- `python -m py_compile backend/app.py` passes.
- Unit tests: masked-secret save preserves stored password; real new secret still applies;
  masked config-import keeps secrets.
- End-to-end (real endpoint functions): Save → disk persist → Rollback reverts correctly;
  `GET /api/settings` no longer pollutes global state; `/api/signals` always returns a list;
  coach review carries the block-stream insight.
