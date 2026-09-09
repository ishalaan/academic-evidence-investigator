from package.schemas import Paper


EXCLUDED_TITLE_PREFIXES = (
    "figure ",
    "table ",
    "front matter",
    "back matter",
    "contents",
    "index",
    "editorial",
    "correction",
    "erratum",
)


def validate_papers(papers: list[Paper]) -> list[Paper]:
    """
    Remove records that are unsuitable as academic evidence.

    Crossref can return figures, tables, front matter and other publication
    components as individual records. These are excluded because the research
    agent should work with substantive scholarly publications rather than
    document fragments.
    """

    valid_papers: list[Paper] = []

    for paper in papers:
        title = paper.title.strip()

        if not title:
            continue

        normalised_title = title.lower()

        if normalised_title.startswith(EXCLUDED_TITLE_PREFIXES):
            continue

        valid_papers.append(paper)

    return valid_papers