"""
Probability calibration — turning a score into a probability you can size on.

The bot reports confidence figures (82%, 92% continuation) and sizes against
them. Nothing currently checks whether those numbers mean what they say. The
existing `services/v15/calibration.py` has the *metrics* (Brier, reliability bins,
ECE) but no fitted calibrator, so a miscalibrated score is measured and then used
anyway.

Both research reviews require this explicitly. The ChatGPT blueprint: "Calibrate
model scores with isotonic or Platt scaling on a time-separated calibration set.
Report Brier score, reliability curve, expected calibration error."

Two calibrators, both dependency-free:

  Platt    a logistic fit, 2 parameters. Best when the raw score is roughly
           monotone in the true probability and data is scarce.
  Isotonic pool-adjacent-violators. Non-parametric, monotone, strictly more
           flexible; needs more samples but cannot impose a shape that isn't there.

`fit_calibrator` picks between them on a held-out split rather than by preference,
and refuses to return either when neither beats the uncalibrated score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

MIN_SAMPLES_PLATT = 50
MIN_SAMPLES_ISOTONIC = 150


def _clamp(p: float, lo: float = 1e-6, hi: float = 1.0 - 1e-6) -> float:
    return max(lo, min(hi, float(p)))


def brier(preds: Sequence[float], outcomes: Sequence[int]) -> float:
    pairs = list(zip(preds, outcomes))
    if not pairs:
        return 1.0
    return sum((_clamp(p) - (1 if y else 0)) ** 2 for p, y in pairs) / len(pairs)


def log_loss(preds: Sequence[float], outcomes: Sequence[int]) -> float:
    pairs = list(zip(preds, outcomes))
    if not pairs:
        return 10.0
    return -sum(math.log(_clamp(p)) if y else math.log(1 - _clamp(p))
                for p, y in pairs) / len(pairs)


def expected_calibration_error(preds: Sequence[float], outcomes: Sequence[int],
                               bins: int = 10) -> float:
    pairs = list(zip(preds, outcomes))
    if not pairs:
        return 1.0
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(max(2, bins))]
    for p, y in pairs:
        idx = min(len(buckets) - 1, int(_clamp(p) * len(buckets)))
        buckets[idx].append((_clamp(p), 1 if y else 0))
    total = len(pairs)
    return sum(
        (len(b) / total) * abs(sum(p for p, _ in b) / len(b) - sum(y for _, y in b) / len(b))
        for b in buckets if b
    )


class PlattCalibrator:
    """Logistic recalibration: p' = sigmoid(a * logit(p) + b)."""

    method = "platt"

    def __init__(self, a: float = 1.0, b: float = 0.0):
        self.a, self.b = float(a), float(b)

    @staticmethod
    def _logit(p: float) -> float:
        p = _clamp(p)
        return math.log(p / (1 - p))

    def predict(self, p: float) -> float:
        z = self.a * self._logit(p) + self.b
        z = max(-30.0, min(30.0, z))
        return _clamp(1.0 / (1.0 + math.exp(-z)))

    @classmethod
    def fit(cls, preds: Sequence[float], outcomes: Sequence[int],
            iterations: int = 200, lr: float = 0.12) -> "PlattCalibrator":
        xs = [cls._logit(p) for p in preds]
        ys = [1.0 if y else 0.0 for y in outcomes]
        a, b, n = 1.0, 0.0, len(xs)
        if n == 0:
            return cls()
        for _ in range(iterations):
            ga = gb = 0.0
            for x, y in zip(xs, ys):
                z = max(-30.0, min(30.0, a * x + b))
                err = 1.0 / (1.0 + math.exp(-z)) - y
                ga += err * x
                gb += err
            a -= lr * ga / n
            b -= lr * gb / n
        return cls(a, b)


class IsotonicCalibrator:
    """Pool-adjacent-violators: the monotone step function fitting the data best."""

    method = "isotonic"

    def __init__(self, thresholds: list[float], values: list[float]):
        self.thresholds, self.values = thresholds, values

    def predict(self, p: float) -> float:
        p = _clamp(p)
        if not self.thresholds:
            return p
        lo, hi = 0, len(self.thresholds) - 1
        while lo < hi:                       # first threshold >= p
            mid = (lo + hi) // 2
            if self.thresholds[mid] < p:
                lo = mid + 1
            else:
                hi = mid
        return _clamp(self.values[lo] if self.thresholds[lo] >= p else self.values[-1])

    @classmethod
    def fit(cls, preds: Sequence[float], outcomes: Sequence[int]) -> "IsotonicCalibrator":
        pairs = sorted(zip((_clamp(p) for p in preds), (1.0 if y else 0.0 for y in outcomes)))
        if not pairs:
            return cls([], [])
        xs = [p for p, _ in pairs]
        blocks = [[y, 1.0] for _, y in pairs]        # [sum, weight]
        i = 0
        while i < len(blocks) - 1:
            if blocks[i][0] / blocks[i][1] <= blocks[i + 1][0] / blocks[i + 1][1] + 1e-12:
                i += 1
                continue
            blocks[i][0] += blocks[i + 1][0]
            blocks[i][1] += blocks[i + 1][1]
            del blocks[i + 1]
            # also delete the matching x so thresholds stay aligned with blocks
            del xs[i + 1]
            if i > 0:
                i -= 1
        return cls(xs, [b[0] / b[1] for b in blocks])


class IdentityCalibrator:
    """Used when no calibrator beats the raw score. Honest about doing nothing."""

    method = "identity"

    def predict(self, p: float) -> float:
        return _clamp(p)


@dataclass(frozen=True)
class CalibrationReport:
    method: str
    samples: int
    brier_before: float
    brier_after: float
    ece_before: float
    ece_after: float
    log_loss_before: float
    log_loss_after: float
    improved: bool
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "samples": self.samples,
            "brierBefore": round(self.brier_before, 5),
            "brierAfter": round(self.brier_after, 5),
            "eceBefore": round(self.ece_before, 5),
            "eceAfter": round(self.ece_after, 5),
            "logLossBefore": round(self.log_loss_before, 5),
            "logLossAfter": round(self.log_loss_after, 5),
            "improved": self.improved,
            "reason": self.reason,
        }


def fit_calibrator(preds: Sequence[float], outcomes: Sequence[int],
                   holdout_fraction: float = 0.3):
    """Fit on the earlier part of the sample, select on the later part.

    The split is chronological, not random: probabilities drift with regime, and a
    random split leaks the future into the fit.
    """
    preds, outcomes = list(preds), [1 if y else 0 for y in outcomes]
    n = len(preds)
    if n < MIN_SAMPLES_PLATT:
        return IdentityCalibrator(), CalibrationReport(
            "identity", n, brier(preds, outcomes), brier(preds, outcomes),
            expected_calibration_error(preds, outcomes),
            expected_calibration_error(preds, outcomes),
            log_loss(preds, outcomes), log_loss(preds, outcomes),
            False, f"need >= {MIN_SAMPLES_PLATT} outcomes, have {n}",
        )

    cut = max(MIN_SAMPLES_PLATT // 2, int(n * (1 - holdout_fraction)))
    fit_p, fit_y = preds[:cut], outcomes[:cut]
    val_p, val_y = preds[cut:], outcomes[cut:]
    if not val_p:
        val_p, val_y = fit_p, fit_y

    candidates = [PlattCalibrator.fit(fit_p, fit_y)]
    if n >= MIN_SAMPLES_ISOTONIC:
        candidates.append(IsotonicCalibrator.fit(fit_p, fit_y))

    base = brier(val_p, val_y)
    best, best_score = IdentityCalibrator(), base
    for cand in candidates:
        score = brier([cand.predict(p) for p in val_p], val_y)
        if score < best_score - 1e-9:
            best, best_score = cand, score

    after = [best.predict(p) for p in val_p]
    improved = best.method != "identity"
    return best, CalibrationReport(
        method=best.method, samples=n,
        brier_before=base, brier_after=brier(after, val_y),
        ece_before=expected_calibration_error(val_p, val_y),
        ece_after=expected_calibration_error(after, val_y),
        log_loss_before=log_loss(val_p, val_y), log_loss_after=log_loss(after, val_y),
        improved=improved,
        reason="" if improved else "no calibrator beat the raw score on the holdout",
    )


if __name__ == "__main__":
    import random
    random.seed(11)
    # A deliberately overconfident scorer: true p is a shrunk version of the score.
    raw, actual = [], []
    for _ in range(900):
        true_p = random.uniform(0.15, 0.85)
        shown = _clamp(0.5 + (true_p - 0.5) * 1.75)     # pushed toward the extremes
        raw.append(shown)
        actual.append(1 if random.random() < true_p else 0)

    cal, rep = fit_calibrator(raw, actual)
    print(f"  selected     {rep.method}  ({rep.samples} samples)")
    print(f"  Brier        {rep.brier_before:.4f} -> {rep.brier_after:.4f}")
    print(f"  ECE          {rep.ece_before:.4f} -> {rep.ece_after:.4f}")
    print(f"  log loss     {rep.log_loss_before:.4f} -> {rep.log_loss_after:.4f}")
    print(f"  improved     {rep.improved}")
    print("\n  what the bot would have shown vs what it means:")
    for shown in (0.60, 0.75, 0.85, 0.92):
        print(f"    displayed {shown:.0%}  ->  calibrated {cal.predict(shown):.0%}")
