from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_account_mode(
    mode: Any,
    *,
    demo_mode: int = 0,
    contest_mode: int = 1,
    real_mode: int = 2,
) -> dict[str, Any]:
    try:
        normalized = int(mode) if mode is not None else None
    except (TypeError, ValueError):
        normalized = None
    if normalized == int(demo_mode):
        name, account_type = "DEMO", "demo"
    elif normalized == int(contest_mode):
        name, account_type = "CONTEST", "contest"
    elif normalized == int(real_mode):
        name, account_type = "REAL", "real"
    else:
        name, account_type = "UNKNOWN", "unknown"
    return {
        "accountTradeMode": normalized,
        "accountTradeModeName": name,
        "accountType": account_type,
        "demo": account_type == "demo",
        "contest": account_type == "contest",
        "real": account_type == "real",
    }


def compute_be_arm_progress(
    position: dict[str, Any],
    protection_state: dict[str, Any],
    trade_management: dict[str, Any],
    atr: float,
    arm_fraction: float,
    protected: bool,
) -> dict[str, Any]:
    direction = str(position.get("direction") or position.get("side") or "").upper()
    entry = _float(position.get("entryPrice") or position.get("priceOpen") or position.get("entry"))
    current = _float(position.get("currentPrice") or position.get("price"))
    risk_basis = abs(_float(protection_state.get("riskBasis")))
    if risk_basis <= 0:
        stop = _float(position.get("sl"))
        risk_basis = abs(entry - stop) if entry and stop else max(_float(atr), 0.0)
    profit_distance = (current - entry) if direction == "BUY" else (entry - current)
    profit_distance = max(0.0, profit_distance)
    profit_r = profit_distance / risk_basis if risk_basis > 0 else 0.0
    profit_atr = profit_distance / atr if atr > 0 else 0.0
    fraction = _bounded(_float(arm_fraction, 0.85), 0.05, 1.0)
    phase = str((protection_state.get("exitIntelligence") or {}).get("phase") or "").upper()

    if protected:
        return {
            "mode": "broker_protected",
            "phase": phase or "PROTECTED",
            "armDistance": 0.0,
            "armR": 0.0,
            "armAtr": 0.0,
            "profitDistance": round(profit_distance, 6),
            "profitR": round(profit_r, 6),
            "profitAtr": round(profit_atr, 6),
            "progress": 1.0,
            "armFraction": fraction,
            "eligible": True,
        }

    ai_dynamic = bool(trade_management.get("aiDynamicStopEnabled", True))
    launch_phase = phase == "LAUNCH" and bool(trade_management.get("launchPhaseEnabled", True))
    if ai_dynamic and launch_phase:
        arm_r = max(0.01, _float(trade_management.get("launchBreakEvenR"), 1.20))
        arm_distance = arm_r * risk_basis if risk_basis > 0 else arm_r * max(atr, 0.0)
        mode = "launch_r"
        arm_atr = arm_distance / atr if atr > 0 else 0.0
    elif ai_dynamic:
        arm_atr = max(0.01, _float(trade_management.get("protectStartAtr"), 0.60))
        arm_distance = arm_atr * max(atr, 0.0)
        arm_r = arm_distance / risk_basis if risk_basis > 0 else 0.0
        mode = "dynamic_atr"
    else:
        candidates: list[tuple[str, float]] = []
        be_r = _float(trade_management.get("breakEvenAtRR"), 0.90)
        if risk_basis > 0 and be_r > 0:
            candidates.append(("legacy_r", be_r * risk_basis))
        be_points = _float(trade_management.get("breakEvenAtPoints"), 0.0)
        if be_points > 0:
            candidates.append(("legacy_points", be_points))
        protect_points = _float(trade_management.get("protectStartPoints"), 0.0)
        if protect_points > 0:
            candidates.append(("legacy_protect_points", protect_points))
        if not candidates:
            candidates.append(("legacy_fallback", max(0.01, 0.60 * max(atr, risk_basis))))
        mode, arm_distance = min(candidates, key=lambda row: row[1])
        arm_r = arm_distance / risk_basis if risk_basis > 0 else 0.0
        arm_atr = arm_distance / atr if atr > 0 else 0.0

    progress = _bounded(profit_distance / arm_distance if arm_distance > 0 else 0.0, 0.0, 1.5)
    return {
        "mode": mode,
        "phase": phase or "DEVELOPING",
        "armDistance": round(arm_distance, 6),
        "armR": round(arm_r, 6),
        "armAtr": round(arm_atr, 6),
        "profitDistance": round(profit_distance, 6),
        "profitR": round(profit_r, 6),
        "profitAtr": round(profit_atr, 6),
        "progress": round(progress, 6),
        "armFraction": fraction,
        "eligible": progress >= fraction,
    }


def update_sustained_evidence(
    state: dict[str, Any],
    campaign_id: str,
    direction: str,
    confidence: float,
    continuation: float,
    qualified: bool,
    now: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    required = max(1, int(config.get("sustainedScanCount", 3) or 3))
    window = max(0.25, _float(config.get("sustainedWindowSeconds"), 5.0))
    max_conf_drop = max(0.0, _float(config.get("maxConfidenceDrop"), 4.0))
    max_cont_drop = max(0.0, _float(config.get("maxContinuationDrop"), 5.0))
    current = deepcopy(state) if isinstance(state, dict) else {}
    reset_reason = ""
    same_campaign = current.get("campaignId") == campaign_id
    same_direction = str(current.get("direction") or "").upper() == str(direction or "").upper()
    last_ts = _float(current.get("lastTs"), 0.0)
    stale = bool(last_ts and now - last_ts > window)
    prior_conf = _float(current.get("lastConfidence"), confidence)
    prior_cont = _float(current.get("lastContinuation"), continuation)
    conf_drop = prior_conf - float(confidence)
    cont_drop = prior_cont - float(continuation)

    if not qualified:
        reset_reason = "gate_unqualified"
    elif not same_campaign and current:
        reset_reason = "campaign_changed"
    elif not same_direction and current:
        reset_reason = "direction_changed"
    elif stale:
        reset_reason = "window_expired"
    elif current and conf_drop > max_conf_drop:
        reset_reason = "confidence_deterioration"
    elif current and cont_drop > max_cont_drop:
        reset_reason = "continuation_deterioration"

    if reset_reason or not current:
        count = 1 if qualified else 0
        samples = []
    else:
        count = int(current.get("count", 0) or 0) + 1
        samples = list(current.get("samples") or [])[-(required - 1):]
    if qualified:
        samples.append({
            "ts": float(now),
            "confidence": round(float(confidence), 3),
            "continuation": round(float(continuation), 3),
        })
    new_state = {
        "campaignId": campaign_id,
        "direction": str(direction or "").upper(),
        "count": count,
        "required": required,
        "firstTs": _float(current.get("firstTs"), now) if count > 1 and not reset_reason else float(now),
        "lastTs": float(now),
        "lastConfidence": round(float(confidence), 3),
        "lastContinuation": round(float(continuation), 3),
        "samples": samples[-required:],
        "stable": bool(qualified and count >= required),
        "resetReason": reset_reason,
    }
    return {
        "state": new_state,
        "count": count,
        "required": required,
        "stable": new_state["stable"],
        "resetReason": reset_reason,
        "ageSeconds": round(max(0.0, now - new_state["firstTs"]), 3),
    }


def choose_batch_size(confidence: float, continuation: float, capacity: int, config: dict[str, Any]) -> int:
    requested = max(2, min(3, int(config.get("batchSize", 3) or 3), int(capacity)))
    if requested < 2:
        return 0
    if not bool(config.get("adaptiveBatch", True)):
        return requested
    strong_conf = _float(config.get("strongBatchConfidence"), 92.0)
    strong_cont = _float(config.get("strongBatchContinuation"), 85.0)
    if requested >= 3 and float(confidence) >= strong_conf and float(continuation) >= strong_cont:
        return 3
    return 2


def evaluate_rounded_basket_risk(
    lots: list[float],
    entry: float,
    stop: float,
    direction: str,
    risk_budget_cash: float,
    loss_per_lot: Callable[[float], float],
) -> dict[str, Any]:
    rows = []
    total = 0.0
    for index, lot in enumerate(lots):
        projected = abs(_float(loss_per_lot(float(lot))))
        total += projected
        rows.append({"index": index + 1, "lot": round(float(lot), 4), "projectedLossCash": round(projected, 4)})
    budget = max(0.0, float(risk_budget_cash))
    overrun = max(0.0, total - budget)
    return {
        "allowed": bool(lots and budget > 0 and total <= budget + 0.01),
        "direction": str(direction or "").upper(),
        "entry": round(float(entry), 6),
        "stop": round(float(stop), 6),
        "riskBudgetCash": round(budget, 4),
        "projectedRiskCash": round(total, 4),
        "overrunCash": round(overrun, 4),
        "legs": rows,
    }


def classify_burst_lifecycle(
    current_stage: str,
    profit_r: float,
    peak_r: float,
    age_seconds: float,
    continuation: float,
    invalidated: bool,
    config: dict[str, Any],
) -> dict[str, Any]:
    stage = str(current_stage or "BURST_PROBE").upper()
    if stage not in {"BURST_PROBE", "BURST_CONFIRMED", "BURST_RUNNER", "BURST_DEFENSIVE"}:
        stage = "BURST_PROBE"
    defensive_floor = _float(config.get("burstDefensiveContinuation"), 52.0)
    if invalidated or float(continuation) < defensive_floor:
        return {"stage": "BURST_DEFENSIVE", "reason": "continuation_invalidated" if invalidated else "continuation_deteriorated"}
    if stage == "BURST_DEFENSIVE":
        return {"stage": stage, "reason": "defensive_is_terminal"}
    if stage == "BURST_RUNNER":
        return {"stage": stage, "reason": "runner_is_one_way"}
    if stage == "BURST_CONFIRMED":
        if (
            float(peak_r) >= _float(config.get("burstRunnerProfitR"), 0.55)
            and float(continuation) >= _float(config.get("burstRunnerContinuation"), 72.0)
        ):
            return {"stage": "BURST_RUNNER", "reason": "runner_thresholds_met"}
        return {"stage": stage, "reason": "confirmed_hold"}
    if (
        float(age_seconds) >= _float(config.get("burstPromotionMinAgeSeconds"), 10.0)
        and float(profit_r) >= _float(config.get("burstPromotionProfitR"), 0.18)
        and float(continuation) >= _float(config.get("burstPromotionContinuation"), 78.0)
    ):
        return {"stage": "BURST_CONFIRMED", "reason": "promotion_thresholds_met"}
    return {"stage": "BURST_PROBE", "reason": "probe_validation_active"}


def build_gate(name: str, passed: bool, *, value: Any = None, threshold: Any = None, reason: str = "") -> dict[str, Any]:
    return {
        "name": str(name),
        "passed": bool(passed),
        "value": value,
        "threshold": threshold,
        "reason": str(reason or ("passed" if passed else "blocked")),
    }
