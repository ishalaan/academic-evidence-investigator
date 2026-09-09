from package.schemas import Paper
from package.workflow.nodes import processing_node


def test_processing_node_returns_processed_papers():
    state = {
        "research_question": (
            "What are the applications of large language models in education?"
        ),
        "raw_papers": [
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
                abstract="Stock market forecasting.",
            ),
        ],
    }

    result = processing_node(state)

    assert len(result["processed_papers"]) == 2

    titles = [
        paper.title
        for paper in result["processed_papers"]
    ]

    assert "Large Language Models in Education" in titles
    assert (
        "Large Language Models for Personalised Learning in Education"
        in titles
    )
    assert "Unrelated Financial Forecasting Study" not in titles