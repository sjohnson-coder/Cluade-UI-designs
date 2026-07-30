# GodMode Gold Bot V12.81 — One Unified "Recommended Actions" (no more duplicate Apply Fix)

## The problem you flagged
The AI Agent page had FOUR separate places all telling you to apply a change:
1. Coach "recommendedFixes" table + standalone **Apply Fix** button
2. Coach "Recommended config: Trend Runner" insight
3. **Adaptive Config Library** — six profile cards each with **Apply**
4. (new in V12.80) the trade-review engine's own proposals

Four buttons, four mental models, easy to double-apply or contradict yourself.

## The fix — one panel, one flow
New **Recommended Actions** card on the AI Agent page merges every proposed change into a
single de-duplicated, severity-ranked list. Each item shows what it changes, why, its risk and
sample-confidence, and one **Approve** button. Backed by `GET /api/ai/unified-recommendations`,
which pulls from all sources and drops duplicate setting-paths (trade-review wins over coach for
the same path).

Everything now applies through ONE path:
- setting diffs -> `/api/ai/apply-proposal` (whitelisted, range-checked, rollback-snapshotted)
- whole profiles -> `/api/config/library/apply`

Removed from the page: the standalone Apply Fix button, the recommendedFixes table, and the
loose config-recommendation insight. The coach card now only does its job (grade, diagnosis,
skip-stats, Daily/Weekly review, Rollback). The Config Library stays for MANUAL profile apply,
but AI-suggested profile switches now surface in Recommended Actions instead of as a 6th button.

## Still sample-gated
Recommended Actions shows nothing to change until there are enough trades to avoid
curve-fitting — it will say so rather than invent tuning. On your current 15-trade sample it
correctly proposes nothing.

## Your uploaded journal — cross-checked
Ran the V12.80 review engine on godmode_trade_journal_20260712.csv (your real export). It
reproduced the AI Agent page exactly: 15 trades, 13W/2L, 86.7%, net +3.94, PF 1.49, and
independently identified the same pattern the coach lines show — Fsrc is the losing strategy
(-2.74 / 75% WR), Volatility Compression Breakout carries the edge (+4.74 / 100%), loss/win
size ratio 4.37x. Two systems agreeing on real data.

## Speed / safety
Boot 0.110s. `/api/signals` unchanged. Frontend: JSX balanced, all symbols wired, dead
surfaces removed, no unused locals. NOTE: the dashboard bundle must be rebuilt
(`cd frontend && npm install && npm run build`) to SEE the unified panel — the /tools page and
the stale-build banner remain the no-rebuild fallback. Full V12.67-81 regression green.
