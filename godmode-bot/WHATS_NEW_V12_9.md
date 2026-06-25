# GodMode V12.9 — Decision & Management Journal (see WHY it traded, or didn't)

Almost every question you've asked this session — *"why didn't it trade those buys?"*, *"is it
even working?"* — was really an **observability** gap. This release closes it: a persisted,
queryable log of every decision and management action, with the exact reasoning.

## What it captures
**Analytics → Decisions.** A live table (newest first, auto-refreshing) with three event types:

- **Entry decisions** — every time the bot evaluates a trade it logs **TAKE_TRADE** or
  **SKIP_OR_WAIT**, with the **side, confidence %, quality, selected strategy**, and the **exact
  blocking reason** (e.g. *"Confidence 68% below minimum threshold 72.0%"* or *"Choppy/range
  market: efficiency 0.21 < 0.28"*). So when it doesn't trade, you see precisely why.
- **Management actions** — break-even moves, trailing-up, **recovery-room** given, **fast-fail**
  closes, TP1–TP4 partials, TP push, dynamic-SL widening, auto-entry pauses — each with its detail.
- **Close outcomes** — WIN/LOSS/FLAT with the P&L, per ticket.

Filter chips (All / Entries / Management / Closes) with live counts, plus Refresh and Clear.

## Smart, not spammy
The bot evaluates every ~3 seconds, so a naive log would be thousands of identical "waiting" rows.
Instead it **collapses identical waiting states** and writes a new entry row **only when the
decision or the reason CHANGES** — so the journal reads like a story: *waiting (conf 68 < 72) →
took a BUY (STANDARD, Liquidity Sweep) → break-even → trailing → closed +1.4R.*

## Persisted across restarts
Events are written to `backend/data/decision_journal.jsonl` and reloaded on startup, so the
history survives a restart (it's gitignored — it's your runtime data). Up to 5,000 recent events
are kept in memory; the file is the durable record.

## Why this matters
- **Answers "why didn't it trade X?" instantly** — the skip reason is right there. (Had this
  existed earlier, the "only sells, never buys" issue would have shown itself in one glance: every
  buy row would have read *"over-extended / confidence below threshold."*)
- **Lets you measure the new mechanisms** — scan the Management rows to see whether **recovery-room**
  give-backs end in wins, whether **fast-fail** is cutting too early, whether **profit-lock** fires
  before pullbacks. Real evidence to tune with, instead of guessing.
- **Builds trust** — you can see the bot is alive and reasoning, even through a quiet session.

## API
- `GET /api/journal/decisions?category=all|entry|management|close&limit=250`
- `POST /api/journal/decisions/clear`

## Validation
Backend compiles ✓ · frontend builds ✓ · **6 simulation suites pass** — including a dedicated
journal suite proving entry-dedup (5 identical ticks → 1 row), changed-reason → new row, TAKE always
logged with full context, management/close capture, and **JSONL persistence + reload (newest-first)**.
