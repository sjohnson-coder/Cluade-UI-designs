from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
import os
import time
from typing import Any

_PROCESS_TOKEN = f"{os.getpid()}:{time.monotonic_ns()}"


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0.0 else None


def valid_live_atr(market: dict[str, Any] | None) -> float | None:
    market = market if isinstance(market, dict) else {}
    for key in ("atr14", "atr"):
        value = _finite_positive(market.get(key))
        if value is not None:
            return value
    return None


def broker_profit_stop_confirmed(direction: str, entry: Any, broker_sl: Any, current_price: Any) -> bool:
    side = str(direction or "").upper()
    e, sl, cur = _finite_positive(entry), _finite_positive(broker_sl), _finite_positive(current_price)
    if side not in {"BUY", "SELL"} or e is None or sl is None or cur is None:
        return False
    return e < sl < cur if side == "BUY" else cur < sl < e


def threshold_activated(profit_atr: Any, threshold_atr: Any, *, already_armed: bool = False) -> bool:
    if already_armed:
        return True
    try:
        profit, threshold = float(profit_atr), float(threshold_atr)
    except (TypeError, ValueError):
        return False
    return isfinite(profit) and isfinite(threshold) and threshold > 0.0 and profit >= threshold


def _keys(key: str) -> tuple[str, str, str]:
    key = str(key or "timer")
    return f"{key}Mono", f"{key}Epoch", f"{key}Process"


def mark_elapsed_anchor(state: dict[str, Any], key: str, *, now_monotonic: float | None = None, now_epoch: float | None = None, process_token: str | None = None) -> None:
    mk, ek, pk = _keys(key)
    state[mk] = float(time.monotonic() if now_monotonic is None else now_monotonic)
    state[ek] = float(time.time() if now_epoch is None else now_epoch)
    state[pk] = process_token or _PROCESS_TOKEN


def clear_elapsed_anchor(state: dict[str, Any], key: str) -> None:
    for field in _keys(key):
        state.pop(field, None)


def elapsed_since(state: dict[str, Any], key: str, *, now_monotonic: float | None = None, now_epoch: float | None = None, process_token: str | None = None) -> float:
    mk, ek, pk = _keys(key)
    now_m = float(time.monotonic() if now_monotonic is None else now_monotonic)
    now_e = float(time.time() if now_epoch is None else now_epoch)
    token = process_token or _PROCESS_TOKEN
    if state.get(pk) == token:
        try:
            return max(0.0, now_m - float(state[mk]))
        except (KeyError, TypeError, ValueError):
            state.pop(mk, None)
    try:
        return max(0.0, now_e - float(state[ek]))
    except (KeyError, TypeError, ValueError):
        return 0.0


def elapsed_confirmation(state: dict[str, Any], action: str, required_seconds: Any, *, structural: bool = False, now_monotonic: float | None = None, now_epoch: float | None = None) -> bool:
    action_key = "RECOVER" if str(action or "").upper() in {"RECOVER", "WIDEN"} else "CUT"
    other = "CUT" if action_key == "RECOVER" else "RECOVER"
    clear_elapsed_anchor(state, f"{other.lower()}Confirm")
    if state.get("confirmationAction") != action_key:
        state["confirmationAction"] = action_key
        mark_elapsed_anchor(state, f"{action_key.lower()}Confirm", now_monotonic=now_monotonic, now_epoch=now_epoch)
    if structural:
        return True
    try:
        required = max(0.0, float(required_seconds))
    except (TypeError, ValueError):
        required = 0.0
    return elapsed_since(state, f"{action_key.lower()}Confirm", now_monotonic=now_monotonic, now_epoch=now_epoch) >= required


def broker_open_epoch(position: dict[str, Any] | None) -> float | None:
    position = position if isinstance(position, dict) else {}
    msc = _finite_positive(position.get("openTimeMsc"))
    if msc is not None:
        return msc / 1000.0
    epoch = _finite_positive(position.get("openTimestamp"))
    if epoch is not None:
        return epoch
    numeric_open = _finite_positive(position.get("openTime"))
    if numeric_open is not None:
        return numeric_open
    text = str(position.get("openTime") or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None
