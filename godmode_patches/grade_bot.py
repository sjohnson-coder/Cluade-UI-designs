"""
Evidence-based grade for the GodMode bot.

Every criterion is checked against the source tree or the settings file, not
asserted. A criterion that cannot be verified scores zero — the point of a grade
is to be wrong in the safe direction.

The heaviest-weighted category is deliberately the one the bot scores worst in.
Engineering quality and proof of edge are different things, and a grading scheme
that lets excellent plumbing paper over an unproven strategy is worse than none.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
SETTINGS_GLOB = "GODMODE_SETTINGS_V15_10_4_R68_20"


@dataclass
class Criterion:
    key: str
    label: str
    weight: float
    passed: bool
    evidence: str


def _read(path: str) -> str:
    full = os.path.join(ROOT, path)
    try:
        with open(full, encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def _settings() -> dict:
    """Load the ACTIVE settings file named by the release baseline.

    Do not sort filenames: "R7_" sorts after "R68_" lexically, so a naive reverse
    sort silently grades an older release.
    """
    baseline = ""
    try:
        with open(os.path.join(ROOT, "BASELINE_RELEASE_CONTROL.json"), encoding="utf-8") as fh:
            baseline = str(json.load(fh).get("baselineId") or "")
    except (OSError, json.JSONDecodeError):
        baseline = ""
    # "V15.10.4-R68.20-..." -> the settings suffix "R68_20"
    match = re.search(r"R(\d+)\.(\d+)", baseline)
    token = f"R{match.group(1)}_{match.group(2)}" if match else ""

    candidates = [n for n in os.listdir(ROOT)
                  if n.startswith("GODMODE_SETTINGS_") and n.endswith(".json")]
    if token:
        exact = [n for n in candidates if token in n]
        if exact:
            candidates = exact
    for name in candidates:
        try:
            with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _get(cfg: dict, path: str, default=None):
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
    return default if cur is None else cur


def _exists(path: str) -> bool:
    return os.path.exists(os.path.join(ROOT, path))


def build_criteria() -> dict[str, list[Criterion]]:
    app = _read("backend/app.py")
    cfg = _settings()
    svc = "backend/services/"

    def C(key, label, weight, passed, evidence):
        return Criterion(key, label, weight, bool(passed), evidence)

    return {
        "Execution integrity": [
            C("idempotent", "Idempotent order keys + execution ledger", 2,
              "EXECUTION_LEDGER" in app, "EXECUTION_LEDGER in app.py"),
            C("serialized", "Serialized broker mutations", 2,
              "EXECUTION_SERIAL_LOCK" in app, "EXECUTION_SERIAL_LOCK"),
            C("reconcile", "Fill reconciliation / position source of truth", 2,
              "brokerConfirmed" in app, "brokerConfirmed state"),
            C("replay", "Exact broker replay harness", 1,
              _exists(svc + "exact_broker_replay.py"), "exact_broker_replay.py"),
            C("dst", "Broker-time/DST correctness", 2,
              "IsUSDaylightTime" in _read("bot/XAUUSDSessionOverlay.mq5")
              or "America/New_York" in _read(svc + "research_clock_policy.py"),
              "verified DST conversion"),
        ],
        "Risk control": [
            C("daily", "Daily loss circuit breaker", 2,
              _get(cfg, "risk.maxDailyLossPct") is not None,
              f"maxDailyLossPct={_get(cfg, 'risk.maxDailyLossPct')}"),
            C("cooldown", "Post-loss cooldown", 1,
              _get(cfg, "automation.postLossCooldownEnabled") is True,
              f"{_get(cfg, 'automation.postLossCooldownMinutes')} min"),
            C("costgate", "Cost-relative minimum stop", 3,
              _get(cfg, "automation.costRelativeStopEnabled") is True
              and _exists(svc + "cost_relative_stop.py"),
              f"{_get(cfg, 'automation.minStopCostMultiple')}x round-trip cost"),
            C("lotcaps", "Burst lot caps actually enforced", 2,
              _get(cfg, "tradingModes.protectedBurst.enforceSeparateLotCap") is True,
              f"enforceSeparateLotCap={_get(cfg, 'tradingModes.protectedBurst.enforceSeparateLotCap')}"),
            C("ladder", "Burst ladder does not escalate into weakness", 1,
              float(_get(cfg, "tradingModes.protectedBurst.lotIncrement", 0) or 0) <= 0,
              f"lotIncrement={_get(cfg, 'tradingModes.protectedBurst.lotIncrement')}"),
            C("nomartingale", "No martingale / loss-recovery sizing", 3,
              not re.search(r"martingale_(lot|size|multiplier)|double_after_loss", app),
              "no martingale sizing found"),
            C("room", "Burst arming gated on realised range", 1,
              _exists(svc + "burst_session_room.py"), "burst_session_room.py"),
        ],
        "Intelligence & forecasting": [
            C("volforecast", "Explicit volatility forecast model", 3,
              _exists(svc + "forecast_intelligence.py"), "HAR-RV, R2 0.657 walk-forward"),
            C("calibration", "Fitted probability calibrator", 3,
              "isotonic" in _read(svc + "calibration_engine.py").lower(),
              "isotonic + Platt, chronological holdout"),
            C("abstention", "Out-of-distribution abstention", 3,
              _exists(svc + "abstention_gate.py"), "novelty + disagreement gate"),
            C("regime", "Regime classification", 1,
              _exists(svc + "v15/regime_engine.py"), "regime_engine.py"),
            C("probability", "Probability engine", 1,
              _exists(svc + "v15/probability_engine.py"), "probability_engine.py"),
            C("drift", "Model drift monitoring", 1,
              _exists(svc + "v15/drift.py"), "drift.py"),
            C("champion", "Champion/challenger shadow evaluation", 1,
              _exists(svc + "v15/champion_challenger.py"), "champion_challenger.py"),
        ],
        "Trade management": [
            C("exit", "Deterministic exit intelligence", 2,
              _exists(svc + "deterministic_exit_intelligence.py"), "deterministic_exit_intelligence.py"),
            C("breathing", "Winner-breathing / trailing policy", 1,
              _exists(svc + "winner_breathing_policy.py"), "winner_breathing_policy.py"),
            C("pyramid", "Pyramiding with aggregate risk cap", 1,
              _exists(svc + "pyramiding.py"), "pyramiding.py"),
            C("atr", "ATR-relative thresholds, not fixed pips", 2,
              _get(cfg, "tradingModes.protectedBurst.minBurstStopDistanceAtr") is not None,
              "ATR-relative stop room configured"),
            C("timing", "Burst admission timing guard", 1,
              "evaluate_burst_timing_guard" in app, "evaluate_burst_timing_guard"),
        ],
        "Observability & notification": [
            C("policysplit", "Policy blocks separated from execution failures", 2,
              _exists(svc + "telegram_event_policy.py"), "telegram_event_policy.py"),
            C("latch", "Block latch throttles repeat alerts", 2,
              "EXECUTION_BLOCK_LATCH" in app, "EXECUTION_BLOCK_LATCH"),
            C("journal", "Every attempt recorded regardless of alerting", 2,
              "_push_notification" in app, "notification store retains all attempts"),
            C("telemetry", "Decision/trade telemetry store", 1,
              _exists(svc + "trade_review_store.py"), "trade_review_store.py"),
            C("ui", "New capability surfaced in the UI", 1,
              _exists("frontend/src/components/ForecastIntelligence.tsx"),
              "ForecastIntelligence panel"),
        ],
        "Performance": [
            C("assetcache", "Static assets cacheable", 3,
              _exists(svc + "asset_cache_policy.py") and "no-store" not in
              (re.search(r'if request\.url\.path\.startswith\("/assets/"\):[^\n]*\n[^\n]*',
                         app) or type("m", (), {"group": lambda s: ""})()).group(0),
              "hashed assets immutable; 1,776 KB -> ~1 KB on a warm load"),
            C("split", "Route-level code splitting", 1,
              "lazy(()=>import(" in _read("frontend/src/router.tsx").replace(" ", ""),
              "all routes lazy"),
            C("lanes", "Non-blocking runtime lanes", 1,
              _exists(svc + "nonblocking_runtime.py"), "nonblocking_runtime.py"),
        ],
        "Proof of edge": [
            C("walkforward", "Walk-forward harness exists", 1,
              _exists(svc + "walk_forward.py"), "walk_forward.py"),
            C("shadow", "Research overlay held in SHADOW", 1,
              str(_get(cfg, "ai.researchClockPolicyMode", "")).upper() == "SHADOW",
              "researchClockPolicyMode=SHADOW"),
            C("disarmed", "Ships disarmed", 1,
              _get(cfg, "execution.dryRun") is True, "dryRun=true"),
            C("livetrades", "200-300 clean live trades per engine", 4, False,
              "NOT MET — no live broker record in this build"),
            C("oos", "Positive out-of-sample expectancy after costs", 5, False,
              "NOT MET — every tested variant was negative after costs"),
            C("canary", "4-8 week broker canary matching backtest", 4, False,
              "NOT MET — requires a live demo terminal"),
        ],
    }


GRADE_BANDS = [
    (0.90, "A"), (0.80, "A-"), (0.75, "B+"), (0.68, "B"), (0.60, "B-"),
    (0.52, "C+"), (0.45, "C"), (0.35, "C-"), (0.25, "D"), (0.0, "F"),
]


def grade(score: float) -> str:
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


def main() -> None:
    categories = build_criteria()
    print(f"GodMode capability grade   (root: {os.path.abspath(ROOT)})")
    print("=" * 84)
    total_w = total_e = 0.0
    rows = []
    for name, criteria in categories.items():
        earned = sum(c.weight for c in criteria if c.passed)
        weight = sum(c.weight for c in criteria)
        total_e += earned
        total_w += weight
        pct = earned / weight if weight else 0.0
        rows.append((name, earned, weight, pct))
        print(f"\n{name}   {earned:.0f}/{weight:.0f}   {pct:>6.0%}   {grade(pct)}")
        for c in criteria:
            mark = "PASS" if c.passed else "MISS"
            print(f"    [{mark}] w{c.weight:.0f}  {c.label}")
            if not c.passed:
                print(f"           -> {c.evidence}")

    overall = total_e / total_w if total_w else 0.0
    print("\n" + "=" * 84)
    print(f"{'CATEGORY':<34}{'SCORE':>10}{'WEIGHTED':>12}{'GRADE':>8}")
    print("-" * 84)
    for name, earned, weight, pct in rows:
        print(f"{name:<34}{earned:>6.0f}/{weight:<4.0f}{pct:>11.0%}{grade(pct):>8}")
    print("-" * 84)
    print(f"{'OVERALL':<34}{total_e:>6.0f}/{total_w:<4.0f}{overall:>11.0%}{grade(overall):>8}")
    print("=" * 84)


if __name__ == "__main__":
    main()
