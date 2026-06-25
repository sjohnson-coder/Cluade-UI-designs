# GodMode V12.10 — Operational safety hardening (don't blow up)

The bot is feature-complete and observable; this makes it **safe to leave running**. Four
production failure modes are now handled.

## 1) Daily-loss circuit breaker
Your **Settings → 8 → Max Daily Loss %** is now enforced. The bot tracks its **realized P&L per
UTC day**; once the day's loss reaches that % of equity, **new auto-entries halt for the rest of
the day** (open trades keep their protection) and you get a red alert. Resets automatically at the
next UTC day. Stops one bad session from snowballing.

## 2) Equity-drawdown stop
**Settings → 8 → Equity Stop Loss %** is now enforced against a **high-water mark**. If equity
falls that far below its peak, the **emergency kill switch engages** and trading halts until you
review and reset it. This is the catastrophic-loss backstop.

Both breakers are gated by **Use Equity Protection** (leave it ON).

## 3) Crash recovery (resume mid-trade after a restart)
The per-trade protection state (locked peak/floor, partials already taken, break-even flag) and the
safety counters (equity high-water mark, daily P&L, loss-streak, cooldowns) are now **persisted to
disk and restored on startup**. If the bot (or the PC) restarts while a trade is open, it **resumes
exactly where it left off** instead of re-arming from scratch or re-taking partials it already took.

## 4) Disconnect pause + auto-resume
If MT5 disconnects, auto-entry **pauses and you get a notification** ("MT5 disconnected — auto-entry
paused"). When the connection returns, it **resumes automatically** with a "reconnected" notice.
Open trades remain protected by their broker-side SL throughout. (This is the class of problem
behind the earlier "charts don't match" — the bot was disconnected; now it tells you.)

---

## Notes
- These reuse the risk settings you already have (Max Daily Loss %, Equity Stop Loss %, Use Equity
  Protection) — they simply **do something now**.
- Runtime state lives in `backend/data/protection_state.json` (gitignored — it's your live data).
- Nothing changes your strategy logic or entries; this is pure capital protection + resilience.

## UI responsiveness audit (also this release)
Drove the built UI in a real headless browser at **mobile (390px)** and desktop. **All new features
— the Decisions journal tab, the Validate-My-Edge button + verdict, and the new Settings cards
(Data Feeds, volatility sizing, smart recovery, risk note) — render cleanly with no horizontal
overflow on mobile.** (One pre-existing global-shell overflow exists only at exactly 1440px laptop
width — present on untouched pages too, fine on mobile and ≥1920px — not introduced here.)

## Validation
Backend compiles ✓ · frontend builds ✓ · **7 simulation suites pass** — including a dedicated safety
suite proving the daily-loss breaker (trips at the threshold, not before), the equity stop (engages
the kill switch), toggle-respect, and crash-recovery persistence round-trip.
