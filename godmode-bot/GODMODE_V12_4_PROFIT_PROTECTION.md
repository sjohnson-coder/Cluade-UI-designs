# GodMode V12.4 — Faster profit protection + chop/No-Trade notes

Your history showed many +$0.10 scratch wins, several -3 to -8 losses, and a few big
winners (+29.52). That's protection that's both too late and too crude. Rebuilt it.

## New: progressive profit protection (ATR-based, fast)
Replaces "break-even at entry+0.10" (which scratched winners) and the late R-only trail.
- **Activates at +0.4 ATR of profit** (not a far R level) — so protection starts FAST,
  even on a wide stop. (ATR trigger fires before your R trigger, so it works without you
  changing settings.)
- **Locks a GROWING fraction of open profit** (35% by default) and **ratchets up** — a
  real winner can no longer fall back to a loss, and small winners exit as small WINS,
  not $0.10 scratches.
- **Trails to ride trends** with a stop that tightens as the move extends (1.0 → 0.5 ATR),
  so big moves like your +29.52 are captured instead of scratched.

Verified locks: +0.4 ATR → +0.09R, +1 ATR → +0.22R, +2 ATR → +0.69R, +3 ATR → +1.38R,
+6 ATR → +3.44R (riding ~2.5 ATR behind).

New controls (Settings → 5c):
- **Protect starts at (ATR)** — lower = faster (try 0.3 for very fast).
- **Profit lock fraction** — higher = lock more (try 0.5 to keep half).
- **Trail starts at (ATR)** — when the ride begins.

## Your other points
- **Dynamic SL ON:** fine now — in chop the recovery monitor says CUT (won't widen); in
  real trends it widens to a risk-capped stop. Losses stay bounded.
- **No-Trade strategy OFF caused the range trading?** Partly — but the real protection is
  the engine's hard gates (chop filter, news, spread, structure), which apply
  REGARDLESS of that toggle. I also made the standby safeguard resolve even when disabled.
  The V12.3 chop filter is what actually stops range trading; you can leave No-Trade on or
  off. For fewer, cleaner entries set AI Strictness to Strict/Sniper (tighter chop filter).

Backend + a Settings card update (bundle rebuilt).
