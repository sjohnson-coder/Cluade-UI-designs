from __future__ import annotations

from dataclasses import dataclass, asdict
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
class ImpulsePrediction:
    side: str | None
    probability: float
    stage: str
    velocity_score: float
    acceleration_score: float
    directional_score: float
    compression_release_score: float
    spread_score: float
    candle_score: float
    sweep_penalty: float
    displacement_atr: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tick_mid(tick: dict[str, Any]) -> float:
    bid = _f(tick.get("bid"))
    ask = _f(tick.get("ask"))
    last = _f(tick.get("last"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return last or bid or ask


def _tick_time(tick: dict[str, Any]) -> float:
    msc = _f(tick.get("time_msc") or tick.get("timeMsc") or tick.get("tickTimeMsc"))
    return (msc / 1000.0) if msc > 0 else _f(tick.get("time"))


def _normalise_ticks(ticks: Iterable[dict[str, Any]]) -> list[tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []
    for tick in ticks:
        price = _tick_mid(tick)
        ts = _tick_time(tick)
        spread = max(0.0, _f(tick.get("ask")) - _f(tick.get("bid")))
        if price > 0 and ts > 0:
            rows.append((ts, price, spread))
    rows.sort(key=lambda row: row[0])
    deduped: list[tuple[float, float, float]] = []
    for row in rows:
        if deduped and row[0] == deduped[-1][0] and row[1] == deduped[-1][1]:
            deduped[-1] = row
        else:
            deduped.append(row)
    return deduped


def predict_impulse(
    *,
    ticks: Iterable[dict[str, Any]],
    candles: list[dict[str, Any]],
    atr: float,
    current_spread: float,
    max_spread: float,
    config: dict[str, Any] | None = None,
) -> ImpulsePrediction:
    """Predict an emerging XAUUSD impulse before a full ATR spike is complete.

    This scorer is deterministic and fail-closed. It combines tick velocity,
    acceleration, directional persistence, compression release, live candle body,
    spread quality and liquidity-sweep risk. It does not place orders.
    """
    cfg = config or {}
    atr = max(_f(atr), 1e-9)
    rows = _normalise_ticks(ticks)
    if len(rows) < int(cfg.get("minTicks", 8)):
        return ImpulsePrediction(None, 0.0, "COLLECTING", 0, 0, 0, 0, 0, 0, 0, 0, "insufficient tick sample")

    window_s = max(2.0, _f(cfg.get("windowSeconds", 12.0), 12.0))
    cutoff = rows[-1][0] - window_s
    rows = [row for row in rows if row[0] >= cutoff]
    if len(rows) < 6:
        return ImpulsePrediction(None, 0.0, "COLLECTING", 0, 0, 0, 0, 0, 0, 0, 0, "insufficient recent ticks")

    prices = [row[1] for row in rows]
    times = [row[0] for row in rows]
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    net = prices[-1] - prices[0]
    side = "BUY" if net > 0 else "SELL" if net < 0 else None
    if side is None:
        return ImpulsePrediction(None, 0.0, "WATCH", 0, 0, 0, 0, 0, 0, 0, 0, "no directional movement")
    sign = 1.0 if side == "BUY" else -1.0

    elapsed = max(times[-1] - times[0], 0.05)
    velocity_atr_s = (net * sign / atr) / elapsed
    velocity_score = _clamp(velocity_atr_s / max(_f(cfg.get("velocityAtrPerSecond", 0.018), 0.018), 1e-6))

    mid = max(2, len(rows) // 2)
    first_elapsed = max(times[mid - 1] - times[0], 0.05)
    second_elapsed = max(times[-1] - times[mid - 1], 0.05)
    first_v = ((prices[mid - 1] - prices[0]) * sign / atr) / first_elapsed
    second_v = ((prices[-1] - prices[mid - 1]) * sign / atr) / second_elapsed
    acceleration = second_v - first_v
    acceleration_score = _clamp(acceleration / max(_f(cfg.get("accelerationAtrPerSecond", 0.012), 0.012), 1e-6))

    aligned = sum(1 for change in changes if change * sign > 0)
    nonzero = max(1, sum(1 for change in changes if change != 0))
    directional_ratio = aligned / nonzero
    directional_score = _clamp((directional_ratio - 0.52) / 0.36)

    spreads = [row[2] for row in rows if row[2] > 0]
    baseline_spread = median(spreads[:-2]) if len(spreads) > 3 else max_spread
    latest_tick_spread = spreads[-1] if spreads else 0.0
    observed_spread = max(max(0.0, current_spread), latest_tick_spread)
    spread_limit = max(max_spread, 1e-9)
    spread_score = _clamp(1.0 - observed_spread / spread_limit)
    if baseline_spread > 0 and observed_spread > baseline_spread * _f(cfg.get("spreadExpansionMultiple", 1.8), 1.8):
        spread_score *= 0.45

    recent = candles[-12:] if candles else []
    ranges = [max(0.0, _f(c.get("high")) - _f(c.get("low"))) for c in recent[:-1]]
    baseline_range = median([value for value in ranges if value > 0]) if ranges else atr
    pre_range = median(ranges[-5:]) if len(ranges) >= 5 else baseline_range
    compression_ratio = pre_range / max(baseline_range, 1e-9)
    compressed = compression_ratio <= _f(cfg.get("compressionRatio", 0.72), 0.72)

    live_candle_analysis = bool(cfg.get("liveCandleAnalysis", True))
    live = (recent[-1] if live_candle_analysis else (recent[-2] if len(recent) >= 2 else (recent[-1] if recent else {}))) if recent else {}
    live_open = _f(live.get("open"), prices[0])
    live_close = prices[-1]
    live_high = max(_f(live.get("high"), live_close), max(prices))
    live_low = min(_f(live.get("low"), live_close), min(prices))
    live_body_atr = abs(live_close - live_open) / atr
    candle_score = _clamp(live_body_atr / max(_f(cfg.get("earlyBodyAtr", 0.32), 0.32), 1e-6))

    prior_high = max((_f(c.get("high")) for c in recent[-7:-1]), default=live_high)
    prior_low = min((_f(c.get("low")) for c in recent[-7:-1]), default=live_low)
    breakout_distance = (live_close - prior_high) / atr if side == "BUY" else (prior_low - live_close) / atr
    compression_release_score = _clamp((breakout_distance + 0.08) / 0.28)
    if compressed:
        compression_release_score = min(1.0, compression_release_score + 0.25)

    candle_range = max(live_high - live_low, 1e-9)
    upper_wick = live_high - max(live_open, live_close)
    lower_wick = min(live_open, live_close) - live_low
    rejection_wick = upper_wick if side == "BUY" else lower_wick
    sweep_penalty = _clamp((rejection_wick / candle_range - 0.35) / 0.40)
    # A breakout that immediately closes back inside prior structure is likely a sweep.
    if side == "BUY" and live_high > prior_high and live_close < prior_high:
        sweep_penalty = max(sweep_penalty, 0.85)
    if side == "SELL" and live_low < prior_low and live_close > prior_low:
        sweep_penalty = max(sweep_penalty, 0.85)

    displacement_atr = abs(net) / atr
    weighted = (
        0.24 * velocity_score
        + 0.18 * acceleration_score
        + 0.18 * directional_score
        + 0.16 * compression_release_score
        + 0.10 * spread_score
        + 0.14 * candle_score
        - 0.22 * sweep_penalty
    )
    probability = _clamp(weighted)

    probe_threshold = _f(cfg.get("probeProbability", 0.70), 0.70)
    confirm_threshold = _f(cfg.get("confirmProbability", 0.82), 0.82)
    if bool(cfg.get("dynamicThresholds", True)):
        # Compression releases earn a small earlier threshold; weak spread or
        # directional quality raises it.  Bounds prevent a permissive runaway.
        adjustment = -0.035 * compression_release_score + 0.025 * (1.0 - spread_score) + 0.020 * (1.0 - directional_score)
        probe_threshold = _clamp(probe_threshold + adjustment, 0.58, 0.90)
        confirm_threshold = _clamp(confirm_threshold + adjustment * 0.7, probe_threshold + 0.06, 0.96)
    min_probe_disp = _f(cfg.get("minProbeDisplacementAtr", 0.16), 0.16)
    min_confirm_disp = _f(cfg.get("minConfirmDisplacementAtr", 0.30), 0.30)
    if probability >= confirm_threshold and displacement_atr >= min_confirm_disp:
        stage = "CONFIRMED"
    elif bool(cfg.get("progressiveExecution", True)) and probability >= probe_threshold and displacement_atr >= min_probe_disp:
        stage = "PROBE"
    else:
        stage = "WATCH"

    reason = (
        f"{side} early impulse {stage}: p={probability:.2f}, velocity={velocity_score:.2f}, "
        f"acceleration={acceleration_score:.2f}, persistence={directional_score:.2f}, "
        f"compressionRelease={compression_release_score:.2f}, sweepPenalty={sweep_penalty:.2f}, "
        f"move={displacement_atr:.2f} ATR"
    )
    return ImpulsePrediction(
        side, round(probability, 4), stage, round(velocity_score, 4),
        round(acceleration_score, 4), round(directional_score, 4),
        round(compression_release_score, 4), round(spread_score, 4),
        round(candle_score, 4), round(sweep_penalty, 4),
        round(displacement_atr, 4), reason,
    )
