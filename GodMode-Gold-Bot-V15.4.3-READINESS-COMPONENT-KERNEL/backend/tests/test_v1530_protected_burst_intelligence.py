from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app.py"
SETTINGS = ROOT / "backend" / "data" / "settings.json"
DASHBOARD = ROOT / "frontend" / "src" / "pages" / "Dashboard.tsx"
SETTINGS_UI = ROOT / "frontend" / "src" / "pages" / "Settings.tsx"
API = ROOT / "frontend" / "src" / "lib" / "api.ts"
DIST_INDEX = ROOT / "frontend" / "dist" / "index.html"
BUILD_ID = "V15.4.3-READINESS-COMPONENT-KERNEL"


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


def test_account_snapshot_exposes_normalized_mt5_account_trade_mode(monkeypatch):
    import services.mt5_bridge as bridge_module

    fake_mt5 = SimpleNamespace(
        ACCOUNT_TRADE_MODE_DEMO=0,
        ACCOUNT_TRADE_MODE_CONTEST=1,
        ACCOUNT_TRADE_MODE_REAL=2,
        account_info=lambda: SimpleNamespace(
            balance=1000.0,
            equity=1000.0,
            margin=0.0,
            margin_free=1000.0,
            currency="USD",
            login=123,
            server="Demo-Server",
            company="Broker",
            leverage=100,
            trade_mode=0,
        ),
        last_error=lambda: (0, "ok"),
    )
    monkeypatch.setattr(bridge_module, "mt5", fake_mt5)
    bridge = bridge_module.MT5Bridge()
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(bridge, "bot_history_pnl", lambda days=1: 0.0)
    monkeypatch.setattr(bridge, "open_bot_risk_details", lambda: {"riskCash": 0.0, "unprotectedPositions": 0, "fallbackCalculations": 0})

    snapshot = bridge.account_snapshot()
    assert snapshot["accountTradeMode"] == 0
    assert snapshot["accountTradeModeName"] == "DEMO"
    assert snapshot["accountType"] == "demo"
    assert snapshot["demo"] is True
    assert snapshot["contest"] is False
    assert snapshot["real"] is False


@pytest.mark.parametrize(
    ("mode", "name", "account_type", "flags"),
    [
        (0, "DEMO", "demo", (True, False, False)),
        (1, "CONTEST", "contest", (False, True, False)),
        (2, "REAL", "real", (False, False, True)),
        (99, "UNKNOWN", "unknown", (False, False, False)),
    ],
)
def test_normalize_account_mode(mode, name, account_type, flags):
    from services.protected_burst_v153 import normalize_account_mode

    result = normalize_account_mode(mode, demo_mode=0, contest_mode=1, real_mode=2)
    assert result["accountTradeModeName"] == name
    assert result["accountType"] == account_type
    assert (result["demo"], result["contest"], result["real"]) == flags


def test_deterministic_be_progress_uses_real_dynamic_arm_not_cost_buffer():
    from services.protected_burst_v153 import compute_be_arm_progress

    result = compute_be_arm_progress(
        position={"direction": "BUY", "entryPrice": 100.0, "currentPrice": 100.20, "sl": 99.0},
        protection_state={"riskBasis": 1.0, "exitIntelligence": {"phase": "DEVELOPING"}},
        trade_management={
            "aiDynamicStopEnabled": True,
            "protectStartAtr": 0.60,
            "breakEvenAtRR": 0.90,
            "breakEvenAtPoints": 3.0,
            "protectStartPoints": 3.0,
            "launchBreakEvenR": 1.20,
        },
        atr=1.0,
        arm_fraction=0.85,
        protected=False,
    )
    assert result["mode"] == "dynamic_atr"
    assert result["armDistance"] == pytest.approx(0.60)
    assert result["progress"] == pytest.approx(1 / 3, rel=1e-3)
    assert result["eligible"] is False


def test_deterministic_be_progress_arms_at_configured_fraction_and_protected_is_complete():
    from services.protected_burst_v153 import compute_be_arm_progress

    near = compute_be_arm_progress(
        position={"direction": "SELL", "entryPrice": 100.0, "currentPrice": 99.48, "sl": 101.0},
        protection_state={"riskBasis": 1.0, "exitIntelligence": {"phase": "DEVELOPING"}},
        trade_management={"aiDynamicStopEnabled": True, "protectStartAtr": 0.60},
        atr=1.0,
        arm_fraction=0.85,
        protected=False,
    )
    assert near["progress"] == pytest.approx(0.8666, rel=1e-3)
    assert near["eligible"] is True

    locked = compute_be_arm_progress(
        position={"direction": "SELL", "entryPrice": 100.0, "currentPrice": 99.9, "sl": 99.95},
        protection_state={"riskBasis": 1.0},
        trade_management={"aiDynamicStopEnabled": True, "protectStartAtr": 0.60},
        atr=1.0,
        arm_fraction=0.85,
        protected=True,
    )
    assert locked["progress"] == 1.0
    assert locked["eligible"] is True
    assert locked["mode"] == "broker_protected"


def test_sustained_evidence_requires_consecutive_stable_scans_and_resets():
    from services.protected_burst_v153 import update_sustained_evidence

    cfg = {
        "sustainedScanCount": 3,
        "sustainedWindowSeconds": 5.0,
        "maxConfidenceDrop": 4.0,
        "maxContinuationDrop": 5.0,
    }
    state = {}
    for index, (confidence, continuation) in enumerate(((88.0, 82.0), (87.0, 81.0), (86.0, 80.0))):
        result = update_sustained_evidence(
            state=state,
            campaign_id="XAUUSD:BUY:1",
            direction="BUY",
            confidence=confidence,
            continuation=continuation,
            qualified=True,
            now=100.0 + index,
            config=cfg,
        )
        state = result["state"]
    assert result["stable"] is True
    assert result["count"] == 3

    reset = update_sustained_evidence(
        state=state,
        campaign_id="XAUUSD:BUY:1",
        direction="SELL",
        confidence=90.0,
        continuation=90.0,
        qualified=True,
        now=104.0,
        config=cfg,
    )
    assert reset["stable"] is False
    assert reset["count"] == 1


def test_sustained_evidence_rejects_large_score_deterioration():
    from services.protected_burst_v153 import update_sustained_evidence

    cfg = {"sustainedScanCount": 3, "sustainedWindowSeconds": 5.0, "maxConfidenceDrop": 4.0, "maxContinuationDrop": 5.0}
    first = update_sustained_evidence({}, "c", "BUY", 90.0, 90.0, True, 10.0, cfg)
    second = update_sustained_evidence(first["state"], "c", "BUY", 82.0, 89.0, True, 11.0, cfg)
    assert second["count"] == 1
    assert second["resetReason"] == "confidence_deterioration"


def test_adaptive_batch_is_immediate_two_or_three_legs():
    from services.protected_burst_v153 import choose_batch_size

    cfg = {"batchSize": 3, "adaptiveBatch": True, "strongBatchConfidence": 92.0, "strongBatchContinuation": 85.0}
    assert choose_batch_size(88.0, 80.0, 3, cfg) == 2
    assert choose_batch_size(93.0, 87.0, 3, cfg) == 3
    assert choose_batch_size(93.0, 87.0, 2, cfg) == 2


def test_final_rounded_basket_risk_blocks_broker_minimum_overrun():
    from services.protected_burst_v153 import evaluate_rounded_basket_risk

    result = evaluate_rounded_basket_risk(
        lots=[0.01, 0.01, 0.01],
        entry=100.0,
        stop=99.0,
        direction="BUY",
        risk_budget_cash=2.0,
        loss_per_lot=lambda lot: lot * 100.0,
    )
    assert result["allowed"] is False
    assert result["projectedRiskCash"] == pytest.approx(3.0)
    assert result["overrunCash"] == pytest.approx(1.0)


def test_burst_lifecycle_is_strict_and_one_way():
    from services.protected_burst_v153 import classify_burst_lifecycle

    cfg = {
        "burstPromotionMinAgeSeconds": 10.0,
        "burstPromotionProfitR": 0.18,
        "burstPromotionContinuation": 78.0,
        "burstRunnerProfitR": 0.55,
        "burstRunnerContinuation": 72.0,
        "burstDefensiveContinuation": 52.0,
    }
    assert classify_burst_lifecycle("BURST_PROBE", 0.05, 0.08, 5.0, 84.0, False, cfg)["stage"] == "BURST_PROBE"
    assert classify_burst_lifecycle("BURST_PROBE", 0.22, 0.25, 12.0, 82.0, False, cfg)["stage"] == "BURST_CONFIRMED"
    assert classify_burst_lifecycle("BURST_CONFIRMED", 0.65, 0.75, 30.0, 80.0, False, cfg)["stage"] == "BURST_RUNNER"
    assert classify_burst_lifecycle("BURST_RUNNER", 0.40, 0.80, 60.0, 45.0, True, cfg)["stage"] == "BURST_DEFENSIVE"
    assert classify_burst_lifecycle("BURST_CONFIRMED", 0.05, 0.30, 40.0, 60.0, False, cfg)["stage"] == "BURST_CONFIRMED"


def test_app_uses_resolved_burst_config_and_exposes_read_only_status_endpoint():
    source = APP.read_text(encoding="utf-8")
    telegram = _function_source(APP, "_telegram_position_buttons")
    toggle = _function_source(APP, "_set_protected_burst_enabled")
    status = _function_source(APP, "_protected_burst_status_snapshot")
    assert "_protected_burst_enabled()" in telegram
    assert "deepcopy(_protected_burst_cfg())" in toggle
    assert '@app.get("/api/trading-modes/protected-burst/status")' in source
    assert "mt5_bridge." not in status
    assert "_decision(" not in status


def test_execution_path_uses_real_be_progress_sustained_scans_and_atomic_basket_preflight():
    source = _function_source(APP, "_maybe_execute_protected_burst_add")
    for token in (
        "compute_be_arm_progress(",
        "update_sustained_evidence(",
        "choose_batch_size(",
        "evaluate_rounded_basket_risk(",
        "atomicBatchRollbackOnFailure",
        "burstRiskPctOfBalance",
    ):
        assert token in source
    assert "needed = max(buffer_points" not in source


def test_burst_settings_are_materialized_and_aligned():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    cfg = data["tradingModes"]["protectedBurst"]
    expected = {
        "enabled": True,
        "batchSize": 3,
        "adaptiveBatch": True,
        "burstBeArmFraction": 0.85,
        "sustainedScanCount": 3,
        "sustainedWindowSeconds": 5.0,
        "atomicBatchRollbackOnFailure": True,
        "burstProbeFastFailSeconds": 45,
        "burstProbeFastFailR": -0.18,
    }
    for key, value in expected.items():
        assert cfg[key] == value


def test_dashboard_and_production_assets_show_live_burst_gate_trace():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    settings_ui = SETTINGS_UI.read_text(encoding="utf-8")
    dist_index = DIST_INDEX.read_text(encoding="utf-8")
    assert "protectedBurstStatus" in api
    assert "Protected Burst Intelligence" in dashboard
    assert "burst-live-v1530.js" in dist_index
    assert "burst-live-v1530.css" in dist_index
    assert (ROOT / "frontend" / "dist" / "burst-live-v1530.js").exists()
    assert (ROOT / "frontend" / "dist" / "burst-live-v1530.css").exists()
    for key in (
        "sustainedScanCount",
        "burstBeArmFraction",
        "strongBatchConfidence",
        "atomicBatchRollbackOnFailure",
        "burstPromotionContinuation",
    ):
        assert key in settings_ui


def test_release_identity_is_distinct_everywhere():
    source = APP.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    settings = SETTINGS.read_text(encoding="utf-8")
    assert BUILD_ID in source
    assert BUILD_ID in api
    assert BUILD_ID in settings


def test_open_trade_manager_enforces_strict_burst_lifecycle():
    source = _function_source(APP, "_auto_manage_open_trades")
    assert "classify_burst_lifecycle(" in source
    assert '"BURST_PROBE"' in source
    assert '"BURST_CONFIRMED"' in source
    assert '"BURST_RUNNER"' in source
    assert '"BURST_DEFENSIVE"' in source
    assert "and not is_burst_leg" in source
    assert 'burstProbeFastFailSeconds' in source
    assert 'burstConfirmedFastFailSeconds' in source
    assert 'burstProbeBreakevenR' in source
    assert 'burstProbeTrailStartR' in source
