from services.runtime_safety import ExecutionLedger

def test_stale_submitting_becomes_unknown(tmp_path):
    l=ExecutionLedger(tmp_path/'x.sqlite'); payload={'operation':'MODIFY_SL','ticket':7,'sl':1.2}
    ok,key,_=l.begin(payload,'t',lease_seconds=1); assert ok; l.mark_submitting(key,lease_seconds=0)
    ok2,_,prior=l.begin(payload,'t',lease_seconds=1); assert not ok2; assert prior['status']=='UNKNOWN'

def test_open_identity_no_time_bucket(tmp_path):
    l=ExecutionLedger(tmp_path/'x.sqlite'); p={'operation':'OPEN','symbol':'XAUUSD','side':'BUY','volume':0.01}
    assert l.key_for(p,'a')==l.key_for(p,'a')

def test_readiness_route_exists():
    import app
    paths={r.path for r in app.app.routes}; assert '/api/readiness' in paths and '/api/liveness' in paths

def test_version_1355():
    import app; assert app.APP_VERSION=='15.4.3'


def test_multi_target_uses_child_transactions():
    import inspect, app
    src=inspect.getsource(app._execute_mt5_multi_serialized)
    assert 'executionId' in src and '_execute_mt5_serialized' in src

def test_instance_lock_helpers_present():
    import app
    assert callable(app._acquire_instance_lock) and callable(app._release_instance_lock)
