from services.prelive_safety import PreLiveSafetySupervisor


def base(tmp_path):
    return PreLiveSafetySupervisor(tmp_path / "pretrade.jsonl")


def healthy():
    return dict(connected=True, tradeAllowed=True), dict(source="mt5", symbol="XAUUSD", spread=.2, ageSeconds=.5), dict(balance=10000, equity=10000)


def test_restricted_mode_caps_volume_and_writes_snapshot(tmp_path):
    supervisor = base(tmp_path)
    mt5, market, account = healthy()
    result = supervisor.assess(
        {"operation":"OPEN","symbol":"XAUUSD","volume":.10,"executionId":"x"}, source="test",
        config={"mode":"LIVE_RESTRICTED","symbol":"XAUUSD","maxRestrictedVolume":.01,"maxSpreadPrice":.8},
        mt5_status=mt5, market=market, account=account, open_positions=[], unresolved_commands=0, runtime_ready=True,
    )
    assert result.ok is True
    assert result.payload["volume"] == .01
    assert "volume capped" in result.warnings[0]
    assert "pts-" in (tmp_path / "pretrade.jsonl").read_text()


def test_restricted_mode_blocks_burst(tmp_path):
    supervisor = base(tmp_path)
    mt5, market, account = healthy()
    result = supervisor.assess(
        {"operation":"BURST","symbol":"XAUUSD","volume":.01}, source="test",
        config={"mode":"LIVE_RESTRICTED","symbol":"XAUUSD"}, mt5_status=mt5, market=market,
        account=account, open_positions=[], unresolved_commands=0, runtime_ready=True,
    )
    assert result.ok is False
    assert any("BURST" in row for row in result.blockers)


def test_missing_spread_and_disconnected_mt5_fail_closed(tmp_path):
    supervisor = base(tmp_path)
    result = supervisor.assess(
        {"operation":"OPEN","symbol":"XAUUSD","volume":.01}, source="test",
        config={"mode":"LIVE_FULL","symbol":"XAUUSD"}, mt5_status={"connected":False,"tradeAllowed":False},
        market={"source":"mt5","symbol":"XAUUSD"}, account={}, open_positions=[], unresolved_commands=0, runtime_ready=True,
    )
    assert result.ok is False
    assert "MT5 is disconnected" in result.blockers
    assert "live spread telemetry is unavailable" in result.blockers


def test_loss_and_position_limits_block(tmp_path):
    supervisor = base(tmp_path)
    mt5, market, account = healthy()
    result = supervisor.assess(
        {"operation":"OPEN","symbol":"XAUUSD","volume":.01}, source="test",
        config={"mode":"LIVE_FULL","symbol":"XAUUSD","maxDailyLoss":50,"maxOpenPositions":1},
        mt5_status=mt5, market=market, account=account, open_positions=[{"ticket":1}], unresolved_commands=0,
        runtime_ready=True, daily_pnl=-60,
    )
    assert result.ok is False
    assert len(result.blockers) == 2


def test_close_operation_is_never_blocked_by_entry_mode(tmp_path):
    supervisor = base(tmp_path)
    result = supervisor.assess(
        {"operation":"CLOSE","ticket":1}, source="test", config={"mode":"SHADOW"}, mt5_status={}, market={},
        account={}, open_positions=[], unresolved_commands=99, runtime_ready=False,
    )
    assert result.ok is True
