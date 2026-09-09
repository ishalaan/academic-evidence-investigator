from package.agents.retrieval import retrieval_node
from package.schemas import Paper, SearchPlan


def test_retrieval_node(monkeypatch):
    """
    The retrieval agent should combine results from both academic sources.
    """

    def fake_semantic_scholar(query, limit=10):
        return [
            Paper(
                title="Semantic Scholar Paper",
                authors=["Author One"],
                abstract="Example abstract",
                doi="10.1000/semantic",
                url="https://example.com/semantic",
                year=2024,
                source="Semantic Scholar",
            )
        ]

    def fake_crossref(query, limit=10):
        return [
            Paper(
                title="Crossref Paper",
                authors=["Author Two"],
                abstract="Another abstract",
                doi="10.1000/crossref",
                url="https://example.com/crossref",
                year=2023,
                source="Crossref",
            )
        ]

    monkeypatch.setattr(
        "package.agents.retrieval.search_semantic_scholar",
        fake_semantic_scholar,
    )

    monkeypatch.setattr(
        "package.agents.retrieval.search_crossref",
        fake_crossref,
    )

    state = {
        "search_plan": SearchPlan(
            research_goal="Test academic retrieval",
            queries=["large language models education"],
        ),
        "raw_papers": [],
    }

    result = retrieval_node(state)

    assert len(result["raw_papers"]) == 2
    assert result["raw_papers"][0].source == "Semantic Scholar"
    assert result["raw_papers"][1].source == "Crossref"


def test_retrieval_preserves_existing_papers(monkeypatch):
    """
    Papers from previous search cycles should remain in the evidence set.
    """

    def fake_semantic_scholar(query, limit=10):
        return []

    def fake_crossref(query, limit=10):
        return [
            Paper(
                title="New Paper",
                authors=["Author Two"],
                doi="10.1000/new",
                source="Crossref",
            )
        ]

    monkeypatch.setattr(
        "package.agents.retrieval.search_semantic_scholar",
        fake_semantic_scholar,
    )

    monkeypatch.setattr(
        "package.agents.retrieval.search_crossref",
        fake_crossref,
    )

    existing_paper = Paper(
        title="Existing Paper",
        authors=["Author One"],
        doi="10.1000/existing",
        source="Crossref",
    )

    state = {
        "search_plan": SearchPlan(
            research_goal="Test accumulated retrieval",
            queries=["artificial intelligence education"],
        ),
        "raw_papers": [existing_paper],
    }

    result = retrieval_node(state)

    assert len(result["raw_papers"]) == 2
    assert result["raw_papers"][0].title == "Existing Paper"
    assert result["raw_papers"][1].title == "New Paper"


def test_retrieval_continues_when_semantic_scholar_fails(monkeypatch):
    """
    A Semantic Scholar failure should not prevent Crossref retrieval.
    """

    def fake_semantic_scholar(query, limit=10):
        raise RuntimeError("Semantic Scholar unavailable")

    def fake_crossref(query, limit=10):
        return [
            Paper(
                title="Fallback Crossref Paper",
                authors=["Author"],
                doi="10.1000/fallback",
                source="Crossref",
            )
        ]

    monkeypatch.setattr(
        "package.agents.retrieval.search_semantic_scholar",
        fake_semantic_scholar,
    )

    monkeypatch.setattr(
        "package.agents.retrieval.search_crossref",
        fake_crossref,
    )

    state = {
        "search_plan": SearchPlan(
            research_goal="Test fallback retrieval",
            queries=["machine learning education"],
        ),
        "raw_papers": [],
    }

    result = retrieval_node(state)

    assert len(result["raw_papers"]) == 1
    assert result["raw_papers"][0].source == "Crossref"