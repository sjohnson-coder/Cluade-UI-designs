from fastapi.testclient import TestClient
import app as app_module


def test_v15_overview_and_evaluate_contracts():
    client = TestClient(app_module.app)
    overview = client.get('/api/v15/overview')
    assert overview.status_code == 200
    assert overview.json()['version'] == '15.4.3'

    payload = {
        'market': {'returns': [0.001, 0.0012], 'atr': 2, 'atr_baseline': 1.2, 'adx': 31, 'range_position': .8, 'liquidity': .8},
        'features': {'trend': .8, 'momentum': .7, 'structure': .7, 'extension': .2, 'spread_quality': .9},
        'broker': {'spread_points': 20, 'slippage_points': 2, 'latency_ms': 70, 'filled': True, 'session': 'london'},
        'position': {'current_r': .3, 'peak_r': .8, 'age_seconds': 120, 'current_stop_r': -.2, 'atr_r': .3},
        'burst': {'base_protected': False, 'bridge_ready': True, 'exposure_r': .1, 'max_exposure_r': .8, 'cooldown_active': False, 'extension': .2, 'max_extension': .8, 'risk_reward': 1.5},
    }
    result = client.post('/api/v15/evaluate', json=payload, headers={'Origin': 'http://127.0.0.1:8000', 'Sec-Fetch-Site': 'same-origin'})
    assert result.status_code == 200
    body = result.json()
    assert body['decision_id']
    assert 'forecast' in body and 'burst' in body and 'exit' in body


def test_v15_governance_material_change_requires_approval():
    import uuid
    client = TestClient(app_module.app)
    candidate_id = 'api-risk-' + uuid.uuid4().hex
    artifacts = app_module.V15_ORCHESTRATOR.governance.artifacts_dir
    artifacts.mkdir(parents=True, exist_ok=True)
    artifact = artifacts / f'{candidate_id}.json'
    artifact.write_text('{"risk_threshold": 0.8}')
    result = client.post('/api/v15/governance/candidates', json={
        'candidate_id': candidate_id, 'change_type': 'risk_threshold',
        'metrics': {'brier': .12, 'drawdown': .08, 'sortino': 1.5, 'samples': 400, 'shadow_passed': True},
        'artifact_path': str(artifact), 'feature_schema': ['trend'],
    }, headers={'Origin': 'http://127.0.0.1:8000', 'Sec-Fetch-Site': 'same-origin'})
    assert result.status_code == 200
    assert result.json()['status'] == 'approval_required'
