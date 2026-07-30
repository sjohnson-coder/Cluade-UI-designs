import time
from pathlib import Path
from services.runtime_safety import ExecutionLedger


def test_unknown_and_acknowledged_never_retry_without_reconciliation(tmp_path: Path):
    ledger=ExecutionLedger(tmp_path/'ledger.sqlite')
    payload={'operation':'OPEN','executionId':'same','symbol':'XAUUSD','side':'BUY','volume':0.01}
    ok,key,_=ledger.begin(payload,'test',lease_seconds=1)
    assert ok
    ledger.fail(key,'network lost',unknown=True)
    ok2,_,prior=ledger.begin(payload,'test',lease_seconds=1)
    assert not ok2 and prior['status']=='UNKNOWN'
    ledger.reconcile(key,'RECONCILED',{'found':False})
    ok3,_,prior3=ledger.begin(payload,'test',lease_seconds=1)
    assert not ok3 and prior3['status']=='RECONCILED'


def test_nested_mt5_result_is_normalised(tmp_path: Path):
    ledger=ExecutionLedger(tmp_path/'ledger.sqlite')
    payload={'operation':'OPEN','executionId':'nested','symbol':'XAUUSD','side':'SELL','volume':0.02}
    ok,key,_=ledger.begin(payload,'test')
    assert ok
    ledger.finish(key, {'ok':True,'request':{'volume':0.02},'result':{'retcode':10009,'deal':77,'order':66,'volume':0.02,'price':4100.5}})
    row=ledger.recent(1)[0]
    assert row['status']=='FILLED'
    assert row['broker_deal']=='77'


def test_mutation_key_is_stable_without_time_bucket(tmp_path: Path):
    ledger=ExecutionLedger(tmp_path/'ledger.sqlite')
    payload={'operation':'MODIFY_SL','ticket':123,'sl':4100.25}
    key1=ledger.key_for(payload,'manager')
    time.sleep(.01)
    key2=ledger.key_for(payload,'manager')
    assert key1==key2
