from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from services.deterministic_exit_intelligence import evaluate_exit_intelligence
from services.runner_capture_policy import (
    resolve_single_position_broker_tp,
    update_qualified_peak,
)

from dist_assets import main_bundle

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app.py"
SETTINGS = ROOT / "backend" / "data" / "settings.json"
UI = ROOT / "frontend" / "src" / "pages" / "Settings.tsx"


def _function_source(name: str) -> str:
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


def _rows(start: float, step: float, count: int = 30, *, last_range: float | None = None):
    rows = []
    price = start
    for index in range(count):
        close = price + step
        rows.append({
            "open": price,
            "high": max(price, close) + 0.20,
            "low": min(price, close) - 0.20,
            "close": close,
            "time": index,
        })
        price = close
    if last_range is not None:
        last = rows[-1]
        mid = last["close"]
        last["high"] = mid + last_range * 0.70
        last["low"] = mid - last_range * 0.30
    return rows


def test_unsplittable_single_position_has_no_fixed_tp_cap_in_dynamic_sl_mode():
    policy = resolve_single_position_broker_tp(
        side="BUY",
        entry=4028.50,
        sl=4027.75,
        plan={"tp1": 4029.25, "tp2": 4029.85, "tp3": 4030.53, "tp4": 4031.50},
        config={"singlePositionBrokerTpMode": "DYNAMIC_SL_ONLY", "singlePositionEmergencyTpR": 12.0},
    )
    assert policy.tp is None
    assert policy.mode == "DYNAMIC_SL_ONLY"
    assert policy.dynamic_stop_authoritative is True


def test_extended_single_position_tp_is_beyond_legacy_tp4():
    policy = resolve_single_position_broker_tp(
        side="BUY",
        entry=4028.50,
        sl=4027.75,
        plan={"tp4": 4031.50},
        config={"singlePositionBrokerTpMode": "EXTENDED", "singlePositionEmergencyTpR": 12.0},
    )
    assert policy.tp == pytest.approx(4037.50)
    assert policy.tp > 4031.50


def test_qualified_peak_ignores_a_transient_tick_wick_until_it_persists():
    state: dict = {}
    first = update_qualified_peak(
        state=state, side="BUY", entry=100.0, current_price=104.0, atr=2.0, now=10.0,
        config={"qualifiedPeakDwellSeconds": 3.0, "qualifiedPeakToleranceAtr": 0.10, "qualifiedPeakMinAdvanceAtr": 0.05},
    )
    assert first.raw_peak_dist == pytest.approx(4.0)
    assert first.qualified_peak_dist == pytest.approx(0.0)

    # Price immediately rejects the wick before the dwell period. The raw MFE is retained
    # for analytics, but the stop-ratcheting peak must not jump to four points.
    second = update_qualified_peak(
        state=first.state, side="BUY", entry=100.0, current_price=101.8, atr=2.0, now=11.0,
        config={"qualifiedPeakDwellSeconds": 3.0, "qualifiedPeakToleranceAtr": 0.10, "qualifiedPeakMinAdvanceAtr": 0.05},
    )
    assert second.raw_peak_dist == pytest.approx(4.0)
    assert second.qualified_peak_dist < 2.1


def test_qualified_peak_advances_after_price_holds_near_the_high():
    cfg = {"qualifiedPeakDwellSeconds": 2.0, "qualifiedPeakToleranceAtr": 0.10, "qualifiedPeakMinAdvanceAtr": 0.05}
    one = update_qualified_peak(state={}, side="BUY", entry=100.0, current_price=103.0, atr=2.0, now=20.0, config=cfg)
    two = update_qualified_peak(state=one.state, side="BUY", entry=100.0, current_price=102.9, atr=2.0, now=22.2, config=cfg)
    assert two.qualified_peak_dist >= 2.9


def test_fresh_high_velocity_breakout_enters_launch_phase_and_defers_peak_ratchet():
    m5 = _rows(4000.0, 0.35, last_range=8.0)
    m15 = _rows(3992.0, 0.25, count=24)
    result = evaluate_exit_intelligence(
        position={
            "direction": "BUY", "entryPrice": 4008.0, "currentPrice": 4011.0,
            "sl": 4007.0, "riskBasis": 1.0, "rawPeakDist": 4.5,
            "qualifiedPeakDist": 0.0, "peakDist": 0.0, "stage": "CONFIRMED",
            "ageSeconds": 35,
        },
        market={"price": 4011.0, "spread": 0.12, "normalSpread": 0.20},
        atr=2.0,
        m5_candles=m5,
        m15_candles=m15,
        decision={"side": "BUY", "features": {"computedSide": "BUY", "htfDailyBias": "BUY"}},
        intent_state={"side": "BUY", "stage": "CONFIRMED", "probability": 0.88},
        impulse_state={"side": "BUY", "stage": "CONFIRMED", "probability": 0.91},
        config={
            "qualifiedPeakEnabled": True,
            "launchPhaseEnabled": True,
            "launchMaxAgeSeconds": 150,
            "launchProtectionPeakR": 1.20,
            "launchGivebackFraction": 0.82,
            "launchTrailAtr": 1.20,
            "absoluteMaxGiveback": 0.85,
            "absoluteMaxTrailAtr": 2.0,
        },
    )
    assert result.phase == "LAUNCH"
    assert result.raw_peak_r >= 4.0
    assert result.qualified_peak_r == 0.0
    assert result.max_giveback_fraction >= 0.80
    assert result.trail_atr >= 1.20
    assert result.action in {"HOLD", "PROTECT"}
    # A transient raw wick must not create a peak-fraction stop.
    assert result.recommended_sl is None or result.recommended_sl <= 4008.20


def test_volatility_expansion_increases_runner_trail_room():
    m5 = _rows(4000.0, 0.45, last_range=10.0)
    m15 = _rows(3980.0, 0.55, count=24)
    result = evaluate_exit_intelligence(
        position={
            "direction": "BUY", "entryPrice": 4005.0, "currentPrice": 4013.0,
            "sl": 4008.0, "riskBasis": 2.0, "rawPeakDist": 9.0,
            "qualifiedPeakDist": 7.5, "peakDist": 7.5, "stage": "CONFIRMED",
            "ageSeconds": 240,
        },
        market={"price": 4013.0, "spread": 0.10, "normalSpread": 0.20},
        atr=2.0, m5_candles=m5, m15_candles=m15,
        decision={"side": "BUY", "features": {"computedSide": "BUY", "htfDailyBias": "BUY"}},
        intent_state={"side": "BUY", "stage": "CONFIRMED", "probability": 0.90},
        impulse_state={"side": "BUY", "stage": "CONFIRMED", "probability": 0.92},
        config={"qualifiedPeakEnabled": True, "volatilityExpansionTrailEnabled": True, "absoluteMaxTrailAtr": 2.0},
    )
    assert result.phase == "RUNNER"
    assert result.range_expansion_atr >= 4.0
    assert result.trail_atr > 1.0
    assert "VOLATILITY_EXPANSION_ROOM" in result.reason_codes


def test_management_uses_qualified_peak_for_protection_and_removes_legacy_tp_cap():
    source = _function_source("_auto_manage_open_trades")
    assert "update_qualified_peak(" in source
    assert '"qualifiedPeakDist"' in source
    assert "resolve_single_position_broker_tp(" in source
    assert '"MODIFY_TP"' in source
    assert '"tp": 0.0' in source


def test_auto_and_telegram_entry_paths_apply_single_position_runner_tp_policy():
    auto = _function_source("_auto_trade_tick")
    telegram = _function_source("_telegram_execute_pending_trade")
    assert "resolve_single_position_broker_tp(" in auto
    assert "resolve_single_position_broker_tp(" in telegram
    assert "config=tm_cfg" in auto
    assert "config=tm_cfg" in telegram


def test_settings_expose_runner_liberation_controls():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    tm = data["trading"]["tradeManagement"]
    for key in (
        "singlePositionBrokerTpMode",
        "singlePositionEmergencyTpR",
        "qualifiedPeakEnabled",
        "qualifiedPeakDwellSeconds",
        "launchPhaseEnabled",
        "launchGivebackFraction",
        "launchTrailAtr",
        "volatilityExpansionTrailEnabled",
        "absoluteMaxTrailAtr",
    ):
        assert key in tm
    assert tm["singlePositionBrokerTpMode"] == "DYNAMIC_SL_ONLY"
    assert tm["qualifiedPeakEnabled"] is True


def test_settings_ui_exposes_runner_liberation_controls():
    source = UI.read_text(encoding="utf-8")
    assert "Qualified Peak" in source
    assert "Single-position broker TP" in source
    for path in (
        "trading.tradeManagement.singlePositionBrokerTpMode",
        "trading.tradeManagement.qualifiedPeakDwellSeconds",
        "trading.tradeManagement.launchGivebackFraction",
        "trading.tradeManagement.volatilityExpansionTrailEnabled",
    ):
        assert path in source


def test_v1529_settings_migration_adds_runner_liberation_without_overwriting_custom():
    import copy
    import app

    legacy = copy.deepcopy(app._default_settings())
    tm = legacy["trading"]["tradeManagement"]
    for key in (
        "singlePositionBrokerTpMode",
        "singlePositionEmergencyTpR",
        "qualifiedPeakEnabled",
        "qualifiedPeakDwellSeconds",
        "launchPhaseEnabled",
        "launchGivebackFraction",
        "volatilityExpansionTrailEnabled",
        "absoluteMaxTrailAtr",
    ):
        tm.pop(key, None)
    tm["runnerGivebackFraction"] = 0.61

    migrated, changes = app._apply_v1529_runner_liberation_migration(legacy)
    migrated_tm = migrated["trading"]["tradeManagement"]
    assert migrated_tm["singlePositionBrokerTpMode"] == "DYNAMIC_SL_ONLY"
    assert migrated_tm["qualifiedPeakEnabled"] is True
    assert migrated_tm["launchPhaseEnabled"] is True
    assert migrated_tm["runnerGivebackFraction"] == 0.61
    assert "v15.2.9-qualified-peak-runner" in migrated["meta"]["appliedMigrations"]
    assert changes


def test_closed_trade_attribution_preserves_raw_and_qualified_peak_and_tp_policy():
    source = _function_source("_auto_manage_open_trades")
    for key in (
        '"rawPeakR"',
        '"qualifiedPeakR"',
        '"singlePositionTpPolicy"',
    ):
        assert key in source


def test_production_chunks_reference_the_packaged_main_bundle():
    """Every entry reference in the build resolves to a file that exists.

    This used to assert the literal name index-V1543-READINESS-COMPONENT-KERNEL.js, which Vite
    never emits — it hashes chunk names — so the assertion held only for the hand-renamed dist
    that shipped and broke the moment anyone ran the documented rebuild. The invariant the test
    was reaching for is that no chunk points at a bundle that is not in the build, which is what
    is checked here, against whatever names the bundler chose.
    """
    dist_assets = ROOT / "frontend" / "dist" / "assets"
    assert main_bundle().is_file()
    present = {p.name for p in dist_assets.glob("*.js")}
    dangling = []
    for path in dist_assets.glob("*.js"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        for ref in re.findall(r'["\'/]([A-Za-z0-9_.-]+-[A-Za-z0-9_-]{6,}\.js)["\']', source):
            if ref not in present:
                dangling.append((path.name, ref))
    assert dangling == [], f"chunks reference bundles that are not in the build: {dangling}"
