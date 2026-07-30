from __future__ import annotations

import copy
from types import SimpleNamespace


def _rows(start: float = 4000.0, count: int = 90, step: float = 0.08) -> list[dict]:
    rows = []
    price = start
    for i in range(count):
        open_ = price
        close = price + step
        rows.append({
            "time": 1_700_000_000 + i * 300,
            "open": open_,
            "high": max(open_, close) + 0.35,
            "low": min(open_, close) - 0.35,
            "close": close,
            "ema20": close - 0.30,
            "ema50": close - 0.60,
        })
        price = close
    return rows


class _Prediction:
    def __init__(self, *, side="BUY", stage="PROBE", probability=0.78):
        self.side = side
        self.stage = stage
        self.probability = probability
        self.sweep_penalty = 0.04
        self.acceleration_score = 0.82
        self.compression_release_score = 0.90
        self.displacement_atr = 0.18
        self.reason = "test impulse"

    def as_dict(self):
        return {
            "side": self.side,
            "stage": self.stage,
            "probability": self.probability,
            "sweep_penalty": self.sweep_penalty,
            "acceleration_score": self.acceleration_score,
            "compression_release_score": self.compression_release_score,
            "displacement_atr": self.displacement_atr,
        }


def _install_common(monkeypatch, app, *, context_allowed=True):
    m5 = _rows(step=0.08)
    m15 = _rows(start=3980.0, step=0.12)

    def candle_series(symbol, tf, *_args, **_kwargs):
        return (m5 if tf == "M5" else m15), {"cached": True}

    monkeypatch.setattr(app, "_predictor_candle_series", candle_series)
    monkeypatch.setattr(app, "_predictor_tick_window", lambda *a, **k: ([{"timeMsc": 1_700_000_000_000 + i * 100, "bid": 4007 + i * 0.01, "ask": 4007.2 + i * 0.01} for i in range(20)], {"tickCount": 20, "latestTickAgeMs": 20}))
    monkeypatch.setattr(app, "_predictor_extension_atr", lambda *a, **k: 0.20)
    monkeypatch.setattr(app, "predict_impulse", lambda **kwargs: _Prediction())
    monkeypatch.setattr(app, "classify_regime", lambda *a, **k: {"regime": "TREND", "reason": "test"})
    monkeypatch.setattr(app, "_publish_predictor_state", lambda *a, **k: None)
    monkeypatch.setattr(app, "qualify_intent_context", lambda **kwargs: SimpleNamespace(
        allowed=context_allowed,
        reasons=[] if context_allowed else ["terminal acceleration"],
        as_dict=lambda: {"allowed": context_allowed, "reasons": [] if context_allowed else ["terminal acceleration"]},
    ))
    monkeypatch.setattr(app, "build_probe_stop", lambda **kwargs: SimpleNamespace(
        allowed=True, sl=4004.5, tp1=4009.0, tp2=4010.5, tp3=4012.0, tp4=4014.0,
        reason="probe_stop_valid", as_dict=lambda: {"allowed": True},
    ))
    app.FAST_SNIPER_STATE["last"] = None
    app.FAST_SNIPER_STATE["lastAt"] = 0
    app.FAST_SNIPER_RETEST_STATE["active"] = False


def test_early_impulse_probe_is_context_qualified_and_uses_probe_risk(monkeypatch):
    import app

    original = copy.deepcopy(app.SETTINGS_STATE)
    try:
        app.SETTINGS_STATE.clear()
        app.SETTINGS_STATE.update(app._default_settings())
        app.SETTINGS_STATE["automation"].update({
            "earlyIntentEnabled": False,
            "earlyImpulsePredictorEnabled": True,
            "fastSniperRequireClosedM5": False,
            "earlyIntentContextGateEnabled": True,
            "earlyIntentProbeRiskPct": 0.12,
        })
        _install_common(monkeypatch, app, context_allowed=True)
        result = app._fast_sniper_decision({
            "symbol": "XAUUSD", "price": 4007.5, "bid": 4007.4, "ask": 4007.6,
            "spread": 0.2, "newsBlackout": False, "dirtyConditions": False,
        })
    finally:
        app.SETTINGS_STATE.clear()
        app.SETTINGS_STATE.update(original)

    assert result["source"] == "early_impulse"
    assert result["features"]["progressiveStage"] == "PROBE"
    assert result["features"]["managementProfile"] == "anticipatory_probe"
    assert result["features"]["probeRiskPct"] == 0.12
    assert result["features"]["intentContext"]["allowed"] is True
    assert result["tradePlan"]["sl"] == 4004.5


def test_early_impulse_cannot_bypass_terminal_context_block(monkeypatch):
    import app

    original = copy.deepcopy(app.SETTINGS_STATE)
    try:
        app.SETTINGS_STATE.clear()
        app.SETTINGS_STATE.update(app._default_settings())
        app.SETTINGS_STATE["automation"].update({
            "earlyIntentEnabled": False,
            "earlyImpulsePredictorEnabled": True,
            "fastSniperRequireClosedM5": False,
            "earlyIntentContextGateEnabled": True,
        })
        _install_common(monkeypatch, app, context_allowed=False)
        result = app._fast_sniper_decision({
            "symbol": "XAUUSD", "price": 4007.5, "bid": 4007.4, "ask": 4007.6,
            "spread": 0.2, "newsBlackout": False, "dirtyConditions": False,
        })
    finally:
        app.SETTINGS_STATE.clear()
        app.SETTINGS_STATE.update(original)

    assert result.get("source") != "early_impulse"


def test_probe_settings_reject_invalid_stop_and_risk_relationships():
    import app
    import pytest

    bad_stop = app._default_settings()
    bad_stop["automation"]["earlyIntentProbeMinStopPoints"] = 4.0
    bad_stop["automation"]["earlyIntentProbeMaxStopPoints"] = 3.0
    with pytest.raises(ValueError, match="minimum stop"):
        app._validate_settings_candidate(bad_stop)

    bad_risk = app._default_settings()
    bad_risk["automation"]["earlyIntentProbeRiskPct"] = 6.0
    with pytest.raises(ValueError, match="earlyIntentProbeRiskPct"):
        app._validate_settings_candidate(bad_risk)


def test_v1527_migration_repairs_only_known_legacy_probe_defaults():
    import app

    legacy = app._default_settings()
    legacy["trading"].update({"timeframe": "M15", "riskPerTrade": 0.50})
    legacy["trading"]["tradeManagement"]["trailStructure"] = "M15"
    legacy["automation"].pop("earlyIntentProbeRiskPct", None)
    legacy["automation"]["earlyIntentStopAtr"] = 0.72
    legacy["risk"].update({"maxDailyLossPct": 5.0, "maxOpenTrades": 3, "equityStopLossPct": 20.0})
    legacy["pyramiding"].update({"enabled": True, "maxAdds": 3, "maxTotalLots": 0.20})

    migrated, changes = app._apply_v1527_probe_safety_migration(legacy)

    assert migrated["trading"]["timeframe"] == "M5"
    assert migrated["trading"]["riskPerTrade"] == 0.25
    assert migrated["trading"]["tradeManagement"]["trailStructure"] == "M5"
    assert migrated["automation"]["earlyIntentProbeRiskPct"] == 0.12
    assert migrated["automation"]["earlyIntentProbeStopAtr"] == 0.45
    assert migrated["risk"]["maxOpenTrades"] == 1
    assert migrated["pyramiding"]["enabled"] is False
    assert "v15.2.7-context-qualified-probe" in migrated["meta"]["appliedMigrations"]
    assert changes

    custom = app._default_settings()
    custom["trading"]["riskPerTrade"] = 0.33
    custom["risk"]["maxOpenTrades"] = 2
    migrated_custom, _ = app._apply_v1527_probe_safety_migration(custom)
    assert migrated_custom["trading"]["riskPerTrade"] == 0.33
    assert migrated_custom["risk"]["maxOpenTrades"] == 2


def test_v1527_settings_ui_exposes_context_and_probe_lifecycle_controls():
    from pathlib import Path

    source = Path("frontend/src/pages/Settings.tsx").read_text(encoding="utf-8")
    dist = Path("frontend/dist/early-impulse-settings-v1529.js").read_text(encoding="utf-8")
    for token in (
        "earlyIntentContextGateEnabled",
        "earlyIntentContextMinScore",
        "earlyIntentProbeRiskPct",
        "earlyIntentProbeMaxStopPoints",
        "earlyIntentProbeFastFailR",
        "earlyIntentProbePromotionProfitR",
    ):
        assert token in source
        assert token in dist
    assert "Context-qualified probe safety" in source
    assert "Context Quality Gate" in dist


def test_v1527_probe_management_is_fail_closed_and_stage_specific():
    from pathlib import Path

    app_source = Path("backend/app.py").read_text(encoding="utf-8")
    assert 'sanitize_probe_runtime_state(st)' in app_source
    assert 'recovery_on = auto_cfg.get("recoveryMonitorEnabled", True) and _probe_stage != "PROBE"' in app_source
    assert 'ai_dynamic_stop = bool(tm_cfg.get("aiDynamicStopEnabled", True)) and _probe_stage != "PROBE"' in app_source
    assert 'risk_pct=_probe_risk_pct' in app_source
    assert 'untradeableAtBrokerMinimum' in app_source


def test_predictor_extension_uses_raw_m5_closes_when_mt5_rows_have_no_ema_fields():
    import app

    candles = [
        {"open": 4000.0 + i, "high": 4001.2 + i, "low": 3999.6 + i, "close": 4001.0 + i}
        for i in range(30)
    ]
    extension = app._predictor_extension_atr(candles, 2.0)
    assert extension > 1.0
