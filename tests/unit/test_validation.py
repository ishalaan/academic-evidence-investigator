from package.processing.validation import validate_papers
from package.schemas import Paper


def test_paper_without_title_is_removed():
    papers = [
        Paper(
            title="Valid Paper",
            authors=["A. Author"],
        ),
        Paper(
            title="   ",
            authors=["B. Author"],
        ),
    ]

    result = validate_papers(papers)

    assert len(result) == 1
    assert result[0].title == "Valid Paper"