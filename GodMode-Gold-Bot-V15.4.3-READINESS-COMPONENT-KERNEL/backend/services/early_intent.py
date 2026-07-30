from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from statistics import median
from typing import Any, Iterable


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class EarlyIntent:
    side: str | None
    probability: float
    stage: str
    displacement_atr: float
    velocity_score: float
    acceleration_score: float
    persistence_score: float
    burst_score: float
    structure_score: float
    compression_score: float
    spread_score: float
    reversal_penalty: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mid(tick: dict[str, Any]) -> float:
    bid = _f(tick.get("bid"))
    ask = _f(tick.get("ask"))
    last = _f(tick.get("last"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return last or bid or ask


def _ts(tick: dict[str, Any]) -> float:
    # MT5Bridge historically emitted timeMsc while the predictor consumed
    # time_msc.  Accept all supported spellings so sub-second timing is never lost.
    msc = _f(tick.get("time_msc") or tick.get("timeMsc") or tick.get("tickTimeMsc"))
    return msc / 1000.0 if msc > 0 else _f(tick.get("time"))


def _rows(ticks: Iterable[dict[str, Any]]) -> list[tuple[float, float, float]]:
    result: list[tuple[float, float, float]] = []
    for tick in ticks:
        price = _mid(tick)
        ts = _ts(tick)
        spread = max(0.0, _f(tick.get("ask")) - _f(tick.get("bid")))
        if price > 0 and ts > 0:
            result.append((ts, price, spread))
    result.sort(key=lambda row: row[0])
    deduped: list[tuple[float, float, float]] = []
    for row in result:
        if deduped and row[:2] == deduped[-1][:2]:
            deduped[-1] = row
        else:
            deduped.append(row)
    return deduped


def predict_early_intent(
    *,
    ticks: Iterable[dict[str, Any]],
    candles: list[dict[str, Any]],
    atr: float,
    current_spread: float,
    max_spread: float,
    config: dict[str, Any] | None = None,
) -> EarlyIntent:
    """Detect directional intent before a conventional momentum spike qualifies.

    The engine is deterministic and deliberately conservative. It requires a short-lived
    burst, rising speed, directional persistence, acceptable spread and proximity to a
    structural release. It returns an intent only; the existing execution and risk stack
    remains authoritative.
    """
    cfg = config or {}
    atr = max(_f(atr), 1e-9)
    rows = _rows(ticks)
    target_ticks = max(6, int(_f(cfg.get("minTicks", 10), 10)))
    hard_min_ticks = max(5, min(target_ticks, int(_f(cfg.get("hardMinTicks", 6), 6))))
    if len(rows) < hard_min_ticks:
        return EarlyIntent(None, 0.0, "COLLECTING", 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           f"collecting intent ticks ({len(rows)}/{target_ticks})")

    window_s = max(1.5, _f(cfg.get("windowSeconds", 4.0), 4.0))
    cutoff = rows[-1][0] - window_s
    rows = [row for row in rows if row[0] >= cutoff]
    if len(rows) < hard_min_ticks:
        return EarlyIntent(None, 0.0, "COLLECTING", 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           f"collecting recent intent ticks ({len(rows)}/{target_ticks})")

    # A short accelerating tail is the actual early signal.  Analysing only the
    # net move across the whole window lets an initial micro-pullback cancel the
    # emerging burst and delays qualification until the move is already mature.
    candidates = [rows]
    for count in range(hard_min_ticks, min(len(rows), target_ticks + 4) + 1):
        candidates.append(rows[-count:])
    def _candidate_strength(candidate: list[tuple[float, float, float]]) -> float:
        if len(candidate) < 2:
            return -1.0
        dt = max(candidate[-1][0] - candidate[0][0], 0.05)
        delta = candidate[-1][1] - candidate[0][1]
        if delta == 0:
            return 0.0
        sign = 1.0 if delta > 0 else -1.0
        diffs = [candidate[i][1] - candidate[i-1][1] for i in range(1, len(candidate))]
        nonzero = [d for d in diffs if d]
        persistence = sum(1 for d in nonzero if d * sign > 0) / max(1, len(nonzero))
        return abs(delta) / dt * (0.55 + 0.45 * persistence) * min(1.0, len(candidate) / target_ticks)
    rows = max(candidates, key=_candidate_strength)
    sample_confidence = min(1.0, len(rows) / max(target_ticks, 1))

    times = [r[0] for r in rows]
    prices = [r[1] for r in rows]
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    net = prices[-1] - prices[0]
    side = "BUY" if net > 0 else "SELL" if net < 0 else None
    if side is None:
        return EarlyIntent(None, 0.0, "WATCH", 0, 0, 0, 0, 0, 0, 0, 0, 0, "no directional intent")
    sign = 1.0 if side == "BUY" else -1.0

    elapsed = max(times[-1] - times[0], 0.05)
    displacement_atr = abs(net) / atr
    velocity = (net * sign / atr) / elapsed
    velocity_target = max(_f(cfg.get("velocityAtrPerSecond", 0.020), 0.020), 1e-6)
    velocity_score = _clamp(velocity / velocity_target)

    split = max(3, int(len(rows) * 0.55))
    first_elapsed = max(times[split - 1] - times[0], 0.05)
    last_elapsed = max(times[-1] - times[split - 1], 0.05)
    first_v = ((prices[split - 1] - prices[0]) * sign / atr) / first_elapsed
    last_v = ((prices[-1] - prices[split - 1]) * sign / atr) / last_elapsed
    acceleration = last_v - first_v
    acceleration_target = max(_f(cfg.get("accelerationAtrPerSecond", 0.015), 0.015), 1e-6)
    acceleration_score = _clamp(acceleration / acceleration_target)

    nonzero = [change for change in changes if change != 0]
    aligned = [change for change in nonzero if change * sign > 0]
    persistence = len(aligned) / max(1, len(nonzero))
    persistence_score = _clamp((persistence - 0.56) / 0.32)

    tail_count = min(8, len(changes))
    tail = changes[-tail_count:]
    aligned_tail = [abs(x) for x in tail if x * sign > 0]
    opposite_tail = [abs(x) for x in tail if x * sign < 0]
    burst_ratio = sum(aligned_tail) / max(sum(aligned_tail) + sum(opposite_tail), 1e-9)
    burst_score = _clamp((burst_ratio - 0.60) / 0.30)

    recent = candles[-14:] if candles else []
    prior = recent[-9:-1] if len(recent) >= 2 else []
    live = recent[-1] if recent else {}
    prior_high = max((_f(c.get("high")) for c in prior), default=prices[-1])
    prior_low = min((_f(c.get("low")) for c in prior), default=prices[-1])
    # The candle history cache may lag the live quote by up to its refresh TTL.
    # Always patch the forming candle from the newest canonical tick so structure,
    # wick and extension calculations represent the market being executed.
    close = prices[-1]
    open_ = _f(live.get("open"), prices[0])
    high = max(_f(live.get("high"), close), max(prices))
    low = min(_f(live.get("low"), close), min(prices))

    proximity_atr = ((close - prior_high) / atr) if side == "BUY" else ((prior_low - close) / atr)
    prebreak_buffer = max(_f(cfg.get("prebreakBufferAtr", 0.08), 0.08), 0.0)
    structure_score = _clamp((proximity_atr + prebreak_buffer) / max(prebreak_buffer + 0.10, 1e-6))

    ranges = [max(0.0, _f(c.get("high")) - _f(c.get("low"))) for c in prior]
    baseline = median([r for r in ranges if r > 0]) if ranges else atr
    short = median(ranges[-4:]) if len(ranges) >= 4 else baseline
    compression_ratio = short / max(baseline, 1e-9)
    compression_target = max(_f(cfg.get("compressionRatio", 0.78), 0.78), 0.1)
    compression_score = _clamp((compression_target - compression_ratio + 0.25) / 0.35)

    spreads = [r[2] for r in rows if r[2] > 0]
    latest_tick_spread = spreads[-1] if spreads else 0.0
    # Use the worse live observation. The market snapshot may be newer than the
    # sampled range during a spread blowout; ignoring it can approve an entry
    # exactly when execution costs have deteriorated.
    observed = max(max(0.0, current_spread), latest_tick_spread)
    spread_score = _clamp(1.0 - observed / max(max_spread, 1e-9))
    baseline_spread = median(spreads[:-2]) if len(spreads) > 4 else observed
    if baseline_spread > 0 and observed > baseline_spread * _f(cfg.get("spreadExpansionMultiple", 1.55), 1.55):
        spread_score *= 0.35

    candle_range = max(high - low, 1e-9)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    adverse_wick = upper_wick if side == "BUY" else lower_wick
    reversal_penalty = _clamp((adverse_wick / candle_range - 0.30) / 0.35)
    reported_close = _f(live.get("close"), close)
    if side == "BUY" and high > prior_high and reported_close < prior_high:
        reversal_penalty = max(reversal_penalty, 0.90)
    elif side == "SELL" and low < prior_low and reported_close > prior_low:
        reversal_penalty = max(reversal_penalty, 0.90)

    probability = _clamp((
        0.22 * velocity_score
        + 0.20 * acceleration_score
        + 0.17 * persistence_score
        + 0.14 * burst_score
        + 0.13 * structure_score
        + 0.07 * compression_score
        + 0.07 * spread_score
        - 0.24 * reversal_penalty
    ) * (0.82 + 0.18 * sample_confidence))

    threshold = _f(cfg.get("intentProbability", 0.68), 0.68)
    min_displacement = _f(cfg.get("minDisplacementAtr", 0.07), 0.07)
    unsafe_spread = observed > max(max_spread, 1e-9)
    max_reversal = _f(cfg.get("maxReversalPenalty", 0.28), 0.28)
    stage = "INTENT" if probability >= threshold and displacement_atr >= min_displacement and not unsafe_spread and reversal_penalty <= max_reversal else "WATCH"
    reason = (
        f"{side} early intent {stage}: p={probability:.2f}, move={displacement_atr:.2f} ATR, "
        f"velocity={velocity_score:.2f}, acceleration={acceleration_score:.2f}, "
        f"persistence={persistence_score:.2f}, burst={burst_score:.2f}, "
        f"structure={structure_score:.2f}, compression={compression_score:.2f}, "
        f"spread={spread_score:.2f}, reversalPenalty={reversal_penalty:.2f}"
    )
    return EarlyIntent(
        side=side,
        probability=round(probability, 4),
        stage=stage,
        displacement_atr=round(displacement_atr, 4),
        velocity_score=round(velocity_score, 4),
        acceleration_score=round(acceleration_score, 4),
        persistence_score=round(persistence_score, 4),
        burst_score=round(burst_score, 4),
        structure_score=round(structure_score, 4),
        compression_score=round(compression_score, 4),
        spread_score=round(spread_score, 4),
        reversal_penalty=round(reversal_penalty, 4),
        reason=reason,
    )
