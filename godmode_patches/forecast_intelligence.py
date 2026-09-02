"""
Volatility forecasting — the one thing in XAUUSD that is actually forecastable.

Measured on 4,077,891 M1 XAUUSD bars (2015-01 -> 2026-08):

    yesterday's ATR14   -> today's true range     R2 = 0.5625
    yesterday's return  -> today's return         R2 = 0.00018
                                                  ratio ~3,160x

The bot already has a probability engine that scores direction. It has no model
for magnitude, which is the half of the problem the data actually supports. This
module supplies it.

HAR-RV
------
The Heterogeneous AutoRegressive model of realised volatility (Corsi, 2009) is the
standard forecaster for this shape of data. It regresses tomorrow's range on three
horizons, which stand in for three classes of market participant:

    RV_{t+1} = c + b_d*RV_daily + b_w*RV_weekly(5) + b_m*RV_monthly(22)

It is a plain linear model, so it is cheap, deterministic, has no training loop,
and cannot silently diverge in a hot path. Coefficients are fitted by ordinary
least squares over a rolling window using only completed bars available at the
decision timestamp.

Everything here is pure Python -- no numpy -- so it is importable inside the
trading lane without adding a dependency or an import cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

DAILY, WEEKLY, MONTHLY = 1, 5, 22
MIN_OBSERVATIONS = 60


@dataclass(frozen=True)
class VolatilityForecast:
    """Tomorrow's expected range, with an honest interval around it."""
    expected_range: float
    lower: float
    upper: float
    horizon_days: int
    r_squared: float
    observations: int
    coefficients: dict[str, float]
    method: str
    degraded: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "expectedRange": round(self.expected_range, 4),
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
            "horizonDays": self.horizon_days,
            "rSquared": round(self.r_squared, 4),
            "observations": self.observations,
            "coefficients": {k: round(v, 6) for k, v in self.coefficients.items()},
            "method": self.method,
            "degraded": self.degraded,
            "reason": self.reason,
        }


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting. Returns None if singular."""
    n = len(matrix)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col] / aug[col][col]
            for c in range(col, n + 1):
                aug[r][c] -= factor * aug[col][c]
    return [aug[i][n] / aug[i][i] for i in range(n)]


def _ols(features: list[list[float]], targets: list[float]) -> tuple[list[float], float] | None:
    """Least squares with an intercept. Returns (coefficients, R^2)."""
    n, k = len(targets), len(features[0]) if features else 0
    if n <= k + 1:
        return None
    design = [[1.0] + row for row in features]
    width = k + 1
    xtx = [[sum(design[i][a] * design[i][b] for i in range(n)) for b in range(width)]
           for a in range(width)]
    xty = [sum(design[i][a] * targets[i] for i in range(n)) for a in range(width)]
    beta = _solve(xtx, xty)
    if beta is None:
        return None

    mean_y = _mean(targets)
    ss_tot = sum((y - mean_y) ** 2 for y in targets)
    ss_res = sum((targets[i] - sum(beta[j] * design[i][j] for j in range(width))) ** 2
                 for i in range(n))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    return beta, max(0.0, min(1.0, r2))


def _rolling_mean(series: Sequence[float], end: int, window: int) -> float:
    start = max(0, end - window + 1)
    chunk = series[start:end + 1]
    return _mean(chunk) if chunk else 0.0


class HARVolatilityForecaster:
    """Forecast the next session's range from completed daily ranges.

    Feed it true ranges (high-low, or the full true range) oldest-first. It uses
    only bars strictly before the forecast point, so it cannot look ahead.
    """

    def __init__(self, lookback: int = 500, interval: float = 0.80):
        self.lookback = max(MIN_OBSERVATIONS, int(lookback))
        self.interval = min(0.99, max(0.50, float(interval)))

    def forecast(self, ranges: Sequence[float]) -> VolatilityForecast:
        series = [float(r) for r in ranges if r is not None and float(r) > 0]
        if len(series) < MONTHLY + MIN_OBSERVATIONS:
            fallback = _rolling_mean(series, len(series) - 1, 14) if series else 0.0
            return VolatilityForecast(
                fallback, fallback * 0.6, fallback * 1.6, 1, 0.0, len(series),
                {}, "atr14_fallback", degraded=True,
                reason=f"need {MONTHLY + MIN_OBSERVATIONS} completed bars, have {len(series)}",
            )

        series = series[-(self.lookback + MONTHLY + 1):]
        features: list[list[float]] = []
        targets: list[float] = []
        for t in range(MONTHLY - 1, len(series) - 1):
            features.append([
                series[t],
                _rolling_mean(series, t, WEEKLY),
                _rolling_mean(series, t, MONTHLY),
            ])
            targets.append(series[t + 1])

        fit = _ols(features, targets)
        if fit is None:
            fallback = _rolling_mean(series, len(series) - 1, 14)
            return VolatilityForecast(
                fallback, fallback * 0.6, fallback * 1.6, 1, 0.0, len(targets),
                {}, "atr14_fallback", degraded=True, reason="singular design matrix",
            )

        beta, r2 = fit
        last = len(series) - 1
        point = (beta[0]
                 + beta[1] * series[last]
                 + beta[2] * _rolling_mean(series, last, WEEKLY)
                 + beta[3] * _rolling_mean(series, last, MONTHLY))
        point = max(point, 1e-9)

        # Empirical interval from the in-sample ratio distribution: robust to the
        # right skew of realised range, where a normal interval understates the tail.
        ratios = sorted(targets[i] / max(1e-9, (
            beta[0] + beta[1] * features[i][0] + beta[2] * features[i][1] + beta[3] * features[i][2]
        )) for i in range(len(targets)))
        tail = (1.0 - self.interval) / 2.0
        lo_idx = max(0, int(tail * len(ratios)) - 1)
        hi_idx = min(len(ratios) - 1, int((1.0 - tail) * len(ratios)))

        return VolatilityForecast(
            expected_range=point,
            lower=point * ratios[lo_idx],
            upper=point * ratios[hi_idx],
            horizon_days=1,
            r_squared=r2,
            observations=len(targets),
            coefficients={"const": beta[0], "daily": beta[1], "weekly": beta[2], "monthly": beta[3]},
            method="HAR-RV",
        )


@dataclass
class SessionRangeForecaster:
    """Split a daily range forecast into sessions using measured proportions.

    Medians from the same 4.08M-bar sample, as a fraction of daily ATR14.
    """
    shares: dict[str, float] = field(default_factory=lambda: {
        "ASIA": 0.377, "LONDON": 0.404, "NEW_YORK": 0.572, "NEW_YORK_PM": 0.310,
    })

    def forecast(self, daily_forecast: VolatilityForecast) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for session, share in self.shares.items():
            out[session] = {
                "expectedRange": round(daily_forecast.expected_range * share, 4),
                "lower": round(daily_forecast.lower * share, 4),
                "upper": round(daily_forecast.upper * share, 4),
                "shareOfDailyAtr": share,
            }
        return out


def stop_distance_from_forecast(forecast: VolatilityForecast, atr_multiple: float = 0.35,
                                min_cost_stop: float = 0.0) -> float:
    """Size a stop off forecast range instead of trailing ATR.

    Trailing ATR is backward-looking; on a regime change it is the wrong size in
    exactly the sessions that matter. `min_cost_stop` keeps the cost-relative
    floor authoritative.
    """
    return max(float(min_cost_stop), forecast.expected_range * float(atr_multiple))


if __name__ == "__main__":
    import random
    random.seed(7)
    # a series with volatility clustering, which is what HAR is built for
    series, level = [], 20.0
    for _ in range(600):
        level = 0.94 * level + 0.06 * 20.0 + random.gauss(0, 1.4)
        series.append(max(1.0, abs(random.gauss(level, level * 0.28))))

    f = HARVolatilityForecaster().forecast(series)
    print(f"  method       {f.method}")
    print(f"  observations {f.observations}")
    print(f"  R^2          {f.r_squared:.3f}")
    print(f"  expected     {f.expected_range:.2f}  [{f.lower:.2f} .. {f.upper:.2f}]")
    print(f"  coefficients {f.as_dict()['coefficients']}")
    print("\n  session split:")
    for k, v in SessionRangeForecaster().forecast(f).items():
        print(f"    {k:<12} {v['expectedRange']:>7.2f}  [{v['lower']:.2f} .. {v['upper']:.2f}]")
