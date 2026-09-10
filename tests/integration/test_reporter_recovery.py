import json
from types import SimpleNamespace

import httpx
import pytest

from package.agents.reporter import reporter_node, MAX_REPORT_ATTEMPTS
from package.schemas import Paper
from package.storage.audit import create_run, get_run
from package.services.report_errors import ReportGenerationError
from package.workflow.audit import observed_node


def response(content, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)])


def valid_payload(summary="Supported finding [S1]."):
    return json.dumps({"summary": summary, "findings": ["Finding [S1]."], "limitations": ["Abstract-level review."]})


class SequenceClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        item = next(self.responses, response(valid_payload()))
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.parametrize("invalid", [response("{broken"), response(""),
    response(valid_payload("Missing citation.")), response(valid_payload("Unknown [S99].")),
    response(valid_payload(), "length"), response(json.dumps(["not an object"]))])
def test_invalid_report_gets_corrected_before_save(monkeypatch, invalid):
    client = SequenceClient([invalid, response(valid_payload())])
    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: client)
    run_id = create_run()
    result = reporter_node({"run_id": run_id, "research_question": "Q", "processed_papers": [Paper(title="Study", abstract="Evidence.")]})
    assert result["final_report"].summary.startswith("Supported finding (Study, no date).")
    assert len(client.calls) == 4
    assert client.calls[0]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    events = [e for e in get_run(run_id)["events"] if e["action"] == "retrying"]
    assert len(events) == 1 and events[0]["action"] == "retrying"
    assert events[0]["details"]["attempt"] == 2


def test_grouped_ids_and_known_author_year_formats_are_accepted(monkeypatch):
    client = SequenceClient([response(valid_payload("Comparison [S1, S2].\n\nA known citation (Smith, 2025)."))])
    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: client)
    result = reporter_node({"research_question": "Q", "processed_papers": [
        Paper(title="First", authors=["Jane Smith"], year=2025, abstract="Evidence."),
        Paper(title="Second", authors=["Jo Jones"], year=2024, abstract="Evidence.")]})
    assert result["final_report"].summary.startswith("Comparison (Smith, 2025; Jones, 2024).\n\nA known citation (Smith, 2025).")
    assert len(client.calls) == 3


def test_retries_are_bounded_and_failure_reason_is_safe(monkeypatch):
    client = SequenceClient([response(valid_payload("PRIVATE unsupported text."))] * MAX_REPORT_ATTEMPTS)
    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: client)
    saved = []
    monkeypatch.setattr("package.agents.reporter.save_report", lambda report: saved.append(report))
    run_id = create_run()
    with pytest.raises(ReportGenerationError):
        observed_node("reporter", reporter_node)({"run_id": run_id, "research_question": "Q",
                                                  "processed_papers": [Paper(title="Study", abstract="Evidence.")]})
    assert len(client.calls) == MAX_REPORT_ATTEMPTS
    assert saved == []
    run = get_run(run_id)
    assert run["status"] == "failed"
    assert run["events"][-1]["details"]["error_code"] == "report_citations_invalid"
    assert "PRIVATE" not in str(run)


def test_network_failure_has_safe_category(monkeypatch):
    client = SequenceClient([httpx.ConnectError("PRIVATE credentials")] * MAX_REPORT_ATTEMPTS)
    monkeypatch.setattr("package.agents.reporter.time.sleep", lambda _: None)
    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: client)
    with pytest.raises(ReportGenerationError) as error:
        reporter_node({"research_question": "Q", "processed_papers": [Paper(title="Study", abstract="Evidence.")]})
    assert error.value.code == "report_model_unavailable"
    assert "PRIVATE" not in str(error.value)


def test_remote_disconnect_retries_without_repeating_completed_content(monkeypatch):
    from package.agents.reporter import request_section
    client = SequenceClient([httpx.RemoteProtocolError('PRIVATE server disconnected'), response(valid_payload())])
    monkeypatch.setattr('package.agents.reporter.time.sleep', lambda _: None)
    result = request_section(client, [{'role': 'user', 'content': 'Section'}], {}, 'findings')
    assert result.choices
    assert len(client.calls) == 2


def test_authentication_errors_are_not_retried(monkeypatch):
    from package.agents.reporter import request_section
    request = httpx.Request('POST', 'https://example.com')
    error = httpx.HTTPStatusError('PRIVATE', request=request, response=httpx.Response(401, request=request))
    client = SequenceClient([error])
    with pytest.raises(ReportGenerationError):
        request_section(client, [], {}, 'summary')
    assert len(client.calls) == 1


def test_missing_citation_retry_explains_defect(monkeypatch):
    client = SequenceClient([response(valid_payload('Unsupported paragraph.')), response(valid_payload())])
    monkeypatch.setattr('package.agents.reporter.get_llm_client', lambda: client)
    result = reporter_node({'research_question': 'Q', 'processed_papers': [Paper(title='Study', abstract='Evidence.')]})
    assert result['final_report']
    assert 'Every non-empty summary paragraph' in client.calls[1]['messages'][-1]['content']


def test_persistent_unknown_citation_has_safe_diagnostic(monkeypatch):
    from package.services.report_errors import failure_details
    client = SequenceClient([response(valid_payload('Unsupported [S99].'))] * MAX_REPORT_ATTEMPTS)
    monkeypatch.setattr('package.agents.reporter.get_llm_client', lambda: client)
    with pytest.raises(ReportGenerationError) as caught:
        reporter_node({'research_question': 'Q', 'processed_papers': [Paper(title='Study', abstract='Evidence.')]})
    assert failure_details(caught.value)['validation_reason'] == 'unknown_source'


def test_provider_402_is_reported_as_credits_required(monkeypatch):
    from huggingface_hub.errors import HfHubHTTPError
    from package.agents.reporter import request_section
    from package.services.report_errors import failure_details
    request = httpx.Request('POST', 'https://example.com')
    error = HfHubHTTPError('PRIVATE provider content', response=httpx.Response(402, request=request))
    client = SequenceClient([error])
    with pytest.raises(ReportGenerationError) as caught:
        request_section(client, [], {}, 'summary')
    assert len(client.calls) == 1
    details = failure_details(caught.value)
    assert details['error_code'] == 'model_credits_required'
    assert 'PRIVATE' not in str(details)


def test_valid_short_section_is_not_rewritten_for_cosmetic_depth(monkeypatch):
    client = SequenceClient([response(valid_payload())] * 3)
    monkeypatch.setattr('package.agents.reporter.get_llm_client', lambda: client)
    papers = [Paper(title=f'Study {i}', abstract='Evidence about education. ' * 100) for i in range(3)]
    report = reporter_node({'research_question': 'Q', 'processed_papers': papers})['final_report']
    assert report.summary
    assert len(client.calls) == 3
