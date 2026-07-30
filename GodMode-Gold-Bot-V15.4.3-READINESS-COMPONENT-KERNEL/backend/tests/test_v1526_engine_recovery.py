from pathlib import Path
from types import SimpleNamespace
import copy
import time

import services.mt5_bridge as bridge_module
from services.mt5_bridge import MT5Bridge
from services.early_intent import predict_early_intent
from services.impulse_prediction import predict_impulse


def _m5_trend(side: str = "SELL", count: int = 30):
    rows = []
    price = 4050.0 if side == "SELL" else 4000.0
    step = -0.8 if side == "SELL" else 0.8
    for i in range(count):
        open_ = price
        close = price + step
        rows.append({
            "time": 1_700_000_000 + i * 300,
            "open": open_,
            "high": max(open_, close) + 0.25,
            "low": min(open_, close) - 0.25,
            "close": close,
            "ema20": close + (1.0 if side == "SELL" else -1.0),
            "ema50": close + (2.0 if side == "SELL" else -2.0),
        })
        price = close
    return rows


def test_latest_tick_is_canonical_and_preserves_milliseconds(monkeypatch):
    class FakeMT5:
        @staticmethod
        def symbol_select(symbol, enabled):
            return True

        @staticmethod
        def symbol_info_tick(symbol):
            return SimpleNamespace(
                time=1_700_000_000,
                time_msc=1_700_000_000_725,
                bid=4040.10,
                ask=4040.34,
                last=4040.20,
                volume=7,
                flags=3,
            )

    monkeypatch.setattr(bridge_module, "mt5", FakeMT5)
    bridge = MT5Bridge()
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))

    tick = bridge.latest_tick("XAUUSD")

    assert tick["time_msc"] == 1_700_000_000_725
    assert tick["timeMsc"] == tick["time_msc"]
    assert tick["bid"] == 4040.10
    assert tick["ask"] == 4040.34
    assert tick["spread"] == 0.24


def test_predictors_use_fresh_tick_price_not_stale_forming_candle_close():
    candles = [
        {"open": 100.0, "high": 100.20, "low": 99.80, "close": 100.0}
        for _ in range(14)
    ]
    candles[-1] = {"open": 100.0, "high": 100.20, "low": 99.80, "close": 100.0}
    prices = [100.00, 100.02, 100.05, 100.09, 100.15, 100.24, 100.36, 100.50]
    ticks = [
        {"time_msc": 1_000_000 + i * 250, "bid": p, "ask": p + 0.08}
        for i, p in enumerate(prices)
    ]

    intent = predict_early_intent(
        ticks=ticks,
        candles=candles,
        atr=5.0,
        current_spread=0.0,
        max_spread=0.40,
        config={
            "hardMinTicks": 4,
            "minTicks": 8,
            "intentProbability": 0.50,
            "minDisplacementAtr": 0.05,
        },
    )
    impulse = predict_impulse(
        ticks=ticks,
        candles=candles,
        atr=5.0,
        current_spread=0.0,
        max_spread=0.40,
        config={
            "minTicks": 6,
            "probeProbability": 0.45,
            "minProbeDisplacementAtr": 0.05,
            "earlyBodyAtr": 0.08,
        },
    )

    assert intent.side == "BUY"
    assert intent.structure_score > 0.5
    assert impulse.side == "BUY"
    assert impulse.candle_score > 0.8
    assert impulse.compression_release_score > 0.4


def test_priority_tick_patches_cached_market_with_fresh_direct_quote(monkeypatch):
    import app as backend_app

    backend_app.PRIORITY_INTENT_STATE.clear()
    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "STARTING", "lastCandidate": {}})
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True, "symbol": "XAUUSD"})
    monkeypatch.setattr(backend_app.mt5_bridge, "latest_tick", lambda symbol: {
        "time": 1_700_000_000,
        "time_msc": 1_700_000_000_500,
        "timeMsc": 1_700_000_000_500,
        "bid": 4041.10,
        "ask": 4041.34,
        "last": 4041.20,
        "spread": 0.24,
    })
    monkeypatch.setattr(backend_app, "_market_state", lambda: {"open": True})
    monkeypatch.setattr(backend_app, "_live_market", lambda: {
        "connected": True,
        "symbol": "XAUUSD",
        "price": 4039.00,
        "bid": 4038.90,
        "ask": 4039.10,
        "spread": 0.20,
    })
    seen = {}

    def decision(market):
        seen.update(market)
        return {"ok": False, "action": "WAIT", "reason": "watching", "features": {}}

    monkeypatch.setattr(backend_app, "_fast_sniper_decision", decision)

    result = backend_app._priority_intent_tick()

    assert result["candidate"] is False
    assert seen["price"] == 4041.34
    assert seen["bid"] == 4041.10
    assert seen["ask"] == 4041.34
    assert seen["tickTimeMsc"] == 1_700_000_000_500


def test_fast_strategy_quality_metrics_use_m5_predictor_cache_not_m15_dashboard_bars(monkeypatch):
    import app as backend_app

    backend_app.PREDICTOR_CANDLE_CACHE.clear()
    m5 = _m5_trend("SELL", 40)
    backend_app.PREDICTOR_CANDLE_CACHE[("XAUUSD", "M5", 90)] = {
        "candles": copy.deepcopy(m5),
        "fetchedAt": time.time(),
    }
    market = {
        "symbol": "XAUUSD",
        "price": m5[-1]["close"],
        "atr14": 5.0,
        "candles": [
            {"open": 4000 + (i % 2), "high": 4002, "low": 3998, "close": 4000 + ((-1) ** i)}
            for i in range(40)
        ],
    }
    decision = {
        "side": "SELL",
        "strategy": "Fast Sniper Retest Continuation",
        "features": {"fastSniper": True, "retestContinuation": True},
    }

    metrics = backend_app._entry_quality_metrics(market, "SELL", decision)

    assert metrics["timeframe"] == "M5"
    assert metrics["candleSource"] == "predictor_cache"
    assert metrics["recentLegEfficiency"] > 0.70
    assert metrics["recentFlips"] <= 1


def test_confirmed_retest_is_not_blocked_by_legacy_long_window_chop(monkeypatch):
    import app as backend_app

    settings = copy.deepcopy(backend_app.SETTINGS_STATE)
    settings.setdefault("automation", {}).update({
        "chopGovernorEnabled": True,
        "chopScoutOnly": True,
        "chopModeMinConfidence": 88.0,
        "chopRetestContinuationEnabled": True,
        "chopRetestMinConfidence": 76.0,
        "chopRetestMinLegEfficiency": 0.42,
        "chopRetestMaxRecentFlips": 3,
    })
    monkeypatch.setattr(backend_app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(backend_app, "_recent_session_edge_stats", lambda: {"total": 0})
    monkeypatch.setattr(backend_app, "_entry_quality_metrics", lambda market, side, decision=None: {
        "ok": True,
        "chop": True,
        "efficiency": 0.217,
        "flips": 12,
        "recentLegEfficiency": 0.76,
        "recentFlips": 1,
        "directionalMoveAtr": 2.1,
        "late": False,
        "pullbackReclaim": True,
    })
    decision = {
        "side": "SELL",
        "confidence": 84.0,
        "quality": "SCOUT",
        "features": {
            "fastSniper": True,
            "retestContinuation": True,
            "mtfScore": 0.76,
        },
    }

    result = backend_app._entry_quality_governor(decision, {"symbol": "XAUUSD"}, source="auto")

    assert result["ok"] is True
    assert result["entryQuality"]["chopOverride"]["allowed"] is True


def test_normal_low_efficiency_setup_remains_blocked(monkeypatch):
    import app as backend_app

    settings = copy.deepcopy(backend_app.SETTINGS_STATE)
    settings.setdefault("automation", {}).update({
        "chopGovernorEnabled": True,
        "chopScoutOnly": True,
        "chopModeMinConfidence": 88.0,
    })
    monkeypatch.setattr(backend_app, "SETTINGS_STATE", settings)
    monkeypatch.setattr(backend_app, "_recent_session_edge_stats", lambda: {"total": 0})
    monkeypatch.setattr(backend_app, "_entry_quality_metrics", lambda market, side, decision=None: {
        "ok": True,
        "chop": True,
        "efficiency": 0.20,
        "flips": 10,
        "recentLegEfficiency": 0.25,
        "recentFlips": 5,
        "directionalMoveAtr": 0.3,
        "late": False,
        "pullbackReclaim": False,
    })
    decision = {"side": "BUY", "confidence": 80.0, "quality": "STANDARD", "features": {}}

    result = backend_app._entry_quality_governor(decision, {"symbol": "XAUUSD"}, source="auto")

    assert result["ok"] is False
    assert "Chop Governor" in result["message"]


def test_priority_cycle_result_does_not_report_wedged_worker_as_healthy(monkeypatch):
    import app as backend_app

    backend_app.PRIORITY_INTENT_STATE.clear()
    backend_app.PRIORITY_INTENT_STATE.update({"runtimeStatus": "WATCH", "lastScanAt": time.time()})
    beats = []
    fails = []
    monkeypatch.setattr(backend_app.RUNTIME_HEALTH, "beat", lambda *args, **kwargs: beats.append((args, kwargs)))
    monkeypatch.setattr(backend_app.RUNTIME_HEALTH, "fail", lambda *args, **kwargs: fails.append((args, kwargs)))

    backend_app._apply_priority_cycle_result({
        "ok": False,
        "wedged": True,
        "timeout": True,
        "message": "priority_intent_tick timed out",
    }, elapsed_ms=4100.0)

    assert backend_app.PRIORITY_INTENT_STATE["runtimeStatus"] == "RECOVERING"
    assert backend_app.PRIORITY_INTENT_STATE["consecutiveFailures"] >= 1
    assert not beats
    assert fails


def test_predictor_sse_and_dashboard_live_card_are_packaged():
    app_text = Path("backend/app.py").read_text(encoding="utf-8")
    index = Path("frontend/dist/index.html").read_text(encoding="utf-8")
    live_js = Path("frontend/dist/predictor-live-v1529.js").read_text(encoding="utf-8")
    live_css = Path("frontend/dist/predictor-live-v1529.css").read_text(encoding="utf-8")

    assert '@app.get("/api/fast-sniper/stream")' in app_text
    assert "StreamingResponse" in app_text
    assert "predictor-live-v1529.js" in index
    assert "predictor-live-v1529.css" in index
    assert "EventSource" in live_js
    assert "godmode-predictor-dashboard" in live_js
    assert "eip-refresh-spin" in live_js
    assert "stopImmediatePropagation" in live_js
    assert "Refreshing…" in live_js
    assert "Updated ${new Date().toLocaleTimeString" in live_js
    assert "predictor-heartbeat" in live_css
    assert "@keyframes predictorPulse" in live_css

def test_predictor_status_does_not_touch_blocking_mt5_ipc(monkeypatch):
    import app as backend_app

    now = time.time()
    backend_app.PRIORITY_INTENT_STATE.update({
        "runtimeStatus": "WATCH",
        "lastScanAt": now,
        "lastCompletedAt": now,
        "lastMt5ConnectedAt": now,
        "lastMt5Symbol": "XAUUSD",
    })
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: (_ for _ in ()).throw(RuntimeError("IPC wedged")))

    result = backend_app.fast_sniper_status()

    assert result["ok"] is True
    assert result["mt5"]["connected"] is True
    assert result["mt5"]["source"] == "priority_heartbeat_cache"

def test_tick_window_uses_direct_quote_between_bounded_history_backfills(monkeypatch):
    import app as backend_app

    now = time.time()
    symbol = "XAUUSD"
    backend_app.PREDICTOR_TICK_BUFFERS.clear()
    backend_app.PREDICTOR_TICK_LAST_FETCH_MSC.clear()
    backend_app.PREDICTOR_TICK_LAST_BACKFILL_AT.clear()
    existing = {"time": int(now)-1, "time_msc": int((now-.5)*1000), "timeMsc": int((now-.5)*1000), "bid": 4040.0, "ask": 4040.2, "last": 4040.1}
    backend_app.PREDICTOR_TICK_BUFFERS[symbol] = [existing]
    backend_app.PREDICTOR_TICK_LAST_FETCH_MSC[symbol] = existing["time_msc"]
    backend_app.PREDICTOR_TICK_LAST_BACKFILL_AT[symbol] = now
    calls = []
    monkeypatch.setattr(backend_app.mt5_bridge, "status", lambda: {"connected": True})
    monkeypatch.setattr(backend_app.mt5_bridge, "copy_ticks_range", lambda *args: calls.append(args) or [])
    market = {"tickTime": int(now), "tickTimeMsc": int(now*1000), "bid": 4040.3, "ask": 4040.5, "price": 4040.5}

    ticks, meta = backend_app._predictor_tick_window(symbol, 4.0, now, market)

    assert not calls
    assert ticks[-1]["ask"] == 4040.5
    assert meta["historyBackfill"] is False
