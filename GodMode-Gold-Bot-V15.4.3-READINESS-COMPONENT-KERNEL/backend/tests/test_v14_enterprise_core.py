import time
from services.dynamic_sl_v14 import (
    BrokerRules, PositionSnapshot, DynamicSLState, decide,
    normalize_price, validate_stop, decision_is_stale,
)

RULES = BrokerRules(tick_size=0.01, stops_level_points=20, freeze_level_points=10, point=0.01)

def snap(side='BUY', sl=2290.0, seq=1):
    return PositionSnapshot(1,'XAUUSD',side,2300.0,2310.0,2310.2,sl,2320.0,0.1,10.0,1.5,1.1,time.time(),seq)

def test_price_normalization():
    assert normalize_price(2300.006, .01) == 2300.01

def test_buy_stop_invariant():
    ok, _ = validate_stop(snap(), RULES, 2305.0)
    assert ok
    ok, reason = validate_stop(snap(), RULES, 2310.0)
    assert not ok and reason.startswith('BUY_')

def test_sell_stop_invariant():
    p = snap('SELL', 2320.0)
    ok, _ = validate_stop(p, RULES, 2315.0)
    assert ok
    ok, reason = validate_stop(p, RULES, 2310.0)
    assert not ok and reason.startswith('SELL_')

def test_profit_stop_never_loosens_buy():
    p=snap(sl=2306.0)
    d=decide(p,RULES,state=DynamicSLState.PROFIT_LOCK,recovery_score=70,invalidated=False)
    assert d.proposed_sl >= 2306.0

def test_profit_stop_never_loosens_sell():
    p=snap('SELL',2304.0)
    d=decide(p,RULES,state=DynamicSLState.PROFIT_LOCK,recovery_score=70,invalidated=False)
    assert d.proposed_sl <= 2304.0

def test_invalidated_goes_exit_pending():
    d=decide(snap(),RULES,state=DynamicSLState.BREATHING,recovery_score=10,invalidated=True)
    assert d.state_after is DynamicSLState.EXIT_PENDING

def test_tp_extension_requires_continuation():
    d=decide(snap(),RULES,state=DynamicSLState.PROFIT_LOCK,recovery_score=85,invalidated=False)
    assert d.state_after is DynamicSLState.TP_EXTENSION
    assert d.proposed_tp > 2320.0

def test_stale_decision_rejected():
    p=snap(seq=1)
    d=decide(p,RULES,state=DynamicSLState.PROFIT_LOCK,recovery_score=70,invalidated=False)
    assert decision_is_stale(d, snap(seq=2))
