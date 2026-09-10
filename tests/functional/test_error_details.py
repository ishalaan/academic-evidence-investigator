import json
import httpx
import pytest
from package.services.report_errors import failure_details
from package.storage.audit import create_run, record_event
from package.web import create_app

@pytest.mark.parametrize('error,code', [
    (httpx.ReadTimeout('SECRET'), 'model_timeout'),
    (httpx.ConnectError('CERTIFICATE_VERIFY_FAILED SECRET'), 'model_certificate'),
    (json.JSONDecodeError('SECRET', 'PRIVATE OUTPUT', 0), 'invalid_json'),
    (RuntimeError('SECRET'), 'workflow_stage_failed'),
])
def test_failure_diagnostics_are_safe(error, code):
    details = failure_details(error)
    assert details['error_code'] == code
    assert 'SECRET' not in str(details) and 'PRIVATE' not in str(details)


def test_failed_status_identifies_agent_and_run():
    app = create_app()
    run_id = create_run()
    record_event(run_id, 'Critic', 'failed', {'error_code': 'invalid_json', 'message': 'SECRET'}, stage='failed', status='failed')
    response = app.test_client().get(f'/runs/{run_id}/status')
    message = response.json['message']
    assert 'Critic failed' in message
    assert 'invalid_json' in message and run_id in message
    assert 'SECRET' not in message
