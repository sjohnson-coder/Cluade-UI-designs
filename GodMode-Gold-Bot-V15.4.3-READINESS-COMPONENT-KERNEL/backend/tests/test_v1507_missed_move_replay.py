from __future__ import annotations

from services.missed_move_replay import deduplicate_events, event_identity, replay_executable_ticks


def test_event_identity_is_candle_stable():
    assert event_identity("xauusd", "buy", "m5", 1000) == "XAUUSD:BUY:M5:1000"
    assert event_identity("XAUUSD", "BUY", "M5", 1000) == event_identity("xauusd", "buy", "m5", 1000)
    assert event_identity("XAUUSD", "BUY", "M5", 1300) != event_identity("XAUUSD", "BUY", "M5", 1000)


def test_deduplicate_events_keeps_first_executable_quote_for_same_event():
    rows = [
        {"eventId": "XAUUSD:BUY:M5:1000", "entryTimeMsc": 1002, "entryPrice": 101.0},
        {"eventId": "XAUUSD:BUY:M5:1000", "entryTimeMsc": 1000, "entryPrice": 100.2},
        {"eventId": "XAUUSD:SELL:M5:1300", "entryTimeMsc": 1301, "entryPrice": 99.8},
    ]
    deduped = deduplicate_events(rows)
    assert len(deduped) == 2
    assert deduped[0]["entryTimeMsc"] == 1000
    assert deduped[0]["entryPrice"] == 100.2


def test_buy_replay_uses_entry_ask_and_exit_bid_in_true_time_order():
    ticks = [
        {"timeMsc": 3000, "bid": 102.0, "ask": 102.2},
        {"timeMsc": 1000, "bid": 100.0, "ask": 100.2},
        {"timeMsc": 2000, "bid": 99.5, "ask": 99.7},
    ]
    result = replay_executable_ticks("BUY", entry_price=100.2, entry_time_msc=1000, ticks=ticks)
    assert result["ok"] is True
    assert result["bestFavourable"] == 1.8
    assert result["worstBeforeBest"] == 0.7
    assert result["bestTimeMsc"] == 3000
    assert result["bestExitPrice"] == 102.0
    assert result["worstBeforeBestExitPrice"] == 99.5


def test_sell_replay_uses_entry_bid_and_exit_ask_in_true_time_order():
    ticks = [
        {"timeMsc": 1000, "bid": 100.0, "ask": 100.2},
        {"timeMsc": 3000, "bid": 98.7, "ask": 98.9},
        {"timeMsc": 2000, "bid": 100.1, "ask": 100.2},
    ]
    result = replay_executable_ticks("SELL", entry_price=100.0, entry_time_msc=1000, ticks=ticks)
    assert result["ok"] is True
    assert result["bestFavourable"] == 1.1
    assert result["worstBeforeBest"] == 0.2
    assert result["bestExitPrice"] == 98.9
    assert result["worstBeforeBestExitPrice"] == 100.2


def test_legacy_duplicate_events_are_clustered_without_five_minute_buckets():
    rows = [
        {"ts": "2026-07-28T04:19:58Z", "symbol": "XAUUSD", "side": "BUY", "timeframe": "M5", "price": 4044.19, "blockedBy": "same blocker"},
        {"ts": "2026-07-28T04:20:01Z", "symbol": "XAUUSD", "side": "BUY", "timeframe": "M5", "price": 4044.19, "blockedBy": "same blocker"},
        {"ts": "2026-07-28T04:25:01Z", "symbol": "XAUUSD", "side": "BUY", "timeframe": "M5", "price": 4044.19, "blockedBy": "same blocker"},
    ]
    deduped = deduplicate_events(rows)
    assert len(deduped) == 2
    assert deduped[0]["ts"] == "2026-07-28T04:19:58Z"
