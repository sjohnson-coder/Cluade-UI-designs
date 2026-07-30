from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    out = values[0]
    for value in values[1:]:
        out = alpha * value + (1.0 - alpha) * out
    return out


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) < 2:
        return 50.0
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    sample = diffs[-period:]
    gains = sum(max(0.0, x) for x in sample) / max(1, len(sample))
    losses = sum(max(0.0, -x) for x in sample) / max(1, len(sample))
    if losses <= 1e-12:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def _stochastic(rows: list[dict[str, Any]], period: int = 14) -> float:
    if not rows:
        return 50.0
    sample = rows[-period:]
    high = max(_f(row.get("high"), _f(row.get("close"))) for row in sample)
    low = min(_f(row.get("low"), _f(row.get("close"))) for row in sample)
    close = _f(sample[-1].get("close"))
    if high <= low:
        return 50.0
    return 100.0 * (close - low) / (high - low)


def _run_bars(closes: list[float], side: str) -> int:
    sign = 1.0 if side == "BUY" else -1.0
    run = 0
    for index in range(len(closes) - 1, 0, -1):
        delta = closes[index] - closes[index - 1]
        if delta * sign > 0:
            run += 1
        else:
            break
    return run


@dataclass(frozen=True)
class IntentContextAssessment:
    allowed: bool
    score: float
    terminal_acceleration: bool
    rsi: float
    stochastic: float
    extension_atr: float
    leg_move_atr: float
    run_bars: int
    range_position: float
    m5_aligned: bool
    m15_aligned: bool
    m15_transition: bool
    reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def qualify_intent_context(
    *,
    side: str,
    m5_candles: list[dict[str, Any]],
    m15_candles: list[dict[str, Any]],
    atr: float,
    intent: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> IntentContextAssessment:
    """Fast, deterministic context gate for a microstructure intent candidate.

    It distinguishes a fresh expansion from terminal acceleration using only cached
    candles.  It performs no broker or network calls and is safe on the priority lane.
    """
    cfg = config or {}
    intent = intent or {}
    side = str(side or "").upper()
    reasons: list[str] = []
    if side not in {"BUY", "SELL"} or len(m5_candles) < 20:
        return IntentContextAssessment(False, 0.0, False, 50.0, 50.0, 0.0, 0.0, 0, 0.5, False, False, False, ["insufficient M5 context"])

    atr = max(_f(atr), 1e-9)
    closes = [_f(row.get("close")) for row in m5_candles if _f(row.get("close")) > 0]
    if len(closes) < 20:
        return IntentContextAssessment(False, 0.0, False, 50.0, 50.0, 0.0, 0.0, 0, 0.5, False, False, False, ["insufficient valid M5 closes"])

    price = closes[-1]
    ema20 = _ema(closes[-80:], 20)
    ema50 = _ema(closes[-100:], 50 if len(closes) >= 50 else min(34, len(closes)))
    sign = 1.0 if side == "BUY" else -1.0
    extension_atr = abs(price - ema20) / atr
    m5_aligned = (price > ema20 and ema20 >= ema50) if side == "BUY" else (price < ema20 and ema20 <= ema50)

    leg_bars = max(5, min(int(_f(cfg.get("legBars", 8), 8)), 14))
    leg_rows = m5_candles[-leg_bars:]
    if side == "BUY":
        leg_anchor = min(_f(row.get("low"), _f(row.get("close"))) for row in leg_rows)
        leg_move_atr = max(0.0, price - leg_anchor) / atr
    else:
        leg_anchor = max(_f(row.get("high"), _f(row.get("close"))) for row in leg_rows)
        leg_move_atr = max(0.0, leg_anchor - price) / atr

    range_rows = m5_candles[-20:]
    range_high = max(_f(row.get("high"), _f(row.get("close"))) for row in range_rows)
    range_low = min(_f(row.get("low"), _f(row.get("close"))) for row in range_rows)
    range_position = (price - range_low) / max(range_high - range_low, 1e-9)

    rsi = _rsi(closes)
    stochastic = _stochastic(m5_candles)
    run_bars = _run_bars(closes, side)

    m15_closes = [_f(row.get("close")) for row in m15_candles if _f(row.get("close")) > 0]
    m15_aligned = False
    m15_transition = False
    if len(m15_closes) >= 8:
        m15_e20 = _ema(m15_closes[-60:], 20)
        m15_e50 = _ema(m15_closes[-100:], 50 if len(m15_closes) >= 50 else min(34, len(m15_closes)))
        m15_price = m15_closes[-1]
        m15_aligned = (m15_price > m15_e20 and m15_e20 >= m15_e50) if side == "BUY" else (m15_price < m15_e20 and m15_e20 <= m15_e50)
        recent_delta = (m15_closes[-1] - m15_closes[-4]) * sign if len(m15_closes) >= 4 else 0.0
        ema_delta = (m15_e20 - _ema(m15_closes[:-1][-60:], 20)) * sign if len(m15_closes) > 8 else 0.0
        m15_transition = recent_delta > 0 and ema_delta >= 0

    high_rsi = _f(cfg.get("exhaustionRsiHigh", 72.0), 72.0)
    low_rsi = _f(cfg.get("exhaustionRsiLow", 28.0), 28.0)
    high_stoch = _f(cfg.get("exhaustionStochHigh", 88.0), 88.0)
    low_stoch = _f(cfg.get("exhaustionStochLow", 12.0), 12.0)
    swing_edge = _f(cfg.get("terminalSwingPosition", 0.12), 0.12)
    max_leg = max(0.25, _f(cfg.get("maxLegMoveAtr", 1.10), 1.10))
    max_run = max(3, int(_f(cfg.get("maxRunBars", 6), 6)))
    max_extension = max(0.10, _f(cfg.get("maxExtensionAtr", 0.70), 0.70))
    at_edge = range_position >= 1.0 - swing_edge if side == "BUY" else range_position <= swing_edge
    oscillator_exhausted = (rsi >= high_rsi or stochastic >= high_stoch) if side == "BUY" else (rsi <= low_rsi or stochastic <= low_stoch)
    terminal = bool(at_edge and oscillator_exhausted and (leg_move_atr >= max_leg or (run_bars > max_run and extension_atr >= max_extension * 0.75)))

    reversal_penalty = _clamp(_f(intent.get("reversal_penalty")))
    structure_score = _clamp(_f(intent.get("structure_score"), 0.0))
    acceleration_score = _clamp(_f(intent.get("acceleration_score"), 0.0))
    freshness = _clamp(1.0 - leg_move_atr / max(max_leg * 1.25, 1e-9))
    extension_score = _clamp(1.0 - extension_atr / max(max_extension, 1e-9))
    oscillator_safe = 0.0 if oscillator_exhausted else 1.0
    htf_score = 1.0 if m15_aligned else 0.70 if m15_transition else 0.0

    score = _clamp(
        0.19 * (1.0 if m5_aligned else 0.25)
        + 0.17 * htf_score
        + 0.16 * structure_score
        + 0.12 * freshness
        + 0.10 * extension_score
        + 0.10 * oscillator_safe
        + 0.08 * acceleration_score
        + 0.08 * (1.0 - reversal_penalty)
    )

    if terminal:
        reasons.append(f"terminal acceleration/exhaustion: leg {leg_move_atr:.2f} ATR, run {run_bars}, RSI {rsi:.1f}, stochastic {stochastic:.1f}")
    if extension_atr > max_extension:
        reasons.append(f"context extension {extension_atr:.2f} ATR exceeds {max_extension:.2f}")
    if reversal_penalty > _f(cfg.get("maxReversalPenalty", 0.28), 0.28):
        reasons.append(f"reversal penalty {reversal_penalty:.2f} too high")
    require_m15 = bool(cfg.get("requireM15Support", True))
    if require_m15 and not (m15_aligned or m15_transition):
        reasons.append("M15 neither aligned nor transitioning with intent")
    if not m5_aligned and structure_score < _f(cfg.get("unalignedStructureFloor", 0.75), 0.75):
        reasons.append("M5 trend location opposes intent without a strong structure break")
    min_score = _f(cfg.get("minScore", 0.58), 0.58)
    if score < min_score:
        reasons.append(f"context score {score:.2f} below {min_score:.2f}")

    return IntentContextAssessment(
        allowed=not reasons,
        score=round(score, 4),
        terminal_acceleration=terminal,
        rsi=round(rsi, 2),
        stochastic=round(stochastic, 2),
        extension_atr=round(extension_atr, 4),
        leg_move_atr=round(leg_move_atr, 4),
        run_bars=run_bars,
        range_position=round(range_position, 4),
        m5_aligned=m5_aligned,
        m15_aligned=m15_aligned,
        m15_transition=m15_transition,
        reasons=reasons,
    )
