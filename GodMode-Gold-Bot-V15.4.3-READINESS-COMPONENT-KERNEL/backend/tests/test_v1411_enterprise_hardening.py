from __future__ import annotations

import copy
import json
import time
from types import SimpleNamespace

import pytest

import app
from services import ai_entry_auditor, ai_monitor
from services import ai_strategy_gen
from services.reporting_versioning import TradeReplayStorage, VersionRegistry
from services.strategy_lab import StrategyLab
from services.walk_forward import _grid
from services.pyramiding import AIPyramidingEngine
from services import mt5_bridge as mt5_module
from services.mt5_bridge import MT5Bridge
from services.runtime_safety import ExecutionLedger


class _Result:
    def __init__(self, **values):
        self.__dict__.update(values)

    def _asdict(self):
        return dict(self.__dict__)


def _fake_mt5(**overrides):
    values = {
        "TRADE_ACTION_DEAL": 1,
        "TRADE_ACTION_SLTP": 2,
        "ORDER_TYPE_BUY": 0,
        "ORDER_TYPE_SELL": 1,
        "POSITION_TYPE_BUY": 0,
        "POSITION_TYPE_SELL": 1,
        "ORDER_FILLING_FOK": 0,
        "ORDER_FILLING_IOC": 1,
        "ORDER_FILLING_RETURN": 2,
        "ORDER_TIME_GTC": 0,
        "SYMBOL_TRADE_MODE_DISABLED": 0,
        "SYMBOL_TRADE_MODE_LONGONLY": 1,
        "SYMBOL_TRADE_MODE_SHORTONLY": 2,
        "SYMBOL_TRADE_MODE_CLOSEONLY": 3,
        "SYMBOL_TRADE_MODE_FULL": 4,
        "symbol_info": lambda symbol: SimpleNamespace(
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            digits=2,
            filling_mode=2,
            trade_stops_level=0,
            trade_freeze_level=0,
            trade_mode=4,
        ),
        "order_check": lambda request: SimpleNamespace(retcode=0, comment="ok"),
        "last_error": lambda: (0, "ok"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_position_reducing_close_never_requires_entry_margin(monkeypatch):
    sent: list[dict] = []
    position = SimpleNamespace(
        ticket=7,
        symbol="XAUUSD",
        type=0,
        volume=0.10,
    )
    fake = _fake_mt5(
        positions_get=lambda **kwargs: [position],
        symbol_select=lambda symbol, enabled: True,
        symbol_info_tick=lambda symbol: SimpleNamespace(bid=100.0, ask=100.1),
        order_calc_margin=lambda *args: pytest.fail("reducing close reached entry-margin calculation"),
        account_info=lambda: SimpleNamespace(margin_free=0.0),
        order_send=lambda request: sent.append(dict(request))
        or _Result(retcode=10009, price=request["price"]),
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()
    bridge.live_enabled = True
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(
        bridge,
        "symbol_specs",
        lambda symbol: {"volumeMin": 0.01, "volumeStep": 0.01, "volumeMax": 100.0},
    )

    result = bridge.close_position({"ticket": 7})

    assert result["ok"] is True
    assert len(sent) == 1
    assert sent[0]["position"] == 7


def test_broker_distance_adjustment_never_weakens_existing_stop(monkeypatch):
    position = SimpleNamespace(
        ticket=9,
        price_current=100.0,
        type=0,
        sl=99.5,
        tp=0.0,
    )
    fake = _fake_mt5(
        symbol_info=lambda symbol: SimpleNamespace(
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            digits=2,
            filling_mode=2,
            trade_stops_level=100,
            trade_freeze_level=0,
        ),
        positions_get=lambda **kwargs: [position],
        order_check=lambda request: pytest.fail("unsafe weakened stop reached broker order_check"),
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()

    ok, request, detail = bridge._preflight(
        "XAUUSD",
        {
            "action": fake.TRADE_ACTION_SLTP,
            "position": 9,
            "symbol": "XAUUSD",
            "sl": 99.8,
            "tp": 0.0,
        },
    )

    assert ok is False
    assert request["sl"] == pytest.approx(99.5)
    assert detail["protectionDirectionViolation"] is True


def test_base_lot_cannot_override_account_risk_ceiling(monkeypatch):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings["pyramiding"].update(
        {"baseLot": 0.10, "lotStep": 0.01, "maxLot": 1.0, "maxTotalLots": 1.0}
    )
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(
        app,
        "_lot_risk_ceiling",
        lambda *args, **kwargs: {
            "lot": 0.05,
            "rawLot": 0.05,
            "riskCash": 5.0,
            "actualRisk": 5.0,
            "minClamped": False,
            "minLot": 0.01,
            "step": 0.01,
            "source": "broker",
        },
    )
    monkeypatch.setattr(app, "_normalise_lot_to_step", lambda symbol, lot: round(lot, 2))

    result = app._safe_entry_lot("XAUUSD", 0.10, 100.0, 99.0)

    assert result["lot"] == pytest.approx(0.05)
    assert result["capLot"] == pytest.approx(0.05)
    assert result["capped"] is True


def test_protected_entry_carries_authoritative_cash_risk_budget(monkeypatch):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)
    monkeypatch.setattr(app, "_live_market", lambda: {"symbol": "XAUUSD", "price": 100.0})
    monkeypatch.setattr(
        app,
        "_safe_entry_lot",
        lambda *args, **kwargs: {
            "lot": 0.05,
            "riskCeiling": {"riskCash": 5.0, "source": "broker"},
            "untradeableAtBrokerMinimum": False,
        },
    )

    order, error = app._protected_entry_payload(
        {
            "symbol": "XAUUSD",
            "side": "BUY",
            "price": 100.0,
            "sl": 99.0,
            "tp": 102.0,
            "volume": 0.10,
        },
        "test",
    )

    assert error is None
    assert order is not None
    assert order["maxRiskCash"] == pytest.approx(5.0)


def test_final_live_geometry_reduces_volume_to_cash_risk_budget(monkeypatch):
    fake = _fake_mt5(
        symbol_info=lambda symbol: SimpleNamespace(
            point=0.01,
            trade_tick_size=0.10,
            trade_tick_value=1.0,
            trade_tick_value_loss=1.0,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=100.0,
            digits=2,
            filling_mode=2,
            trade_stops_level=0,
            trade_freeze_level=0,
        )
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()

    ok, request, detail = bridge._cap_request_to_cash_risk(
        "XAUUSD",
        {
            "action": fake.TRADE_ACTION_DEAL,
            "type": fake.ORDER_TYPE_BUY,
            "price": 100.0,
            "sl": 99.0,
            "volume": 0.10,
        },
        0.50,
    )

    assert ok is True
    assert request["volume"] == pytest.approx(0.05)
    assert detail["riskAdjusted"] is True
    assert detail["finalRiskCash"] <= 0.50


def test_live_open_requires_exact_protected_position_readback(monkeypatch):
    calls = {"positions": 0}
    confirmed = SimpleNamespace(
        ticket=77,
        symbol="XAUUSD",
        type=0,
        volume=0.05,
        sl=99.0,
        tp=102.0,
        magic=20250525,
        comment="GODMODE_test",
        price_open=100.0,
        time_msc=1,
    )

    def positions_get(**kwargs):
        calls["positions"] += 1
        return [] if calls["positions"] == 1 else [confirmed]

    fake = _fake_mt5(
        positions_get=positions_get,
        symbol_select=lambda symbol, enabled: True,
        symbol_info_tick=lambda symbol: SimpleNamespace(bid=99.9, ask=100.0),
        order_calc_margin=lambda *args: 10.0,
        account_info=lambda: SimpleNamespace(margin_free=1000.0),
        order_send=lambda request: _Result(
            retcode=10009,
            price=100.0,
            volume=request["volume"],
            order=77,
            deal=88,
        ),
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()
    bridge.live_enabled = True
    bridge.auto_trading_enabled = True
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(
        bridge,
        "market_open",
        lambda *_args: {"open": True, "reason": "Open", "source": "test"},
    )
    monkeypatch.setattr(
        bridge,
        "symbol_specs",
        lambda symbol: {
            "volumeMin": 0.01,
            "volumeStep": 0.01,
            "volumeMax": 100.0,
            "tradeTickSize": 0.10,
            "tradeTickValue": 1.0,
            "tickSize": 0.10,
        },
    )

    result = bridge.execute(
        {
            "symbol": "XAUUSD",
            "side": "BUY",
            "volume": 0.05,
            "sl": 99.0,
            "tp": 102.0,
            "maxRiskCash": 1.0,
            "comment": "test",
        }
    )

    assert result["ok"] is True
    assert result["readbackConfirmed"] is True
    assert result["confirmedPosition"]["ticket"] == 77
    assert result["confirmedPosition"]["sl"] == pytest.approx(99.0)
    assert result["confirmedPosition"]["tp"] == pytest.approx(102.0)


def test_live_open_without_broker_stop_is_blocked(monkeypatch):
    fake = _fake_mt5()
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()
    bridge.live_enabled = True
    bridge.auto_trading_enabled = True
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(
        bridge,
        "symbol_specs",
        lambda symbol: {"volumeMin": 0.01, "volumeStep": 0.01, "volumeMax": 100.0},
    )

    result = bridge.execute(
        {"symbol": "XAUUSD", "side": "BUY", "volume": 0.01, "manualTrigger": True}
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "stop" in result["message"].lower()


def test_generic_api_modify_cannot_remove_stop(monkeypatch, tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    position = {
        "ticket": 91,
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entryPrice": 100.0,
        "currentPrice": 101.0,
        "sl": 99.0,
        "tp": 103.0,
        "lots": 0.10,
    }
    monkeypatch.setattr(app, "EXECUTION_LEDGER", ledger)
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=False: [position])
    monkeypatch.setattr(
        app.mt5_bridge,
        "symbol_specs",
        lambda symbol: {
            "tickSize": 0.01,
            "tradeTickSize": 0.01,
            "tradeTickValue": 1.0,
            "volumeStep": 0.01,
        },
    )
    monkeypatch.setattr(
        app.mt5_bridge,
        "modify_position",
        lambda payload: pytest.fail("stop-removal request reached MT5"),
    )

    result = app._execute_mt5_mutation_serialized(
        "MODIFY_SL",
        {"ticket": 91, "sl": 0.0, "expectedCurrentSl": 99.0},
        "api_modify_position",
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["protectionInvariant"] is True


def test_generic_api_modify_cannot_widen_stop(monkeypatch, tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    position = {
        "ticket": 92,
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entryPrice": 100.0,
        "currentPrice": 101.0,
        "sl": 99.0,
        "tp": 103.0,
        "lots": 0.10,
    }
    monkeypatch.setattr(app, "EXECUTION_LEDGER", ledger)
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=False: [position])
    monkeypatch.setattr(
        app.mt5_bridge,
        "symbol_specs",
        lambda symbol: {
            "tickSize": 0.01,
            "tradeTickSize": 0.01,
            "tradeTickValue": 1.0,
            "volumeStep": 0.01,
        },
    )
    monkeypatch.setattr(
        app.mt5_bridge,
        "modify_position",
        lambda payload: pytest.fail("unauthorized wider stop reached MT5"),
    )

    result = app._execute_mt5_mutation_serialized(
        "MODIFY_SL",
        {"ticket": 92, "sl": 98.5, "expectedCurrentSl": 99.0},
        "api_modify_position",
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["protectionInvariant"] is True


def test_dynamic_widening_requires_fresh_evidence_and_cash_cap(monkeypatch, tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    position = {
        "ticket": 93,
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entryPrice": 100.0,
        "currentPrice": 101.0,
        "sl": 99.0,
        "tp": 103.0,
        "lots": 0.10,
    }
    monkeypatch.setattr(app, "EXECUTION_LEDGER", ledger)
    monkeypatch.setattr(app.mt5_bridge, "open_positions", lambda bot_only=False: [dict(position)])
    monkeypatch.setattr(
        app.mt5_bridge,
        "symbol_specs",
        lambda symbol: {
            "tickSize": 0.01,
            "tradeTickSize": 0.01,
            "tradeTickValue": 1.0,
            "volumeStep": 0.01,
        },
    )
    monkeypatch.setattr(
        app.mt5_bridge,
        "modify_position",
        lambda payload: pytest.fail("stale widening evidence reached MT5"),
    )

    result = app._execute_mt5_mutation_serialized(
        "MODIFY_SL",
        {
            "ticket": 93,
            "sl": 98.5,
            "expectedCurrentSl": 99.0,
            "allowRiskWidening": True,
            "riskWideningAuthorization": {
                "fresh": False,
                "maxRiskCash": 20.0,
                "decisionId": "stale-decision",
            },
        },
        "dynamic_sl_breathe",
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["protectionInvariant"] is True


def test_stale_or_featureless_recovery_evidence_can_never_widen():
    result = ai_monitor.dynamic_sl_recovery_decision(
        {
            "direction": "BUY",
            "entryPrice": 100.0,
            "currentPrice": 99.2,
            "sl": 99.0,
            "profitR": -0.8,
        },
        {
            "side": "BUY",
            "stale": True,
            "staleReason": "decision_refresh_failed",
            "features": {},
        },
        {"spread": 0.20},
        {"dynamicSlMinRecoveryScore": 62},
        atr=1.0,
        max_risk_distance=1.35,
    )

    assert result["action"] != "WIDEN"
    assert result["evidenceFresh"] is False


def test_stale_continuation_evidence_can_never_authorize_profit_breathing():
    result = ai_monitor.assess_continuation(
        {
            "direction": "SELL",
            "entryPrice": 100.0,
            "currentPrice": 98.0,
            "sl": 99.0,
            "riskBasis": 1.0,
            "peakDist": 3.0,
        },
        {"side": "SELL", "stale": True, "features": {}},
        {"spread": 0.20},
        atr=1.0,
    )

    assert result["evidenceFresh"] is False
    assert result["continuationScore"] == 0.0


def test_ai_auditor_cache_signature_binds_stop_plan_provider_and_model():
    ai_entry_auditor._AUDIT_CACHE.clear()
    calls: list[str] = []

    def llm(provider, api_key, model, system, prompt, **kwargs):
        calls.append(prompt)
        return {
            "ok": True,
            "json": {
                "verdict": "APPROVE",
                "confidenceAdjust": 0,
                "invalidationPrice": 99.5,
                "reason": "structure valid",
                "entryQualityNotes": [],
            },
        }

    common = {
        "cfg": {"cooldownSeconds": 60},
        "decision": {
            "side": "BUY",
            "selectedStrategy": {"name": "TEST"},
            "_generatedAt": time.time(),
        },
        "market": {"symbol": "XAUUSD", "timeframe": "M15"},
        "plan": {"entry": 100.0, "tp1": 102.0, "tp2": 103.0},
        "provider": "claude",
        "api_key": "test-key",
        "model": "model-a",
    }
    first = ai_entry_auditor.audit_entry(
        llm, payload={"side": "BUY", "price": 100.0, "sl": 99.0}, **common
    )
    second = ai_entry_auditor.audit_entry(
        llm, payload={"side": "BUY", "price": 100.0, "sl": 98.0}, **common
    )
    third = ai_entry_auditor.audit_entry(
        llm,
        payload={"side": "BUY", "price": 100.0, "sl": 98.0},
        **{**common, "model": "model-b"},
    )

    assert len(calls) == 3
    assert first["signature"] != second["signature"]
    assert second["signature"] != third["signature"]


def test_fresh_internal_widening_under_cash_cap_reaches_broker_and_readback(monkeypatch, tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.sqlite")
    before = {
        "ticket": 94,
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entryPrice": 100.0,
        "currentPrice": 99.2,
        "sl": 99.0,
        "tp": 103.0,
        "lots": 0.10,
    }
    after = {**before, "sl": 98.5}
    calls = {"positions": 0, "modify": 0}

    def positions(bot_only=False):
        calls["positions"] += 1
        return [dict(before if calls["positions"] == 1 else after)]

    monkeypatch.setattr(app, "EXECUTION_LEDGER", ledger)
    monkeypatch.setattr(app.mt5_bridge, "open_positions", positions)
    monkeypatch.setattr(
        app.mt5_bridge,
        "symbol_specs",
        lambda symbol: {
            "tickSize": 0.01,
            "tradeTickSize": 0.01,
            "tradeTickValue": 1.0,
            "volumeStep": 0.01,
        },
    )

    def modify(payload):
        calls["modify"] += 1
        return {"ok": True, "mt5Request": {"sl": payload["sl"]}}

    monkeypatch.setattr(app.mt5_bridge, "modify_position", modify)
    result = app._execute_mt5_mutation_serialized(
        "MODIFY_SL",
        {
            "ticket": 94,
            "sl": 98.5,
            "expectedCurrentSl": 99.0,
            "allowRiskWidening": True,
            "riskWideningAuthorization": {
                "fresh": True,
                "maxRiskCash": 20.0,
                "decisionId": "decision-94",
            },
        },
        "dynamic_sl_breathe",
    )

    assert result["ok"] is True
    assert result["readbackConfirmed"] is True
    assert calls["modify"] == 1


def test_strategy_lab_never_mutates_the_live_engine():
    class Engine:
        def __init__(self):
            self.mode = "live"

        def strictness_dict(self):
            return {"strictnessMode": self.mode}

        def configure_strictness(self, payload):
            self.mode = str(payload.get("strictnessMode") or self.mode)

    class Backtester:
        def run(self, candles, engine, strategies, params, progress=None):
            assert engine is not live_engine
            return {
                "ok": True,
                "span": "test",
                "overall": {
                    "trades": 40,
                    "expectancyR": 0.1,
                    "profitFactor": 1.2,
                    "winRate": 55,
                    "maxDrawdownR": 2,
                },
                "oosConsistencyPct": 60,
            }

    live_engine = Engine()
    lab = StrategyLab()
    result = lab.evaluate(
        [{}],
        live_engine,
        [],
        Backtester(),
        {"strictnessMode": "balanced"},
        {"minSample": 30},
    )

    assert result["ok"] is True
    assert live_engine.mode == "live"


def test_direct_strategy_lab_candidates_cross_the_same_sanitizer():
    lab = StrategyLab()
    added = lab.add_candidates(
        [
            {
                "id": "../../evil",
                "name": "unsafe",
                "profile": {
                    "standardConfidence": -999,
                    "maxSpread": 999,
                    "code": "os.system('bad')",
                },
            }
        ]
    )

    assert added == 1
    candidate = lab.extra[0]
    assert candidate["id"].startswith("direct_")
    assert candidate["profile"]["standardConfidence"] == 55.0
    assert candidate["profile"]["maxSpread"] == 1.0
    assert "code" not in candidate["profile"]


def test_walk_forward_grid_rejects_oversized_product_before_allocation():
    with pytest.raises(ValueError, match="60"):
        _grid({"a": list(range(9)), "b": list(range(8))})


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com/feed.json",
        "https://127.0.0.1/feed.json",
        "https://localhost/feed.json",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_configurable_feed_urls_reject_local_or_non_https_targets(url):
    with pytest.raises(ValueError):
        ai_strategy_gen.validate_public_https_url(url)


def test_replay_storage_rejects_path_traversal_and_oversized_image(tmp_path, monkeypatch):
    from services import reporting_versioning

    monkeypatch.setattr(reporting_versioning, "REPLAY_DIR", tmp_path / "replays")
    (tmp_path / "replays").mkdir()
    storage = TradeReplayStorage()

    traversal = storage.store({"tradeId": "../../escape", "events": []})
    huge = storage.store(
        {
            "tradeId": "safe-id",
            "chartImageBase64": "A" * (3 * 1024 * 1024),
            "events": [],
        }
    )

    assert traversal["ok"] is False
    assert huge["ok"] is False
    assert not (tmp_path / "escape.json").exists()


def test_config_export_always_masks_every_registered_secret(monkeypatch):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("strategyLab", {})["feedKey"] = "feed-secret"
    settings.setdefault("telegram", {})["botToken"] = "telegram-secret"
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)

    result = app.config_export(include_secrets=True)

    assert result["settings"]["strategyLab"]["feedKey"] == ""
    assert result["settings"]["telegram"]["botToken"] == ""
    assert result["secretsIncluded"] is False


def test_risk_center_update_changes_the_live_risk_configuration(monkeypatch):
    settings = copy.deepcopy(app.SETTINGS_STATE)
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "_save_settings", lambda reason="": {"ok": True})
    monkeypatch.setattr(app, "_save_risk", lambda: None)

    result = app.update_risk({"rule": "Max Daily Loss", "limit": "2.5%", "enabled": True})

    assert result["ok"] is True
    assert app.SETTINGS_STATE["risk"]["maxDailyLossPct"] == pytest.approx(2.5)


def test_manage_live_route_executes_requested_break_even(monkeypatch):
    called = {}

    def control(ticket, action):
        called.update(ticket=ticket, action=action)
        return {"ok": True, "action": action, "ticket": ticket}

    monkeypatch.setattr(app, "_manual_position_control", control)
    result = app.manage_live_trade({"ticket": 1234, "action": "BE"})

    assert result["ok"] is True
    assert called == {"ticket": 1234, "action": "BE"}


def test_live_entry_news_guard_fails_closed_when_calendar_evidence_is_unavailable(monkeypatch):
    class Calendar:
        _cache = []
        _cache_at = None
        _failure_count = 1

        def blackout_status(self):
            return {
                "isBlackout": False,
                "liveConfigured": True,
                "status": "live",
            }

    settings = copy.deepcopy(app.SETTINGS_STATE)
    settings.setdefault("automation", {})["newsFailClosed"] = True
    monkeypatch.setattr(app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(app, "calendar", Calendar())
    monkeypatch.setattr(app.mt5_bridge, "live_enabled", True)

    result = app._news_entry_guard()

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["newsProtectionUnavailable"] is True


def test_pyramiding_settings_reject_invalid_types_without_mutating_state():
    engine = AIPyramidingEngine()
    before = engine.settings_dict()

    with pytest.raises(ValueError):
        engine.update_settings({"maxAdds": "not-a-number"})

    assert engine.settings_dict() == before


def test_pyramiding_settings_are_clamped_to_enterprise_safety_bounds():
    engine = AIPyramidingEngine()
    updated = engine.update_settings(
        {
            "maxAdds": 999,
            "baseLot": -2,
            "maxLot": 10000,
            "maxStackRiskPct": 90,
            "enabled": "false",
        }
    )

    assert updated["maxAdds"] == 5
    assert updated["baseLot"] >= 0.01
    assert updated["maxLot"] <= 100.0
    assert updated["maxStackRiskPct"] <= 10.0
    assert updated["enabled"] is False


def test_public_performance_memory_injection_is_disabled():
    result = app.record_trade(
        {"isBotTrade": True, "source": "godmode", "outcome": "WIN", "pnlUsd": 999999}
    )

    assert result["ok"] is False
    assert result["blocked"] is True


def test_performance_memory_requires_broker_stamp(tmp_path):
    from services.performance_memory import PerformanceMemory

    memory = PerformanceMemory(tmp_path / "memory.db")
    memory.magic = 4242
    memory.comment_prefix = "GODMODE_"

    assert memory.is_bot_trade({"isBotTrade": True})[0] is False
    assert memory.is_bot_trade({"source": "godmode"})[0] is False
    assert memory.is_bot_trade({"magic": 4242})[0] is True
    assert memory.is_bot_trade({"comment": "GODMODE_live"})[0] is True


def test_explicit_rollback_snapshot_id_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "CONFIG_SNAPSHOTS_DIR", tmp_path)

    result = app.ai_optimisation_rollback({"snapshotId": "../settings"})

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "invalid" in result["message"].lower()


def test_settings_save_failure_restores_in_memory_configuration(monkeypatch, tmp_path):
    before = copy.deepcopy(app.SETTINGS_STATE)
    settings_file = tmp_path / "settings.json"
    last_good = tmp_path / "settings.lastgood.json"
    settings_file.write_text(json.dumps(before), encoding="utf-8")
    last_good.write_text(json.dumps(before), encoding="utf-8")
    monkeypatch.setattr(app, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(app, "SETTINGS_LAST_GOOD_FILE", last_good)
    monkeypatch.setattr(app, "_settings_snapshot", lambda label: {"id": "safe-snapshot"})
    real_write = app._write_settings_payload
    calls = {"count": 0}
    def fail_first(path, payload):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("disk full")
        return real_write(path, payload)
    monkeypatch.setattr(app, "_write_settings_payload", fail_first)

    with pytest.raises(RuntimeError, match="rolled back"):
        app._update_settings_locked({"risk": {"maxRiskPerTradePct": 4.9}})

    assert app.SETTINGS_STATE == before


def test_account_snapshot_flags_unprotected_bot_positions(monkeypatch):
    bridge = MT5Bridge()
    info = SimpleNamespace(
        balance=1000.0,
        equity=1000.0,
        margin=0.0,
        margin_free=1000.0,
        currency="USD",
        login=1,
        server="demo",
        company="broker",
        leverage=100,
    )
    fake_mt5 = SimpleNamespace(account_info=lambda: info)
    monkeypatch.setattr(mt5_module, "mt5", fake_mt5)
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(
        bridge,
        "open_positions",
        lambda bot_only=True: [
            {"ticket": 7, "symbol": "XAUUSD", "direction": "BUY", "entryPrice": 2400.0, "sl": 0.0, "lots": 0.01}
        ],
    )
    monkeypatch.setattr(bridge, "bot_history_pnl", lambda days=1: 0.0)

    snapshot = bridge.account_snapshot()

    assert snapshot["openRiskKnown"] is False
    assert snapshot["unprotectedPositions"] == 1
    assert snapshot["openRiskPct"] == 100.0


def test_version_registry_rejects_identifier_path_traversal(monkeypatch, tmp_path):
    import services.reporting_versioning as reporting

    monkeypatch.setattr(reporting, "VERSION_DIR", tmp_path)
    registry = VersionRegistry()

    assert registry.register_strategy({"strategyId": "../escape"})["blocked"] is True
    assert registry.register_parameters({"profile": "../../escape"})["blocked"] is True
    assert not list(tmp_path.parent.glob("escape*.json"))


def test_risk_update_rejects_out_of_bounds_limit_without_mutating_state():
    risk_before = copy.deepcopy(app.RISK_STATE)
    settings_before = copy.deepcopy(app.SETTINGS_STATE)

    result = app.update_risk({"rule": "Max Risk Per Trade", "limit": "99%", "enabled": True})

    assert result["ok"] is False
    assert result["blocked"] is True
    assert app.RISK_STATE == risk_before
    assert app.SETTINGS_STATE == settings_before


def test_risk_update_save_failure_restores_all_in_memory_state(monkeypatch):
    risk_before = copy.deepcopy(app.RISK_STATE)
    settings_before = copy.deepcopy(app.SETTINGS_STATE)
    monkeypatch.setattr(app, "_save_risk", lambda: None)
    monkeypatch.setattr(app, "_save_settings", lambda reason="": (_ for _ in ()).throw(OSError("disk full")))

    result = app.update_risk({"rule": "Max Daily Loss", "limit": "2.25%", "enabled": True})

    assert result["ok"] is False
    assert app.RISK_STATE == risk_before
    assert app.SETTINGS_STATE == settings_before


def test_performance_memory_deduplicates_broker_ticket_across_restarts(tmp_path):
    from services.performance_memory import PerformanceMemory

    first = PerformanceMemory(tmp_path / "memory.db")
    first.magic = 4242
    trade = {
        "ticket": "broker-position-77",
        "magic": 4242,
        "symbol": "XAUUSD",
        "outcome": "WIN",
        "pnl": 5.0,
    }
    one = first.record_trade(trade)
    second_process = PerformanceMemory(tmp_path / "memory.db")
    second_process.magic = 4242
    two = second_process.record_trade(trade)

    assert one["recorded"] is True
    assert two["recorded"] is False
    assert two["duplicate"] is True
    assert second_process.stats(live_only=True)["totalTrades"] == 1
