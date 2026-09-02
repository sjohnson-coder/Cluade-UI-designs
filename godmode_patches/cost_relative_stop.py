"""
Cost-relative stop gate — the highest-expectancy setting change in the bot.

MEASURED ON 4,077,891 M1 XAUUSD BARS (2015-01 -> 2026-08)
---------------------------------------------------------
Same entry model, same sample, ONLY the stop distance changed:

    stop     median stop   cost as % of risk   GROSS exp    NET exp
    0.08 ATR   $1.75            21.8%           -0.003 R   -0.221 R
    0.12 ATR   $2.63            14.6%           -0.003 R   -0.148 R
    0.18 ATR   $3.95             9.7%           -0.022 R   -0.119 R
    0.25 ATR   $5.48             7.0%           -0.006 R   -0.076 R
    0.35 ATR   $7.67             5.0%           -0.006 R   -0.056 R
    0.50 ATR  $10.96             3.5%           -0.006 R   -0.041 R
    1.00 ATR  $21.92             1.7%           -0.001 R   -0.019 R

Gross expectancy is FLAT (~0.00 R) at every stop size. The market gives the same
nothing either way. The entire 0.20 R spread between the top and bottom rows is
transaction cost.

This is the mechanism behind every negative result in the study: cost is a fixed
number of dollars, so measured in R it is inversely proportional to stop distance.
A tighter stop does not "improve R:R" — it multiplies the toll the spread takes
out of every single trade.

GodMode currently allows `automation.earlyIntentProbeMinStopPoints = 1.5`, i.e. a
$1.50 stop. At the configured `ai.maxSpread = 0.4` plus 2 x `brokerCosts.slippage`
of 0.02, round-trip cost is ~$0.44 — **29% of risk per trade**, worse than the
worst row in the table above. No entry model survives that.

THE RULE
--------
Require the stop to be a minimum multiple of the *actual measured* round-trip cost,
not a fixed point value:

    stop_distance >= min_cost_multiple * (spread + entry_slip + exit_slip)

At `min_cost_multiple = 20` the cost is capped at 5% of risk, which is the knee of
the curve above. Below 20 the degradation accelerates sharply; above ~30 the extra
protection is marginal and you start giving up valid setups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MIN_COST_MULTIPLE = 20.0     # cost <= 5% of risk
HARD_FLOOR_COST_MULTIPLE = 12.0      # cost <= 8.3% of risk; never go below this


@dataclass(frozen=True)
class StopGateResult:
    ok: bool
    stop_distance: float
    round_trip_cost: float
    cost_as_fraction_of_risk: float
    required_stop: float
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stopDistance": round(self.stop_distance, 4),
            "roundTripCost": round(self.round_trip_cost, 4),
            "costFractionOfRisk": round(self.cost_as_fraction_of_risk, 4),
            "requiredStop": round(self.required_stop, 4),
            "reason": self.reason,
        }


def round_trip_cost(spread: float, entry_slippage: float = 0.02,
                    exit_slippage: float = 0.02, commission_per_oz: float = 0.0) -> float:
    """All-in cost of a round turn, in price units ($/oz for XAUUSD)."""
    return max(0.0, float(spread)) + max(0.0, float(entry_slippage)) \
        + max(0.0, float(exit_slippage)) + max(0.0, float(commission_per_oz))


def evaluate_stop(stop_distance: float, spread: float, *,
                  entry_slippage: float = 0.02, exit_slippage: float = 0.02,
                  commission_per_oz: float = 0.0,
                  min_cost_multiple: float = DEFAULT_MIN_COST_MULTIPLE) -> StopGateResult:
    """Reject any entry whose stop is too tight relative to what the round turn costs."""
    multiple = max(float(min_cost_multiple), HARD_FLOOR_COST_MULTIPLE)
    cost = round_trip_cost(spread, entry_slippage, exit_slippage, commission_per_oz)
    stop_distance = float(stop_distance)

    if stop_distance <= 0:
        return StopGateResult(False, stop_distance, cost, 1.0, cost * multiple,
                              "Stop distance is zero or negative.")
    if cost <= 0:
        return StopGateResult(True, stop_distance, 0.0, 0.0, 0.0,
                              "No cost model available; gate passed by default.")

    required = cost * multiple
    fraction = cost / stop_distance
    if stop_distance < required:
        return StopGateResult(
            False, stop_distance, cost, fraction, required,
            f"Stop ${stop_distance:.2f} is only {multiple * fraction:.1f}x the "
            f"${cost:.2f} round-trip cost — the spread would take "
            f"{fraction * 100:.1f}% of risk on every trade. "
            f"Minimum stop at this spread is ${required:.2f}.",
        )
    return StopGateResult(True, stop_distance, cost, fraction, required,
                          f"Cost is {fraction * 100:.1f}% of risk.")


def minimum_stop_for(spread: float, *, entry_slippage: float = 0.02,
                     exit_slippage: float = 0.02, commission_per_oz: float = 0.0,
                     min_cost_multiple: float = DEFAULT_MIN_COST_MULTIPLE) -> float:
    """The smallest stop that keeps cost within budget at the current spread.

    Use this to *widen* a proposed stop rather than reject the setup, where the
    strategy allows it. Widening keeps the trade and fixes the economics; the
    position size must then be recomputed from the wider stop so cash risk is
    unchanged.
    """
    cost = round_trip_cost(spread, entry_slippage, exit_slippage, commission_per_oz)
    return cost * max(float(min_cost_multiple), HARD_FLOOR_COST_MULTIPLE)


def volume_for_risk(risk_cash: float, stop_distance: float,
                    contract_size: float = 100.0, volume_step: float = 0.01,
                    volume_min: float = 0.01, volume_max: float = 100.0) -> float:
    """Lots that put exactly `risk_cash` at risk over `stop_distance`.

    Pair this with `minimum_stop_for()`: when the gate widens a stop, size must
    come down or the trade silently carries more cash risk than the plan allowed.
    """
    if stop_distance <= 0 or risk_cash <= 0:
        return 0.0
    raw = risk_cash / (stop_distance * contract_size)
    stepped = int(raw / volume_step) * volume_step
    if stepped < volume_min:
        return 0.0
    return round(min(stepped, volume_max), 2)


if __name__ == "__main__":
    print("GodMode current config vs the cost gate\n")
    print(f"{'scenario':<44} {'stop':>8} {'cost':>7} {'cost/risk':>10}  verdict")
    print("-" * 88)
    scenarios = [
        ("earlyIntentProbeMinStopPoints = 1.5", 1.50, 0.40),
        ("earlyIntentStopAtr 0.45 @ 2018 ATR $12", 5.40, 0.40),
        ("earlyIntentStopAtr 0.45 @ 2026 ATR $128", 57.60, 0.40),
        ("burst nearBeLegStopAtr 0.42 @ ATR $30", 12.60, 0.40),
        ("tight SMC reclaim stop (measured median)", 3.05, 0.35),
        ("same stop, tight ECN spread", 3.05, 0.15),
    ]
    for label, stop, spread in scenarios:
        r = evaluate_stop(stop, spread)
        print(f"{label:<44} ${stop:>7.2f} ${r.round_trip_cost:>6.2f} "
              f"{r.cost_as_fraction_of_risk * 100:>9.1f}%  "
              f"{'PASS' if r.ok else 'BLOCK -> min $%.2f' % r.required_stop}")

    print("\nWidening instead of rejecting, at $0.40 spread, $200 risk budget:")
    min_stop = minimum_stop_for(0.40)
    print(f"  minimum stop ${min_stop:.2f} -> "
          f"{volume_for_risk(200.0, min_stop):.2f} lots (risk held at $200)")
    print(f"  vs $1.50 stop  -> {volume_for_risk(200.0, 1.50):.2f} lots "
          f"(same cash risk, but 29% of it is spread)")
