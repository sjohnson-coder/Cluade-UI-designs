from pathlib import Path
from types import SimpleNamespace

import services.mt5_bridge as bridge_module
from services.mt5_bridge import MT5Bridge
from services.early_intent import predict_early_intent
from services.impulse_prediction import predict_impulse


class FakeMT5:
    COPY_TICKS_ALL = 0

    @staticmethod
    def copy_ticks_range(symbol, start, end, flags):
        # Two ticks deliberately share the same integer second. The millisecond
        # timestamp must survive the bridge or acceleration/velocity are corrupted.
        return [
            SimpleNamespace(time=1_700_000_000, time_msc=1_700_000_000_100, bid=100.0, ask=100.1, last=100.05, volume=1, flags=1),
            SimpleNamespace(time=1_700_000_000, time_msc=1_700_000_000_450, bid=100.2, ask=100.3, last=100.25, volume=1, flags=1),
        ]


def _candles(live_close=100.9):
    rows = []
    for i in range(13):
        base = 100.0 + (i % 2) * 0.02
        rows.append({"open": base, "high": base + 0.18, "low": base - 0.18, "close": base + 0.01})
    rows[-1] = {"open": 100.0, "high": live_close + 0.05, "low": 99.95, "close": live_close}
    return rows


def test_bridge_preserves_canonical_millisecond_tick_timestamp(monkeypatch):
    monkeypatch.setattr(bridge_module, "mt5", FakeMT5)
    bridge = MT5Bridge()
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    rows = bridge.copy_ticks_range("XAUUSD", 1.0, 2.0)
    assert rows[0]["time_msc"] == 1_700_000_000_100
    assert rows[0]["timeMsc"] == rows[0]["time_msc"]
    assert rows[1]["time_msc"] - rows[0]["time_msc"] == 350


def test_predictors_accept_bridge_camelcase_time_and_use_subsecond_elapsed():
    prices = [100.00, 100.01, 100.03, 100.06, 100.10, 100.16, 100.24, 100.34, 100.46, 100.60]
    ticks = [
        {"time": 1_700_000_000, "timeMsc": 1_700_000_000_000 + i * 250, "bid": p, "ask": p + 0.08}
        for i, p in enumerate(prices)
    ]
    intent = predict_early_intent(
        ticks=ticks,
        candles=_candles(100.60),
        atr=5.0,
        current_spread=0.08,
        max_spread=0.40,
        config={"intentProbability": 0.55, "minDisplacementAtr": 0.06},
    )
    impulse = predict_impulse(
        ticks=ticks,
        candles=_candles(100.60),
        atr=5.0,
        current_spread=0.08,
        max_spread=0.40,
        config={"probeProbability": 0.50, "minProbeDisplacementAtr": 0.06},
    )
    assert intent.side == "BUY"
    assert intent.velocity_score > 0
    assert intent.acceleration_score > 0
    assert impulse.side == "BUY"
    assert impulse.velocity_score > 0


def test_early_intent_uses_recent_accelerating_tail_instead_of_cancelled_full_window():
    # Initial micro pullback should not force the engine to wait until the entire
    # 4-second window becomes positive. The last accelerating burst is the signal.
    prices = [100.10, 100.06, 100.03, 100.02, 100.04, 100.08, 100.14, 100.22, 100.32, 100.44, 100.58, 100.74]
    ticks = [
        {"time_msc": 1_000_000 + i * 300, "bid": p, "ask": p + 0.08}
        for i, p in enumerate(prices)
    ]
    result = predict_early_intent(
        ticks=ticks,
        candles=_candles(100.74),
        atr=7.0,
        current_spread=0.08,
        max_spread=0.40,
        config={"intentProbability": 0.60, "minDisplacementAtr": 0.07},
    )
    assert result.side == "BUY"
    assert result.stage == "INTENT"
    assert result.displacement_atr >= 0.07


def test_runtime_exposes_real_predictor_state_and_dedicated_entry_floor():
    app = Path("backend/app.py").read_text(encoding="utf-8")
    assert '"earlyIntent": intent_state' in app
    assert '"earlyImpulse": impulse_state' in app
    assert 'entryThresholdPct' in app
    assert 'requiredConfidence' in app
    assert 'PREDICTOR_TICK_BUFFERS' in app


def test_legacy_spike_fallback_is_direction_locked_and_not_hardcoded_quality():
    app = Path("backend/app.py").read_text(encoding="utf-8")
    assert "_resolve_momentum_fallback" in app
    assert 'confidence_label = "Fallback quality"' in app
    assert "82 if kind == \"spike\"" not in app


def test_status_endpoint_exposes_live_predictor_states(monkeypatch):
    import app as backend_app

    now = __import__('time').time()
    backend_app.FAST_SNIPER_STATE['earlyIntent'] = {
        'stage': 'WATCH', 'runtimeStatus': 'WATCH', 'probability': 0.41,
        'tickCount': 17, 'latestTickAgeMs': 80, 'updatedAt': now,
    }
    backend_app.FAST_SNIPER_STATE['earlyImpulse'] = {
        'stage': 'PROBE', 'runtimeStatus': 'PROBE', 'probability': 0.74,
        'tickCount': 17, 'latestTickAgeMs': 80, 'updatedAt': now,
    }
    monkeypatch.setattr(backend_app, '_live_market', lambda: {'symbol': 'XAUUSD'})
    monkeypatch.setattr(backend_app, '_fast_sniper_decision', lambda market: {'ok': False, 'reason': 'watching'})
    backend_app.PRIORITY_INTENT_STATE.update({'lastMt5ConnectedAt': now, 'lastMt5Symbol': 'XAUUSD', 'lastCompletedAt': now, 'lastScanAt': now})
    monkeypatch.setattr(backend_app.mt5_bridge, 'status', lambda: (_ for _ in ()).throw(AssertionError('read-only status must not touch MT5 IPC')))
    result = backend_app.fast_sniper_status()
    assert result['earlyIntent']['runtimeStatus'] == 'WATCH'
    assert result['earlyImpulse']['runtimeStatus'] == 'PROBE'
    assert result['earlyImpulse']['tickCount'] == 17
    assert result['mt5']['connected'] is True


def test_momentum_fallback_suppresses_opposing_same_candle_flip():
    import app as backend_app

    backend_app.MOMENTUM_FALLBACK_STATE.clear()
    backend_app.MOMENTUM_FALLBACK_STATE.update({'side': None, 'candleTime': 0, 'updatedAt': 0.0})
    backend_app.FAST_SNIPER_STATE['earlyIntent'] = {}
    backend_app.FAST_SNIPER_STATE['earlyImpulse'] = {}
    first = backend_app._resolve_momentum_fallback(candle_side='BUY', move_atr=0.8, candle_time=100, now=1000.0)
    second = backend_app._resolve_momentum_fallback(candle_side='SELL', move_atr=0.8, candle_time=100, now=1001.0)
    assert first['allowed'] is True and first['side'] == 'BUY'
    assert second['allowed'] is False and second['side'] == 'BUY'


def test_shared_tick_window_merges_and_deduplicates(monkeypatch):
    import app as backend_app

    backend_app.PREDICTOR_TICK_BUFFERS.clear()
    now = 1_700_000_010.0
    rows = [
        {'time': 1_700_000_009, 'timeMsc': 1_700_000_009_100, 'bid': 100.0, 'ask': 100.1},
        {'time': 1_700_000_009, 'time_msc': 1_700_000_009_500, 'bid': 100.2, 'ask': 100.3},
    ]
    monkeypatch.setattr(backend_app.mt5_bridge, 'status', lambda: {'connected': True})
    monkeypatch.setattr(backend_app.mt5_bridge, 'copy_ticks_range', lambda *args, **kwargs: rows + rows)
    ticks, meta = backend_app._predictor_tick_window('XAUUSD', 4.0, now, {
        'tickTime': 1_700_000_009, 'tickTimeMsc': 1_700_000_009_900,
        'bid': 100.4, 'ask': 100.5, 'price': 100.5,
    })
    assert len(ticks) == 3
    assert [t['time_msc'] for t in ticks] == sorted(t['time_msc'] for t in ticks)
    assert meta['tickCount'] == 3
    assert meta['latestTickAgeMs'] == 100


def test_predictor_settings_cross_field_validation():
    import copy
    import app as backend_app

    candidate = copy.deepcopy(backend_app._default_settings())
    candidate['automation']['earlyIntentHardMinTicks'] = 11
    candidate['automation']['earlyIntentMinTicks'] = 10
    try:
        backend_app._validate_settings_candidate(candidate, strict_ranges=True)
    except ValueError as exc:
        assert 'hard minimum ticks' in str(exc)
    else:
        raise AssertionError('invalid Early Intent sample relationship was accepted')
