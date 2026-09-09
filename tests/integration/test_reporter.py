from types import SimpleNamespace

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
                          "summary": "The evidence suggests mixed outcomes.",
                          "findings": [
                            "Some studies report improved learning outcomes."
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

    assert report.summary == "The evidence suggests mixed outcomes."
    assert len(report.findings) == 1
    assert len(report.limitations) == 1
    assert len(report.sources) == 1
    assert report.sources[0].doi == "10.1234/example"
    assert result["report_id"] == 1