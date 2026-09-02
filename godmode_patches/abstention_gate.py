"""
Out-of-distribution detection and abstention.

Grep the shipped backend for `abstain`, `abstention`, `out-of-distribution`, `ood`,
`mahalanobis` or `conformal` and you get zero hits. The bot always has an opinion.

Both research reviews call this out. The ChatGPT blueprint is explicit: "Use
abstention. If the event is novel, cross-asset response is contradictory, or the
feature vector is outside the training distribution, output NO TRADE or
paper-only." A model asked to score a market state unlike anything it was fitted
on will still return a confident number, and that number is meaningless.

Two independent signals, because they fail differently:

  novelty     Mahalanobis-style distance of the live feature vector from the
              training mean, using a diagonal covariance so it stays O(k) and
              needs no matrix inversion in the hot path. Catches "this bar looks
              nothing like what we learned on".

  disagreement Spread across independent signal sources. Catches "the inputs
              contradict each other", which a distance check cannot see because
              each feature can be individually ordinary.

Either one crossing its threshold downgrades the decision. The policy is
deliberately three-state -- TRADE / REDUCE / ABSTAIN -- because forcing a binary
choice on an uncertain state is what produced the problem in the first place.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

TRADE, REDUCE, ABSTAIN = "TRADE", "REDUCE", "ABSTAIN"


@dataclass(frozen=True)
class AbstentionDecision:
    action: str
    novelty_z: float
    disagreement: float
    size_multiplier: float
    reasons: tuple[str, ...] = ()

    @property
    def should_trade(self) -> bool:
        return self.action != ABSTAIN

    def as_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "noveltyZ": round(self.novelty_z, 3),
            "disagreement": round(self.disagreement, 3),
            "sizeMultiplier": round(self.size_multiplier, 3),
            "reasons": list(self.reasons),
        }


@dataclass
class FeatureDistribution:
    """Running mean and variance per feature. Welford, so it never stores history."""
    counts: dict[str, int] = field(default_factory=dict)
    means: dict[str, float] = field(default_factory=dict)
    m2: dict[str, float] = field(default_factory=dict)

    def observe(self, features: Mapping[str, float]) -> None:
        for key, raw in features.items():
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            n = self.counts.get(key, 0) + 1
            mean = self.means.get(key, 0.0)
            delta = value - mean
            mean += delta / n
            self.counts[key] = n
            self.means[key] = mean
            self.m2[key] = self.m2.get(key, 0.0) + delta * (value - mean)

    def std(self, key: str) -> float:
        n = self.counts.get(key, 0)
        if n < 2:
            return 0.0
        return math.sqrt(max(0.0, self.m2.get(key, 0.0) / (n - 1)))

    @property
    def observations(self) -> int:
        return min(self.counts.values()) if self.counts else 0

    def novelty_z(self, features: Mapping[str, float]) -> tuple[float, list[str]]:
        """Root-mean-square per-feature z-score, plus the features driving it."""
        scores: list[tuple[str, float]] = []
        for key, raw in features.items():
            if self.counts.get(key, 0) < 2:
                continue
            sd = self.std(key)
            if sd <= 1e-12:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            scores.append((key, abs(value - self.means[key]) / sd))
        if not scores:
            return 0.0, []
        rms = math.sqrt(sum(z * z for _, z in scores) / len(scores))
        drivers = [k for k, z in sorted(scores, key=lambda kv: -kv[1])[:3] if z >= 2.0]
        return rms, drivers

    def as_dict(self) -> dict[str, object]:
        return {"observations": self.observations, "features": len(self.counts)}


def signal_disagreement(signals: Sequence[float]) -> float:
    """0 = unanimous, 1 = maximally split. Signals are directional in [-1, 1]."""
    values = [max(-1.0, min(1.0, float(s))) for s in signals
              if s is not None and math.isfinite(float(s))]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return min(1.0, math.sqrt(variance))


@dataclass
class AbstentionGate:
    novelty_warn: float = 2.0
    novelty_block: float = 3.5
    disagreement_warn: float = 0.45
    disagreement_block: float = 0.75
    min_observations: int = 200
    reduced_size: float = 0.5

    def evaluate(self, distribution: FeatureDistribution,
                 features: Mapping[str, float],
                 signals: Sequence[float] = ()) -> AbstentionDecision:
        reasons: list[str] = []

        if distribution.observations < self.min_observations:
            # Not enough history to judge novelty. Reduce rather than abstain --
            # a cold start is not evidence of an unusual market.
            return AbstentionDecision(
                REDUCE, 0.0, 0.0, self.reduced_size,
                (f"distribution still warming: {distribution.observations}/"
                 f"{self.min_observations} observations",),
            )

        novelty, drivers = distribution.novelty_z(features)
        disagreement = signal_disagreement(signals)
        action, size = TRADE, 1.0

        if novelty >= self.novelty_block:
            action, size = ABSTAIN, 0.0
            reasons.append(
                f"feature vector is {novelty:.1f} sigma from the learned distribution"
                + (f" (driven by {', '.join(drivers)})" if drivers else "")
            )
        elif novelty >= self.novelty_warn:
            action, size = REDUCE, self.reduced_size
            reasons.append(
                f"unusual market state ({novelty:.1f} sigma)"
                + (f": {', '.join(drivers)}" if drivers else "")
            )

        if disagreement >= self.disagreement_block:
            action, size = ABSTAIN, 0.0
            reasons.append(f"signal sources contradict each other ({disagreement:.2f})")
        elif disagreement >= self.disagreement_warn and action == TRADE:
            action, size = REDUCE, self.reduced_size
            reasons.append(f"signal sources partly disagree ({disagreement:.2f})")

        if action == TRADE:
            reasons.append("in distribution, sources agree")
        return AbstentionDecision(action, novelty, disagreement, size, tuple(reasons))


if __name__ == "__main__":
    import random
    random.seed(3)
    dist = FeatureDistribution()
    for _ in range(600):
        dist.observe({
            "atr": random.gauss(30, 6),
            "spread": random.gauss(0.30, 0.05),
            "trend_efficiency": random.gauss(0.42, 0.11),
            "session_range_atr": random.gauss(0.40, 0.09),
        })

    gate = AbstentionGate()
    cases = [
        ("normal market, sources agree",
         {"atr": 31.0, "spread": 0.31, "trend_efficiency": 0.44, "session_range_atr": 0.41},
         [0.7, 0.6, 0.75]),
        ("normal market, sources split",
         {"atr": 30.0, "spread": 0.30, "trend_efficiency": 0.42, "session_range_atr": 0.40},
         [0.8, -0.7, 0.1]),
        ("volatility shock, never seen",
         {"atr": 140.0, "spread": 1.9, "trend_efficiency": 0.9, "session_range_atr": 1.5},
         [0.8, 0.75, 0.8]),
        ("mildly unusual",
         {"atr": 48.0, "spread": 0.45, "trend_efficiency": 0.65, "session_range_atr": 0.62},
         [0.6, 0.55, 0.7]),
    ]
    print(f"  distribution: {dist.as_dict()}\n")
    print(f"  {'case':<32}{'action':<10}{'novelty':>9}{'disagree':>10}{'size':>7}")
    print("  " + "-" * 68)
    for label, feats, sigs in cases:
        d = gate.evaluate(dist, feats, sigs)
        print(f"  {label:<32}{d.action:<10}{d.novelty_z:>9.2f}{d.disagreement:>10.2f}{d.size_multiplier:>7.2f}")
        print(f"  {'':<32}{d.reasons[0]}")
