from pathlib import Path


def test_impulse_capture_defaults_are_live_candle_and_low_latency():
    source = Path(__file__).parents[1].joinpath("app.py").read_text(encoding="utf-8")
    assert '"fastSniperRequireClosedM5": False' in source
    assert '"fastSniperLoopSeconds": 0.5' in source
    assert '"shockImpulseEntryEnabled": True' in source
    assert '"shockImpulseMinDisplacementAtr": 1.10' in source


def test_shock_regime_can_reach_momentum_lane_without_bypassing_later_guards():
    source = Path(__file__).parents[1].joinpath("app.py").read_text(encoding="utf-8")
    shock_pos = source.index("shock_impulse = bool(")
    spread_pos = source.index("if spread and spread > max_spread:", shock_pos)
    exhaustion_pos = source.index("fastSniperExhaustionGuard", spread_pos)
    extension_pos = source.index("if extension_atr > max_ext", exhaustion_pos)
    assert shock_pos < spread_pos < exhaustion_pos < extension_pos
    assert '_rpolicy = {**_rpolicy, "sniper": True, "momentum": True, "counterHtfMomentum": True}' in source


def test_cascade_proposal_rebuilds_action_matrix():
    source = Path(__file__).parents[1].joinpath("app.py").read_text(encoding="utf-8")
    marker = "if _prop:"
    pos = source.index(marker, source.index("def _auto_trade_tick"))
    snippet = source[pos:pos + 900]
    assert "matrix = _action_matrix(decision=_prop" in snippet
    assert "decision = matrix.get(\"decision\"" in snippet
