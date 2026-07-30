from __future__ import annotations

import math

from services.protection_determinism import (
    broker_open_epoch,
    broker_profit_stop_confirmed,
    elapsed_confirmation,
    elapsed_since,
    mark_elapsed_anchor,
    threshold_activated,
    valid_live_atr,
)


def test_valid_live_atr_is_fail_closed():
    assert valid_live_atr({"atr14": 5.25}) == 5.25
    assert valid_live_atr({"atr": 1.1}) == 1.1
    assert valid_live_atr({"atr14": 0}) is None
    assert valid_live_atr({"atr14": float("nan")}) is None
    assert valid_live_atr({}) is None


def test_broker_profit_stop_requires_live_profitable_readback():
    assert broker_profit_stop_confirmed("BUY", 100.0, 100.5, 101.0)
    assert not broker_profit_stop_confirmed("BUY", 100.0, 100.0, 101.0)
    assert not broker_profit_stop_confirmed("BUY", 100.0, 101.2, 101.0)
    assert broker_profit_stop_confirmed("SELL", 100.0, 99.5, 99.0)
    assert not broker_profit_stop_confirmed("SELL", 100.0, 100.0, 99.0)


def test_threshold_cannot_activate_early_but_stays_armed_after_activation():
    assert not threshold_activated(0.54, 0.55, already_armed=False)
    assert threshold_activated(0.55, 0.55, already_armed=False)
    assert threshold_activated(0.10, 0.55, already_armed=True)


def test_elapsed_confirmation_uses_duration_not_call_count():
    state = {}
    assert not elapsed_confirmation(state, "RECOVER", 3.0, now_monotonic=10.0, now_epoch=100.0)
    assert not elapsed_confirmation(state, "RECOVER", 3.0, now_monotonic=11.0, now_epoch=101.0)
    assert elapsed_confirmation(state, "RECOVER", 3.0, now_monotonic=13.1, now_epoch=103.1)
    assert not elapsed_confirmation(state, "CUT", 2.0, now_monotonic=13.2, now_epoch=103.2)


def test_elapsed_anchor_survives_process_token_change_via_epoch():
    state = {}
    mark_elapsed_anchor(state, "cooldown", now_monotonic=50.0, now_epoch=1000.0, process_token="old")
    assert math.isclose(
        elapsed_since(state, "cooldown", now_monotonic=2.0, now_epoch=1012.5, process_token="new"),
        12.5,
    )


def test_broker_open_epoch_prefers_millisecond_timestamp():
    assert broker_open_epoch({"openTimeMsc": 1_700_000_000_123, "openTimestamp": 1_700_000_000}) == 1_700_000_000.123
    assert broker_open_epoch({"openTimestamp": 1_700_000_000}) == 1_700_000_000.0
    assert broker_open_epoch({"openTime": "2026-07-28 06:20:00 UTC"}) > 0


def test_broker_open_epoch_accepts_numeric_mt5_open_time_alias():
    assert broker_open_epoch({"openTime": 1_700_000_000}) == 1_700_000_000.0
