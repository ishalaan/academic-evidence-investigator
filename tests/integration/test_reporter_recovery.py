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
    assert len(client.calls) == 6
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
    assert len(client.calls) == 5


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
