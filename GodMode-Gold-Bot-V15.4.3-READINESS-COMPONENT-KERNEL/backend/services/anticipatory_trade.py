from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if isfinite(result) else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ProbeStopPlan:
    allowed: bool
    side: str
    sl: float
    risk_distance: float
    tp1: float
    tp2: float
    tp3: float
    tp4: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProbeLifecycle:
    stage: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProbeManagementDecision:
    action: str
    reason: str
    allow_widen: bool = False
    allow_breathe: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_probe_stop(
    *,
    side: str,
    entry: float,
    atr: float,
    recent_candles: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> ProbeStopPlan:
    cfg = config or {}
    side = str(side or "").upper()
    entry = _f(entry)
    atr = max(_f(atr), 1e-9)
    if side not in {"BUY", "SELL"} or entry <= 0 or not recent_candles:
        return ProbeStopPlan(False, side, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "invalid_probe_inputs")
    min_stop = max(0.1, _f(cfg.get("minStopPoints", 1.5), 1.5))
    max_stop = max(min_stop, _f(cfg.get("maxStopPoints", 3.5), 3.5))
    stop_atr = max(0.10, _f(cfg.get("stopAtr", 0.45), 0.45))
    buffer_atr = max(0.0, _f(cfg.get("structureBufferAtr", 0.05), 0.05))
    rows = recent_candles[-3:]
    if side == "BUY":
        structural = min(_f(row.get("low"), entry) for row in rows) - buffer_atr * atr
        structure_distance = entry - structural
    else:
        structural = max(_f(row.get("high"), entry) for row in rows) + buffer_atr * atr
        structure_distance = structural - entry
    if structure_distance <= 0:
        return ProbeStopPlan(False, side, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "invalid_structural_stop")
    if structure_distance > max_stop + 1e-9:
        return ProbeStopPlan(False, side, 0.0, structure_distance, 0.0, 0.0, 0.0, 0.0, f"structure_requires_{structure_distance:.2f}_points_above_{max_stop:.2f}_cap")
    distance = max(min_stop, atr * stop_atr, structure_distance)
    if distance > max_stop + 1e-9:
        return ProbeStopPlan(False, side, 0.0, distance, 0.0, 0.0, 0.0, 0.0, f"probe_stop_{distance:.2f}_points_above_{max_stop:.2f}_cap")
    sl = entry - distance if side == "BUY" else entry + distance
    sign = 1.0 if side == "BUY" else -1.0
    tps = [entry + sign * distance * multiple for multiple in (0.8, 1.5, 2.4, 3.5)]
    return ProbeStopPlan(True, side, round(sl, 3), round(distance, 3), *(round(x, 3) for x in tps), "probe_stop_valid")


def classify_probe_lifecycle(
    *,
    side: str,
    profit_r: float,
    peak_r: float | None = None,
    context_score: float | None = None,
    intent_state: dict[str, Any] | None,
    impulse_state: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
) -> ProbeLifecycle:
    cfg = config or {}
    side = str(side or "").upper()
    intent = intent_state or {}
    impulse = impulse_state or {}
    confirm_probability = _f(cfg.get("confirmProbability", 0.84), 0.84)
    promotion_r = _f(cfg.get("promotionProfitR", 0.35), 0.35)
    impulse_confirmed = (
        str(impulse.get("side") or "").upper() == side
        and str(impulse.get("stage") or "").upper() == "CONFIRMED"
        and _f(impulse.get("probability")) >= confirm_probability
    )
    intent_persistent = (
        str(intent.get("side") or "").upper() == side
        and str(intent.get("stage") or "").upper() in {"INTENT", "PROBE", "CONFIRMED"}
        and _f(intent.get("probability")) >= _f(cfg.get("intentHoldProbability", 0.66), 0.66)
    )
    peak_value = max(_f(profit_r), _f(peak_r))
    context_value = _f(context_score)
    peak_confirmed = (
        peak_value >= _f(cfg.get("promotionPeakR", 0.55), 0.55)
        and context_value >= _f(cfg.get("promotionContextScore", 0.68), 0.68)
    )
    if impulse_confirmed or (_f(profit_r) >= promotion_r and intent_persistent) or peak_confirmed:
        reason = "peak and context confirmed the probe" if peak_confirmed and not impulse_confirmed else "impulse confirmation or profitable persistent intent"
        return ProbeLifecycle("CONFIRMED", reason)
    return ProbeLifecycle("PROBE", "awaiting impulse confirmation")


def probe_management_decision(
    *,
    side: str,
    stage: str,
    profit_r: float,
    peak_r: float,
    age_seconds: float,
    intent_state: dict[str, Any] | None,
    impulse_state: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
) -> ProbeManagementDecision:
    cfg = config or {}
    if str(stage or "").upper() != "PROBE":
        return ProbeManagementDecision("NORMAL", "confirmed trade uses standard management")
    side = str(side or "").upper()
    profit_r = _f(profit_r)
    peak_r = _f(peak_r)
    age_seconds = max(0.0, _f(age_seconds))
    intent = intent_state or {}
    impulse = impulse_state or {}
    opposite = "SELL" if side == "BUY" else "BUY"
    opposite_probability = _f(cfg.get("oppositeProbability", 0.70), 0.70)
    for state in (intent, impulse):
        if str(state.get("side") or "").upper() == opposite and _f(state.get("probability")) >= opposite_probability and str(state.get("stage") or "").upper() in {"INTENT", "PROBE", "CONFIRMED"}:
            return ProbeManagementDecision("CUT", f"opposite {opposite} predictor qualified")
    fast_fail_r = _f(cfg.get("fastFailR", -0.25), -0.25)
    if profit_r <= fast_fail_r:
        return ProbeManagementDecision("CUT", f"probe fast-fail {profit_r:.2f}R <= {fast_fail_r:.2f}R")
    stall_seconds = max(5.0, _f(cfg.get("stallSeconds", 45.0), 45.0))
    min_progress_r = _f(cfg.get("minProgressR", 0.12), 0.12)
    if age_seconds >= stall_seconds and peak_r < min_progress_r and profit_r <= 0:
        return ProbeManagementDecision("CUT", f"probe stalled {age_seconds:.0f}s without {min_progress_r:.2f}R progress")
    grace = max(2.0, _f(cfg.get("accelerationGraceSeconds", 12.0), 12.0))
    same_side = str(intent.get("side") or "").upper() == side
    acceleration = _f(intent.get("acceleration_score"))
    probability = _f(intent.get("probability"))
    if age_seconds >= grace and same_side and acceleration < _f(cfg.get("minAccelerationHold", 0.12), 0.12) and probability < _f(cfg.get("minIntentHoldProbability", 0.52), 0.52) and profit_r <= 0:
        return ProbeManagementDecision("CUT", "intent acceleration and probability collapsed")
    if profit_r >= _f(cfg.get("breakevenR", 0.35), 0.35):
        return ProbeManagementDecision("PROTECT", "probe earned tight protection")
    return ProbeManagementDecision("HOLD", "probe remains within confirmation window")


def sanitize_probe_runtime_state(state: dict[str, Any]) -> list[str]:
    """Remove legacy recovery/breathe directives that are unsafe for a live probe."""
    removed: list[str] = []
    pending = state.get("pendingDirective")
    if isinstance(pending, dict) and str(pending.get("command") or "").upper() in {"RECOVER", "WIDEN", "BREATH"}:
        state.pop("pendingDirective", None)
        removed.append("pendingDirective")
    if "pendingBreath" in state:
        state.pop("pendingBreath", None)
        removed.append("pendingBreath")
    if _f(state.get("breathingUntil")) != 0.0:
        removed.append("breathingUntil")
    state["breathingUntil"] = 0.0
    if bool(state.get("dynamicRecoveryMode")):
        removed.append("dynamicRecoveryMode")
    state["dynamicRecoveryMode"] = False
    return removed
