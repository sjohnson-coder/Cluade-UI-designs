# GodMode V9 — Forecast, Recovery & Discipline Upgrade

This release fixes the exact failures you saw (5 SELLs into a rally, hours-late
history, bare Telegram alerts, Asia not trading) and adds the AI recovery monitor,
dynamic stop, richer alerts, recaps, more settings, and mobile access.

## Do I need to leave MetaTrader 5?  → NO.
The "closed trades take hours to appear" problem is **not** an MT5 limitation. The
history query used `end = now (UTC)`, but brokers stamp deals in **server time**
(usually UTC+2/+3), so a just-closed deal sat *after* the query window and stayed
invisible until UTC caught up — hours later. Fixed by padding the window
(`mt5_bridge.closed_bot_trades`) and reconciling recent closes every cycle.

## The 5-SELLs-in-72-seconds failure → fixed by 3 guards
1. **Post-loss cooldown** — after any loss the bot pauses (default 10 min) to
   re-analyse instead of instantly re-entering.
2. **Loss-streak circuit breaker** — N losses in a row (default 3) hard-pause
   auto-entry (default 60 min) and send an alert to review the market.
3. **Repeat-setup guard** — it will not re-fire the *same* direction that just lost
   until the market actually changes (price moved ≥0.8 ATR **or** the H4/D1 bias now
   agrees). Combined with the V8 HTF-bias gate, this stops selling into a rally.

## AI Recovery Monitor + Dynamic Stop (what you asked for)
The blunt candle-count fast-fail is now gated by a live recovery assessment
(`services/ai_monitor.py`) built from concrete signals — H4/D1 bias agreement, M15
structure side, MACD/RSI posture, adverse move in ATR, and **structural
invalidation** (has the setup's swing broken?):
- **RECOVER** → the trade is held (no premature fast-fail); if you enable
  **Dynamic SL**, the AI widens the stop toward the structural invalidation level…
- **…but never beyond `dynamicSlMaxRiskPct` of equity** (hard cap, default 1%). This
  is the critical guardrail: widening a stop increases risk, so it is OFF by default
  and always capped.
- **CUT** → if the AI judges it can't recover (or structure invalidated), it closes
  immediately, even before the candle counter.
- Honest note: this improves the *quality* of hold-vs-cut decisions, but no monitor
  can truly predict recovery — the capped hard stop is always the backstop.

## Asia (and other off-prime sessions) now trade when enabled
The engine had a separate hard "dead-zone session" block (Asia score 32 < min 55)
that ignored your Session Filter. Now, if you enable a session in Settings, that hard
block becomes a soft (reduced-size scout) block, so Asia actually trades. Toggle:
*Settings → 5b → Trade enabled off-prime sessions*.

## Telegram, rebuilt
- **Entry/close alerts** now include side, entry, SL, **TP1–TP4**, confidence,
  strategy, a brief reason, **and a candlestick chart image** with the levels drawn.
- The meaningless **"WAIT … Lots 0.01"** message is gone (alerts only fire on real
  BUY/SELL fills).
- **WAIT forecast** (optional): periodically sends the *projected* entry/SL/TP + why
  it's waiting + chart, so a flat market is still actionable.
- **Daily & weekly recap** with an equity-curve image + KPIs, at your chosen UTC hour.
- Chart images use `matplotlib` (now in requirements). Without it, alerts still send
  as text — nothing breaks.

## Faster reconciliation
Closed trades now appear effectively immediately: the window fix + a per-cycle
reconciler that catches scalps the loop never saw open, caches them for instant
display, learns them, and counts them toward the loss-streak logic.

## New Settings (Settings page)
- **5b** Trade enabled off-prime sessions.
- **5e** Automation & AI Recovery Monitor: post-loss cooldown, loss-streak pause,
  repeat-setup guard, recovery monitor on/off, HOLD/CUT thresholds, dynamic SL on/off
  + max risk cap.
- **7** Telegram: chart images, WAIT forecast + interval, daily/weekly recap + UTC
  hour, "Send Test Recap" button.
- **12b** Mobile Access: LAN toggle, bind host, port + instructions.

## Mobile access
Run **`start_backend_mobile.bat`** (binds 0.0.0.0, relaxes host/origin checks, prints
your PC IP). On your phone (same Wi-Fi) open `http://<your-PC-IP>:8000` — the UI is
responsive. For access anywhere, put a free tunnel in front (Cloudflare Tunnel or
Tailscale) or rely on the Telegram alerts/recaps. MT5 must keep running on the PC.

## New/changed files
- `backend/services/ai_monitor.py` (new) — recovery assessment + risk-capped SL.
- `backend/services/chart_render.py` (new) — Telegram chart + recap images.
- `backend/services/mt5_bridge.py` — history-window timezone fix; exit-reason labels.
- `backend/services/decision_engine.py` — session-respect relaxation.
- `backend/app.py` — cooldowns/circuit-breaker/repeat-guard, recovery-gated fast-fail,
  dynamic SL, reconciler, rich Telegram + photo, recap/forecast loop, new endpoints.
- `frontend/src/pages/Settings.tsx` + `lib/api.ts` — new controls (bundle rebuilt).
- `start_backend_mobile.bat` (new); `requirements.txt` (+matplotlib).

## Endpoints added
`POST /api/telegram/recap` (test recap+forecast), `GET /api/ai/monitor` (live recovery read).
