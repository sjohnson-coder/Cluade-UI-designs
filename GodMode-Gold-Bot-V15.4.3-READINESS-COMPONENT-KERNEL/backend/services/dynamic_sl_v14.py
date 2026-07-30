from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from math import isfinite
from typing import Any, Dict, Optional
import time


class DynamicSLState(str, Enum):
    INACTIVE = "INACTIVE"
    INITIAL_PROTECTION = "INITIAL_PROTECTION"
    LOSS_RECOVERY = "LOSS_RECOVERY"
    BREATHING = "BREATHING"
    BREAK_EVEN_LOCK = "BREAK_EVEN_LOCK"
    PROFIT_LOCK = "PROFIT_LOCK"
    TRAILING_CONTINUATION = "TRAILING_CONTINUATION"
    TP_EXTENSION = "TP_EXTENSION"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    ERROR_SAFE = "ERROR_SAFE"


@dataclass(frozen=True)
class BrokerRules:
    tick_size: float
    stops_level_points: float
    freeze_level_points: float
    point: float


@dataclass(frozen=True)
class PositionSnapshot:
    ticket: int
    symbol: str
    side: str
    entry: float
    bid: float
    ask: float
    sl: Optional[float]
    tp: Optional[float]
    volume: float
    initial_risk_price: float
    peak_profit_r: float
    current_profit_r: float
    timestamp: float
    sequence: int


@dataclass(frozen=True)
class DynamicSLDecision:
    ticket: int
    state_before: DynamicSLState
    state_after: DynamicSLState
    proposed_sl: Optional[float]
    proposed_tp: Optional[float]
    expected_current_sl: Optional[float]
    snapshot_sequence: int
    created_at: float
    reason_codes: tuple[str, ...]
    blocked: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["state_before"] = self.state_before.value
        value["state_after"] = self.state_after.value
        value["reason_codes"] = list(self.reason_codes)
        return value


def normalize_price(price: float, tick_size: float) -> float:
    if not isfinite(price) or not isfinite(tick_size) or tick_size <= 0:
        raise ValueError("price and tick_size must be finite; tick_size must be positive")
    return round(round(price / tick_size) * tick_size, 10)


def validate_snapshot(p: PositionSnapshot, rules: BrokerRules, *, max_age_seconds: float = 5.0) -> None:
    numeric = (p.entry, p.bid, p.ask, p.volume, p.initial_risk_price, p.timestamp)
    if p.ticket <= 0 or not p.symbol.strip():
        raise ValueError("invalid position identity")
    if p.side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if not all(isfinite(float(v)) for v in numeric):
        raise ValueError("snapshot contains non-finite numeric data")
    if p.volume <= 0 or p.initial_risk_price <= 0:
        raise ValueError("volume and initial risk must be positive")
    age = time.time() - p.timestamp
    if age < -1.0 or age > max_age_seconds:
        raise ValueError("stale or future-dated position snapshot")
    if rules.tick_size <= 0 or rules.point <= 0:
        raise ValueError("invalid broker rules")


def validate_stop(p: PositionSnapshot, rules: BrokerRules, proposed_sl: float) -> tuple[bool, str]:
    proposed_sl = normalize_price(proposed_sl, rules.tick_size)
    min_distance = max(rules.stops_level_points, rules.freeze_level_points) * rules.point
    if p.side == "BUY":
        if proposed_sl >= p.bid:
            return False, "BUY_SL_NOT_BELOW_BID"
        if (p.bid - proposed_sl) + 1e-12 < min_distance:
            return False, "BUY_SL_INSIDE_BROKER_DISTANCE"
    else:
        if proposed_sl <= p.ask:
            return False, "SELL_SL_NOT_ABOVE_ASK"
        if (proposed_sl - p.ask) + 1e-12 < min_distance:
            return False, "SELL_SL_INSIDE_BROKER_DISTANCE"
    return True, "OK"


def _state_for(p: PositionSnapshot, *, recovery_score: float, invalidated: bool) -> DynamicSLState:
    if invalidated:
        return DynamicSLState.EXIT_PENDING
    if p.current_profit_r < 0:
        return DynamicSLState.LOSS_RECOVERY if recovery_score >= 70 else DynamicSLState.ERROR_SAFE
    if p.current_profit_r < 0.15:
        return DynamicSLState.INITIAL_PROTECTION
    if p.current_profit_r < 0.45:
        return DynamicSLState.BREAK_EVEN_LOCK
    if recovery_score >= 78 and p.current_profit_r >= 1.0:
        return DynamicSLState.TP_EXTENSION
    if recovery_score >= 70 and p.current_profit_r < max(0.5, p.peak_profit_r * 0.75):
        return DynamicSLState.BREATHING
    if p.current_profit_r >= 1.0:
        return DynamicSLState.TRAILING_CONTINUATION
    return DynamicSLState.PROFIT_LOCK


def decide(
    p: PositionSnapshot,
    rules: BrokerRules,
    *,
    state: DynamicSLState,
    recovery_score: float,
    invalidated: bool,
    max_giveback_fraction: float = 0.45,
    min_lock_r: float = 0.05,
    tp_extension_r: float = 0.75,
    desired_sl: Optional[float] = None,
    desired_tp: Optional[float] = None,
) -> DynamicSLDecision:
    """Deterministic V14 decision. No broker mutation or hidden fallback occurs here."""
    try:
        validate_snapshot(p, rules)
        if not 0.05 <= max_giveback_fraction <= 0.95:
            raise ValueError("max_giveback_fraction outside safe range")
        if not 0 <= recovery_score <= 100:
            raise ValueError("recovery_score outside 0..100")

        next_state = _state_for(p, recovery_score=recovery_score, invalidated=invalidated)
        if next_state is DynamicSLState.EXIT_PENDING:
            return DynamicSLDecision(p.ticket, state, next_state, p.sl, p.tp, p.sl, p.sequence, time.time(), ("STRUCTURE_INVALIDATED",))
        if next_state is DynamicSLState.ERROR_SAFE and p.current_profit_r < 0:
            return DynamicSLDecision(p.ticket, state, next_state, p.sl, p.tp, p.sl, p.sequence, time.time(), ("LOSS_WITHOUT_RECOVERY_CONFIRMATION",), blocked=True, error="loss recovery evidence insufficient")

        locked_r = max(min_lock_r, max(0.0, p.peak_profit_r) * (1.0 - max_giveback_fraction))
        computed = p.entry + locked_r * p.initial_risk_price if p.side == "BUY" else p.entry - locked_r * p.initial_risk_price
        requested = desired_sl if desired_sl is not None else computed
        # The peak-retention floor is an invariant, not a caller convention. BREATHING
        # may relax the current broker stop only as far as this floor; a stale or buggy
        # caller can never surrender more than the configured giveback budget.
        bounded = max(requested, computed) if p.side == "BUY" else min(requested, computed)
        candidate_sl = normalize_price(bounded, rules.tick_size)

        # Never loosen a protected stop unless the explicit BREATHING state authorises it.
        if p.sl is not None and next_state is not DynamicSLState.BREATHING:
            candidate_sl = max(candidate_sl, p.sl) if p.side == "BUY" else min(candidate_sl, p.sl)

        legal, reason = validate_stop(p, rules, candidate_sl)
        if not legal:
            return DynamicSLDecision(p.ticket, state, DynamicSLState.ERROR_SAFE, p.sl, p.tp, p.sl, p.sequence, time.time(), (reason,), blocked=True, error=reason)

        proposed_tp = desired_tp if desired_tp is not None else p.tp
        reasons = ["V14_STATE_TRANSITION", next_state.value]
        if desired_sl is not None and normalize_price(requested, rules.tick_size) != candidate_sl:
            reasons.append("PEAK_RETENTION_FLOOR")
        if next_state is DynamicSLState.TP_EXTENSION:
            extension = tp_extension_r * p.initial_risk_price
            # Extend from the live market (or an already-valid farther target), never
            # from entry. Extending from entry after price has already travelled >1R
            # can place a SELL TP above ask or a BUY TP below bid, which is behind the
            # position and cannot represent a continuation target.
            if p.side == "BUY":
                live_base = max(p.bid, proposed_tp if proposed_tp is not None else p.bid)
                proposed_tp = normalize_price(live_base + extension, rules.tick_size)
            else:
                live_base = min(p.ask, proposed_tp if proposed_tp is not None else p.ask)
                proposed_tp = normalize_price(live_base - extension, rules.tick_size)
            reasons.append("CONTINUATION_CONFIRMED")
        if p.sl is not None and candidate_sl == p.sl:
            reasons.append("IDEMPOTENT_NO_CHANGE")
        else:
            reasons.append("BROKER_SAFE_STOP")

        return DynamicSLDecision(p.ticket, state, next_state, candidate_sl, proposed_tp, p.sl, p.sequence, time.time(), tuple(reasons))
    except Exception as exc:
        return DynamicSLDecision(p.ticket, state, DynamicSLState.ERROR_SAFE, p.sl, p.tp, p.sl, p.sequence, time.time(), ("DECISION_VALIDATION_FAILED",), blocked=True, error=str(exc))


def decision_is_stale(decision: DynamicSLDecision, snapshot: PositionSnapshot, *, max_age_seconds: float = 2.0) -> bool:
    return (
        decision.ticket != snapshot.ticket
        or decision.snapshot_sequence != snapshot.sequence
        or time.time() - decision.created_at > max_age_seconds
        or decision.expected_current_sl != snapshot.sl
    )
