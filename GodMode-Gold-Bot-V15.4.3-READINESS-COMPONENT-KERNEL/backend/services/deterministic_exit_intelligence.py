from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    use_period = max(1, min(int(period), len(values)))
    alpha = 2.0 / (use_period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _directional_metrics(rows: list[dict[str, Any]], side: str, lookback: int = 8) -> dict[str, float | int | bool]:
    closes = [_f(row.get("close")) for row in rows if _f(row.get("close")) > 0]
    if len(closes) < 3:
        return {"efficiency": 0.0, "signed_move": 0.0, "flips": 0, "aligned": False, "ema_slope": 0.0}
    sample = closes[-max(3, min(lookback, len(closes))):]
    sign = 1.0 if side == "BUY" else -1.0
    signed_move = (sample[-1] - sample[0]) * sign
    path = sum(abs(sample[index] - sample[index - 1]) for index in range(1, len(sample)))
    efficiency = max(0.0, signed_move) / max(path, 1e-9)
    directional_deltas = [(sample[index] - sample[index - 1]) * sign for index in range(1, len(sample))]
    flips = sum(1 for index in range(1, len(directional_deltas)) if directional_deltas[index] * directional_deltas[index - 1] < 0)
    ema_now = _ema(closes[-40:], 20)
    ema_prev = _ema(closes[:-1][-40:], 20) if len(closes) > 3 else ema_now
    ema_slope = (ema_now - ema_prev) * sign
    aligned = signed_move > 0 and ema_slope >= -1e-9
    return {
        "efficiency": round(efficiency, 4),
        "signed_move": round(signed_move, 6),
        "flips": flips,
        "aligned": aligned,
        "ema_slope": round(ema_slope, 6),
    }


def _predictor_support(state: dict[str, Any] | None, side: str) -> tuple[float, bool, bool]:
    state = state if isinstance(state, dict) else {}
    state_side = str(state.get("side") or "").upper()
    stage = str(state.get("stage") or state.get("state") or "WATCH").upper()
    probability = _clamp(_f(state.get("probability")), 0.0, 1.0)
    same = state_side == side and stage in {"INTENT", "PROBE", "CONFIRMED"}
    opposite = state_side in {"BUY", "SELL"} and state_side != side and stage in {"INTENT", "PROBE", "CONFIRMED"}
    return probability, same, opposite


@dataclass(frozen=True)
class ExitIntelligenceDecision:
    phase: str
    action: str
    continuation_score: float
    invalidated: bool
    protection_armed: bool
    allow_widen: bool
    recommended_sl: float | None
    max_giveback_fraction: float
    trail_atr: float
    profit_r: float
    peak_r: float
    raw_peak_r: float
    qualified_peak_r: float
    range_expansion_atr: float
    retracement_fraction: float
    recent_efficiency: float
    recent_flips: int
    m5_aligned: bool
    m15_aligned: bool
    predictor_support: float
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        return payload


def evaluate_exit_intelligence(
    *,
    position: dict[str, Any],
    market: dict[str, Any] | None,
    atr: float,
    m5_candles: list[dict[str, Any]],
    m15_candles: list[dict[str, Any]],
    decision: dict[str, Any] | None,
    intent_state: dict[str, Any] | None,
    impulse_state: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
) -> ExitIntelligenceDecision:
    """Return an auditable deterministic exit/stop-management decision.

    The engine deliberately separates *entry confidence* from *open-trade continuation*.
    It never widens on missing context, never predicts certainty, and never permits a
    protected winner to move back through entry.  Strong, clean trend legs receive a
    wider structure-aware runner budget; invalidated or opposing legs are tightened/cut.
    """
    cfg = config or {}
    market = market if isinstance(market, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    side = str(position.get("direction") or position.get("side") or "").upper()
    entry = _f(position.get("entryPrice") or position.get("entry"))
    price = _f(position.get("currentPrice") or position.get("price") or market.get("price"))
    sl = _f(position.get("sl"))
    risk = abs(_f(position.get("riskBasis") or position.get("initialRisk")))
    atr_value = _f(atr)
    raw_peak_dist = max(0.0, _f(position.get("rawPeakDist") or position.get("peakDist")))
    qualified_peak_present = "qualifiedPeakDist" in position
    qualified_peak_dist = max(0.0, _f(position.get("qualifiedPeakDist")))
    qualified_peak_enabled = bool(cfg.get("qualifiedPeakEnabled", False)) and qualified_peak_present
    stage = str(position.get("stage") or position.get("progressiveStage") or "NORMAL").upper()
    if side not in {"BUY", "SELL"} or entry <= 0 or price <= 0 or risk <= 0 or atr_value <= 0 or len(m5_candles) < 8:
        return ExitIntelligenceDecision(
            "SAFE_HOLD", "HOLD", 0.0, False, False, False, None,
            _clamp(_f(cfg.get("baseGivebackFraction"), 0.45), 0.20, 0.80),
            _clamp(_f(cfg.get("baseTrailAtr"), 0.65), 0.25, 1.50),
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, False, False, 0.0,
            ("INSUFFICIENT_FRESH_CONTEXT",),
        )

    sign = 1.0 if side == "BUY" else -1.0
    profit_dist = (price - entry) * sign
    profit_r = profit_dist / risk
    raw_peak_dist = max(raw_peak_dist, max(0.0, profit_dist))
    if not qualified_peak_enabled:
        qualified_peak_dist = raw_peak_dist
    raw_peak_r = raw_peak_dist / risk
    qualified_peak_r = qualified_peak_dist / risk
    peak_r = raw_peak_r
    retracement = max(0.0, raw_peak_dist - max(0.0, profit_dist)) / max(raw_peak_dist, 1e-9) if raw_peak_dist > 0 else 0.0

    last_row = m5_candles[-1] if m5_candles else {}
    last_range = max(0.0, _f(last_row.get("high")) - _f(last_row.get("low")))
    range_expansion_atr = last_range / atr_value if atr_value > 0 else 0.0

    m5_metrics = _directional_metrics(m5_candles, side, int(_f(cfg.get("recentBars"), 8)))
    m15_metrics = _directional_metrics(m15_candles, side, int(_f(cfg.get("m15Bars"), 7))) if len(m15_candles) >= 5 else {"efficiency": 0.0, "signed_move": 0.0, "flips": 0, "aligned": False, "ema_slope": 0.0}
    m5_aligned = bool(m5_metrics["aligned"])
    m15_aligned = bool(m15_metrics["aligned"])
    recent_efficiency = _f(m5_metrics["efficiency"])
    recent_flips = int(m5_metrics["flips"])

    intent_prob, intent_same, intent_opposite = _predictor_support(intent_state, side)
    impulse_prob, impulse_same, impulse_opposite = _predictor_support(impulse_state, side)
    predictor_support = max(intent_prob if intent_same else 0.0, impulse_prob if impulse_same else 0.0)
    predictor_opposition = max(intent_prob if intent_opposite else 0.0, impulse_prob if impulse_opposite else 0.0)

    features = decision.get("features") if isinstance(decision.get("features"), dict) else {}
    computed_side = str(features.get("computedSide") or decision.get("computedSide") or decision.get("side") or "WAIT").upper()
    htf_side = str(features.get("htfDailyBias") or "NEUTRAL").upper()
    decision_same = computed_side == side
    decision_opposite = computed_side in {"BUY", "SELL"} and computed_side != side
    htf_same = htf_side == side
    htf_opposite = htf_side in {"BUY", "SELL"} and htf_side != side

    score = 50.0
    reasons: list[str] = []
    if m5_aligned:
        score += 18.0; reasons.append("M5_RECENT_LEG_ALIGNED")
    else:
        score -= 15.0; reasons.append("M5_RECENT_LEG_NOT_ALIGNED")
    if recent_efficiency >= 0.68 and recent_flips <= 1:
        score += 16.0; reasons.append("CLEAN_HIGH_EFFICIENCY_LEG")
    elif recent_efficiency >= 0.48 and recent_flips <= 2:
        score += 9.0; reasons.append("USABLE_DIRECTIONAL_LEG")
    elif recent_efficiency < 0.24 or recent_flips >= 4:
        score -= 18.0; reasons.append("CHOP_OR_FLIP_HEAVY_LEG")
    if m15_aligned:
        score += 12.0; reasons.append("M15_ALIGNED")
    elif len(m15_candles) >= 5:
        score -= 8.0; reasons.append("M15_NOT_ALIGNED")
    if predictor_support >= 0.82:
        score += 15.0; reasons.append("PREDICTOR_CONFIRMED_CONTINUATION")
    elif predictor_support >= 0.66:
        score += 9.0; reasons.append("PREDICTOR_SUPPORT")
    if predictor_opposition >= _f(cfg.get("oppositeInvalidationProbability"), 0.82):
        score -= 38.0; reasons.append("OPPOSITE_PREDICTOR_CONFIRMED")
    elif predictor_opposition >= 0.70:
        score -= 20.0; reasons.append("OPPOSITE_PREDICTOR_RISK")
    if decision_same:
        score += 8.0; reasons.append("DECISION_STRUCTURE_ALIGNED")
    elif decision_opposite:
        score -= 18.0; reasons.append("DECISION_STRUCTURE_OPPOSED")
    if htf_same:
        score += 7.0; reasons.append("HTF_SUPPORT")
    elif htf_opposite:
        score -= 9.0; reasons.append("HTF_OPPOSITION")
    if retracement <= 0.35:
        score += 7.0; reasons.append("SHALLOW_RETRACEMENT")
    elif retracement >= 0.82:
        score -= 22.0; reasons.append("DEEP_WINNER_GIVEBACK")
    elif retracement >= 0.62:
        score -= 11.0; reasons.append("MATERIAL_RETRACEMENT")
    if peak_r >= 1.0:
        score += 7.0
    elif peak_r >= 0.55:
        score += 4.0

    spread = _f(market.get("spread") or market.get("currentSpread"))
    normal_spread = _f(market.get("normalSpread") or market.get("spreadMedian"), 0.0)
    if spread > 0 and normal_spread > 0 and spread > normal_spread * _f(cfg.get("spreadSpikeMultiple"), 1.8):
        score -= 18.0; reasons.append("SPREAD_SPIKE")

    recent_rows = m5_candles[-max(5, min(8, len(m5_candles))):]
    recent_low = min(_f(row.get("low"), _f(row.get("close"))) for row in recent_rows)
    recent_high = max(_f(row.get("high"), _f(row.get("close"))) for row in recent_rows)
    structure_buffer = max(0.03, _f(cfg.get("structureInvalidationAtr"), 0.12)) * atr_value
    structure_invalidated = (side == "BUY" and price < recent_low - structure_buffer) or (side == "SELL" and price > recent_high + structure_buffer)
    invalidated = bool(structure_invalidated or predictor_opposition >= _f(cfg.get("oppositeInvalidationProbability"), 0.82))
    if structure_invalidated:
        score -= 35.0; reasons.append("RECENT_M5_STRUCTURE_INVALIDATED")

    raw_score = _clamp(score, 0.0, 100.0)
    previous_score = _f(previous.get("continuation_score") or previous.get("continuationScore"), raw_score)
    # Preserve responsiveness to invalidation; smooth only ordinary one-cycle noise.
    continuation_score = raw_score if invalidated else _clamp(previous_score * 0.40 + raw_score * 0.60, 0.0, 100.0)

    runner_threshold = _f(cfg.get("runnerScore"), 70.0)
    confirmed_threshold = _f(cfg.get("confirmedScore"), 58.0)
    runner_peak_r = _f(cfg.get("runnerMinPeakR"), 0.55)
    previous_phase = str(previous.get("phase") or "").upper()
    age_seconds = max(0.0, _f(position.get("ageSeconds")))
    launch_enabled = bool(cfg.get("launchPhaseEnabled", True))
    launch_max_age = max(10.0, _f(cfg.get("launchMaxAgeSeconds"), 150.0))
    launch_support = predictor_support >= _f(cfg.get("launchPredictorSupport"), 0.74)
    launch_leg = (
        m5_aligned
        and recent_efficiency >= _f(cfg.get("launchMinEfficiency"), 0.58)
        and recent_flips <= int(_f(cfg.get("launchMaxFlips"), 2))
    )
    launch_active = bool(
        launch_enabled
        and age_seconds <= launch_max_age
        and not invalidated
        and stage != "PROBE"
        and (launch_support or launch_leg)
        and qualified_peak_r < _f(cfg.get("launchExitQualifiedPeakR"), runner_peak_r)
    )
    if invalidated or continuation_score < _f(cfg.get("defensiveScore"), 42.0):
        phase = "DEFENSIVE"
    elif previous_phase == "RUNNER" and continuation_score >= _f(cfg.get("runnerHoldScore"), 58.0) and peak_r >= runner_peak_r:
        phase = "RUNNER"
    elif launch_active:
        phase = "LAUNCH"
    elif continuation_score >= runner_threshold and peak_r >= runner_peak_r and stage != "PROBE":
        phase = "RUNNER"
    elif continuation_score >= confirmed_threshold and peak_r >= _f(cfg.get("confirmedMinPeakR"), 0.30):
        phase = "CONFIRMED"
    else:
        phase = "PROBE" if stage == "PROBE" else "DEVELOPING"

    base_giveback = _clamp(_f(cfg.get("baseGivebackFraction"), 0.45), 0.20, 0.80)
    if phase == "LAUNCH":
        max_giveback = max(base_giveback, _f(cfg.get("launchGivebackFraction"), 0.82))
        trail_atr = _f(cfg.get("launchTrailAtr"), 1.20)
    elif phase == "RUNNER":
        max_giveback = max(base_giveback, _f(cfg.get("runnerGivebackFraction"), 0.64))
        if recent_efficiency >= 0.72 and recent_flips <= 1 and m15_aligned:
            max_giveback = max(max_giveback, _f(cfg.get("strongRunnerGivebackFraction"), 0.70))
        if peak_r >= 1.5:
            max_giveback = max(max_giveback, _f(cfg.get("matureRunnerGivebackFraction"), 0.72))
        trail_atr = _f(cfg.get("runnerTrailAtr"), 0.85)
        if recent_efficiency >= 0.70:
            trail_atr += 0.15
        if peak_r >= 1.5:
            trail_atr += 0.10
    elif phase == "CONFIRMED":
        max_giveback = max(base_giveback, _f(cfg.get("confirmedGivebackFraction"), 0.54))
        trail_atr = _f(cfg.get("confirmedTrailAtr"), 0.68)
    elif phase == "DEFENSIVE":
        max_giveback = min(base_giveback, _f(cfg.get("defensiveGivebackFraction"), 0.28))
        trail_atr = _f(cfg.get("defensiveTrailAtr"), 0.28)
    else:
        max_giveback = base_giveback
        trail_atr = _f(cfg.get("developingTrailAtr"), 0.65)
    if (
        bool(cfg.get("volatilityExpansionTrailEnabled", True))
        and phase in {"LAUNCH", "RUNNER"}
        and range_expansion_atr >= _f(cfg.get("volatilityExpansionThresholdAtr"), 1.50)
    ):
        expansion_fraction = _clamp(_f(cfg.get("volatilityExpansionTrailFraction"), 0.35), 0.10, 0.75)
        expansion_trail = range_expansion_atr * expansion_fraction
        if expansion_trail > trail_atr:
            trail_atr = expansion_trail
            reasons.append("VOLATILITY_EXPANSION_ROOM")
        max_giveback = max(max_giveback, _f(cfg.get("volatilityExpansionGivebackFraction"), 0.80))

    max_giveback = _clamp(max_giveback, 0.20, _f(cfg.get("absoluteMaxGiveback"), 0.85))
    trail_atr = _clamp(trail_atr, 0.20, _f(cfg.get("absoluteMaxTrailAtr"), 2.00))

    protection_peak_r = qualified_peak_r if qualified_peak_enabled else peak_r
    if phase == "LAUNCH":
        protection_armed = protection_peak_r >= _f(cfg.get("launchProtectionPeakR"), 1.20)
    else:
        protection_armed = protection_peak_r >= _f(cfg.get("minPeakRForProtection"), 0.55)
    recommended_sl: float | None = None
    allow_widen = False
    action = "HOLD"

    if phase == "DEFENSIVE":
        if invalidated and profit_r <= _f(cfg.get("cutProfitR"), 0.0):
            action = "CUT"
        elif protection_armed and profit_dist > 0:
            keep_r = max(_f(cfg.get("defensiveMinimumLockR"), 0.20), peak_r * (1.0 - max_giveback))
            candidate = entry + sign * keep_r * risk
            recommended_sl = round(candidate, 3)
            action = "PROTECT"
    elif phase == "LAUNCH":
        # A fresh expansion is allowed to breathe. Only a cost-protected break-even
        # stop is permitted until a peak has persisted long enough to qualify.
        if profit_r >= _f(cfg.get("launchBreakEvenR"), 1.20):
            cost_buffer = max(_f(cfg.get("minimumCostBuffer"), 0.03), spread + _f(market.get("slippage"), 0.0))
            candidate = entry + sign * cost_buffer
            recommended_sl = round(candidate, 3)
            if (side == "BUY" and (sl <= 0 or recommended_sl > sl + 0.01)) or (side == "SELL" and (sl <= 0 or recommended_sl < sl - 0.01)):
                action = "PROTECT"
    elif protection_armed and phase in {"CONFIRMED", "RUNNER"}:
        cost_buffer = max(_f(cfg.get("minimumCostBuffer"), 0.03), spread + _f(market.get("slippage"), 0.0))
        min_lock_r = _f(cfg.get("runnerMinimumLockR"), 0.08) if phase == "RUNNER" else _f(cfg.get("confirmedMinimumLockR"), 0.12)
        protection_peak_dist = qualified_peak_dist if qualified_peak_enabled else raw_peak_dist
        min_profit_dist = max(cost_buffer, min_lock_r * risk, protection_peak_dist * (1.0 - max_giveback))
        floor_stop = entry + sign * min_profit_dist
        structure_window = m5_candles[-max(3, min(int(_f(cfg.get("structureBars"), 5)), len(m5_candles))):]
        if side == "BUY":
            structure_stop = min(_f(row.get("low"), price) for row in structure_window) - _f(cfg.get("structureTrailBufferAtr"), 0.08) * atr_value
            volatility_stop = price - trail_atr * atr_value
            candidate = max(floor_stop, min(structure_stop, volatility_stop))
            candidate = min(candidate, price - max(0.02, 0.04 * atr_value))
            recommended_sl = round(candidate, 3) if candidate > entry else None
            if recommended_sl is not None and sl > 0 and recommended_sl < sl - 0.01:
                allow_widen = True
                action = "BREATHE"
            elif recommended_sl is not None and (sl <= 0 or recommended_sl > sl + 0.01):
                action = "PROTECT"
        else:
            structure_stop = max(_f(row.get("high"), price) for row in structure_window) + _f(cfg.get("structureTrailBufferAtr"), 0.08) * atr_value
            volatility_stop = price + trail_atr * atr_value
            candidate = min(floor_stop, max(structure_stop, volatility_stop))
            candidate = max(candidate, price + max(0.02, 0.04 * atr_value))
            recommended_sl = round(candidate, 3) if candidate < entry else None
            if recommended_sl is not None and sl > 0 and recommended_sl > sl + 0.01:
                allow_widen = True
                action = "BREATHE"
            elif recommended_sl is not None and (sl <= 0 or recommended_sl < sl - 0.01):
                action = "PROTECT"

    if action == "BREATHE" and phase != "RUNNER":
        # Ordinary confirmed trades may protect, but only true runners can deliberately
        # loosen an already profitable broker stop.
        action = "HOLD"
        recommended_sl = None
        allow_widen = False
    if action == "BREATHE" and (profit_dist <= 0 or sl <= 0):
        action = "HOLD"
        recommended_sl = None
        allow_widen = False

    reasons.insert(0, f"PHASE_{phase}")
    reasons.append(f"SCORE_{continuation_score:.1f}")
    reasons.append(f"GIVEBACK_{max_giveback:.2f}")
    reasons.append(f"TRAIL_{trail_atr:.2f}_ATR")
    return ExitIntelligenceDecision(
        phase=phase,
        action=action,
        continuation_score=round(continuation_score, 1),
        invalidated=invalidated,
        protection_armed=protection_armed,
        allow_widen=allow_widen,
        recommended_sl=recommended_sl,
        max_giveback_fraction=round(max_giveback, 3),
        trail_atr=round(trail_atr, 3),
        profit_r=round(profit_r, 3),
        peak_r=round(peak_r, 3),
        raw_peak_r=round(raw_peak_r, 3),
        qualified_peak_r=round(qualified_peak_r, 3),
        range_expansion_atr=round(range_expansion_atr, 3),
        retracement_fraction=round(retracement, 3),
        recent_efficiency=round(recent_efficiency, 3),
        recent_flips=recent_flips,
        m5_aligned=m5_aligned,
        m15_aligned=m15_aligned,
        predictor_support=round(predictor_support, 3),
        reason_codes=tuple(reasons[:14]),
    )
