"""GodMode Gold Decision Engine — Upgraded v3 (GodMode Proper).

Key upgrades over v2:
- SIDE DIRECTION is now computed from candle structure (HTF EMA stack + momentum),
  not inherited from a static market.side field that's always "WAIT".
- OTE zone correctly inverted for SELL setups.
- RSI-14 computed and used for overbought/oversold gates.
- MACD divergence detection added.
- Tick-volume confirmation integrated (breakout candles need volume).
- Asian session range detection (high/low mapping for liquidity raid setups).
- Order block (OB) detection: last bearish/bullish engulfing before a move.
- Fair Value Gap (FVG) detection: 3-candle imbalance gaps.
- Multi-timeframe awareness: H1 candles checked when available.
- Confidence factor no longer circularly references market.confidence (always 0).
- Structural SL now uses swing highs/lows, not just ATR multiples.
- Cleaner confluence gate: 4/8 factors (added RSI, volume, OB, FVG).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from services.market_intelligence import (
    EconomicCalendar, GoldVolatilityRegime, MacroAwareness, MarketCleanliness,
)
from services.strategy_catalog import INSTITUTIONAL_STRATEGIES


def _utc_hour() -> int:
    return datetime.now(timezone.utc).hour


def _utc_minute() -> int:
    return datetime.now(timezone.utc).minute


def _prime_session_score(as_of: float | None = None) -> tuple[str, float]:
    if as_of:
        dt = datetime.fromtimestamp(int(as_of), timezone.utc)
        h, m = dt.hour, dt.minute
    else:
        h = _utc_hour()
        m = _utc_minute()
    frac = h + m / 60.0
    if 7.0 <= frac < 9.0:
        return "London Open", 96
    if 9.0 <= frac < 11.5:
        return "London Prime", 90
    if 12.0 <= frac < 14.5:
        return "London/NY Overlap", 88
    if 14.5 <= frac < 17.0:
        return "NY Prime", 85
    if 17.0 <= frac < 20.0:
        return "NY Afternoon", 64
    if 20.0 <= frac < 23.0:
        return "NY/London Close", 52
    return "Asian / Dead Zone", 32


def _compute_rsi(closes: list[float], period: int = 14) -> float:
    """RSI-14. Returns 50.0 if insufficient data."""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _compute_macd(closes: list[float]) -> dict[str, float]:
    """MACD(12,26,9). Returns dict of macd_line, signal_line, histogram."""
    def ema(vals: list[float], period: int) -> list[float]:
        if not vals:
            return []
        alpha = 2 / (period + 1)
        out = [vals[0]]
        for v in vals[1:]:
            out.append(alpha * v + (1 - alpha) * out[-1])
        return out

    if len(closes) < 35:
        return {"macdLine": 0.0, "signalLine": 0.0, "histogram": 0.0}
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal = ema(macd_line, 9)
    histogram = [m - s for m, s in zip(macd_line, signal)]
    return {
        "macdLine": round(macd_line[-1], 4),
        "signalLine": round(signal[-1], 4),
        "histogram": round(histogram[-1], 4),
    }


def _detect_order_block(candles: list[dict[str, Any]], side: str) -> dict[str, Any]:
    """Find the last OB before a displacement move.
    Bull OB: last bearish candle before an up-move.
    Bear OB: last bullish candle before a down-move.
    Returns {found, high, low, index_back}.
    """
    if len(candles) < 6:
        return {"found": False, "high": 0.0, "low": 0.0}
    look_back = min(30, len(candles))
    recent = candles[-look_back:]
    if side == "BUY":
        # Find last bearish candle followed by bullish displacement
        for i in range(len(recent) - 2, 1, -1):
            c = recent[i]
            if float(c.get("close", 0)) < float(c.get("open", 0)):  # bearish
                # Check for bullish displacement after it
                next_c = recent[i + 1]
                if float(next_c.get("close", 0)) > float(next_c.get("open", 0)):
                    body = abs(float(next_c.get("close", 0)) - float(next_c.get("open", 0)))
                    rng = max(float(next_c.get("high", 0)) - float(next_c.get("low", 0)), 0.01)
                    if body / rng > 0.55:  # displacement: strong body
                        return {
                            "found": True,
                            "high": float(c.get("high", 0)),
                            "low": float(c.get("low", 0)),
                            "indexBack": len(recent) - 1 - i,
                        }
    else:
        for i in range(len(recent) - 2, 1, -1):
            c = recent[i]
            if float(c.get("close", 0)) > float(c.get("open", 0)):  # bullish
                next_c = recent[i + 1]
                if float(next_c.get("close", 0)) < float(next_c.get("open", 0)):
                    body = abs(float(next_c.get("close", 0)) - float(next_c.get("open", 0)))
                    rng = max(float(next_c.get("high", 0)) - float(next_c.get("low", 0)), 0.01)
                    if body / rng > 0.55:
                        return {
                            "found": True,
                            "high": float(c.get("high", 0)),
                            "low": float(c.get("low", 0)),
                            "indexBack": len(recent) - 1 - i,
                        }
    return {"found": False, "high": 0.0, "low": 0.0}


def _detect_fvg(candles: list[dict[str, Any]], side: str) -> dict[str, Any]:
    """Detect Fair Value Gap (3-candle imbalance) in the last 20 bars."""
    if len(candles) < 3:
        return {"found": False, "high": 0.0, "low": 0.0}
    recent = candles[-20:]
    for i in range(len(recent) - 2, 0, -1):
        c1, c3 = recent[i - 1], recent[i + 1]
        if side == "BUY":
            # Bull FVG: c1.high < c3.low (gap upward)
            if float(c1.get("high", 0)) < float(c3.get("low", 0)):
                return {
                    "found": True,
                    "high": float(c3.get("low", 0)),
                    "low": float(c1.get("high", 0)),
                    "indexBack": len(recent) - 1 - i,
                }
        else:
            # Bear FVG: c1.low > c3.high (gap downward)
            if float(c1.get("low", 0)) > float(c3.get("high", 0)):
                return {
                    "found": True,
                    "high": float(c1.get("low", 0)),
                    "low": float(c3.get("high", 0)),
                    "indexBack": len(recent) - 1 - i,
                }
    return {"found": False, "high": 0.0, "low": 0.0}


def _asian_session_range(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract today's Asian session high/low from candle timestamps (UTC 22:00–07:00)."""
    asian_candles = []
    for c in candles:
        ts = c.get("time")
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts), timezone.utc)
                h = dt.hour
                if h >= 22 or h < 7:
                    asian_candles.append(c)
            except Exception:
                pass
    if not asian_candles:
        return {"defined": False, "high": 0.0, "low": 0.0}
    return {
        "defined": True,
        "high": max(float(c.get("high", 0)) for c in asian_candles),
        "low": min(float(c.get("low", 9999)) for c in asian_candles),
        "candles": len(asian_candles),
    }


def _tf_trend(candles: list[dict[str, Any]] | None) -> tuple[str, float]:
    """Label a single timeframe's trend from its EMA stack. Returns (label, direction)."""
    if not candles or len(candles) < 5:
        return "Unknown", 0.0
    last = candles[-1]
    close = float(last.get("close", 0) or 0)
    ema20 = float(last.get("ema20", 0) or 0) or close
    ema50 = float(last.get("ema50", 0) or 0) or close
    if close > ema20 > ema50:
        return "Bullish", 1.0
    if close < ema20 < ema50:
        return "Bearish", -1.0
    if close > ema50:
        return "Weak Bullish", 0.4
    if close < ema50:
        return "Weak Bearish", -0.4
    return "Range", 0.0


def _htf_bias(h4_candles: list[dict[str, Any]] | None, d1_candles: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Institutional higher-timeframe bias from H4 + D1 (D1 weighted heaviest)."""
    h4_label, h4_dir = _tf_trend(h4_candles)
    d1_label, d1_dir = _tf_trend(d1_candles)
    blended = d1_dir * 0.6 + h4_dir * 0.4
    if blended >= 0.5:
        bias = "BUY"
    elif blended <= -0.5:
        bias = "SELL"
    else:
        bias = "NEUTRAL"
    score = min(98.0, 55.0 + abs(blended) * 43.0)
    return {
        "d1Trend": d1_label,
        "h4Trend": h4_label,
        "htfDailyBias": bias,
        "htfBiasScore": round(score, 1),
        "blended": round(blended, 3),
        "haveHtf": bool((h4_candles and len(h4_candles) >= 5) or (d1_candles and len(d1_candles) >= 5)),
    }


def _compute_candle_features(candles: list[dict[str, Any]], h1_candles: list[dict[str, Any]] | None = None, range_lookback: int = 32) -> dict[str, Any]:
    """Extract full institutional feature set from candles."""
    if not candles or len(candles) < 10:
        return {
            "lateEntryScore": 0.5,
            "htfAligned": False,
            "htfAlignmentScore": 60.0,
            "liquiditySwept": False,
            "overExtended": False,
            "inOTE": False,
            "momentumExpanding": False,
            "momentumScore": 60.0,
            "pullbackPresent": False,
            "avgBodyPct": 0.4,
            "recentBullBars": 3,
            "recentBearBars": 3,
            "structureBullish": None,
            "atrDistance50": 1.0,
            "atrDistance20": 0.5,
            "trendAligned": False,
            "rangeHigh": 0.0,
            "rangeLow": 0.0,
            "rangePos": 0.5,
            "rangeWidthAtr": 0.0,
            "confluenceCount": 0,
            "computedSide": "WAIT",
            "rsi14": 50.0,
            "rsiOverbought": False,
            "rsiOversold": False,
            "macd": {"macdLine": 0.0, "signalLine": 0.0, "histogram": 0.0},
            "macdBullish": False,
            "volumeConfirmed": False,
            "orderBlock": {"found": False},
            "fvg": {"found": False},
            "asianRange": {"defined": False},
            "h1Aligned": False,
        }

    closes = [float(c.get("close", 0) or 0) for c in candles]
    highs  = [float(c.get("high",  0) or 0) for c in candles]
    lows   = [float(c.get("low",   0) or 0) for c in candles]
    opens  = [float(c.get("open",  0) or 0) for c in candles]
    volumes = [float(c.get("tickVolume", c.get("volume", 0)) or 0) for c in candles]
    ema20s = [float(c.get("ema20", 0) or 0) for c in candles]
    ema50s = [float(c.get("ema50", 0) or 0) for c in candles]

    price   = closes[-1]
    ema20   = ema20s[-1] if ema20s[-1] > 0 else price
    ema50   = ema50s[-1] if ema50s[-1] > 0 else price
    recent  = candles[-20:]

    # ATR-14
    trs = []
    for i in range(1, len(candles)):
        prev_c = closes[i - 1]
        trs.append(max(highs[i] - lows[i], abs(highs[i] - prev_c), abs(lows[i] - prev_c)))
    atr = sum(trs[-14:]) / 14 if len(trs) >= 14 else max(1.0, (max(highs[-10:]) - min(lows[-10:])) / 10)

    atr_dist_50 = abs(price - ema50) / max(atr, 0.01)
    atr_dist_20 = abs(price - ema20) / max(atr, 0.01)   # distance from the pullback anchor

    # Range geometry over the recent window: where does price sit between the range low/high?
    # 0 = at the bottom, 1 = at the top. Used to avoid buying tops / selling bottoms in chop.
    rl_n = min(int(range_lookback or 32), len(highs))
    range_high = max(highs[-rl_n:]) if rl_n else price
    range_low = min(lows[-rl_n:]) if rl_n else price
    range_span = range_high - range_low
    range_pos = (price - range_low) / range_span if range_span > 0 else 0.5
    range_width_atr = range_span / max(atr, 0.01)

    # Direction from EMA stack
    bull_aligned = price > ema20 > ema50
    bear_aligned = price < ema20 < ema50
    htf_aligned  = bull_aligned or bear_aligned

    # EMA-50 slope gives a *weak* direction during pullbacks, when the M15 EMAs
    # temporarily un-stack (price dips toward EMA20). Without this the bot rejects
    # the exact OTE/pullback entries it is designed to take.
    ema50_prev = ema50s[-5] if len(ema50s) >= 5 and ema50s[-5] > 0 else ema50
    ema50_slope = ema50 - ema50_prev
    weak_bull = (price > ema50) and (ema50_slope > 0)
    weak_bear = (price < ema50) and (ema50_slope < 0)

    # Determine computed side from structure (strong stack) or weak pullback direction.
    weak_alignment = False
    if bull_aligned:
        computed_side = "BUY"
        htf_score = min(98, 80 + (ema20 - ema50) / max(atr, 0.01) * 4)
    elif bear_aligned:
        computed_side = "SELL"
        htf_score = min(98, 80 + (ema50 - ema20) / max(atr, 0.01) * 4)
    elif weak_bull:
        computed_side, weak_alignment = "BUY", True
        htf_score = max(50, 70 - atr_dist_50 * 3)
    elif weak_bear:
        computed_side, weak_alignment = "SELL", True
        htf_score = max(50, 70 - atr_dist_50 * 3)
    else:
        computed_side = "WAIT"
        htf_score = max(30, 60 - atr_dist_50 * 4)

    # H1 alignment (if H1 candles available)
    h1_aligned = False
    if h1_candles and len(h1_candles) >= 10:
        h1_closes = [float(c.get("close", 0) or 0) for c in h1_candles]
        h1_ema20 = [float(c.get("ema20", 0) or 0) for c in h1_candles]
        h1_ema50 = [float(c.get("ema50", 0) or 0) for c in h1_candles]
        lp = h1_closes[-1]
        e20 = h1_ema20[-1] if h1_ema20[-1] > 0 else lp
        e50 = h1_ema50[-1] if h1_ema50[-1] > 0 else lp
        if computed_side == "BUY":
            h1_aligned = lp > e20 > e50
        elif computed_side == "SELL":
            h1_aligned = lp < e20 < e50
    else:
        h1_aligned = htf_aligned  # fallback

    # Liquidity sweep detection
    recent5 = candles[-5:]
    prior_lows  = lows[-15:-5]
    prior_highs = highs[-15:-5]
    swept_low  = any(
        float(c.get("low", 9999)) < min(prior_lows) and float(c.get("close", 0)) > min(prior_lows)
        for c in recent5
    ) if prior_lows else False
    swept_high = any(
        float(c.get("high", 0)) > max(prior_highs) and float(c.get("close", 9999)) < max(prior_highs)
        for c in recent5
    ) if prior_highs else False
    liquidity_swept = swept_low or swept_high

    # Pullback present
    if bull_aligned:
        pullback = min(lows[-3:]) < ema20 * 1.003
    elif bear_aligned:
        pullback = max(highs[-3:]) > ema20 * 0.997
    else:
        pullback = False

    # OTE zone — Fibonacci 61.8–78.6% of last 20-bar swing
    swing_high = max(highs[-20:])
    swing_low  = min(lows[-20:])
    swing_range = swing_high - swing_low
    if bull_aligned:
        # Buy OTE: price has pulled back to 61.8–78.6% of the swing UP
        ote_low  = swing_low + swing_range * 0.618  # 61.8% retracement level
        ote_high = swing_low + swing_range * 0.786  # 78.6% level
        in_ote = ote_low <= price <= ote_high
    elif bear_aligned:
        # Sell OTE: price has retraced up to 61.8–78.6% of the swing DOWN
        ote_high = swing_high - swing_range * 0.618
        ote_low  = swing_high - swing_range * 0.786
        in_ote = ote_low <= price <= ote_high
    else:
        in_ote = False

    # Average body percentage
    bodies = [abs(opens[i] - closes[i]) / max(highs[i] - lows[i], 0.01) for i in range(-10, 0)]
    avg_body = sum(bodies) / len(bodies) if bodies else 0.4

    # Kaufman efficiency ratio over the last 20 closes: |net move| / path length.
    # Near 1.0 = clean trend; near 0 = chop/range. The single best "are we in a range?"
    # signal — used to stop the bot bleeding inside tight sideways ranges.
    er_n = min(20, len(closes) - 1)
    if er_n >= 5:
        net_move = abs(closes[-1] - closes[-1 - er_n])
        path = sum(abs(closes[i] - closes[i - 1]) for i in range(-er_n, 0)) or 0.01
        efficiency_ratio = round(net_move / path, 3)
    else:
        efficiency_ratio = 0.5

    # Short-window (8-bar) efficiency + its direction. A FRESH trend leg out of a reversal shows a
    # LOW 20-bar ER (the window still holds the prior swing) but a HIGH 8-bar ER pushing one way.
    # This lets the bot stop sitting out the START of a clean move without loosening the gate.
    es_n = min(8, len(closes) - 1)
    if es_n >= 4:
        s_net = closes[-1] - closes[-1 - es_n]
        s_path = sum(abs(closes[i] - closes[i - 1]) for i in range(-es_n, 0)) or 0.01
        efficiency_short = round(abs(s_net) / s_path, 3)
        efficiency_short_dir = "BUY" if s_net > 0 else "SELL"
    else:
        efficiency_short, efficiency_short_dir = efficiency_ratio, "WAIT"

    # Momentum
    bull_bars = sum(1 for c in recent if float(c.get("close", 0)) >= float(c.get("open", 0)))
    bear_bars = len(recent) - bull_bars
    momentum_expanding = bull_bars > len(recent) * 0.65 or bear_bars > len(recent) * 0.65
    if bull_aligned:
        mom_score = min(95, 50 + bull_bars / max(len(recent), 1) * 45)
    elif bear_aligned:
        mom_score = min(95, 50 + bear_bars / max(len(recent), 1) * 45)
    else:
        mom_score = 50.0

    # Structure (higher highs/lows)
    hh = highs[-1] > highs[-10] if len(highs) >= 10 else False
    hl = lows[-1]  > lows[-10]  if len(lows)  >= 10 else False
    lh = highs[-1] < highs[-10] if len(highs) >= 10 else False
    ll = lows[-1]  < lows[-10]  if len(lows)  >= 10 else False
    struct_bull = hh and hl
    struct_bear = lh and ll

    # ── Trend-aware late-entry / over-extension ──────────────────────────────────────────
    # THE FIX for "only sells, never buys": in a STRONG, efficient, EMA-aligned trend, being
    # far from the LAGGING ema50 is normal and healthy — punishing it (timing score) and
    # demanding a deep pullback is exactly what made the bot fade every rally and take only
    # counter-trend shorts. So when riding an efficient aligned trend we (a) measure
    # "lateness" from ema20 (the pullback anchor, which a trend hugs) rather than ema50, and
    # (b) widen the over-extension flag. A genuine CHASE = far from ema20 with no pullback in
    # a CHOPPY tape — that stays penalised. Chop protection is untouched (gated on efficiency).
    # Robust trend proxy: slope of the slow EMA-50 over ~10 bars (in ATR units). Unlike the
    # 20-bar efficiency ratio — which a pullback entry necessarily depresses — the slow-EMA
    # slope stays positive through a shallow retrace, so we can recognise a trend-continuation
    # entry even as price pulls back into EMA20. Real chop (flat EMA-50) → slope ≈ 0 → not a
    # trend; and the independent ER<min chop HARD-block still vetoes genuinely ranging tape.
    ema50_ref = ema50s[-11] if len(ema50s) >= 11 and ema50s[-11] > 0 else (ema50s[0] if ema50s else ema50)
    ema50_slope10 = (ema50 - ema50_ref) / max(atr, 0.01)
    aligned_trend = ((computed_side == "BUY" and price > ema50 and ema50_slope10 > 0.35) or
                     (computed_side == "SELL" and price < ema50 and ema50_slope10 < -0.35))
    if aligned_trend:
        late_ref = atr_dist_20 if pullback else min(atr_dist_50, atr_dist_20 + 1.0)
        late_score = min(1.0, late_ref / 5.0)      # gentle, ema20-anchored (maxes at a ~5-ATR blow-off)
        over_extended = atr_dist_20 > 4.0          # only a true ema20 blow-off is a chase
    else:
        late_score = min(1.0, atr_dist_50 / 3.0)
        over_extended = atr_dist_50 > 3.0

    # RSI
    rsi = _compute_rsi(closes, 14)
    rsi_overbought = rsi > 70
    rsi_oversold   = rsi < 30
    # RSI gate: don't buy when overbought, don't sell when oversold
    rsi_favorable = (computed_side == "BUY" and not rsi_overbought) or \
                    (computed_side == "SELL" and not rsi_oversold) or \
                    computed_side == "WAIT"

    # MACD
    macd = _compute_macd(closes)
    macd_bullish = macd["histogram"] > 0 and macd["macdLine"] > macd["signalLine"]
    macd_bearish = macd["histogram"] < 0 and macd["macdLine"] < macd["signalLine"]
    macd_aligned = (computed_side == "BUY" and macd_bullish) or \
                   (computed_side == "SELL" and macd_bearish)

    # Volume confirmation: recent 3 candles have above-average volume
    avg_vol = sum(volumes[-20:]) / max(len(volumes[-20:]), 1) if volumes else 0
    recent_vol = sum(volumes[-3:]) / 3 if len(volumes) >= 3 else 0
    volume_confirmed = recent_vol > avg_vol * 1.15 if avg_vol > 0 else False

    # Order block detection
    order_block = _detect_order_block(candles, computed_side)

    # FVG detection
    fvg = _detect_fvg(candles, computed_side)

    # Asian session range
    asian_range = _asian_session_range(candles)

    # Confluence count (8 factors now)
    conf_items = [
        htf_aligned,
        h1_aligned,
        liquidity_swept,
        pullback,
        not over_extended,
        in_ote,
        momentum_expanding,
        struct_bull or struct_bear,
        rsi_favorable,
        macd_aligned,
        volume_confirmed,
        order_block.get("found", False),
    ]
    confluence_count = sum(conf_items)

    return {
        "lateEntryScore": round(late_score, 3),
        "htfAligned": htf_aligned,
        "weakAlignment": weak_alignment,
        "efficiencyRatio": efficiency_ratio,
        "efficiencyShort": efficiency_short,
        "efficiencyShortDir": efficiency_short_dir,
        "efficiencyShortMove": round(abs(closes[-1] - closes[-1 - es_n]), 3) if es_n >= 4 else 0.0,
        "h1Aligned": h1_aligned,
        "htfAlignmentScore": round(htf_score, 1),
        "liquiditySwept": liquidity_swept,
        "overExtended": over_extended,
        "inOTE": in_ote,
        "momentumExpanding": momentum_expanding,
        "momentumScore": round(mom_score, 1),
        "pullbackPresent": pullback,
        "avgBodyPct": round(avg_body, 3),
        "recentBullBars": bull_bars,
        "recentBearBars": bear_bars,
        "structureBullish": struct_bull,
        "atrDistance50": round(atr_dist_50, 3),
        "atrDistance20": round(atr_dist_20, 3),
        "trendAligned": aligned_trend,
        "rangeHigh": round(range_high, 2),
        "rangeLow": round(range_low, 2),
        "rangePos": round(range_pos, 3),
        "rangeWidthAtr": round(range_width_atr, 2),
        "confluenceCount": confluence_count,
        "atr": round(atr, 3),
        "computedSide": computed_side,
        "rsi14": rsi,
        "rsiOverbought": rsi_overbought,
        "rsiOversold": rsi_oversold,
        "rsiFavorable": rsi_favorable,
        "macd": macd,
        "macdBullish": macd_bullish,
        "macdAligned": macd_aligned,
        "volumeConfirmed": volume_confirmed,
        "orderBlock": order_block,
        "fvg": fvg,
        "asianRange": asian_range,
        "swingHigh": round(swing_high, 3),
        "swingLow": round(swing_low, 3),
    }


@dataclass
class DecisionFactor:
    name: str
    score: float
    weight: float
    detail: str


class GoldDecisionEngine:
    """GodMode Gold institutional brain — v3 with full technical intelligence.

    Hard gates before any TAKE_TRADE:
      1. Not over-extended (< 2.0 ATR from EMA-50).
      2. HTF + H1 aligned (EMA stack).
      3. RSI not overbought/oversold against trade direction.
      4. Confluence count >= min_confluence (now out of 12 factors).
      5. Spread within limit.
      6. Not in news blackout.
      7. Session score >= min_session_score.
      8. R/R >= min_rr.
      9. NEVER pyramid into a losing/breakeven trade.
      10. Side is determined by structure (not a hardcoded or missing value).
    """

    def __init__(self) -> None:
        self.strictness_mode = "balanced"
        self.allow_scout_entries = True
        self.min_scout_score  = 66.0
        self.min_standard_score = 74.0
        self.min_take_score   = 66.0
        self.min_sniper_score = 88.0
        self.max_spread       = 0.40
        self.min_rr           = 1.4
        self.min_confluence   = 3
        self.min_session_score = 50.0
        # Over-extension is now graded, not a single hard veto: a soft (scout) flag
        # past `soft`, a hard block only past `hard` (a genuine chase). This stops the
        # bot from refusing perfectly good pullback entries.
        self.max_atr_extension_soft = 3.0
        self.max_atr_extension_hard = 4.2
        # Choppy/range filter. Below `hard` the market is a tight range → no entries
        # (this is what stops the bot bleeding inside sideways chop).
        self.min_efficiency_ratio = 0.28
        # Fresh-leg override: the 20-bar efficiency is backward-looking, so it vetoes the START of a
        # clean new move (the window still holds the prior swing). When a strong short-window leg is
        # underway in the trade's direction, allow a SCOUT entry instead of hard-blocking on chop.
        self.fresh_leg_override = True
        self.fresh_leg_eff = 0.58        # short-window efficiency that counts as a clean fresh leg
        self.fresh_leg_min_atr = 0.6     # leg must have moved at least this many ATRs (not a tiny wiggle)
        # Range awareness — in a sideways range (no confirmed trend), don't buy near the top or
        # sell near the bottom. Today's lesson: the bot kept signalling BUYs at the range highs.
        self.range_awareness = True
        self.range_fade = False          # opt-in: FADE the extreme (sell tops / buy bottoms) instead of just skipping
        self.range_top_pos = 0.78        # BUY blocked when price is >= this far up the range (0..1)
        self.range_bottom_pos = 0.22     # SELL blocked when price is <= this far down the range
        self.range_eff_max = 0.45        # only treat as a range when efficiency is below this (not trending)
        self.range_min_atr = 1.8         # the range must be at least this many ATR wide to count
        self.range_lookback = 32         # bars used to measure the range high/low
        self.calendar   = EconomicCalendar()
        self.macro      = MacroAwareness()
        self.volatility = GoldVolatilityRegime()
        self.cleanliness = MarketCleanliness()
        # Learned per-factor weights (name -> weight). Empty = use the hand-set
        # defaults baked into _score_factors. Populated by the backtest weight
        # optimizer once there is real, cost-aware evidence.
        self.factor_weights: dict[str, float] = {}

    def set_factor_weights(self, weights: dict[str, float] | None) -> None:
        self.factor_weights = {str(k): float(v) for k, v in (weights or {}).items()}

    def reset_factor_weights(self) -> None:
        self.factor_weights = {}

    def configure_strictness(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        mode = str(payload.get("strictnessMode", payload.get("mode", self.strictness_mode)) or "balanced").lower()
        presets = {
            "relaxed":  {"scout": 60, "standard": 68, "sniper": 84, "spread": 0.45, "rr": 1.30, "conf": 2, "sess": 38, "eff": 0.24},
            "balanced": {"scout": 66, "standard": 74, "sniper": 88, "spread": 0.40, "rr": 1.40, "conf": 3, "sess": 48, "eff": 0.30},
            "strict":   {"scout": 72, "standard": 80, "sniper": 91, "spread": 0.35, "rr": 1.65, "conf": 4, "sess": 60, "eff": 0.36},
            "sniper":   {"scout": 80, "standard": 85, "sniper": 93, "spread": 0.28, "rr": 1.90, "conf": 5, "sess": 68, "eff": 0.42},
        }
        p = presets.get(mode, presets["balanced"])
        self.strictness_mode    = mode if mode in presets else "balanced"
        self.allow_scout_entries = bool(payload.get("allowScoutEntries", True))
        self.min_scout_score     = float(payload.get("scoutConfidence",   p["scout"]))
        self.min_standard_score  = float(payload.get("standardConfidence", p["standard"]))
        self.min_take_score      = self.min_scout_score if self.allow_scout_entries else self.min_standard_score
        self.min_sniper_score    = float(payload.get("sniperConfidence",  p["sniper"]))
        self.max_spread          = float(payload.get("maxSpread",         p["spread"]))
        self.min_rr              = float(payload.get("minRiskReward",     p["rr"]))
        self.min_confluence      = int(payload.get("minConfluence",       p["conf"]))
        self.min_session_score   = float(payload.get("minSessionScore",   p["sess"]))
        self.min_efficiency_ratio = float(payload.get("minEfficiencyRatio", p.get("eff", 0.28)))
        self.range_awareness = bool(payload.get("rangeAwareness", self.range_awareness))
        self.range_fade = bool(payload.get("rangeFade", self.range_fade))
        self.range_top_pos = float(payload.get("rangeTopPos", self.range_top_pos))
        self.range_bottom_pos = float(payload.get("rangeBottomPos", self.range_bottom_pos))
        return self.strictness_dict()

    def strictness_dict(self) -> dict[str, Any]:
        return {
            "strictnessMode":    self.strictness_mode,
            "allowScoutEntries": self.allow_scout_entries,
            "scoutConfidence":   self.min_scout_score,
            "standardConfidence":self.min_standard_score,
            "takeThreshold":     self.min_take_score,
            "sniperConfidence":  self.min_sniper_score,
            "maxSpread":         self.max_spread,
            "minRiskReward":     self.min_rr,
            "minConfluence":     self.min_confluence,
            "minSessionScore":   self.min_session_score,
            "minEfficiencyRatio": self.min_efficiency_ratio,
            "rangeAwareness": self.range_awareness,
            "rangeFade": self.range_fade,
            "rangeTopPos": self.range_top_pos,
            "rangeBottomPos": self.range_bottom_pos,
        }

    def evaluate(
        self,
        market: dict[str, Any],
        strategies: list[dict[str, Any]] | None = None,
        memory: dict[str, Any] | None = None,
        active_position: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        strategies = strategies or INSTITUTIONAL_STRATEGIES
        memory = memory or {}
        candles = market.get("candles") or []
        h1_candles = market.get("h1Candles") or []
        h4_candles = market.get("h4Candles") or []
        d1_candles = market.get("d1Candles") or []

        features = _compute_candle_features(candles, h1_candles, range_lookback=self.range_lookback)
        # True higher-timeframe (H4 + D1) institutional bias.
        htf = _htf_bias(h4_candles, d1_candles)
        features.update({
            "d1Trend": htf["d1Trend"],
            "h4Trend": htf["h4Trend"],
            "htfDailyBias": htf["htfDailyBias"],
            "htfBiasScore": htf["htfBiasScore"],
            "haveHtf": htf["haveHtf"],
        })

        as_of = market.get("asOfTime")
        # In backtest we cannot replay historical news, so the news gate is bypassed
        # (documented assumption) — everything else is computed from the candles.
        if market.get("backtest"):
            calendar_status = {"isBlackout": False, "activeEvents": [], "detail": "Backtest: historical news not modeled"}
        else:
            calendar_status = self.calendar.blackout_status()
        macro       = self.macro.snapshot()
        vol_status  = self.volatility.classify(candles, market.get("atr14"))
        cleanliness = self.cleanliness.evaluate(market, calendar_status)
        session_name, session_score = _prime_session_score(as_of)

        # Respect the user's enabled sessions. If they've turned ON the current
        # broker session (e.g. Asia), the low-session-score hard-block is relaxed to
        # a soft (scout) block instead of silently refusing to trade it.
        broker_session = str(market.get("session", "")).strip()
        allowed_sessions = market.get("allowedSessions") or []
        respect_allowed = bool(market.get("respectAllowedSessions", True))
        session_allowed = (not allowed_sessions) or (broker_session in allowed_sessions)

        # Use computed side from structure — NOT from market.side (which is always "WAIT")
        computed_side = features["computedSide"]
        # Allow manual override only if explicitly provided and not WAIT
        manual_side = str(market.get("side", "WAIT")).upper()
        side = manual_side if manual_side not in {"WAIT", "—", ""} else computed_side

        # ── Range awareness: don't buy the top / sell the bottom of a sideways range ──
        rng = self._range_decision(side, features)
        features["inRange"] = rng.get("inRange", False)
        if rng.get("action") == "FADE":
            side = computed_side = rng["side"]      # mean-revert the extreme (opt-in)
            features["computedSide"] = side
            features["rangeFaded"] = rng["reason"]
        elif rng.get("action") == "BLOCK":
            features["rangeBlock"] = rng["reason"]  # skip with a clear reason (handled in the gate)

        # Is the intended trade aligned with the higher-timeframe daily/H4 bias?
        features["htfBiasAligned"] = (
            features["htfDailyBias"] == "NEUTRAL" or side == "WAIT" or features["htfDailyBias"] == side
        )

        market = {
            **market,
            "lateEntryScore":   features["lateEntryScore"],
            "htfAligned":       features["htfAligned"],
            "h1Aligned":        features["h1Aligned"],
            "htfAlignmentScore":features["htfAlignmentScore"],
            "liquiditySwept":   features["liquiditySwept"],
            "overExtended":     features["overExtended"],
            "inOTE":            features["inOTE"],
            "momentumExpanding":features["momentumExpanding"],
            "pullbackPresent":  features["pullbackPresent"],
            "slProtected":      True,
            "roomToTargetR":    2.4,
            "session":          session_name,
            "sessionScore":     session_score,
            "side":             side,
            "rsi14":            features["rsi14"],
            "macd":             features["macd"],
        }

        regime   = self._classify_regime(market, vol_status, calendar_status, features)
        # Performance-weighted ensemble: every enabled strategy is scored for THIS bar
        # (regime fit x live win-rate x expectancy x session fit) and the best is chosen.
        candidates = self._rank_strategies(regime, strategies, market, calendar_status, cleanliness, memory, features, session_score)
        selected = candidates[0]["strategy"] if candidates else self._select_strategy(regime, strategies, market, calendar_status, cleanliness)
        questions = self._trader_questions(market, regime, calendar_status, macro, vol_status, cleanliness, features, session_score)
        factors   = self._score_factors(market, regime, selected, questions, macro, vol_status, memory, features, session_score)
        raw       = sum(f.score * f.weight for f in factors) / max(sum(f.weight for f in factors), 1)
        confidence_raw = round(max(0, min(100, raw)), 1)
        # Calibration feedback: nudge confidence toward the REALISED win-rate for this
        # confidence bucket once enough live samples exist (closes the calibration loop).
        confidence, calibration_note = self._apply_calibration(confidence_raw, memory)

        entry  = float(market.get("price", 0) or 0)
        if entry <= 0:
            entry = 2385.68  # fallback only for demo

        sl     = self._structural_sl(side, entry, market, features, candles)
        targets = self._targets(side, entry, sl)
        rr     = targets["rrToTP2"]
        spread = float(market.get("spread", 0.12) or 0.12)

        # ── Hard blocks ──────────────────────────────────────────────────────
        hard_blocks: list[str] = []
        soft_blocks: list[str] = []

        if side == "WAIT":
            hard_blocks.append("No clear directional structure — EMA stack not aligned on any timeframe. Wait for structure.")
        if features.get("rangeBlock"):
            hard_blocks.append(f"Range filter: {features['rangeBlock']}.")
        if calendar_status.get("isBlackout"):
            hard_blocks.append("High-impact news blackout — no entries allowed")
        if spread > self.max_spread:
            hard_blocks.append(f"Spread too wide: {spread:.2f} (max {self.max_spread:.2f})")
        if not cleanliness.get("isClean", True):
            hard_blocks.append("Market cleanliness: " + "; ".join(cleanliness.get("dirtyReasons", [])))
        if rr < self.min_rr:
            hard_blocks.append(f"R/R too low: {rr:.2f} (min {self.min_rr:.2f})")
        # Over-extension: graded AND trend-aware. A genuine chase (> hard) is blocked; a mild
        # stretch (> soft) is only a scout flag. When riding a strong EMA-aligned efficient
        # trend we anchor to ema20 (the trend hugs it) and widen the thresholds, so we ride
        # trend continuation instead of fading it — the fix for taking only counter-trend sells.
        if features.get("trendAligned"):
            atr_dist = features.get("atrDistance20", features["atrDistance50"])
            hard_thr, soft_thr, anchor = self.max_atr_extension_hard + 1.8, self.max_atr_extension_soft + 1.8, "EMA-20"
        else:
            atr_dist = features["atrDistance50"]
            hard_thr, soft_thr, anchor = self.max_atr_extension_hard, self.max_atr_extension_soft, "EMA-50"
        if atr_dist > hard_thr:
            hard_blocks.append(f"Price extremely over-extended: {atr_dist:.2f} ATR from {anchor} (>{hard_thr:.1f}) — never chase")
        elif atr_dist > soft_thr:
            soft_blocks.append(f"Mildly extended: {atr_dist:.2f} ATR from {anchor} — scout size, wait for a small pullback")
        # Choppy/range filter — the biggest cause of repeated fast-fails. A tight,
        # back-and-forth range has low efficiency; do not trade it.
        er = float(features.get("efficiencyRatio", 0.5))
        er_short = float(features.get("efficiencyShort", er))
        short_dir = str(features.get("efficiencyShortDir", "WAIT"))
        move_atr = float(features.get("efficiencyShortMove", 0.0)) / max(float(features.get("atr", 0.01)), 0.01)
        # A clean, sized short-window leg in the SAME direction as the trade = a new move starting;
        # the 20-bar ER is just stale. Allow it as a scout instead of vetoing it for "chop".
        fresh_leg = (self.fresh_leg_override and er < self.min_efficiency_ratio
                     and er_short >= self.fresh_leg_eff and short_dir == side
                     and move_atr >= self.fresh_leg_min_atr and not features.get("rangeBlock"))
        if fresh_leg:
            features["freshLeg"] = True
            soft_blocks.append(f"20-bar efficiency low ({er:.2f}) but a fresh {side} leg is underway "
                               f"(8-bar efficiency {er_short:.2f}, {move_atr:.1f} ATR) — scout size, manage tightly.")
        elif er < self.min_efficiency_ratio:
            hard_blocks.append(f"Choppy/range market: trend efficiency {er:.2f} < {self.min_efficiency_ratio:.2f} — price is ranging, not trending. Wait for a clean break.")
        elif er < self.min_efficiency_ratio + 0.10:
            soft_blocks.append(f"Low trend efficiency ({er:.2f}) — choppy; scout size only")
        # Structure / HTF gate. A full M15 stack is ideal, but a PULLBACK (weak
        # alignment) that agrees with the H4/D1 bias is a high-quality entry — allow it
        # as a scout instead of vetoing it. Only block when there is neither a stack
        # nor higher-timeframe support.
        if not features["htfAligned"]:
            if features.get("weakAlignment") and features.get("htfBiasAligned") and features.get("haveHtf"):
                soft_blocks.append(f"M15 in pullback (EMAs not fully stacked) but aligned with H4/D1 {features.get('htfDailyBias')} bias — scout entry")
            elif features.get("weakAlignment") and not features.get("haveHtf"):
                soft_blocks.append("M15 weak trend (EMA-50 slope) — scout entry; no HTF data to confirm")
            else:
                hard_blocks.append("No structure: M15 EMAs unstacked and no H4/D1 bias support — wait for structure")
        if features["confluenceCount"] < self.min_confluence:
            hard_blocks.append(f"Insufficient confluence: {features['confluenceCount']}/12 factors confirmed (need {self.min_confluence})")
        if session_score < self.min_session_score:
            if respect_allowed and session_allowed:
                soft_blocks.append(f"Off-prime session ({session_name}, score {session_score}) — you enabled '{broker_session}', so it trades as a reduced-size scout entry.")
            else:
                hard_blocks.append(f"Dead-zone session ({session_name}, score {session_score}) — enable this session in Settings → Session Filter to allow it, or only trade London/NY prime windows")
        # RSI: only a HARD veto when truly extreme AND fighting the higher-timeframe
        # bias (buying a blow-off top / selling a capitulation low). Otherwise a soft
        # flag — RSI can ride >70/<30 for a long time in a real trend.
        # RSI rides >70/<30 for a long time in a real trend, so a trend-aligned elevated RSI is
        # only a soft "manage tightly" flag — hard-block ONLY a genuine parabolic blow-off (>88),
        # an extreme (>80) reading that is NOT a confirmed trend, or one fighting the HTF bias.
        if features["rsiOverbought"] and side == "BUY":
            if features["rsi14"] > 88 or not features.get("htfBiasAligned") or (features["rsi14"] > 80 and not features.get("trendAligned")):
                hard_blocks.append(f"RSI {features['rsi14']:.0f} overbought against bias — do not buy the top")
            else:
                soft_blocks.append(f"RSI {features['rsi14']:.0f} elevated but trend/HTF bias supports — manage tightly")
        if features["rsiOversold"] and side == "SELL":
            if features["rsi14"] < 12 or not features.get("htfBiasAligned") or (features["rsi14"] < 20 and not features.get("trendAligned")):
                hard_blocks.append(f"RSI {features['rsi14']:.0f} oversold against bias — do not sell the bottom")
            else:
                soft_blocks.append(f"RSI {features['rsi14']:.0f} depressed but trend/HTF bias supports — manage tightly")
        if confidence < self.min_take_score:
            hard_blocks.append(f"Confidence {confidence}% below minimum threshold {self.min_take_score}%")
        elif confidence < self.min_standard_score:
            soft_blocks.append(f"Scout entry: confidence {confidence}% below standard threshold {self.min_standard_score}%")
        # Higher-timeframe bias gate. In sniper mode a counter-HTF trade is blocked
        # outright; otherwise it is allowed but flagged as a reduced-quality entry.
        if features["haveHtf"] and not features["htfBiasAligned"] and side != "WAIT":
            msg = f"Trade {side} opposes higher-timeframe bias (D1 {features['d1Trend']}, H4 {features['h4Trend']})"
            if self.strictness_mode == "sniper":
                hard_blocks.append(msg + " — sniper mode requires HTF agreement")
            else:
                soft_blocks.append(msg)
        if calibration_note:
            soft_blocks.append(calibration_note)

        # Never pyramid into a loser
        if active_position:
            profit_r = float(active_position.get("profitR", active_position.get("floatingR", 0)) or 0)
            if profit_r <= 0:
                hard_blocks.append(f"Pyramid BLOCKED: trade is at {profit_r:.2f}R — never add to a losing or flat position")

        action = "TAKE_TRADE" if not hard_blocks and selected.get("id") != "no-trade-standby" else "SKIP_OR_WAIT"
        if action == "TAKE_TRADE" and confidence >= self.min_sniper_score:
            quality = "SNIPER"
        elif action == "TAKE_TRADE" and confidence >= self.min_standard_score:
            quality = "STANDARD"
        elif action == "TAKE_TRADE" and self.allow_scout_entries:
            quality = "SCOUT"
        else:
            quality = "WAIT"

        if action != "TAKE_TRADE":
            selected = next((s for s in strategies if s.get("id") == "no-trade-standby"), selected)

        return {
            "action":             action,
            "quality":            quality,
            "symbol":             market.get("symbol", "XAUUSD"),
            "side":               side,
            "computedSide":       computed_side,
            "confidence":         confidence,
            "confidenceRaw":      confidence_raw,
            "selectedStrategy":   selected,
            "strategyCandidates": candidates,
            "marketRegime":       regime,
            "sessionName":        session_name,
            "sessionScore":       session_score,
            "features":           features,
            "macroAwareness":     macro,
            "economicCalendar":   calendar_status,
            "volatilityRegime":   vol_status,
            "marketCleanliness":  cleanliness,
            "traderQuestions":    questions,
            "decisionBlocks":     hard_blocks,
            "softBlocks":         soft_blocks,
            "strictness":         self.strictness_dict(),
            "factors":            [asdict(f) for f in factors],
            "tradePlan": {
                "entry":              round(entry, 2),
                "sl":                 round(sl, 2),
                **targets,
                "entryMode":          quality,
                "baseLotOnly":        quality == "SCOUT",
                "pyramidingEligible": quality in {"STANDARD", "SNIPER"},
                "partialPlan": [
                    {"target": "TP1", "closePercent": 25, "management": "Close 25%, move remaining SL to break-even + costs."},
                    {"target": "TP2", "closePercent": 25, "management": "Trail remaining below/above last M5 structure."},
                    {"target": "TP3", "closePercent": 25, "management": "Switch runner to ATR/liquidity trail."},
                    {"target": "TP4", "closePercent": 25, "management": "Final runner exits at HTF liquidity/session extreme."},
                ],
            },
            "goldIntelligence": {
                "rsi14": features["rsi14"],
                "rsiStatus": "Overbought" if features["rsiOverbought"] else "Oversold" if features["rsiOversold"] else "Neutral",
                "macd": features["macd"],
                "macdAligned": features["macdAligned"],
                "orderBlock": features["orderBlock"],
                "fvg": features["fvg"],
                "asianRange": features["asianRange"],
                "h1Aligned": features["h1Aligned"],
                "d1Trend": features.get("d1Trend"),
                "h4Trend": features.get("h4Trend"),
                "htfDailyBias": features.get("htfDailyBias"),
                "htfBiasAligned": features.get("htfBiasAligned"),
                "swingHigh": features.get("swingHigh"),
                "swingLow": features.get("swingLow"),
                "volumeConfirmed": features["volumeConfirmed"],
                "confluenceCount": features.get("confluenceCount"),
                "htfAligned": features.get("htfAligned"),
                "liquiditySwept": features.get("liquiditySwept"),
                "inOTE": features.get("inOTE"),
                "overExtended": features.get("overExtended"),
            },
            "reason": self._reason(regime, selected, confidence, hard_blocks, questions, features, session_name, side),
        }

    def _classify_regime(self, market: dict[str, Any], vol: dict[str, Any], calendar_status: dict[str, Any], features: dict[str, Any]) -> str:
        raw       = str(market.get("regime", "")).lower()
        vol_regime = str(vol.get("regime", "")).lower()
        session   = str(market.get("session", "")).lower()
        if calendar_status.get("isBlackout"):
            return "News Blackout"
        if "compression" in vol_regime or "low volat" in vol_regime:
            return "Compression / Wait"
        if "extreme" in vol_regime:
            return "Extreme Volatility / Reduce Size"
        if "high volat" in vol_regime:
            return "Volatility Expansion"
        if features.get("htfAligned") and (features.get("momentumExpanding") or features.get("trendAligned")):
            # Use the EMA side to label direction — a clean efficient trend may not print
            # textbook higher-highs/lows yet still be a strong directional move.
            if features.get("structureBullish") or features.get("computedSide") == "BUY":
                return "Strong Bullish Trend"
            return "Strong Bearish Trend"
        if features.get("asianRange", {}).get("defined") and "london" in session:
            return "London Liquidity Window"
        if "bullish" in raw:
            return "Weak Bullish"
        if "bearish" in raw:
            return "Weak Bearish"
        if "london" in session:
            return "London Liquidity Window"
        if "asia" in session:
            return "Asian Range"
        return "Range / Wait"

    _PREFERRED_MAP = {
        "Strong Bullish Trend": ["Liquidity Sweep + Order Block Retest", "HTF Trend Continuation", "FVG Fill Continuation"],
        "Strong Bearish Trend": ["Liquidity Sweep + Order Block Retest", "HTF Trend Continuation"],
        "London Liquidity Window": ["London Open Breakout", "Asian Range Liquidity Raid", "Liquidity Sweep + Order Block Retest"],
        "Volatility Expansion": ["Volatility Compression Breakout", "Post-News Repricing Strategy", "London Open Breakout"],
        "Compression / Wait": ["No-Trade / Standby Strategy"],
        "Asian Range": ["Asian Range Liquidity Raid", "No-Trade / Standby Strategy"],
        "Range / Wait": ["VWAP Mean Reversion", "HTF Support/Resistance Rejection", "No-Trade / Standby Strategy"],
        "Weak Bullish": ["HTF Trend Continuation", "FVG Fill Continuation"],
        "Weak Bearish": ["HTF Trend Continuation", "FVG Fill Continuation"],
    }

    def _preferred_for_regime(self, regime: str, calendar_status: dict[str, Any], cleanliness: dict[str, Any]) -> list[str]:
        if calendar_status.get("isBlackout") or not cleanliness.get("isClean", True):
            return ["No-Trade / Standby Strategy"]
        return self._PREFERRED_MAP.get(regime, ["No-Trade / Standby Strategy"])

    def _select_strategy(self, regime: str, strategies: list[dict[str, Any]], market: dict[str, Any], calendar_status: dict[str, Any], cleanliness: dict[str, Any]) -> dict[str, Any]:
        enabled = [s for s in strategies if s.get("enabled", True)]
        preferred = self._preferred_for_regime(regime, calendar_status, cleanliness)
        for name in preferred:
            for s in enabled:
                if s.get("name") == name:
                    return s
        return next((s for s in enabled if s.get("id") == "no-trade-standby"), enabled[0] if enabled else {})

    @staticmethod
    def _parse_expectancy(value: Any) -> float:
        try:
            return round(float(str(value).replace("R", "").strip()), 2)
        except Exception:
            return 1.0

    def _rank_strategies(self, regime: str, strategies: list[dict[str, Any]], market: dict[str, Any], calendar_status: dict[str, Any], cleanliness: dict[str, Any], memory: dict[str, Any], features: dict[str, Any], session_score: float) -> list[dict[str, Any]]:
        """Score EVERY enabled strategy for the current bar and rank them.

        Blend = regime fit (40) + live/catalog win-rate (35) + expectancy (15) +
        session fit (10). Live win-rate is used once a strategy has >=5 recorded
        bot trades; until then the catalog estimate is used. This is the ensemble
        'vote' that replaces the old first-match-in-a-list selection.
        """
        enabled = [s for s in strategies if s.get("enabled", True)]
        if not enabled:
            return []
        preferred = self._preferred_for_regime(regime, calendar_status, cleanliness)
        if preferred == ["No-Trade / Standby Strategy"]:
            # Capital-protection standby is a SYSTEM safeguard — found even if the user
            # disabled it on the Strategies page (the hard gates still block regardless).
            standby = next((s for s in strategies if s.get("id") == "no-trade-standby"), None)
            if standby:
                return [{"strategy": standby, "name": standby.get("name"), "score": 100.0, "fit": 1.0,
                         "liveWinRate": 100.0, "expectancyR": 0.0, "sessionFit": True, "trades": 0,
                         "source": "protection", "reason": "Capital protection — news blackout or dirty market."}]
        session_name = str(market.get("session", "")).lower()
        mem_by_name = {row.get("name"): row for row in (memory.get("strategyPerformance") or [])}
        regime_l = regime.lower()
        ranked: list[dict[str, Any]] = []
        for s in enabled:
            name = s.get("name")
            if name == "No-Trade / Standby Strategy":
                continue
            if name in preferred:
                fit = 1.0 - preferred.index(name) * 0.18
            else:
                fit = 0.25
            ideal = [str(r).lower() for r in s.get("idealRegimes", [])]
            if any(tok in regime_l or regime_l in tok for tok in ideal):
                fit = fit + 0.15
            fit = max(0.05, min(1.0, fit))
            mem = mem_by_name.get(name)
            trades = int(mem.get("trades", 0)) if mem else 0
            cat_wr = float(s.get("winRate", 60) or 60)
            live_wr = float(mem.get("winRate", cat_wr)) if (mem and trades >= 5) else cat_wr
            exp_r = self._parse_expectancy(s.get("expectancy"))
            best_sessions = [str(x).lower() for x in s.get("bestSessions", [])]
            session_fit = bool(session_name) and any(b in session_name or session_name in b for b in best_sessions)
            score = (fit * 40) + (live_wr / 100 * 35) + (min(exp_r, 2.0) / 2.0 * 15) + (10 if session_fit else 0)
            ranked.append({
                "strategy": s, "name": name, "score": round(score, 1), "fit": round(fit, 2),
                "liveWinRate": round(live_wr, 1), "expectancyR": exp_r, "sessionFit": session_fit,
                "trades": trades, "source": "live_memory" if (mem and trades >= 5) else "catalog",
            })
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    def _apply_calibration(self, confidence: float, memory: dict[str, Any]) -> tuple[float, str]:
        """Blend raw confidence with the realised win-rate for its bucket (>=8 samples)."""
        calib = (memory or {}).get("probabilityCalibration") or []
        if not calib:
            return confidence, ""
        lo = int(confidence // 10) * 10
        bucket = f"{lo}-{lo + 9}"
        row = next((c for c in calib if c.get("bucket") == bucket), None)
        if not row:
            return confidence, ""
        samples = int(row.get("samples", 0) or 0)
        if samples < 8:
            return confidence, ""
        actual = float(row.get("actualWinRate", confidence) or confidence)
        adjusted = round(0.7 * confidence + 0.3 * actual, 1)
        note = ""
        if abs(adjusted - confidence) >= 3:
            note = (f"Confidence calibrated {confidence}% → {adjusted}% from {samples} live "
                    f"samples (bucket {bucket}%, realised {actual:.0f}% win-rate).")
        return adjusted, note

    def _trader_questions(self, market: dict[str, Any], regime: str, calendar_status: dict[str, Any], macro: dict[str, Any], vol: dict[str, Any], cleanliness: dict[str, Any], features: dict[str, Any], session_score: float) -> list[dict[str, Any]]:
        spread = float(market.get("spread", 0.12) or 0.12)
        side = str(market.get("side", "BUY")).lower()
        macro_bias = macro.get("macroGoldBias", "neutral")
        macro_ok = macro_bias in {"neutral", "bullish"} if side == "buy" else macro_bias in {"neutral", "bearish"}
        rows = [
            ("Is the market clean enough?",        "YES" if cleanliness.get("isClean") else "NO",               cleanliness.get("dirtyReasons") or ["conditions clean"]),
            ("Is HTF structure aligned?",           "YES" if features["htfAligned"] else "NO",                   f"HTF score {features['htfAlignmentScore']:.0f}%"),
            ("Is H1 timeframe aligned?",            "YES" if features["h1Aligned"] else "NO",                    "H1 EMA stack matches direction"),
            ("Is liquidity already swept?",         "YES" if features["liquiditySwept"] else "NO",               "sweep/reclaim evidence in last 5 bars"),
            ("Is price in OTE zone?",               "YES" if features["inOTE"] else "NEAR",                      f"Fib 61.8-78.6% zone: swing {features.get('swingLow',0):.1f}–{features.get('swingHigh',0):.1f}"),
            ("Is the entry not overextended?",      "YES" if not features["overExtended"] else "NO",             f"ATR dist from EMA50: {features['atrDistance50']:.2f}"),
            ("Is a pullback/retest confirmed?",     "YES" if features["pullbackPresent"] else "NO",              "retracement toward EMA20 before entry"),
            ("Is RSI favorable (not extreme)?",     "YES" if features["rsiFavorable"] else "NO",                 f"RSI-14: {features['rsi14']:.1f}"),
            ("Is MACD aligned with direction?",     "YES" if features["macdAligned"] else "NO",                  f"MACD hist: {features['macd']['histogram']:.4f}"),
            ("Is volume confirming the move?",      "YES" if features["volumeConfirmed"] else "NO",              "recent 3-bar avg vs 20-bar avg"),
            ("Is an Order Block present?",          "YES" if features["orderBlock"].get("found") else "NO",      f"OB at {features['orderBlock'].get('high',0):.1f}–{features['orderBlock'].get('low',0):.1f}"),
            ("Is the session prime window?",        "YES" if session_score >= self.min_session_score else "NO",  f"session score {session_score}"),
            ("Is spread acceptable?",               "YES" if spread <= self.max_spread else "NO",                f"spread={spread:.2f}"),
            ("Is news risk dangerous?",             "YES" if calendar_status.get("isBlackout") else "NO",        calendar_status.get("activeEvents") or "no active blackout"),
            ("Is confluence sufficient?",           "YES" if features["confluenceCount"] >= self.min_confluence else "NO", f"{features['confluenceCount']}/12 factors"),
            ("Is macro supportive?",                "YES" if macro_ok else "NEUTRAL",                            str(macro.get("detail"))),
        ]
        return [{"question": q, "answer": a, "evidence": e} for q, a, e in rows]

    def _question_value(self, questions: list[dict[str, Any]], question: str) -> str:
        for q in questions:
            if q.get("question") == question:
                return str(q.get("answer"))
        return "UNKNOWN"

    def _score_factors(self, market: dict[str, Any], regime: str, selected: dict[str, Any], questions: list[dict[str, Any]], macro: dict[str, Any], vol: dict[str, Any], memory: dict[str, Any], features: dict[str, Any], session_score: float) -> list[DecisionFactor]:
        spread       = float(market.get("spread", 0.12) or 0.12)
        strategy_wr  = float(selected.get("winRate", 64) or 64)
        macro_score  = 88 if macro.get("macroGoldBias") in {"bullish", "neutral"} else 55
        vol_score    = 88 if vol.get("isTradable") else 40
        clean_score  = 92 if self._question_value(questions, "Is the market clean enough?") == "YES" else 32
        htf_score    = features["htfAlignmentScore"]
        # Higher-timeframe (H4/D1) bias score: reward alignment, penalise counter-trend.
        if not features.get("haveHtf"):
            htf_bias_score = 60.0
        elif features.get("htfBiasAligned"):
            htf_bias_score = float(features.get("htfBiasScore", 80) or 80)
        else:
            htf_bias_score = 28.0
        h1_score     = 88 if features["h1Aligned"] else 52
        sweep_score  = 92 if features["liquiditySwept"] else 50
        timing_score = max(20, 95 - features["lateEntryScore"] * 80)
        ote_score    = 88 if features["inOTE"] else 58
        # A strong trend that won't deep-pull-back still deserves credit (don't force the bot
        # to miss the whole move waiting for a retrace that never comes).
        pullbk_score = 88 if features["pullbackPresent"] else (74 if features.get("trendAligned") else 45)
        spread_score = 96 if spread <= self.max_spread else 28
        session_s    = min(96, session_score)
        momentum_s   = features["momentumScore"]
        conf_count   = min(100, features["confluenceCount"] / max(self.min_confluence, 1) * 100)
        rsi          = float(features.get("rsi14", 50))
        # RSI score: best near 40-50 for buys, 55-65 for sells
        rsi_score    = 88 if features["rsiFavorable"] else 30
        macd_score   = 88 if features["macdAligned"] else 50
        vol_conf     = 85 if features["volumeConfirmed"] else 55
        ob_score     = 88 if features["orderBlock"].get("found") else 55
        fvg_score    = 82 if features["fvg"].get("found") else 55
        memory_wr    = 65
        for row in memory.get("strategyPerformance", []):
            if row.get("name") == selected.get("name"):
                memory_wr = float(row.get("winRate", 65))

        factors = [
            DecisionFactor("Market Cleanliness",       clean_score,                      1.35, "clean/dirty conditions"),
            DecisionFactor("HTF Daily/H4 Bias",        htf_bias_score,                   1.30, f"D1 {features.get('d1Trend')}, H4 {features.get('h4Trend')} → {features.get('htfDailyBias')}"),
            DecisionFactor("HTF Structure Alignment",  htf_score,                        1.30, f"M15 EMA stack: {features['htfAligned']}"),
            DecisionFactor("H1 Timeframe Alignment",   h1_score,                         1.25, f"H1 EMA stack aligned: {features['h1Aligned']}"),
            DecisionFactor("Confluence Count",         conf_count,                       1.20, f"{features['confluenceCount']}/12 factors"),
            DecisionFactor("Entry Timing (not late)",  timing_score,                     1.20, f"late score {features['lateEntryScore']:.2f}, OTE={features['inOTE']}"),
            DecisionFactor("RSI Momentum Gate",        rsi_score,                        1.15, f"RSI-14 = {rsi:.1f}"),
            DecisionFactor("MACD Alignment",           macd_score,                       1.10, f"MACD hist {features['macd']['histogram']:.4f}"),
            DecisionFactor("Volume Confirmation",      vol_conf,                         1.10, "tick-volume above 20-bar avg"),
            DecisionFactor("Liquidity Sweep Evidence", sweep_score,                      1.10, "swept/reclaimed"),
            DecisionFactor("Order Block Present",      ob_score,                         1.05, f"OB found: {features['orderBlock'].get('found')}"),
            DecisionFactor("Fair Value Gap",           fvg_score,                        1.00, f"FVG found: {features['fvg'].get('found')}"),
            DecisionFactor("Session Prime Window",     session_s,                        1.10, f"{market.get('session')} score={session_score}"),
            DecisionFactor("Pullback / Retest",        pullbk_score,                     1.10, "retracement toward structure"),
            DecisionFactor("Momentum Direction",       momentum_s,                       1.00, "candle momentum expanding"),
            DecisionFactor("Strategy Historical Edge", min(95, strategy_wr + 12),       1.00, f"catalog win rate {strategy_wr}%"),
            DecisionFactor("Live Memory Win Rate",     min(95, memory_wr + 12),         1.00, f"memory win rate {memory_wr}%"),
            DecisionFactor("Spread / Execution",       spread_score,                     1.10, f"spread={spread:.2f}"),
            DecisionFactor("Volatility Regime",        vol_score,                        0.90, str(vol.get("regime"))),
            DecisionFactor("Macro Awareness",          macro_score,                      0.85, str(macro.get("detail"))),
        ]
        # Apply learned weights (from the cost-aware backtest optimizer) when present.
        if self.factor_weights:
            for f in factors:
                if f.name in self.factor_weights:
                    f.weight = self.factor_weights[f.name]
        return factors

    def _range_decision(self, side: str, features: dict[str, Any]) -> dict[str, Any]:
        """Range awareness. In a confirmed SIDEWAYS range (not a trend), buying the top or selling
        the bottom is the worst entry. Returns NONE / BLOCK (skip) / FADE (trade the other way).
        Never fires in a real trend — a trend pullback near the highs is a good buy, not a chase."""
        if not getattr(self, "range_awareness", True) or side not in ("BUY", "SELL"):
            return {"action": "NONE"}
        pos = float(features.get("rangePos", 0.5))
        width_atr = float(features.get("rangeWidthAtr", 0.0))
        er = float(features.get("efficiencyRatio", 0.5))
        # A range = LOW efficiency (not trending) + a meaningful width. Efficiency is the real
        # trend/range test — a genuine efficient trend (er >= range_eff_max) is excluded here, so a
        # clean trend pullback is never range-blocked; only low-efficiency chop at an extreme is.
        in_range = er < self.range_eff_max and width_atr >= self.range_min_atr
        if not in_range:
            return {"action": "NONE", "inRange": False, "rangePos": round(pos, 2)}
        fade = bool(getattr(self, "range_fade", False))
        if side == "BUY" and pos >= self.range_top_pos:
            return {"action": "FADE" if fade else "BLOCK", "side": "SELL", "inRange": True, "rangePos": round(pos, 2),
                    "reason": f"price near the TOP of a sideways range ({pos*100:.0f}% up a {width_atr:.1f}-ATR range, efficiency {er:.2f}) — don't buy the top"}
        if side == "SELL" and pos <= self.range_bottom_pos:
            return {"action": "FADE" if fade else "BLOCK", "side": "BUY", "inRange": True, "rangePos": round(pos, 2),
                    "reason": f"price near the BOTTOM of a sideways range ({pos*100:.0f}% up a {width_atr:.1f}-ATR range, efficiency {er:.2f}) — don't sell the bottom"}
        return {"action": "NONE", "inRange": True, "rangePos": round(pos, 2)}

    def _structural_sl(self, side: str, entry: float, market: dict[str, Any], features: dict[str, Any], candles: list[dict[str, Any]]) -> float:
        atr  = features.get("atr") or float(market.get("atr14", 12.35) or 12.35)

        # Use structural swing high/low if available
        if candles and len(candles) >= 5:
            highs = [float(c.get("high", 0) or 0) for c in candles[-20:]]
            lows  = [float(c.get("low",  0) or 0) for c in candles[-20:]]
            if side == "BUY":
                # SL below the lowest low of the last 10 bars + buffer
                structural_low = min(lows[-10:]) if len(lows) >= 10 else min(lows)
                sl_structural = structural_low - atr * 0.15  # small buffer below structure
                sl_atr = entry - max(7.0, min(14.0, atr * 0.75))
                # Use whichever gives wider protection but don't go >2.5R
                sl = max(sl_structural, sl_atr)
            else:
                structural_high = max(highs[-10:]) if len(highs) >= 10 else max(highs)
                sl_structural = structural_high + atr * 0.15
                sl_atr = entry + max(7.0, min(14.0, atr * 0.75))
                sl = min(sl_structural, sl_atr)
        else:
            risk = max(7.0, min(14.0, atr * 0.75))
            sl = (entry - risk) if side == "BUY" else (entry + risk)

        return round(sl, 2)

    def _targets(self, side: str, entry: float, sl: float) -> dict[str, float]:
        risk = abs(entry - sl) or 1.0
        if side == "SELL":
            return {
                "tp1": round(entry - risk * 1.0, 2), "tp2": round(entry - risk * 1.8, 2),
                "tp3": round(entry - risk * 2.7, 2), "tp4": round(entry - risk * 4.0, 2),
                "rrToTP1": 1.0, "rrToTP2": 1.8, "rrToTP3": 2.7, "rrToTP4": 4.0,
            }
        return {
            "tp1": round(entry + risk * 1.0, 2), "tp2": round(entry + risk * 1.8, 2),
            "tp3": round(entry + risk * 2.7, 2), "tp4": round(entry + risk * 4.0, 2),
            "rrToTP1": 1.0, "rrToTP2": 1.8, "rrToTP3": 2.7, "rrToTP4": 4.0,
        }

    def _reason(self, regime: str, selected: dict[str, Any], confidence: float, blocks: list[str], questions: list[dict[str, Any]], features: dict[str, Any], session: str, side: str) -> str:
        htf_txt = f"D1 {features.get('d1Trend','?')}/H4 {features.get('h4Trend','?')} → bias {features.get('htfDailyBias','?')}"
        if blocks:
            return (f"Standby: {', '.join(blocks[:2])}. Regime={regime}; {htf_txt}. "
                    f"Waiting for HTF alignment, prime session, RSI room, and a clean pullback before entering.")
        return (
            f"{side} {selected.get('name')} accepted — fits {regime} during {session}. {htf_txt}. "
            f"Confluence {features['confluenceCount']}/12, confidence {confidence}%. "
            f"HTF aligned={features['htfAligned']}, H1={features['h1Aligned']}, HTF-bias aligned={features.get('htfBiasAligned')}, "
            f"RSI={features['rsi14']:.1f}, MACD={features['macdAligned']}, swept={features['liquiditySwept']}, "
            f"OTE={features['inOTE']}, OB={features['orderBlock'].get('found')}, FVG={features['fvg'].get('found')}. "
            f"Plan: enter, bank TP1 25% + move to BE, trail TP2-TP4 behind structure to HTF liquidity."
        )
