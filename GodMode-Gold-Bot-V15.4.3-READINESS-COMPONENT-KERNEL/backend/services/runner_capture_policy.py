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


@dataclass(frozen=True)
class SinglePositionTpPolicy:
    mode: str
    tp: float | None
    dynamic_stop_authoritative: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualifiedPeakUpdate:
    raw_peak_dist: float
    qualified_peak_dist: float
    candidate_peak_dist: float
    candidate_since: float
    qualified_at: float
    state: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_single_position_broker_tp(
    *,
    side: str,
    entry: float,
    sl: float,
    plan: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
) -> SinglePositionTpPolicy:
    """Resolve the broker TP for an unsplittable single-position runner.

    A 0.01-lot position cannot take 25% partials. Capping that entire position at the
    conventional TP4 prevents the deterministic stop engine from managing an exceptional
    runner. The default therefore keeps the broker SL as the safety backstop and leaves
    the profit exit to the deterministic manager. Operators can explicitly select the
    legacy TP4 or a farther emergency target instead.
    """
    cfg = config if isinstance(config, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    side_u = str(side or "").upper()
    mode = str(cfg.get("singlePositionBrokerTpMode") or "DYNAMIC_SL_ONLY").upper()
    if mode not in {"DYNAMIC_SL_ONLY", "EXTENDED", "TP4"}:
        mode = "DYNAMIC_SL_ONLY"

    entry_f = _f(entry)
    sl_f = _f(sl)
    risk = abs(entry_f - sl_f)
    if side_u not in {"BUY", "SELL"} or entry_f <= 0 or risk <= 0:
        return SinglePositionTpPolicy(
            mode="DYNAMIC_SL_ONLY",
            tp=None,
            dynamic_stop_authoritative=True,
            reason="Invalid side or stop geometry; fixed profit cap suppressed.",
        )

    if mode == "TP4":
        tp4 = _f(plan.get("tp4"))
        return SinglePositionTpPolicy(
            mode=mode,
            tp=tp4 if tp4 > 0 else None,
            dynamic_stop_authoritative=False,
            reason="Legacy TP4 cap selected by configuration.",
        )

    if mode == "EXTENDED":
        target_r = max(4.0, _f(cfg.get("singlePositionEmergencyTpR"), 12.0))
        target = entry_f + risk * target_r if side_u == "BUY" else entry_f - risk * target_r
        return SinglePositionTpPolicy(
            mode=mode,
            tp=round(target, 6),
            dynamic_stop_authoritative=True,
            reason=f"Extended emergency broker target at {target_r:.1f}R; deterministic stop remains primary.",
        )

    return SinglePositionTpPolicy(
        mode="DYNAMIC_SL_ONLY",
        tp=None,
        dynamic_stop_authoritative=True,
        reason="No fixed broker profit cap for an unsplittable runner; broker SL remains authoritative safety.",
    )


def update_qualified_peak(
    *,
    state: dict[str, Any] | None,
    side: str,
    entry: float,
    current_price: float,
    atr: float,
    now: float,
    config: dict[str, Any] | None = None,
) -> QualifiedPeakUpdate:
    """Track raw MFE separately from the peak allowed to ratchet the broker stop.

    Raw tick highs/lows are valuable telemetry, but a transient wick must not instantly
    tighten the stop. A candidate peak becomes qualified only after price remains close
    to it for the configured dwell period. If the wick rejects before that, the raw MFE
    is retained while the stop-ratcheting peak stays unchanged.
    """
    cfg = config if isinstance(config, dict) else {}
    prior = dict(state) if isinstance(state, dict) else {}
    side_u = str(side or "").upper()
    entry_f = _f(entry)
    price_f = _f(current_price)
    atr_f = max(0.0, _f(atr))
    now_f = max(0.0, _f(now))
    sign = 1.0 if side_u == "BUY" else -1.0
    favorable = max(0.0, (price_f - entry_f) * sign) if side_u in {"BUY", "SELL"} and entry_f > 0 and price_f > 0 else 0.0

    raw_peak = max(_f(prior.get("rawPeakDist")), favorable)
    qualified = max(0.0, _f(prior.get("qualifiedPeakDist")))
    candidate = max(qualified, _f(prior.get("peakCandidateDist"), qualified))
    candidate_since = _f(prior.get("peakCandidateSince"), now_f)
    qualified_at = _f(prior.get("qualifiedPeakAt"), 0.0)

    dwell = _clamp(_f(cfg.get("qualifiedPeakDwellSeconds"), 3.0), 0.5, 30.0)
    tolerance = max(0.01, atr_f * _clamp(_f(cfg.get("qualifiedPeakToleranceAtr"), 0.10), 0.01, 0.50))
    min_advance = max(0.01, atr_f * _clamp(_f(cfg.get("qualifiedPeakMinAdvanceAtr"), 0.05), 0.01, 0.50))

    if candidate <= 0 and favorable > 0:
        candidate = favorable
        candidate_since = now_f
    elif favorable > candidate + min_advance:
        candidate = favorable
        candidate_since = now_f
    elif candidate > qualified and favorable >= candidate - tolerance:
        if now_f - candidate_since >= dwell:
            qualified = max(qualified, candidate)
            qualified_at = now_f
    elif favorable < candidate - tolerance:
        # The peak rejected before qualification. Start a new candidate from the current
        # favorable distance, but never reduce an already-qualified peak.
        candidate = max(qualified, favorable)
        candidate_since = now_f

    next_state = {
        **prior,
        "rawPeakDist": round(raw_peak, 8),
        "qualifiedPeakDist": round(qualified, 8),
        "peakCandidateDist": round(candidate, 8),
        "peakCandidateSince": round(candidate_since, 6),
        "qualifiedPeakAt": round(qualified_at, 6),
    }
    return QualifiedPeakUpdate(
        raw_peak_dist=raw_peak,
        qualified_peak_dist=qualified,
        candidate_peak_dist=candidate,
        candidate_since=candidate_since,
        qualified_at=qualified_at,
        state=next_state,
    )
