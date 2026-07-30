from __future__ import annotations

from types import SimpleNamespace

import pytest

import app
from services import mt5_bridge as mt5_module
from services.mt5_bridge import MT5Bridge


class _Result:
    def __init__(self, **values):
        self.__dict__.update(values)

    def _asdict(self):
        return dict(self.__dict__)


def _symbol_info(trade_mode: int = 4):
    return SimpleNamespace(
        point=0.01,
        trade_tick_size=0.01,
        trade_tick_value=1.0,
        trade_tick_value_loss=1.0,
        volume_min=0.01,
        volume_step=0.01,
        volume_max=100.0,
        digits=2,
        filling_mode=2,
        trade_stops_level=0,
        trade_freeze_level=0,
        trade_mode=trade_mode,
    )


def _fake_mt5(**overrides):
    values = {
        "TRADE_ACTION_DEAL": 1,
        "TRADE_ACTION_SLTP": 2,
        "TRADE_ACTION_PENDING": 5,
        "ORDER_TYPE_BUY": 0,
        "ORDER_TYPE_SELL": 1,
        "ORDER_TYPE_BUY_LIMIT": 2,
        "ORDER_TYPE_SELL_LIMIT": 3,
        "ORDER_TYPE_BUY_STOP": 4,
        "ORDER_TYPE_SELL_STOP": 5,
        "ORDER_TYPE_BUY_STOP_LIMIT": 6,
        "ORDER_TYPE_SELL_STOP_LIMIT": 7,
        "POSITION_TYPE_BUY": 0,
        "POSITION_TYPE_SELL": 1,
        "ORDER_FILLING_FOK": 0,
        "ORDER_FILLING_IOC": 1,
        "ORDER_FILLING_RETURN": 2,
        "ORDER_TIME_GTC": 0,
        "ORDER_TIME_SPECIFIED": 1,
        "SYMBOL_TRADE_MODE_DISABLED": 0,
        "SYMBOL_TRADE_MODE_LONGONLY": 1,
        "SYMBOL_TRADE_MODE_SHORTONLY": 2,
        "SYMBOL_TRADE_MODE_CLOSEONLY": 3,
        "SYMBOL_TRADE_MODE_FULL": 4,
        "symbol_info": lambda _symbol: _symbol_info(),
        "symbol_select": lambda _symbol, _enabled: True,
        "symbol_info_tick": lambda _symbol: SimpleNamespace(bid=99.9, ask=100.0, time=1),
        "order_calc_margin": lambda *_args: 1.0,
        "account_info": lambda: SimpleNamespace(margin_free=10_000.0),
        "positions_get": lambda **_kwargs: [],
        "order_check": lambda _request: SimpleNamespace(retcode=0, comment="ok"),
        "last_error": lambda: (0, "ok"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _entry_request(fake, order_type: int):
    return {
        "action": fake.TRADE_ACTION_DEAL,
        "symbol": "XAUUSD",
        "volume": 0.01,
        "type": order_type,
        "price": 100.0,
        "sl": 99.0 if order_type == fake.ORDER_TYPE_BUY else 101.0,
        "tp": 102.0 if order_type == fake.ORDER_TYPE_BUY else 98.0,
    }


def test_preflight_requeries_and_enforces_current_trade_mode(monkeypatch):
    modes = iter([4, 3])
    calls = {"symbol_info": 0, "order_check": 0}

    def symbol_info(_symbol):
        calls["symbol_info"] += 1
        return _symbol_info(next(modes))

    fake = _fake_mt5(
        symbol_info=symbol_info,
        order_check=lambda _request: calls.__setitem__(
            "order_check", calls["order_check"] + 1
        )
        or SimpleNamespace(retcode=0, comment="ok"),
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()

    first_ok, _, first = bridge._preflight(
        "XAUUSD", _entry_request(fake, fake.ORDER_TYPE_BUY)
    )
    second_ok, _, second = bridge._preflight(
        "XAUUSD", _entry_request(fake, fake.ORDER_TYPE_BUY)
    )

    assert first_ok is True
    assert first["tradeModeName"] == "FULL"
    assert second_ok is False
    assert second["brokerCloseOnly"] is True
    assert second["tradeModeName"] == "CLOSEONLY"
    assert second["cooldown"]["active"] is True
    assert calls == {"symbol_info": 2, "order_check": 1}


@pytest.mark.parametrize(
    ("trade_mode", "order_type", "allowed"),
    [
        (1, 0, True),
        (1, 1, False),
        (2, 0, False),
        (2, 1, True),
        (0, 0, False),
        (4, 0, True),
        (4, 1, True),
    ],
)
def test_trade_mode_direction_matrix(monkeypatch, trade_mode, order_type, allowed):
    fake = _fake_mt5(symbol_info=lambda _symbol: _symbol_info(trade_mode))
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()

    ok, _, detail = bridge._preflight(
        "XAUUSD", _entry_request(fake, order_type)
    )

    assert ok is allowed
    assert detail["tradeMode"] == trade_mode


def test_close_reduction_remains_allowed_when_symbol_is_close_only(monkeypatch):
    fake = _fake_mt5(symbol_info=lambda _symbol: _symbol_info(3))
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()
    request = {
        **_entry_request(fake, fake.ORDER_TYPE_SELL),
        "position": 91,
    }

    ok, _, detail = bridge._preflight("XAUUSD", request)

    assert ok is True
    assert detail["tradeModeName"] == "CLOSEONLY"
    assert detail["marginCheck"] == "bypassed_position_reduction"


def test_missing_trade_mode_fails_closed_before_order_check(monkeypatch):
    info = _symbol_info()
    delattr(info, "trade_mode")
    fake = _fake_mt5(
        symbol_info=lambda _symbol: info,
        order_check=lambda _request: pytest.fail(
            "entry with unknown trade mode reached order_check"
        ),
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()

    ok, _, detail = bridge._preflight(
        "XAUUSD", _entry_request(fake, fake.ORDER_TYPE_BUY)
    )

    assert ok is False
    assert detail["classification"] == "BROKER_TRADE_MODE_UNKNOWN"
    assert detail["tradeModeName"] == "UNKNOWN"


def test_order_check_retcode_10044_activates_close_only_cooldown(monkeypatch):
    fake = _fake_mt5(
        order_check=lambda _request: SimpleNamespace(
            retcode=10044,
            comment="Only position closing is allowed",
        )
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()

    ok, _, detail = bridge._preflight(
        "XAUUSD", _entry_request(fake, fake.ORDER_TYPE_BUY)
    )

    assert ok is False
    assert detail["retcode"] == 10044
    assert detail["brokerCloseOnly"] is True
    assert detail["classification"] == "BROKER_CLOSE_ONLY"
    assert bridge.broker_entry_cooldown("XAUUSD")["active"] is True


def test_market_tick_exception_fails_closed(monkeypatch):
    fake = _fake_mt5(
        symbol_info_tick=lambda _symbol: (_ for _ in ()).throw(
            RuntimeError("terminal IPC unavailable")
        )
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()
    monkeypatch.setattr(bridge, "_schedule_open", lambda: (True, "Open"))
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))

    state = bridge.market_open()

    assert state["open"] is False
    assert state["source"] == "error"
    assert "IPC unavailable" in state["reason"]


def test_app_market_state_exception_fails_closed(monkeypatch):
    monkeypatch.setattr(
        app.mt5_bridge,
        "market_open",
        lambda: (_ for _ in ()).throw(RuntimeError("market probe failed")),
    )

    state = app._market_state()

    assert state["open"] is False
    assert state["source"] == "error"
    assert state["error"] is True


def test_live_entry_market_probe_exception_never_reaches_order_send(monkeypatch):
    sent: list[dict] = []
    fake = _fake_mt5(
        order_send=lambda request: sent.append(dict(request))
        or _Result(retcode=10009, price=request["price"]),
    )
    monkeypatch.setattr(mt5_module, "mt5", fake)
    bridge = MT5Bridge()
    bridge.live_enabled = True
    bridge.auto_trading_enabled = True
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(
        bridge,
        "market_open",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("market state unavailable")),
    )

    result = bridge.execute(
        {
            "executionId": "market-fail-closed",
            "symbol": "XAUUSD",
            "side": "BUY",
            "volume": 0.01,
            "sl": 99.0,
            "tp": 102.0,
            "maxRiskCash": 10.0,
        }
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["marketStateUnavailable"] is True
    assert sent == []


def test_retcode_10044_is_classified_and_cooldown_suppresses_retries(monkeypatch):
    calls = {"order_send": 0}

    def order_send(request):
        calls["order_send"] += 1
        return _Result(
            retcode=10044,
            comment="Only position closing is allowed",
            price=request["price"],
        )

    fake = _fake_mt5(order_send=order_send)
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
    payload = {
        "executionId": "close-only-first",
        "symbol": "XAUUSD",
        "side": "BUY",
        "volume": 0.01,
        "sl": 99.0,
        "tp": 102.0,
        "maxRiskCash": 10.0,
    }

    first = bridge.execute(payload)
    second = bridge.execute({**payload, "executionId": "close-only-second"})

    assert first["ok"] is False
    assert first["blocked"] is True
    assert first["retcode"] == 10044
    assert first["classification"] == "BROKER_CLOSE_ONLY"
    assert first["brokerCloseOnly"] is True
    assert first["cooldown"]["active"] is True
    assert second["ok"] is False
    assert second["brokerCloseOnly"] is True
    assert second["cooldown"]["retryAfterSeconds"] > 0
    assert calls["order_send"] == 1


def test_pending_entry_uses_same_trade_mode_admission(monkeypatch):
    sent: list[dict] = []
    fake = _fake_mt5(
        symbol_info=lambda _symbol: _symbol_info(3),
        order_send=lambda request: sent.append(dict(request))
        or _Result(retcode=10009, order=1),
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

    result = bridge.place_pending_stop(
        {
            "symbol": "XAUUSD",
            "side": "BUY",
            "volume": 0.01,
            "price": 101.0,
            "sl": 99.0,
            "tp": 103.0,
        }
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["brokerCloseOnly"] is True
    assert sent == []
