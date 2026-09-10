import json
from types import SimpleNamespace

import pytest
import httpx

from package.agents.reporter import reporter_node, validate_report_content, MAX_CONTEXT_CHARACTERS
from package.schemas import Paper
from package.services.references import reference_entries, report_references, used_source_ids
from package.services.report_errors import ReportGenerationError


class SectionClient:
    def __init__(self):
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        section = kwargs["messages"][1]["content"].splitlines()[0].split(": ")[1]
        body = {
            "summary_answer": {"summary": "Contextual question answering supports teaching [S2]."},
            "summary_analysis": {"summary": "Knowledge graphs ground contextual answers [S2]."},
            "summary_implications": {"summary": "Teachers can use contextual support [S2]."},
            "findings": {"findings": ["Contextual answers draw on a knowledge graph [S2]."]},
            "limitations": {"limitations": ["The retrieved abstracts do not describe long-term learning outcomes."]},
        }[section]
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(body)))])


def test_all_sources_remain_available_and_only_cited_references_are_shown(monkeypatch):
    client = SectionClient()
    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: client)
    papers = [Paper(title="Classroom overview", authors=["Khine", "Afari"], year=2025),
              Paper(title="Educational QA", authors=["Kok Arslan"], year=2025,
                    abstract="LLMs and knowledge graphs support context-aware educational question answering.")]
    result = reporter_node({"research_question": "LLMs in education", "processed_papers": papers})
    report = result["final_report"]
    assert report.cited_source_ids == ["S2"]
    assert [entry["id"] for entry in report_references(report)] == ["S2"]
    assert "knowledge graphs" in report.summary.lower()
    assert "excluded" not in report.summary and "restriction" not in report.summary
    assert len(client.calls) == 5
    for call in client.calls:
        assert 'ALL AVAILABLE SOURCE IDS: ["S1", "S2"]' in call["messages"][1]["content"]
        assert "Use only supplied [S1] source IDs" not in str(call)


@pytest.mark.parametrize("text", [
    "The source is excluded as per the current constraint to use only [S1].",
    "This restriction to [S1] prevents discussion of the other evidence.",
    "The study [S2], excluded here, cannot be included due to the restriction to [S1].",
])
def test_invented_single_source_restrictions_are_rejected(text):
    papers = [Paper(title="First"), Paper(title="Second")]
    with pytest.raises(ReportGenerationError) as error:
        validate_report_content(json.dumps({"summary": text}), papers, reference_entries(papers), "Q")
    assert error.value.code == "report_invented_restriction"


def test_long_abstracts_do_not_overflow_each_section_context(monkeypatch):
    client = SectionClient()
    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: client)
    papers = [Paper(title=f"Relevant study {i}", abstract="Evidence about tutoring. " * 6000) for i in range(10)]
    reporter_node({"research_question": "LLMs in education", "processed_papers": papers})
    assert all(sum(len(m["content"]) for m in call["messages"]) <= MAX_CONTEXT_CHARACTERS for call in client.calls)
    assert all(call["max_tokens"] == 2400 for call in client.calls)
    assert all('"source_id": "S10"' in call["messages"][1]["content"] for call in client.calls)


def test_uncited_source_label_in_prose_does_not_enter_references():
    entries = reference_entries([Paper(title="First"), Paper(title="Second")])
    assert used_source_ids("The label S2 is not a citation. Evidence [S1].", entries) == {"S1"}


def test_temporary_failure_retries_only_current_section(monkeypatch):
    class IntermittentClient(SectionClient):
        def __init__(self):
            super().__init__()
            self.failures = 0

        def chat_completion(self, **kwargs):
            if "SECTION: findings\n" in kwargs["messages"][1]["content"] and not self.failures:
                self.failures += 1
                raise httpx.ReadTimeout("Temporary interruption")
            return super().chat_completion(**kwargs)

    client = IntermittentClient()
    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: client)
    monkeypatch.setattr("package.agents.reporter.time.sleep", lambda _: None)
    report = reporter_node({"research_question": "Q", "processed_papers": [
        Paper(title="First", abstract="Evidence."), Paper(title="Second", abstract="Evidence.")]})["final_report"]
    assert report.findings
    assert client.failures == 1 and len(client.calls) == 5
