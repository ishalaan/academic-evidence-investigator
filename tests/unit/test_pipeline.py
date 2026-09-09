from package.processing.pipeline import process_papers
from package.schemas import Paper


def test_processing_pipeline_validates_deduplicates_filters_and_ranks():
    papers = [
        Paper(
            title="Large Language Models in Education",
            year=2020,
            abstract="Applications of large language models in teaching.",
            doi="10.1234/older",
        ),
        Paper(
            title="Large Language Models in Education Duplicate",
            year=2020,
            abstract="Duplicate educational paper.",
            doi="10.1234/older",
        ),
        Paper(
            title="Large Language Models for Personalised Learning in Education",
            year=2025,
            abstract=(
                "Large language models support personalised learning "
                "and educational tutoring."
            ),
        ),
        Paper(
            title="Unrelated Financial Forecasting Study",
            year=2026,
            abstract="Stock market forecasting and investment analysis.",
        ),
        Paper(
            title="   ",
            year=2026,
            abstract="Invalid title",
        ),
    ]

    result = process_papers(
        papers,
        research_question=(
            "What are the applications of large language models in education?"
        ),
    )

    assert len(result) == 2

    titles = [paper.title for paper in result]

    assert "Large Language Models in Education" in titles
    assert (
        "Large Language Models for Personalised Learning in Education"
        in titles
    )
    assert "Unrelated Financial Forecasting Study" not in titles