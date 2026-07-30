# GodMode V12.24 — UI batch: notifications, CSV, AI Agent, Returns Calendar, Mac fix

A focused pass through everything you flagged. All twelve items, done and verified in the browser.

## Fixes & upgrades

1. **Notification bell pops up again.** The condensed top bar (laptop widths) was clipping the
   dropdown with `overflow:hidden`. It now lets the popup escape downward and is responsive on phones.
2. **Trades → Export is now a real CSV file** (was JSON). One click → `godmode_trades.csv`.
3. **AI Agent top cards are responsive.** Smaller value font + wrapping, so "Waiting for MT5" /
   "TAKE SELL" never overflow to the right at any width.
4. **AI Agent bottom layout.** "Why the AI is NOT trading" + "Performance Adaptation" are now **2 per
   row**, and **"Journal of AI Decisions" spans full width** below to fill the space. (Also: status
   tags like **BLOCK** no longer wrap to "BLO​CK".)
5. **Analytics → Returns Calendar (redesigned).** A proper **Mon–Fri calendar**, week by week,
   colour-graded by P&L, **full-width** to fill the row, with **Top Strategies moved up** next to the
   equity curve. **Click any day** → it tells you *what the AI detected that day* and the *best
   optimisation for the next day* — all computed from that day's real trades.
6. **Journal search box redesigned.** It's now a normal labelled field that lines up perfectly with
   the other filters at every width — no more distortion.
7. **Settings → per-mode confluence.** You can now set the **Min Confluence (of 12)** required for
   **each** strict mode (Relaxed/Balanced/Strict/Sniper) independently. The active mode applies now;
   the rest are saved for when you switch.
8. **Backtest results persist.** Like the Strategy Lab, a finished backtest/validate is restored when
   you come back to the tab — even if you clicked away before it finished, or reloaded the page.
9. **Returns insight** (see #5): per-day "what the AI detected + best optimisation for the next day."
10. **macOS one-click actually installs & runs** like `start_all.bat`. The launcher now: finds Python
    across Homebrew/python.org locations, installs the full requirements and **falls back to the core
    packages** if the optional `matplotlib` can't build on the newest Python, **self-heals** the
    executable bit and download "quarantine" flag, and verifies the app imports before launching.
11. **Run & manage guide:** `HOW_TO_RUN_AND_MANAGE.md` — start (Win/Mac), connect MT5, the safety
    ladder, day-to-day management, tuning, alerts, troubleshooting.
12. **Settings → "12a. How to get your URLs, keys & mobile access":** step-by-step for the
    news/economic-calendar URL, DXY/US10Y feeds, the AI-generator key (Claude/ChatGPT), the Strategy-
    Lab feed URL, and mobile/Tailscale access — with example JSON shapes.

## Validation
Frontend builds clean · backend imports & byte-compiles · engine per-mode confluence unit-tested ·
returns-calendar + day-insight helpers tested · backtest persistence verified end-to-end · notification
popup, AI Agent layout, Returns Calendar, Journal search and Settings all verified in a headless browser
at 1280/1518/1600 widths.
