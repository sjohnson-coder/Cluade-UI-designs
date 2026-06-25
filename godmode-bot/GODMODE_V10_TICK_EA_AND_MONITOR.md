# GodMode V10 — Tick-level EA + Recovery Monitor panel

Two additions on top of V9.

## 1) MQL5 tick-level stop EA (true sub-second management)
`mt5_ea/GodModeTickGuard.mq5` runs INSIDE MetaTrader 5 and reacts on every tick —
the part the Python bot's ~3s poll loop cannot do. It manages only GodMode trades
(magic / comment match) and does, sub-second:
- **Break-even** at a configurable R,
- **ATR trailing** (tightens only),
- a **hard protective floor** (instant catastrophe stop).

**Hybrid bridge (optional):** the Python AI now writes `godmode_control.csv` with
per-ticket `HOLD` / `CUT` directives derived from the AI Recovery Monitor. The EA
reads it every second:
- `HOLD` → EA skips its hard floor so a *recovering* trade isn't cut early (Python
  holds the wider, risk-capped stop),
- `CUT` → EA closes the position on the next tick.

Enable it in **Settings → 5e → MQL5 control-file path** (point it at your
`...\MQL5\Files` folder). Without the path the EA still runs fully autonomously.
Full install steps: `mt5_ea/README_EA_INSTALL.md`.

Division of labour:
| Job | Where | Cadence |
|---|---|---|
| Entries, strategy, HTF bias, recovery verdict | Python bot | ~3 s |
| Break-even, ATR trailing, hard floor | **EA (this file)** | every tick |
| Enforce AI HOLD/CUT | EA via control file | ~1 s |

## 2) AI Recovery Monitor panel (AI Agent page)
The AI Agent page now shows a live **AI Recovery Monitor** card for the open trade:
the verdict (RECOVER / CUT / NEUTRAL), a recovery-score ring, the concrete reasons
(HTF agreement, structure, momentum, adverse-ATR, invalidation), the adverse move in
ATR, and the ticket/direction. It reads `GET /api/ai/monitor` every 5s and shows an
idle state when no trade is open.

## Files
- `mt5_ea/GodModeTickGuard.mq5` (new), `mt5_ea/README_EA_INSTALL.md` (new)
- `backend/app.py` — `_write_mql5_control()` + control lines emitted from the
  management loop; `automation.mql5ControlFilePath` setting.
- `frontend/src/pages/AIAgent.tsx` — recovery panel; `Settings.tsx` — control-file
  path field; `lib/api.ts` — `aiMonitor()` (bundle rebuilt).
