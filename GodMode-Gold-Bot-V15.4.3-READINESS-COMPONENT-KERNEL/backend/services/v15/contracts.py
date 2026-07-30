from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a numeric signal while treating non-finite input as neutral.

    NaN previously collapsed to the upper bound because of Python's min/max
    comparison semantics. In a trading engine that can turn corrupt telemetry
    into maximum confidence. A midpoint fallback is fail-neutral and bounded.
    """
    lo = float(lo)
    hi = float(hi)
    if lo > hi:
        lo, hi = hi, lo
    try:
        number = float(value)
    except (TypeError, ValueError):
        return (lo + hi) / 2.0
    if not math.isfinite(number):
        return (lo + hi) / 2.0
    return max(lo, min(hi, number))


@dataclass(frozen=True)
class EngineHealth:
    name: str
    ok: bool
    score: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Explanation:
    summary: str
    reasons: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    uncertainty: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
