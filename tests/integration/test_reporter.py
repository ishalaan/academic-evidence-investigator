from types import SimpleNamespace
import json
import pytest
from package.services.report_errors import ReportGenerationError

from package.agents.reporter import reporter_node
from package.schemas import Paper


class FakeClient:
    def chat_completion(self, **kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="""
                        {
                          "research_question": "Does generative AI improve academic performance?",
                          "summary": "The evidence suggests mixed outcomes [S1].",
                          "findings": [
                            "Some studies report improved learning outcomes [S1]."
                          ],
                          "limitations": [
                            "The available evidence is limited."
                          ],
                          "sources": []
                        }
                        """
                    )
                )
            ]
        )


def test_reporter_returns_structured_report(monkeypatch):
    monkeypatch.setattr(
        "package.agents.reporter.get_llm_client",
        lambda: FakeClient(),
    )

    monkeypatch.setattr(
        "package.agents.reporter.save_report",
        lambda report: 1,
    )

    state = {
        "research_question": "Does generative AI improve academic performance?",
        "processed_papers": [
            Paper(
                title="Example Paper",
                authors=["A. Author"],
                abstract="An example abstract.",
                doi="10.1234/example",
                url="https://example.com",
                year=2025,
                source="Semantic Scholar",
            )
        ],
    }

    result = reporter_node(state)

    report = result["final_report"]

    assert report.summary.startswith("The evidence suggests mixed outcomes (Author, 2025).")
    assert report.cited_source_ids == ["S1"]
    assert len(report.findings) == 1
    assert len(report.limitations) == 1
    assert len(report.sources) == 1
    assert report.sources[0].doi == "10.1234/example"
    assert result["report_id"] == 1


def test_reporter_uses_real_metadata_for_citations_and_bibliography(monkeypatch):
    captured = {}

    class CitedClient:
        def chat_completion(self, **kwargs):
            captured.update(kwargs)
            payload = {"research_question": "Invented question", "summary": "A detailed comparison [S1] [S2].",
                       "findings": ["Evidence-supported finding [S2]."], "limitations": ["Only abstracts were available."],
                       "sources": [{"title": "Fabricated", "authors": ["Invented"], "year": 1990}]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: CitedClient())
    papers = [Paper(title="Alpha", authors=["Jane Smith"], year=2025, abstract="A relevant result."),
              Paper(title="Beta", authors=["Jane Smith"], year=2025, abstract="Another result.")]
    report = reporter_node({"research_question": "Actual question", "processed_papers": papers})["final_report"]
    assert report.research_question == "Actual question"
    assert report.summary.startswith("A detailed comparison (Smith, 2025a; Smith, 2025b).")
    assert report.findings == ["Evidence-supported finding (Smith, 2025b)."]
    assert report.sources == papers
    assert captured["max_tokens"] == 2400
    assert '"source_id": "S1"' in captured["messages"][1]["content"]
    assert "ALL AVAILABLE SOURCE IDS" in captured["messages"][1]["content"]


@pytest.mark.parametrize("summary", ["An invented citation [S99].", "Uncited claims."])
def test_reporter_rejects_untraceable_text_before_saving(monkeypatch, summary):
    saved = []

    class InvalidClient:
        def chat_completion(self, **kwargs):
            payload = {"summary": summary, "findings": [], "limitations": []}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: InvalidClient())
    monkeypatch.setattr("package.agents.reporter.save_report", lambda report: saved.append(report))
    with pytest.raises(ReportGenerationError):
        reporter_node({"research_question": "Q", "processed_papers": [Paper(title="Study", abstract="Evidence.")]})
    assert saved == []


def test_reporter_handles_no_evidence_without_fabricated_findings(monkeypatch):
    class EmptyClient:
        def chat_completion(self, **kwargs):
            payload = {"summary": "No evidence-based answer is available.", "findings": [],
                       "limitations": ["No papers were retrieved."]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    monkeypatch.setattr("package.agents.reporter.get_llm_client", lambda: EmptyClient())
    report = reporter_node({"research_question": "Q", "processed_papers": []})["final_report"]
    assert report.sources == report.findings == []
