"""Tests for telegram_event_policy — replays the exact storm from the screenshot."""

import time

from telegram_event_policy import (
    BlockLatch,
    classify_execution_outcome,
    format_block_message,
    format_clear_message,
)

# The literal result dict GodMode produces when _news_entry_guard() blocks a dispatch.
NEWS_BLOCK = {
    "ok": False,
    "blocked": True,
    "newsBlackout": True,
    "message": "New live entry blocked by the high-impact economic-news window.",
}

BROKER_REJECT = {
    "ok": False,
    "message": "Order rejected by broker: invalid stops (retcode 10016).",
    "reason": "broker_reject",
}


def test_news_block_is_a_policy_block_not_a_failure():
    out = classify_execution_outcome(NEWS_BLOCK)
    assert out.kind == "policy_block"
    assert out.is_policy
    # forces the collapsing "rejection:{bucket}" key instead of "other:{bucket}:{sha}"
    assert out.category == "rejection"
    assert "paused" in out.headline


def test_broker_rejection_is_still_a_real_failure():
    out = classify_execution_outcome(BROKER_REJECT)
    assert out.kind == "execution_failure"
    assert not out.is_policy
    assert out.telegram is True


def test_the_screenshot_storm_collapses_to_one_message():
    """5 blocked dispatches inside one news window -> 1 Telegram message."""
    latch = BlockLatch(remind_after_seconds=900.0)
    out = classify_execution_outcome(NEWS_BLOCK)

    sent = []
    now = time.time()
    for i in range(5):                      # 5 scan cycles, ~2 s apart
        alert, info = latch.should_alert(out.reason_code, now=now + i * 2)
        if alert:
            sent.append(format_block_message(out, NEWS_BLOCK, "BUY", 0.02, info))

    assert len(sent) == 1, f"expected 1 alert, got {len(sent)}"
    assert "No order was sent" in sent[0]
    assert latch._active[out.reason_code]["suppressed"] == 4


def test_long_block_sends_one_reminder_not_hundreds():
    latch = BlockLatch(remind_after_seconds=900.0)
    out = classify_execution_outcome(NEWS_BLOCK)
    now = time.time()

    sent = 0
    # a 30-minute news window, scanned every 2 seconds = 900 attempts
    for i in range(900):
        alert, info = latch.should_alert(out.reason_code, now=now + i * 2)
        if alert:
            sent += 1
    assert sent == 2, f"entry + one 15-min reminder expected, got {sent}"


def test_all_clear_reports_what_was_skipped():
    latch = BlockLatch()
    out = classify_execution_outcome(NEWS_BLOCK)
    now = time.time()
    for i in range(12):
        latch.should_alert(out.reason_code, now=now + i * 5)

    info = latch.clear(out.reason_code, now=now + 300)
    assert info is not None
    assert info["transition"] == "cleared"
    assert info["attempts"] == 12
    msg = format_clear_message(out.reason_code, info)
    assert "resumed" in msg and "12 setup" in msg


def test_distinct_block_reasons_latch_independently():
    latch = BlockLatch()
    news = classify_execution_outcome(NEWS_BLOCK)
    spread = classify_execution_outcome(
        {"ok": False, "message": "Spread spike — entry delayed.", "reason": "spread_spike"}
    )
    assert news.reason_code != spread.reason_code

    now = time.time()
    assert latch.should_alert(news.reason_code, now=now)[0] is True
    assert latch.should_alert(spread.reason_code, now=now)[0] is True
    assert latch.should_alert(news.reason_code, now=now + 1)[0] is False
    assert sorted(latch.active_reasons) == sorted([news.reason_code, spread.reason_code])


def test_volatile_reason_text_does_not_split_the_latch():
    """Numbers in the message must not create a new alert each attempt."""
    latch = BlockLatch()
    now = time.time()
    sent = 0
    for i in range(6):
        result = {
            "ok": False, "blocked": True,
            "message": f"Spread spike — entry delayed. Current spread 0.4{i} > 0.40.",
        }
        out = classify_execution_outcome(result)
        assert out.is_policy
        if latch.should_alert(out.reason_code, now=now + i)[0]:
            sent += 1
    assert sent == 1, f"volatile digits split the key: {sent} alerts"


def test_broker_failures_are_never_latched_away():
    """A real rejection must alert every time — this is what R48 protects."""
    out = classify_execution_outcome(BROKER_REJECT)
    assert out.kind == "execution_failure"
    msg = format_block_message(out, BROKER_REJECT, "SELL", 0.02, {})
    assert "0.02 lots" in msg
    assert "did not reach the broker" in msg


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
                passed += 1
            except AssertionError as exc:
                print(f"  FAIL  {name}: {exc}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
