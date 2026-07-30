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


def _has_fresh_management_evidence(decision: dict[str, Any]) -> tuple[bool, str]:
    """Return whether a decision contains current, usable management evidence."""
    if not isinstance(decision, dict) or not decision:
        return False, "missing decision evidence"
    if bool(decision.get("stale")):
        return False, str(decision.get("staleReason") or "decision evidence is stale")
    feats = decision.get("features")
    if not isinstance(feats, dict) or not any(
        key in feats
        for key in (
            "htfDailyBias",
            "computedSide",
            "macd",
            "rsi14",
            "efficiencyRatio",
            "swingLow",
            "swingHigh",
        )
    ):
        return False, "decision evidence is incomplete"
    return True, "fresh"


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


def dynamic_sl_recovery_decision(position: dict[str, Any], decision: dict[str, Any], market: dict[str, Any],
                                 automation_settings: dict[str, Any], atr: float,
                                 max_risk_distance: float) -> dict[str, Any]:
    """Decide whether a losing trade should be cut, held, or given capped recovery room.

    This is the dedicated Dynamic SL Recovery engine:
      • Only considers widening when the trade is genuinely close to its SL / fast-fail zone.
      • Uses evidence from the decision engine, live market cleanliness/news, spread, and structure.
      • Cuts immediately when the original setup is invalidated or a dirty/news condition appears.
      • Proposes a new SL only when recovery probability is strong and the new stop remains inside
        a hard risk cap. It never martingales, never adds to a loser, and never removes the broker stop.
    """
    automation_settings = automation_settings or {}
    evidence_fresh, evidence_reason = _has_fresh_management_evidence(decision)
    if not evidence_fresh:
        recovery = {
            "recoveryScore": 0.0,
            "verdict": "NEUTRAL",
            "invalidated": False,
            "reasons": [evidence_reason],
            "evidenceFresh": False,
        }
        return {
            "action": "HOLD",
            "recovery": recovery,
            "newSL": None,
            "nearSL": False,
            "evidenceFresh": False,
            "reason": f"No risk may be added: {evidence_reason}",
            "reasons": [evidence_reason],
        }
    direction = str(position.get("direction") or position.get("side") or "BUY").upper()
    entry = _f(position.get("entryPrice") or position.get("entry"))
    price = _f(position.get("currentPrice") or position.get("price") or entry)
    sl = _f(position.get("sl"))
    atr = atr or 8.0
    profit_r = _f(position.get("profitR"), 0.0)

    near_sl_atr = max(0.05, _f(automation_settings.get("dynamicSlNearSlAtr"), 0.25))
    near_loss_r = -abs(_f(automation_settings.get("dynamicSlNearLossR"), 0.35))
    spread = _f(market.get("spread"), 0.0)
    max_spread = _f((automation_settings.get("maxSpread") if automation_settings.get("maxSpread") is not None else 0.40), 0.40)
    news_hard_cut = bool(automation_settings.get("dynamicSlNewsHardCut", True))

    dist_to_sl = 999999.0
    if sl:
        dist_to_sl = (price - sl) if direction == "BUY" else (sl - price)
    near_sl = (dist_to_sl >= 0 and dist_to_sl <= near_sl_atr * atr) or profit_r <= near_loss_r

    recovery = assess_recovery(position, decision, atr,
                               _f(automation_settings.get("recoveryHoldThreshold"), 62.0),
                               _f(automation_settings.get("recoveryCutThreshold"), 38.0))
    reasons = list(recovery.get("reasons") or [])

    dirty = bool(market.get("newsBlackout") or market.get("dirtyConditions") or market.get("highImpactNewsNow"))
    spread_spike = bool(spread and max_spread and spread > max_spread)
    if news_hard_cut and dirty and profit_r < 0:
        return {"action": "CUT", "recovery": recovery, "newSL": None, "nearSL": near_sl,
                "reason": "Unexpected news/dirty market while trade is underwater", "reasons": ["News/dirty market active"] + reasons[:3]}
    if spread_spike and profit_r < 0 and recovery.get("verdict") != "RECOVER":
        return {"action": "CUT", "recovery": recovery, "newSL": None, "nearSL": near_sl,
                "reason": f"Spread spike ({spread:.2f}) while recovery evidence is weak", "reasons": ["Spread spike"] + reasons[:3]}
    if recovery.get("invalidated") or recovery.get("verdict") == "CUT":
        return {"action": "CUT", "recovery": recovery, "newSL": None, "nearSL": near_sl,
                "reason": "Setup invalidated / recovery score too weak", "reasons": reasons[:4]}
    if profit_r >= 0:
        return {"action": "HOLD", "recovery": recovery, "newSL": None, "nearSL": False,
                "reason": "Trade is not underwater; use BE/trailing/TP management", "reasons": reasons[:4]}
    if recovery.get("verdict") == "RECOVER":
        min_score = _f(automation_settings.get("dynamicSlMinRecoveryScore"), _f(automation_settings.get("recoveryHoldThreshold"), 62.0))
        if _f(recovery.get("recoveryScore"), 0.0) < min_score:
            return {"action": "HOLD", "recovery": recovery, "newSL": None, "nearSL": near_sl,
                    "reason": f"Recovery score below dynamic SL minimum ({min_score:.0f})", "reasons": reasons[:4]}
        if not near_sl:
            return {"action": "HOLD", "recovery": recovery, "newSL": None, "nearSL": False,
                    "reason": "Recovery likely, but price is not near SL yet", "reasons": reasons[:4]}
        new_sl = compute_widened_sl(position, decision, atr, max_risk_distance)
        if new_sl is None:
            return {"action": "HOLD", "recovery": recovery, "newSL": None, "nearSL": True,
                    "reason": "Recovery likely, but no safe capped SL widening is available", "reasons": reasons[:4]}
        # Don't widen by a meaningless amount.
        if sl and abs(new_sl - sl) < max(0.03, 0.03 * atr):
            return {"action": "HOLD", "recovery": recovery, "newSL": None, "nearSL": True,
                    "reason": "Safe widened SL would not give meaningful extra recovery room", "reasons": reasons[:4]}
        return {"action": "WIDEN", "recovery": recovery, "newSL": new_sl, "nearSL": True,
                "evidenceFresh": True,
                "reason": "High-confidence recovery; widen SL within hard risk cap", "reasons": reasons[:4]}
    return {"action": "HOLD", "recovery": recovery, "newSL": None, "nearSL": near_sl,
            "evidenceFresh": True,
            "reason": "Recovery neutral; classic fast-fail rules remain active", "reasons": reasons[:4]}


def assess_continuation(position: dict[str, Any], decision: dict[str, Any], market: dict[str, Any], atr: float) -> dict[str, Any]:
    """Deterministic open-trade continuation score.

    This deliberately differs from entry confidence. It estimates whether the next
    objective is more likely to be reached before the protected-profit floor using
    only auditable, bounded features. The score is a calibrated-ready deterministic
    score, not a claim of statistical probability until live calibration is complete.
    """
    evidence_fresh, evidence_reason = _has_fresh_management_evidence(decision)
    if not evidence_fresh:
        return {
            "continuationScore": 0.0,
            "invalidated": False,
            "profitR": 0.0,
            "retracementFraction": 0.0,
            "reasons": [evidence_reason],
            "evidenceFresh": False,
        }
    feats = decision.get("features", {}) if isinstance(decision.get("features"), dict) else {}
    direction = str(position.get("direction") or position.get("side") or "").upper()
    entry = _f(position.get("entryPrice") or position.get("entry"))
    price = _f(position.get("currentPrice") or position.get("price") or entry)
    risk = abs(_f(position.get("riskBasis"))) or abs(entry - _f(position.get("originalSL") or position.get("sl"))) or atr or 1.0
    atr = atr or 8.0
    profit_r = ((price-entry)/risk) if direction == "BUY" else ((entry-price)/risk)
    peak_dist = max(0.0, _f(position.get("peakDist")))
    current_dist = max(0.0, (price-entry) if direction == "BUY" else (entry-price))
    retrace_frac = max(0.0, (peak_dist-current_dist)/peak_dist) if peak_dist > 0 else 0.0

    score = 50.0
    reasons: list[str] = []
    invalidated = False
    computed = str(feats.get("computedSide") or decision.get("computedSide") or decision.get("side") or "WAIT").upper()
    htf = str(feats.get("htfDailyBias") or "NEUTRAL").upper()
    hist = _f((feats.get("macd") or {}).get("histogram"))
    rsi = _f(feats.get("rsi14"), 50.0)
    er = _f(feats.get("efficiencyRatio"), 0.5)
    spread = _f(market.get("spread") or market.get("currentSpread"))
    max_spread = _f(market.get("normalSpread") or market.get("spreadMedian"), 0.30)

    if computed == direction:
        score += 16; reasons.append("live structure remains aligned")
    elif computed in {"BUY", "SELL"}:
        score -= 24; reasons.append("live structure opposes the open trade")
    if htf == direction:
        score += 12; reasons.append("higher timeframe supports continuation")
    elif htf in {"BUY", "SELL"}:
        score -= 16; reasons.append("higher timeframe is opposed")
    momentum_ok = (direction == "BUY" and hist > 0 and rsi >= 48) or (direction == "SELL" and hist < 0 and rsi <= 52)
    if momentum_ok:
        score += 12; reasons.append("momentum remains directional")
    elif hist != 0:
        score -= 10; reasons.append("momentum has weakened or reversed")
    if er >= 0.42:
        score += 12; reasons.append("trend efficiency is strong")
    elif er < 0.22:
        score -= 22; reasons.append("market is choppy")
    elif er < 0.30:
        score -= 10; reasons.append("trend efficiency is weak")
    if profit_r >= 1.0:
        score += 8
    elif profit_r >= 0.35:
        score += 4
    if retrace_frac <= 0.35:
        score += 6; reasons.append("retracement remains shallow")
    elif retrace_frac >= 0.75:
        score -= 16; reasons.append("most of the impulse has been retraced")
    elif retrace_frac >= 0.55:
        score -= 8
    if spread and max_spread and spread > max_spread * 1.6:
        score -= 18; reasons.append("spread is abnormally wide")

    swing_low = _f(feats.get("swingLow"))
    swing_high = _f(feats.get("swingHigh"))
    if direction == "BUY" and swing_low and price < swing_low - 0.10*atr:
        invalidated = True; score -= 40; reasons.append("BUY structure invalidated")
    elif direction == "SELL" and swing_high and price > swing_high + 0.10*atr:
        invalidated = True; score -= 40; reasons.append("SELL structure invalidated")
    if bool(market.get("newsBlackout") or market.get("highImpactNewsNow")):
        score -= 20; reasons.append("high-impact news risk active")

    score = max(0.0, min(100.0, round(score, 1)))
    return {
        "continuationScore": score,
        "invalidated": invalidated,
        "profitR": round(profit_r, 3),
        "retracementFraction": round(retrace_frac, 3),
        "reasons": reasons[:6],
        "evidenceFresh": True,
    }


def compute_protected_profit_breathing_stop(position: dict[str, Any], decision: dict[str, Any],
                                             market: dict[str, Any], atr: float,
                                             minimum_locked_r: float = 0.05,
                                             max_giveback_fraction: float = 0.65) -> float | None:
    """Return a deterministic, structure-aware stop that remains net profitable.

    It can only run after break-even/profit protection. It never returns a stop on
    the loss side of entry and caps giveback from the best open profit.
    """
    feats = decision.get("features", {}) if isinstance(decision.get("features"), dict) else {}
    direction = str(position.get("direction") or position.get("side") or "").upper()
    entry = _f(position.get("entryPrice") or position.get("entry"))
    price = _f(position.get("currentPrice") or position.get("price"))
    current_sl = _f(position.get("sl"))
    risk = abs(_f(position.get("riskBasis"))) or abs(entry-current_sl) or atr or 1.0
    peak_dist = max(0.0, _f(position.get("peakDist")))
    if direction not in {"BUY", "SELL"} or not entry or not price or peak_dist <= 0:
        return None
    atr = atr or 8.0
    keep_fraction = max(0.0, min(0.95, 1.0-max(0.0, min(0.90, max_giveback_fraction))))
    cost_buffer = max(0.01, _f(market.get("spread"), 0.0) + _f(market.get("slippage"), 0.0))
    min_profit_dist = max(minimum_locked_r*risk, peak_dist*keep_fraction, cost_buffer)
    profit_limit = entry + min_profit_dist if direction == "BUY" else entry - min_profit_dist

    swing_low = _f(feats.get("swingLow"))
    swing_high = _f(feats.get("swingHigh"))
    # Conservative deterministic Q90 proxy until the offline quantile model is calibrated.
    er = _f(feats.get("efficiencyRatio"), 0.35)
    retracement_atr = 0.75 if er >= 0.42 else (0.55 if er >= 0.30 else 0.35)
    forecast_stop = price - retracement_atr*atr if direction == "BUY" else price + retracement_atr*atr
    structure_stop = (swing_low-0.10*atr) if direction == "BUY" and swing_low else forecast_stop
    if direction == "SELL" and swing_high:
        structure_stop = swing_high+0.10*atr

    if direction == "BUY":
        proposed = max(profit_limit, min(forecast_stop, structure_stop))
        proposed = min(proposed, price-0.05*atr)
        if proposed <= entry or (current_sl and proposed >= current_sl):
            return None
    else:
        proposed = min(profit_limit, max(forecast_stop, structure_stop))
        proposed = max(proposed, price+0.05*atr)
        if proposed >= entry or (current_sl and proposed <= current_sl):
            return None
    return round(proposed, 2)
