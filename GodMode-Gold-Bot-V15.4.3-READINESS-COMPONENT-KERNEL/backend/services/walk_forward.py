"""V13.11 — Walk-Forward Optimization harness (Phase 2 of the GodMode roadmap).

Why this exists: a single backtest fitted to all history is how strategies get overfit —
high simulated performance is easy to reach after trying a handful of configurations, and
such strategies then systematically underperform live. The industry-standard defence
(Pardo 1992/2008) is walk-forward analysis: optimize parameters on an in-sample window,
validate them on the NEXT unseen window, roll forward, and judge ONLY the concatenated
out-of-sample results. Fewer than 5 cycles is treated as unreliable by construction.

This harness wraps the existing CostAwareBacktester (spread/commission/slippage aware) so
every parameter idea must survive data it was never fitted to BEFORE it touches live config.
"""
from __future__ import annotations

import itertools
from typing import Any, Callable


def _grid(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Expand {'a':[1,2],'b':[x]} into [{'a':1,'b':x},{'a':2,'b':x}] — small grids only."""
    if not param_grid:
        return [{}]
    keys = sorted(param_grid.keys())
    size = 1
    values: list[list[Any]] = []
    for key in keys:
        row = list(param_grid[key])
        if not row:
            raise ValueError(f"Parameter grid value list is empty for {key!r}.")
        size *= len(row)
        if size > 60:
            raise ValueError(f"Grid too large ({size} combos). Keep it under 60.")
        values.append(row)
    combos = list(itertools.product(*values))
    return [dict(zip(keys, c)) for c in combos]


def _objective(stats: dict[str, Any]) -> float:
    """In-sample selection objective. Expectancy-first (PF alone rewards tiny-sample flukes);
    profit factor breaks ties; a minimum trade count keeps degenerate configs from winning
    by barely trading."""
    if not stats or not stats.get("ok"):
        return float("-inf")
    ov = stats.get("overall") or {}
    n = int(ov.get("trades") or 0)
    if n < 8:
        return float("-inf")
    exp = float(ov.get("expectancyR") or 0.0)
    pf = float(ov.get("profitFactor") or 0.0)
    return exp + min(pf, 3.0) * 0.05  # expectancy dominates; PF is the tie-breaker


def run_walk_forward(candles: list[dict[str, Any]],
                     run_backtest: Callable[[list[dict[str, Any]], dict[str, Any]], dict[str, Any]],
                     param_grid: dict[str, list[Any]],
                     base_params: dict[str, Any] | None = None,
                     train_bars: int = 2000,
                     test_bars: int = 500,
                     warmup: int = 250) -> dict[str, Any]:
    """Anchor-free (rolling) WFO. Each cycle: fit the grid on train_bars, keep the best config,
    score it on the NEXT test_bars it has never seen. Only the concatenated OOS results are
    reported as 'the' performance; in-sample numbers are shown purely to expose overfitting
    (a big IS->OOS drop is the tell)."""
    base = dict(base_params or {})
    base["warmup"] = warmup
    n = len(candles or [])
    step = test_bars
    min_needed = train_bars + test_bars + warmup
    if n < min_needed:
        return {"ok": False, "message": f"Need >= {min_needed} candles for even one WFO cycle; got {n}."}
    if train_bars <= 0 or test_bars <= 0 or warmup < 0:
        return {"ok": False, "message": "trainBars and testBars must be positive; warmup cannot be negative."}
    try:
        grid = _grid(param_grid)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "message": str(exc)}
    cycles: list[dict[str, Any]] = []
    start = 0
    while start + train_bars + test_bars <= n:
        train = candles[start: start + train_bars]
        test = candles[start + train_bars: start + train_bars + test_bars]
        best_cfg, best_score, best_is = None, float("-inf"), None
        for cfg in grid:
            params = {**base, **cfg}
            stats = run_backtest(train, params)
            sc = _objective(stats)
            if sc > best_score:
                best_cfg, best_score, best_is = cfg, sc, (stats.get("overall") or {})
        if best_cfg is None:
            start += step
            continue
        oos = run_backtest(test, {**base, **best_cfg})
        oos_ov = (oos.get("overall") or {}) if oos.get("ok") else {}
        cycles.append({
            "cycle": len(cycles) + 1,
            "trainBars": [start, start + train_bars],
            "testBars": [start + train_bars, start + train_bars + test_bars],
            "chosenParams": best_cfg,
            "inSample": {k: best_is.get(k) for k in ("trades", "profitFactor", "expectancyR", "netR")} if best_is else {},
            "outOfSample": {k: oos_ov.get(k) for k in ("trades", "profitFactor", "expectancyR", "netR")} if oos_ov else {"ok": False, "message": oos.get("message")},
            "oosOk": bool(oos.get("ok")),
        })
        start += step
    scored = [c for c in cycles if c.get("oosOk") and (c["outOfSample"].get("trades") or 0) > 0]
    total_trades = sum(int(c["outOfSample"].get("trades") or 0) for c in scored)
    # concatenate OOS: trade-weighted expectancy; PF recomputed from netR proxy is not possible
    # without raw trades, so report trade-weighted mean PF alongside per-cycle values (honest label).
    agg_exp = (sum(float(c["outOfSample"].get("expectancyR") or 0.0) * int(c["outOfSample"].get("trades") or 0) for c in scored) / total_trades) if total_trades else 0.0
    agg_pf = (sum(float(c["outOfSample"].get("profitFactor") or 0.0) * int(c["outOfSample"].get("trades") or 0) for c in scored) / total_trades) if total_trades else 0.0
    positive_cycles = sum(1 for c in scored if float(c["outOfSample"].get("expectancyR") or 0.0) > 0)
    # parameter stability: how often did the winning config repeat?
    from collections import Counter
    cfg_counts = Counter(str(sorted((c.get("chosenParams") or {}).items())) for c in cycles)
    stability = (cfg_counts.most_common(1)[0][1] / len(cycles)) if cycles else 0.0
    enough = len(scored) >= 5
    robust = enough and agg_exp > 0 and positive_cycles >= max(3, int(0.6 * len(scored)))
    verdict = ("ROBUST — positive out-of-sample expectancy across cycles" if robust
               else ("INSUFFICIENT CYCLES — fewer than 5 scored OOS windows; treat as chance" if not enough
                     else "NOT ROBUST — the edge does not survive data it was not fitted to"))
    return {
        "ok": True,
        "cycles": cycles,
        "summary": {
            "cyclesRun": len(cycles), "cyclesScored": len(scored), "oosTrades": total_trades,
            "oosExpectancyR": round(agg_exp, 4), "oosMeanProfitFactor": round(agg_pf, 3),
            "positiveCycles": positive_cycles, "paramStability": round(stability, 2),
            "verdict": verdict, "robust": robust,
        },
        "note": ("Judge ONLY the out-of-sample line. In-sample numbers are shown to expose overfitting: "
                 "a large IS->OOS drop means the parameters memorised the past. paramStability near 1.0 "
                 "means the same config keeps winning (good); near 1/len(grid) means the optimizer is "
                 "chasing noise."),
    }
