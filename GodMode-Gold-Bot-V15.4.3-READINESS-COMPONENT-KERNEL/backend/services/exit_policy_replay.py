"""Deterministic quote-by-quote replay of the production Dynamic-SL policy."""
from __future__ import annotations

import math
import time
from typing import Any, Iterable

from .dynamic_sl_v14 import (
    BrokerRules,
    DynamicSLState,
    PositionSnapshot,
    decide,
)


def _number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def replay_dynamic_sl(
    ticks: Iterable[dict[str, Any]],
    *,
    side: str,
    entry: float,
    initial_sl: float,
    tick_size: float,
    point: float,
    stops_level_points: float = 0.0,
    freeze_level_points: float = 0.0,
    max_giveback_fraction: float = 0.45,
    protect_start_r: float = 0.55,
) -> dict[str, Any]:
    """Replay protection on actual bid/ask quotes; never fabricates market data."""
    side = str(side or "").upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    entry_value = _number(entry, "entry")
    stop = _number(initial_sl, "initial_sl")
    risk = (
        entry_value - stop
        if side == "BUY"
        else stop - entry_value
    )
    if risk <= 0:
        raise ValueError("initial_sl must define positive risk for the selected side")
    if not 0 < protect_start_r <= 5:
        raise ValueError("protect_start_r outside safe range")

    rules = BrokerRules(
        tick_size=_number(tick_size, "tick_size"),
        point=_number(point, "point"),
        stops_level_points=max(0.0, _number(stops_level_points, "stops_level_points")),
        freeze_level_points=max(0.0, _number(freeze_level_points, "freeze_level_points")),
    )
    rows = list(ticks)
    if not rows:
        return {
            "ok": False,
            "message": "No quotes supplied.",
            "events": [],
            "source": "caller_supplied_quotes",
        }

    state = DynamicSLState.INACTIVE
    peak_r = 0.0
    events: list[dict[str, Any]] = []
    exit_reason = "END_OF_DATA"
    exit_price: float | None = None
    realized_r: float | None = None
    prior_time: float | None = None

    for sequence, quote in enumerate(rows, start=1):
        quote_time = _number(quote.get("time"), "quote.time")
        if prior_time is not None and quote_time < prior_time:
            raise ValueError("quotes must be chronological")
        prior_time = quote_time
        bid = _number(quote.get("bid"), "quote.bid")
        ask = _number(quote.get("ask"), "quote.ask")
        if bid <= 0 or ask <= 0 or ask < bid:
            raise ValueError("quote must have positive bid and ask with ask >= bid")
        close_price = bid if side == "BUY" else ask
        current_r = (
            (close_price - entry_value) / risk
            if side == "BUY"
            else (entry_value - close_price) / risk
        )
        peak_r = max(peak_r, current_r)

        stop_hit = (
            close_price <= stop
            if side == "BUY"
            else close_price >= stop
        )
        if stop_hit:
            exit_reason = "STOP_HIT"
            exit_price = close_price
            realized_r = current_r
            events.append(
                {
                    "sequence": sequence,
                    "time": quote_time,
                    "bid": bid,
                    "ask": ask,
                    "state": state.value,
                    "stop": stop,
                    "currentR": round(current_r, 6),
                    "peakR": round(peak_r, 6),
                    "lockedR": round(
                        (
                            (stop - entry_value) / risk
                            if side == "BUY"
                            else (entry_value - stop) / risk
                        ),
                        6,
                    ),
                    "action": "EXIT",
                    "reasonCodes": ["BROKER_STOP_HIT"],
                }
            )
            break

        reason_codes: list[str] = ["PROTECTION_NOT_ARMED"]
        blocked = False
        if peak_r >= protect_start_r and current_r > 0:
            snapshot = PositionSnapshot(
                ticket=1,
                symbol=str(quote.get("symbol") or "XAUUSD"),
                side=side,
                entry=entry_value,
                bid=bid,
                ask=ask,
                sl=stop,
                tp=None,
                volume=1.0,
                initial_risk_price=risk,
                peak_profit_r=peak_r,
                current_profit_r=current_r,
                timestamp=time.time(),
                sequence=sequence,
            )
            decision = decide(
                snapshot,
                rules,
                state=state,
                recovery_score=max(
                    0.0,
                    min(100.0, _number(quote.get("recoveryScore", 65), "recoveryScore")),
                ),
                invalidated=bool(quote.get("invalidated", False)),
                max_giveback_fraction=max_giveback_fraction,
            )
            state = decision.state_after
            reason_codes = list(decision.reason_codes)
            blocked = decision.blocked
            if not decision.blocked and decision.proposed_sl is not None:
                stop = float(decision.proposed_sl)

        locked_r = (
            (stop - entry_value) / risk
            if side == "BUY"
            else (entry_value - stop) / risk
        )
        events.append(
            {
                "sequence": sequence,
                "time": quote_time,
                "bid": bid,
                "ask": ask,
                "state": state.value,
                "stop": stop,
                "currentR": round(current_r, 6),
                "peakR": round(peak_r, 6),
                "lockedR": round(locked_r, 6),
                "action": "HOLD" if blocked else "PROTECT",
                "blocked": blocked,
                "reasonCodes": reason_codes,
            }
        )

    if realized_r is None:
        final = rows[-1]
        exit_price = _number(
            final.get("bid") if side == "BUY" else final.get("ask"),
            "final close price",
        )
        realized_r = (
            (exit_price - entry_value) / risk
            if side == "BUY"
            else (entry_value - exit_price) / risk
        )

    return {
        "ok": True,
        "source": "caller_supplied_quotes",
        "model": "production_dynamic_sl_v14_quote_replay",
        "side": side,
        "entry": entry_value,
        "initialSl": initial_sl,
        "finalStop": stop,
        "exitPrice": exit_price,
        "exitReason": exit_reason,
        "peakR": round(peak_r, 6),
        "realizedR": round(realized_r, 6),
        "givebackR": round(max(0.0, peak_r - realized_r), 6),
        "events": events,
        "limitations": [
            "Uses caller-supplied quote sequence and recovery scores.",
            "Does not predict broker slippage, gaps, latency, or disconnected-terminal behavior.",
        ],
    }
