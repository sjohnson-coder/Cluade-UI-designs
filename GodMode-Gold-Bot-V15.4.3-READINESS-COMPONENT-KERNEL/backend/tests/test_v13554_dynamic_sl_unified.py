import importlib.util
from pathlib import Path

APP=Path(__file__).resolve().parents[1]/"app.py"
spec=importlib.util.spec_from_file_location("gm_app_13554",APP)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_tick_normalization():
    old=mod.mt5_bridge.symbol_specs
    mod.mt5_bridge.symbol_specs=lambda s:{"tradeTickSize":0.005,"digits":3}
    try:
        assert mod._normalize_price("XAUUSD", 2350.1234)==2350.125
    finally: mod.mt5_bridge.symbol_specs=old

def test_hysteresis_recover_and_cut(monkeypatch):
    clock = {"mono": 10.0, "epoch": 100.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setattr(mod.time, "time", lambda: clock["epoch"])
    st={}
    assert not mod._hysteresis_confirm(st,"RECOVER",recover_seconds=2.0)
    clock.update(mono=12.1, epoch=102.1)
    assert mod._hysteresis_confirm(st,"RECOVER",recover_seconds=2.0)
    assert not mod._hysteresis_confirm(st,"CUT",cut_seconds=2.0)
    clock.update(mono=14.2, epoch=104.2)
    assert mod._hysteresis_confirm(st,"CUT",cut_seconds=2.0)
    assert mod._hysteresis_confirm({},"CUT",structural=True,cut_seconds=2.0)

def test_directional_freshness():
    import time
    d={"side":"BUY","symbol":"XAUUSD","_generatedAt":time.time()}
    assert mod._fresh_directional_decision(d,"BUY","XAUUSD")[1]
    assert not mod._fresh_directional_decision(d,"SELL","XAUUSD")[1]

def test_risk_binary_search_uses_broker_calc():
    old=mod.mt5_bridge.order_calc_profit
    mod.mt5_bridge.order_calc_profit=lambda side,symbol,lots,entry,stop: -abs(entry-stop)*100*lots
    try:
        dist=mod._max_stop_distance_for_risk("XAUUSD","BUY",1.0,2000,10000,1.0,5.0)
        assert 0.99 <= dist <= 1.01
    finally: mod.mt5_bridge.order_calc_profit=old

def test_buy_sell_management_price():
    market={"bid":2000.1,"ask":2000.4,"price":2000.25}
    assert mod._management_price("BUY",market,{})==2000.1
    assert mod._management_price("SELL",market,{})==2000.4
