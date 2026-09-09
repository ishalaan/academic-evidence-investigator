from package.processing.ranking import rank_papers
from package.schemas import Paper


def test_rank_papers_prioritises_relevance():
    papers = [
        Paper(
            title="Large Language Models in Education",
            authors=["Author One"],
            abstract="Applications of language models for personalised learning.",
            year=2024,
            source="Crossref",
        ),
        Paper(
            title="Large Language Models in Finance",
            authors=["Author Two"],
            abstract="Applications of language models for financial forecasting.",
            year=2026,
            source="Crossref",
        ),
    ]

    ranked = rank_papers(
        papers,
        "What are the applications of large language models in education?",
    )

    assert ranked[0].title == "Large Language Models in Education"


def test_rank_papers_uses_abstract_and_year_as_secondary_signals():
    papers = [
        Paper(
            title="Artificial Intelligence Study",
            abstract=None,
            year=2026,
        ),
        Paper(
            title="Artificial Intelligence Study",
            abstract="Education and personalised learning applications.",
            year=2024,
        ),
    ]

    ranked = rank_papers(
        papers,
        "artificial intelligence education",
    )

    assert ranked[0].abstract is not None