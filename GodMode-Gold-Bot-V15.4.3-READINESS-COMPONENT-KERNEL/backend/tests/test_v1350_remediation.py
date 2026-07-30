import time
from pathlib import Path
from services.runtime_safety import ExecutionLedger


def test_execution_lease_recovers_after_expiry(tmp_path: Path):
    ledger=ExecutionLedger(tmp_path/'ledger.sqlite')
    payload={'symbol':'XAUUSD','side':'BUY','volume':0.01,'executionId':'lease-case'}
    ok,key,_=ledger.begin(payload,'test',lease_seconds=1)
    assert ok
    ok2,_,prior=ledger.begin(payload,'test',lease_seconds=1)
    assert not ok2 and prior['status']=='VALIDATED'
    time.sleep(1.1)
    ok3,_,meta=ledger.begin(payload,'test',lease_seconds=1)
    assert ok3 and meta.get('recovered') is True


def test_acknowledged_is_not_filled(tmp_path: Path):
    ledger=ExecutionLedger(tmp_path/'ledger.sqlite')
    payload={'symbol':'XAUUSD','side':'SELL','volume':0.01,'executionId':'ack-case'}
    ok,key,_=ledger.begin(payload,'test')
    assert ok
    ledger.finish(key,{'ok':True,'message':'accepted','request':payload})
    assert ledger.recent(1)[0]['status']=='ACKNOWLEDGED'


def test_confirmed_deal_is_filled(tmp_path: Path):
    ledger=ExecutionLedger(tmp_path/'ledger.sqlite')
    payload={'symbol':'XAUUSD','side':'SELL','volume':0.01,'executionId':'deal-case'}
    ok,key,_=ledger.begin(payload,'test')
    assert ok
    ledger.finish(key,{'ok':True,'deal':123,'filledVolume':0.01,'request':payload})
    assert ledger.recent(1)[0]['status']=='FILLED'
