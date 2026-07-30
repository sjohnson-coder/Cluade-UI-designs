"""V13.11 — Market regime classifier (Phase 3 of the GodMode roadmap).

Research-grounded premise: the single biggest predictor of a strategy's profitability is
whether it matches CURRENT market behaviour — one engine run identically through trend,
chop and news-shock loses over a full cycle. This module classifies each scan into one of
four regimes from plain M5 candle facts (no ML, no fitting, fully explainable):

  TREND      — directional efficiency high: closes travel a large fraction of the range
  RANGE      — low efficiency, price oscillating inside a compressed band
  SHOCK      — volatility explosion (current ATR-window >> baseline) or news blackout
  QUIET      — dead tape: range too small for scalp targets to clear costs

The classifier only NAMES the weather. What each engine may do per regime lives in
settings (automation.regimePolicy) so it is inspectable, journal-able and coach-tunable.
"""
from __future__ import annotations

from typing import Any


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def classify_regime(candles: list[dict[str, Any]], news_blackout: bool = False,
                    lookback: int = 36, baseline: int = 288) -> dict[str, Any]:
    """Classify from closed M5 candles. lookback=36 bars = 3 hours of 'now';
    baseline=288 bars = 24 hours of context. Returns regime + the evidence."""
    if news_blackout:
        return {"regime": "SHOCK", "reason": "news blackout window", "confidence": 0.95}
    rows = [c for c in (candles or []) if c.get("high") is not None]
    if len(rows) < baseline:
        return {"regime": "UNKNOWN", "reason": f"need {baseline} candles, have {len(rows)}", "confidence": 0.0}
    recent = rows[-lookback:]
    base = rows[-baseline:]

    def tr(c: dict[str, Any], prev_close: float) -> float:
        hi, lo = _f(c.get("high")), _f(c.get("low"))
        return max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))

    # ATR of the recent window vs the 24h baseline: the volatility ratio
    atr_recent = sum(tr(c, _f(recent[i - 1].get("close")) if i else _f(c.get("open"))) for i, c in enumerate(recent)) / max(1, len(recent))
    atr_base = sum(tr(c, _f(base[i - 1].get("close")) if i else _f(c.get("open"))) for i, c in enumerate(base)) / max(1, len(base))
    vol_ratio = atr_recent / max(atr_base, 1e-9)

    # Directional efficiency (Kaufman-style): |net move| / sum(|bar moves|) over the window.
    closes = [_f(c.get("close")) for c in recent]
    net = abs(closes[-1] - closes[0])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))) or 1e-9
    efficiency = net / path

    # Window range in ATR units: distinguishes QUIET (tiny) from RANGE (normal, oscillating)
    win_hi = max(_f(c.get("high")) for c in recent)
    win_lo = min(_f(c.get("low")) for c in recent)
    range_atr = (win_hi - win_lo) / max(atr_base, 1e-9)

    if vol_ratio >= 2.2:
        regime, conf, why = "SHOCK", min(0.95, 0.5 + (vol_ratio - 2.2) / 3), f"volatility {vol_ratio:.1f}x its 24h baseline"
    elif efficiency >= 0.35 and range_atr >= 4.0:
        regime, conf, why = "TREND", min(0.95, efficiency + 0.3), f"directional efficiency {efficiency:.2f}, {range_atr:.1f} ATR travelled"
    elif range_atr < 2.0:
        regime, conf, why = "QUIET", 0.7, f"3h range only {range_atr:.1f} ATR — targets cannot clear costs"
    else:
        regime, conf, why = "RANGE", 0.7, f"efficiency {efficiency:.2f} with {range_atr:.1f} ATR of oscillation"
    return {"regime": regime, "reason": why, "confidence": round(conf, 2),
            "evidence": {"volRatio": round(vol_ratio, 2), "efficiency": round(efficiency, 3),
                         "rangeAtr": round(range_atr, 2), "atrRecent": round(atr_recent, 3)}}


DEFAULT_REGIME_POLICY: dict[str, dict[str, bool]] = {
    # What each regime PERMITS. Mirrors current behaviour closely on TREND so switching this on
    # does not silently strangle trade frequency; the protective changes are RANGE (no counter-HTF
    # momentum chasing inside chop — fake pumps live there) and QUIET (stand down: spread eats
    # every target on a dead tape). SHOCK entry-blocking already exists via the news gate; brackets
    # stay allowed because a pre-placed stop at a base edge is exactly the shock-day instrument.
    "TREND": {"sniper": True, "momentum": True, "counterHtfMomentum": True, "brackets": True},
    "RANGE": {"sniper": True, "momentum": True, "counterHtfMomentum": False, "brackets": True},
    "SHOCK": {"sniper": False, "momentum": False, "counterHtfMomentum": False, "brackets": True},
    "QUIET": {"sniper": False, "momentum": False, "counterHtfMomentum": False, "brackets": False},
    "UNKNOWN": {"sniper": True, "momentum": True, "counterHtfMomentum": True, "brackets": True},
}
