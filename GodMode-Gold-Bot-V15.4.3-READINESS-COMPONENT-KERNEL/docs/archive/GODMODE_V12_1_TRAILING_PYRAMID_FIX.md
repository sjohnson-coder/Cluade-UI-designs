# GodMode V12.1 — Why trailing & pyramid weren't working (+ fixes)

## Pyramid — it was structurally impossible to fire. Three real bugs:
1. **Quality label mismatch.** The pyramid engine required quality ∈ {SNIPER, HIGH},
   but the decision engine only ever emits SNIPER / STANDARD / SCOUT — never "HIGH".
   So every STANDARD/SCOUT trade was blocked. → Now accepts STANDARD (final add still
   needs SNIPER).
2. **winStreak was never populated.** The live MT5 position has no winStreak field →
   defaulted to 0 → the "needs 2 recent wins" gate always blocked. → The bot now tracks
   a real win-streak, the gate is 1, and the open position is enriched with it.
3. **Confidence threshold 92% for the first add** vs your ~66–80% balanced confidence →
   never cleared. → Lowered to 78 / 85 / 92 for add 1 / 2 / final.
   Also: the open position now carries beMoved / locked-profit / base-lot so the
   break-even and protection gates evaluate against reality, and pyramid lot-scaling
   (0.01 → 0.02 → 0.03) now actually applies (was always base lot).

   Note: the first pyramid still won't fire until the bot has banked **one win** and the
   base trade is **+0.8R and at break-even** — that's intended anti-martingale safety.

## Trailing — it was being starved of room
V12 put the **broker TP at TP2 (1.8R)**, so trades closed at 1.8R before the trailing
stop (starts at 1.0R) or pyramiding could do anything. → The broker TP is now a backstop
at **TP4 (4R)**; the management loop takes TP1–TP3 partials and **trails the runner out**
before then. Trailing is also now **dynamic** — the stop tightens as profit grows
(mult drops from ~1.2 ATR toward 0.5 ATR past +1R) so big runners give back less.

## Requirements for both to actually run (check these)
- **Live Trading ON + Auto Trading ON + MT5 connected** (management/pyramid don't run in
  dry-run).
- A trade must reach **+0.8R** (break-even), then **+1.0R** (trailing). If fast-fail or
  the recovery monitor closes it first, neither engages.
- Pyramid also needs a **fresh TAKE_TRADE continuation signal** in the same direction
  while the base trade is in profit.
