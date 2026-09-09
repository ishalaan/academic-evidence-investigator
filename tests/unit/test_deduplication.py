from package.processing.deduplication import deduplicate_papers
from package.schemas import Paper


def test_duplicate_doi_is_removed():
    papers = [
        Paper(
            title="Original Paper",
            authors=["A. Author"],
            doi="10.1234/example",
        ),
        Paper(
            title="Duplicate Paper",
            authors=["A. Author"],
            doi="10.1234/example",
        ),
    ]

    result = deduplicate_papers(papers)

    assert len(result) == 1