from __future__ import annotations

from typing import Iterable

from .contracts import clamp


def brier_score(predictions: Iterable[float], outcomes: Iterable[int]) -> float:
    pairs = [(clamp(p), 1 if int(y) else 0) for p, y in zip(predictions, outcomes)]
    if not pairs:
        return 1.0
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def empirical_calibrate(probability: float, wins: int = 0, samples: int = 0, prior_strength: float = 20.0) -> float:
    p = clamp(probability)
    if samples <= 0:
        return p
    empirical = clamp(wins / max(1, samples))
    return clamp((p * prior_strength + empirical * samples) / (prior_strength + samples))
