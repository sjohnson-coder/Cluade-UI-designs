# GodMode V12.25 — Precise cost gate + honest "blocked preview" alerts

Two fixes from the range/chop + cost analysis, plus a transparency note on strategy selection.

## 1. Cost discipline now measures cost ÷ the trade's actual stop (R), and counts commission

Before, the gate compared **spread ÷ ATR**. But the number that actually subtracts from your
expectancy is **(spread + commission) ÷ stop distance (R)** — and your stops aren't always 1 ATR, so
the ATR proxy over-penalised wide-stop trades and under-counted tight-stop ones.

Live example from your own forecasts:
- **9:04 SELL** (stop = 1.55× ATR): old gate read **6.6% of ATR → blocked**, but the true cost was only
  **4.25% of its risk → now correctly allowed.**
- **8:34 SELL** (stop = 0.82× ATR): **6.6% of R → still blocked** (cost really is too high vs the risk).

New behaviour:
- Gate = `(spread + commission) ÷ |entry − SL|` vs a **Max cost ÷ R** cap (default **0.05**).
- **Commission is included** — set your broker's round-trip commission (price terms) in Settings; an
  ECN gold commission of ~$0.10 will, for instance, tip the 9:04 trade back to blocked (5.82% of R).
- All three knobs are now exposed: **Settings → 4. AI Strictness → Cost discipline** (toggle,
  Max cost ÷ R, Commission / trade). The old `maxSpreadAtrFrac` setting still works (back-compat).

This is **more honest, not looser** — it won't manufacture edge. The real levers remain a tighter
spread (ECN/raw) and/or a higher timeframe.

## 2. "Waiting" Telegram forecasts are now clearly marked BLOCKED — preview only

A standby forecast used to show **"Confidence: 85%"** + a full TP ladder next to **"No-Trade /
Standby"**, which read like the bot was refusing an obvious trade. Now it:
- leads with **"Forecast — BLOCKED (preview only, not a trade)"**,
- relabels the number as **"Signal quality (not a trade signal)"**,
- says plainly: *"🚫 NOT TRADING — the bot has a {BUY/SELL} bias here but is standing aside ({regime}).
  Blocked by: …"*, and shows **"Standing aside · {regime}"** instead of the confusing strategy name.

## On "is it picking the best strategy?" — yes, but with a regime gate above it

The engine **does** score every enabled strategy each bar (regime fit + live win-rate + expectancy +
session fit) and picks the highest — a real ensemble vote, not first-match. **But** when the regime
classifier labels the tape a *wait* regime (e.g. **Compression / Wait** on a thin, low-volatility
Sunday open — exactly this morning), it short-circuits to **No-Trade / Standby** before ranking, and
the chop + cost gates veto on top. So this morning it wasn't choosing among your strategies — it was
deliberately standing aside in a regime that backtests negative. The directionally-correct SELLs you
saw were the *bias*, correctly held back, not "missed" tradable edge. Loosening those gates re-opens
the losers documented in `EDGE_DIAGNOSIS.md`.
