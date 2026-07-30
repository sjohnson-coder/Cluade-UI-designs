from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app.py"
SETTINGS = ROOT / "backend" / "data" / "settings.json"
UI = ROOT / "frontend" / "src" / "pages" / "Settings.tsx"
DIST_SETTINGS = ROOT / "frontend" / "dist" / "assets" / "Settings-V1513-JOURNAL-DRIVEN-FIXES.js"


def _function_source(name: str) -> str:
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


def test_management_computes_fresh_exit_intelligence_before_probe_promotion():
    source = _function_source("_auto_manage_open_trades")
    assert "evaluate_exit_intelligence(" in source
    assert source.index("evaluate_exit_intelligence(") < source.index("classify_probe_lifecycle(")
    assert "peak_r=float(st.get(\"peakR\"" in source
    assert "context_score=float(_exit_intel.continuation_score" in source


def test_runner_policy_controls_giveback_trail_and_v14_floor():
    source = _function_source("_auto_manage_open_trades")
    assert "_adaptive_giveback = float(_exit_intel.max_giveback_fraction)" in source
    assert "_adaptive_trail_atr = float(_exit_intel.trail_atr)" in source
    assert "max_giveback=_adaptive_giveback" in source
    assert "max_giveback_fraction=_adaptive_giveback" in source
    assert "dyn_mult = _adaptive_trail_atr" in source
    assert "_eff_lock_frac = max(0.0, 1.0 - _adaptive_giveback)" in source
    assert "_eff_trail_atr_mult - max(0.0, profit_atr - 1.0)" not in source


def test_runner_can_preemptively_breathe_without_waiting_for_stop_proximity():
    source = _function_source("_auto_manage_open_trades")
    assert '_exit_intel.action == "BREATHE"' in source
    assert "_exit_intel.allow_widen" in source
    assert "_exit_intel.recommended_sl" in source
    assert "preemptive runner room" in source


def test_packaged_settings_expose_deterministic_runner_controls():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    tm = data["trading"]["tradeManagement"]
    expected = {
        "deterministicExitIntelligenceEnabled",
        "runnerContinuationScore",
        "runnerMinPeakR",
        "runnerGivebackFraction",
        "strongRunnerGivebackFraction",
        "runnerTrailAtr",
        "runnerBreathCooldownSeconds",
        "runnerPromotionPeakR",
        "runnerPromotionContextScore",
    }
    assert expected <= set(tm)
    assert tm["deterministicExitIntelligenceEnabled"] is True
    assert tm["runnerGivebackFraction"] >= 0.60
    assert tm["runnerTrailAtr"] >= 0.75


def test_settings_ui_exposes_runner_intelligence_not_just_fixed_dynamic_sl():
    source = UI.read_text(encoding="utf-8")
    assert "Deterministic Runner Intelligence" in source
    for path in (
        "trading.tradeManagement.deterministicExitIntelligenceEnabled",
        "trading.tradeManagement.runnerContinuationScore",
        "trading.tradeManagement.runnerGivebackFraction",
        "trading.tradeManagement.runnerTrailAtr",
        "trading.tradeManagement.runnerBreathCooldownSeconds",
    ):
        assert path in source


def test_runner_settings_are_range_checked_and_monotonic():
    import copy
    import pytest
    import app

    bad = copy.deepcopy(app._default_settings())
    bad["trading"]["tradeManagement"]["runnerGivebackFraction"] = 0.90
    with pytest.raises(ValueError, match="runnerGivebackFraction"):
        app._validate_settings_candidate(bad, strict_ranges=True)

    reversed_policy = copy.deepcopy(app._default_settings())
    tm = reversed_policy["trading"]["tradeManagement"]
    tm["runnerGivebackFraction"] = 0.70
    tm["strongRunnerGivebackFraction"] = 0.60
    with pytest.raises(ValueError, match="runner giveback"):
        app._validate_settings_candidate(reversed_policy, strict_ranges=True)


def test_trade_management_status_exposes_exit_intelligence_telemetry():
    import app

    row = app._decorate_trade_protection(
        {
            "ticket": "1528",
            "direction": "SELL",
            "entryPrice": 4015.49,
            "currentPrice": 4010.00,
            "sl": 4014.25,
        },
        {
            "riskBasis": 3.0,
            "currentR": 1.83,
            "peakR": 2.10,
            "adaptiveGiveback": 0.70,
            "adaptiveTrailAtr": 1.0,
            "exitIntelligence": {
                "phase": "RUNNER",
                "action": "BREATHE",
                "continuation_score": 84.5,
                "recommended_sl": 4013.75,
                "reason_codes": ["PHASE_RUNNER", "M5_RECENT_LEG_ALIGNED"],
            },
        },
    )

    assert row["exitPhase"] == "RUNNER"
    assert row["exitAction"] == "BREATHE"
    assert row["exitContinuationScore"] == 84.5
    assert row["adaptiveGiveback"] == 0.70
    assert row["adaptiveTrailAtr"] == 1.0
    assert row["exitRecommendedSl"] == 4013.75
    assert "PHASE_RUNNER" in row["exitReasonCodes"]


def test_closed_trade_context_preserves_exit_intelligence_attribution():
    source = _function_source("_auto_manage_open_trades")
    for key in (
        '"exitPhase"',
        '"exitAction"',
        '"exitContinuationScore"',
        '"adaptiveGiveback"',
        '"adaptiveTrailAtr"',
    ):
        assert key in source


def test_v1528_settings_migration_adds_runner_controls_without_overwriting_custom():
    import copy
    import app

    legacy = copy.deepcopy(app._default_settings())
    tm = legacy["trading"]["tradeManagement"]
    for key in (
        "deterministicExitIntelligenceEnabled",
        "runnerContinuationScore",
        "runnerGivebackFraction",
        "runnerTrailAtr",
        "runnerPromotionPeakR",
    ):
        tm.pop(key, None)
    tm["aiDynamicMaxGivebackFraction"] = 0.39

    migrated, changes = app._apply_v1528_runner_intelligence_migration(legacy)
    migrated_tm = migrated["trading"]["tradeManagement"]
    assert migrated_tm["deterministicExitIntelligenceEnabled"] is True
    assert migrated_tm["runnerGivebackFraction"] >= 0.60
    assert migrated_tm["runnerTrailAtr"] >= 0.75
    assert migrated_tm["aiDynamicMaxGivebackFraction"] == 0.39
    assert "v15.2.8-deterministic-runner-intelligence" in migrated["meta"]["appliedMigrations"]
    assert changes


def test_production_settings_bundle_exposes_runner_intelligence_controls():
    source = DIST_SETTINGS.read_text(encoding="utf-8")
    assert "Deterministic Runner Intelligence" in source
    assert "trading.tradeManagement.runnerContinuationScore" in source
    assert "trading.tradeManagement.runnerGivebackFraction" in source
    assert "trading.tradeManagement.runnerTrailAtr" in source
