"""
Burst arming gate: require *room*, not just time and score.

A burst needs continuation to exist. Measured median session range on 4,077,891
M1 XAUUSD bars (2015-01 -> 2026-08), expressed as a multiple of daily ATR14:

    NY AM  08:00-12:00   median 0.572   p90 1.048
    London 02:00-08:00   median 0.404   p90 0.704
    Asia   18:05-02:00   median 0.377   p90 0.683
    NY PM  12:00-17:00   median 0.310   p90 0.640

New York morning offers 52% more room than Asia and 85% more than the New York
afternoon. A three-leg ladder armed in a dead NY afternoon has nowhere to go, and
the existing admission path gates on confidence, continuation and timing but never
on whether the session has actually produced any range today.

This gate compares the range realised *so far in the current session* against that
session's historical median. It fails open when inputs are missing, so it can only
ever refuse a burst, never authorise one that other gates rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Median session range as a fraction of daily ATR14, from the study above.
SESSION_MEDIAN_RANGE_ATR: dict[str, float] = {
    "ASIA": 0.377,
    "LONDON": 0.404,
    "NEW_YORK": 0.572,      # 08:00-12:00 dominates the New York block
    "NEW_YORK_PM": 0.310,
    "FLAT": 0.0,
}


@dataclass(frozen=True)
class RoomGate:
    ok: bool
    session: str
    realised_atr: float
    median_atr: float
    ratio: float
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "session": self.session,
            "realisedRangeAtr": round(self.realised_atr, 4),
            "sessionMedianAtr": round(self.median_atr, 4),
            "ratio": round(self.ratio, 4),
            "reason": self.reason,
        }


def evaluate_session_room(session: str, session_high: float | None, session_low: float | None,
                          atr: float | None, *, min_ratio: float = 0.25,
                          enabled: bool = True) -> RoomGate:
    """Has this session produced enough range to justify adding legs?

    `min_ratio` is the fraction of the session's *historical median* range that must
    already have been realised. 0.25 is deliberately permissive: it rejects only a
    genuinely dead session, not a merely quiet one.
    """
    key = str(session or "").upper().replace(" ", "_")
    median = SESSION_MEDIAN_RANGE_ATR.get(key, 0.0)

    if not enabled:
        return RoomGate(True, key, 0.0, median, 0.0, "Session room gate disabled.")
    if key in {"FLAT", ""}:
        return RoomGate(False, key, 0.0, median, 0.0,
                        "Flat/rollover window — no burst continuation to trade.")

    try:
        hi, lo, a = float(session_high), float(session_low), float(atr)
    except (TypeError, ValueError):
        return RoomGate(True, key, 0.0, median, 0.0,
                        "Session range or ATR unavailable — gate failed open.")
    if a <= 0 or hi <= lo or median <= 0:
        return RoomGate(True, key, 0.0, median, 0.0,
                        "Insufficient inputs — gate failed open.")

    realised = (hi - lo) / a
    ratio = realised / median
    if ratio < min_ratio:
        return RoomGate(
            False, key, realised, median, ratio,
            f"{key} has realised only {realised:.2f} ATR of range "
            f"({ratio * 100:.0f}% of its {median:.2f} ATR median). "
            f"A burst ladder needs room to continue; minimum is {min_ratio * 100:.0f}%.",
        )
    return RoomGate(True, key, realised, median, ratio,
                    f"{key} realised {realised:.2f} ATR ({ratio * 100:.0f}% of median).")


if __name__ == "__main__":
    cases = [
        ("NEW_YORK", 4520.0, 4460.0, 128.0, "active NY morning"),
        ("NEW_YORK_PM", 4505.0, 4498.0, 128.0, "dead NY afternoon"),
        ("ASIA", 4500.0, 4488.0, 128.0, "quiet but tradeable Asia"),
        ("FLAT", 4500.0, 4499.0, 128.0, "rollover window"),
        ("LONDON", None, None, 128.0, "missing data — must fail open"),
    ]
    print(f"{'case':<28} {'session':<13} {'realised':>9} {'ratio':>7}  verdict")
    print("-" * 78)
    for sess, hi, lo, atr, label in cases:
        g = evaluate_session_room(sess, hi, lo, atr)
        print(f"{label:<28} {g.session:<13} {g.realised_atr:>9.3f} {g.ratio:>6.0%}  "
              f"{'ARM' if g.ok else 'BLOCK'}")
