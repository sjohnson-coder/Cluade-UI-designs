from __future__ import annotations
from datetime import datetime
from math import isfinite
from typing import Any, Iterable


def _num(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return n if isfinite(n) else default


def _time_msc(row: dict[str, Any]) -> int:
    direct = int(_num(row.get("entryTimeMsc") or row.get("timeMsc") or row.get("epoch")))
    if direct > 0:
        return direct if direct > 10_000_000_000 else direct * 1000
    text = str(row.get("ts") or row.get("timestamp") or "").strip()
    if not text:
        return 0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int(parsed.timestamp() * 1000)


def event_identity(symbol: str, side: str, timeframe: str, candle_epoch: Any) -> str:
    return f"{str(symbol or '').upper()}:{str(side or '').upper()}:{str(timeframe or '').upper()}:{int(_num(candle_epoch))}"


def _derived_event_id(row: dict[str, Any]) -> str:
    candle_epoch = row.get("candleEpoch") or row.get("signalCandleEpoch") or row.get("barEpoch")
    if _num(candle_epoch) <= 0:
        return ""
    return event_identity(
        str(row.get("symbol") or ""),
        str(row.get("side") or row.get("direction") or ""),
        str(row.get("timeframe") or row.get("tf") or "M5"),
        candle_epoch,
    )


def _legacy_fingerprint(row: dict[str, Any]) -> tuple[str, str, str, float, str]:
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("side") or row.get("direction") or "").upper(),
        str(row.get("timeframe") or row.get("tf") or "M5").upper(),
        round(_num(row.get("entryPrice") or row.get("price") or row.get("signalPrice")), 2),
        str(row.get("blockedBy") or row.get("reason") or "").strip(),
    )


def deduplicate_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse exact event identities and legacy duplicate observations.

    Modern rows are deduplicated by eventId (or a derived candle identity). Legacy
    rows without a candle identity are clustered only when their stable market
    fingerprint matches and their observations are no more than ten seconds apart.
    This removes boundary duplicates without merging genuinely later opportunities.
    """
    identified: dict[str, dict[str, Any]] = {}
    legacy_clusters: dict[tuple[str, str, str, float, str], list[dict[str, Any]]] = {}

    for raw in events:
        row = dict(raw)
        key = str(row.get("eventId") or "").strip() or _derived_event_id(row)
        if key:
            ts = _time_msc(row)
            old = identified.get(key)
            old_ts = _time_msc(old or {})
            if old is None or (ts and (not old_ts or ts < old_ts)):
                identified[key] = row
            continue

        fingerprint = _legacy_fingerprint(row)
        clusters = legacy_clusters.setdefault(fingerprint, [])
        ts = _time_msc(row)
        duplicate_index = None
        for idx, existing in enumerate(clusters):
            existing_ts = _time_msc(existing)
            if ts and existing_ts and abs(ts - existing_ts) <= 10_000:
                duplicate_index = idx
                break
        if duplicate_index is None:
            clusters.append(row)
        elif ts and (not _time_msc(clusters[duplicate_index]) or ts < _time_msc(clusters[duplicate_index])):
            clusters[duplicate_index] = row

    legacy = [row for clusters in legacy_clusters.values() for row in clusters]
    return sorted(list(identified.values()) + legacy, key=_time_msc)


def replay_executable_ticks(side: str, *, entry_price: Any, entry_time_msc: Any, ticks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    side = str(side or "").upper()
    entry, start = _num(entry_price), int(_num(entry_time_msc))
    if side not in {"BUY", "SELL"} or entry <= 0 or start <= 0:
        return {"ok": False, "reason": "invalid_entry", "bestFavourable": 0.0, "worstBeforeBest": 0.0}
    ordered = sorted((dict(t) for t in ticks if int(_num(t.get("timeMsc") or t.get("time_msc"))) >= start), key=lambda t: int(_num(t.get("timeMsc") or t.get("time_msc"))))
    best = worst = worst_before_best = 0.0
    best_time = None
    best_exit_price = None
    worst_exit_price = None
    worst_before_best_exit_price = None
    count = 0
    for tick in ordered:
        exit_price = _num(tick.get("bid" if side == "BUY" else "ask"))
        if exit_price <= 0:
            continue
        count += 1
        fav = exit_price - entry if side == "BUY" else entry - exit_price
        adv = entry - exit_price if side == "BUY" else exit_price - entry
        if adv > worst:
            worst = adv
            worst_exit_price = exit_price
        if fav > best:
            best, worst_before_best = fav, worst
            best_time = int(_num(tick.get("timeMsc") or tick.get("time_msc")))
            best_exit_price = exit_price
            worst_before_best_exit_price = worst_exit_price
    return {
        "ok": count > 0,
        "reason": "ok" if count else "no_tick_data",
        "bestFavourable": round(max(0.0, best), 10),
        "worstBeforeBest": round(max(0.0, worst_before_best), 10),
        "bestTimeMsc": best_time,
        "bestExitPrice": best_exit_price,
        "worstBeforeBestExitPrice": worst_before_best_exit_price,
        "observations": count,
    }
