"""GodMode AI live-trade recovery monitor.

This powers the behaviour requested: instead of a blunt candle-count fast-fail, the
AI continuously assesses an open, underwater trade and decides whether it is likely
to RECOVER (hold, optionally give it structural room) or is genuinely invalidated
(CUT now, even before the fast-fail counter). It is a *probability tilt* built from
concrete, defensible signals — not a crystal ball — so a hard risk cap on any stop
adjustment is always the backstop.

Signals used (all already computed by the decision engine each cycle):
  • Higher-timeframe (H4/D1) bias agreement with the trade direction.
  • M15 EMA-structure side vs the trade direction.
  • MACD histogram sign and RSI posture vs the trade direction.
  • Depth of the adverse excursion measured in ATR (noise vs structural break).
  • Structural invalidation: has price closed beyond the swing that defined the setup?
"""
from __future__ import annotations

from typing import Any


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def assess_recovery(position: dict[str, Any], decision: dict[str, Any], atr: float,
                    hold_threshold: float = 62.0, cut_threshold: float = 38.0) -> dict[str, Any]:
    """Return {recoveryScore, verdict, invalidated, reasons} for an underwater trade."""
    feats = decision.get("features", {}) if isinstance(decision.get("features"), dict) else {}
    direction = str(position.get("direction") or position.get("side") or "BUY").upper()
    entry = _f(position.get("entryPrice"))
    price = _f(position.get("currentPrice") or position.get("price") or entry)
    atr = atr or 8.0

    score = 50.0
    reasons: list[str] = []
    invalidated = False

    # 1) Higher-timeframe bias agreement
    htf = str(feats.get("htfDailyBias") or "NEUTRAL").upper()
    if htf == direction:
        score += 20; reasons.append(f"HTF daily/H4 bias ({htf}) still supports the trade")
    elif htf not in ("NEUTRAL", ""):
        score -= 26; reasons.append(f"HTF daily/H4 bias flipped against the trade ({htf})")

    # 2) M15 structure side
    cs = str(feats.get("computedSide") or "WAIT").upper()
    if cs == direction:
        score += 14; reasons.append("M15 structure still aligned with the trade")
    elif cs not in ("WAIT", ""):
        score -= 20; reasons.append(f"M15 structure flipped to {cs}")

    # 3) Momentum (MACD histogram + RSI) vs trade direction
    hist = _f((feats.get("macd") or {}).get("histogram"))
    if (direction == "BUY" and hist > 0) or (direction == "SELL" and hist < 0):
        score += 10; reasons.append("MACD momentum favours the trade")
    elif hist != 0:
        score -= 10; reasons.append("MACD momentum is against the trade")
    rsi = _f(feats.get("rsi14"), 50)
    if direction == "BUY":
        score += 8 if rsi >= 50 else (-8 if rsi < 40 else 0)
    else:
        score += 8 if rsi <= 50 else (-8 if rsi > 60 else 0)

    # 4) Depth of adverse excursion in ATR (noise vs structural)
    adverse = (entry - price) if direction == "BUY" else (price - entry)
    adverse_atr = adverse / atr if atr else 0.0
    if adverse_atr <= 0:
        score += 6; reasons.append("Position is not underwater on close basis")
    elif adverse_atr < 0.8:
        score += 8; reasons.append(f"Adverse move shallow ({adverse_atr:.2f} ATR) — likely noise")
    elif adverse_atr > 2.0:
        score -= 16; reasons.append(f"Deep adverse move ({adverse_atr:.2f} ATR)")

    # 4b) Chop CAP — in a low-efficiency range, EMA "alignment" is noise and there is no
    # trend to recover into, so cap the score below the HOLD threshold. This stops the
    # false RECOVER reads that held losers (e.g. to -1.24R) inside a sideways range.
    er = _f(feats.get("efficiencyRatio"), 0.5)
    if er < 0.22:
        score = min(score, 35.0); reasons.append(f"Choppy range (efficiency {er:.2f}) — no trend to recover into; do not hold")
    elif er < 0.32:
        score = min(score, 52.0); reasons.append(f"Low trend efficiency ({er:.2f}) — choppy, don't add risk holding")

    # 5) Structural invalidation — the swing that defined the setup has broken
    swing_low = _f(feats.get("swingLow"))
    swing_high = _f(feats.get("swingHigh"))
    if direction == "BUY" and swing_low and price < swing_low - 0.10 * atr:
        invalidated = True; score -= 35; reasons.append("Setup swing-low broken — structure invalidated")
    elif direction == "SELL" and swing_high and price > swing_high + 0.10 * atr:
        invalidated = True; score -= 35; reasons.append("Setup swing-high broken — structure invalidated")

    score = max(0.0, min(100.0, round(score, 1)))
    if invalidated:
        verdict = "CUT"
    elif score >= hold_threshold:
        verdict = "RECOVER"
    elif score <= cut_threshold:
        verdict = "CUT"
    else:
        verdict = "NEUTRAL"
    return {"recoveryScore": score, "verdict": verdict, "invalidated": invalidated, "reasons": reasons[:4], "adverseAtr": round(adverse_atr, 2)}


def compute_widened_sl(position: dict[str, Any], decision: dict[str, Any], atr: float,
                       max_risk_distance: float) -> float | None:
    """Propose a SL at the setup's structural invalidation, HARD-CAPPED by max risk.

    Returns a new SL only if it gives the trade more room (further from price) AND
    stays within ``max_risk_distance`` from entry. Never exceeds the risk cap, never
    moves the SL closer (that is the trailing logic's job). Returns None if no safe
    widening is possible.
    """
    feats = decision.get("features", {}) if isinstance(decision.get("features"), dict) else {}
    direction = str(position.get("direction") or "BUY").upper()
    entry = _f(position.get("entryPrice"))
    sl = _f(position.get("sl"))
    atr = atr or 8.0
    if not entry or max_risk_distance <= 0:
        return None
    swing_low = _f(feats.get("swingLow"))
    swing_high = _f(feats.get("swingHigh"))
    if direction == "BUY":
        structural = (swing_low - 0.15 * atr) if swing_low else (entry - max_risk_distance)
        capped = max(structural, entry - max_risk_distance)   # never risk more than the cap
        # only widen (move SL DOWN, further from price) relative to the current stop
        if sl and capped >= sl:
            return None
        return round(capped, 2)
    else:
        structural = (swing_high + 0.15 * atr) if swing_high else (entry + max_risk_distance)
        capped = min(structural, entry + max_risk_distance)
        if sl and capped <= sl:
            return None
        return round(capped, 2)
