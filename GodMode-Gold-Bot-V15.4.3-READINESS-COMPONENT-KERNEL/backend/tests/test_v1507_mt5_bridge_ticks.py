from __future__ import annotations

from types import SimpleNamespace

import services.mt5_bridge as bridge_module
from services.mt5_bridge import MT5Bridge


class FakeMT5:
    POSITION_TYPE_BUY = 0
    COPY_TICKS_ALL = 0

    @staticmethod
    def positions_get():
        return [SimpleNamespace(
            ticket=123,
            identifier=123,
            type=0,
            symbol="XAUUSD",
            volume=0.01,
            price_open=100.0,
            price_current=101.0,
            profit=1.0,
            sl=99.0,
            tp=103.0,
            time=1_700_000_000,
            time_msc=1_700_000_000_123,
            magic=202501,
            comment="GODMODE",
        )]

    @staticmethod
    def copy_ticks_range(symbol, start, end, flags):
        return [
            {"time": 2, "time_msc": 2002, "bid": 101.0, "ask": 101.2, "last": 101.1, "volume": 2, "flags": 1},
            {"time": 1, "time_msc": 1001, "bid": 100.0, "ask": 100.2, "last": 100.1, "volume": 1, "flags": 1},
        ]


def test_open_positions_exposes_broker_open_timestamps(monkeypatch):
    monkeypatch.setattr(bridge_module, "mt5", FakeMT5)
    bridge = MT5Bridge()
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    monkeypatch.setattr(bridge, "_open_position_entry_costs_batch", lambda ids: {"123": 0.0})
    row = bridge.open_positions(bot_only=False)[0]
    assert row["openTimestamp"] == 1_700_000_000
    assert row["openTimeMsc"] == 1_700_000_000_123


def test_copy_ticks_range_returns_chronological_bid_ask(monkeypatch):
    monkeypatch.setattr(bridge_module, "mt5", FakeMT5)
    bridge = MT5Bridge()
    monkeypatch.setattr(bridge, "_ensure_initialized", lambda: (True, "ok"))
    rows = bridge.copy_ticks_range("XAUUSD", 1.0, 3.0)
    assert [row["timeMsc"] for row in rows] == [1001, 2002]
    assert rows[0]["bid"] == 100.0
    assert rows[0]["ask"] == 100.2
