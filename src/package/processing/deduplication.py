import re

from package.schemas import Paper


def _normalise_doi(doi: str | None) -> str | None:
    """
    Normalise DOI values before duplicate comparison.

    DOI matching is preferred because it is generally more reliable than title
    comparison for identifying the same academic work across retrieval sources.
    """

    if not doi:
        return None

    normalised = doi.strip().lower()

    # Versioned preprints such as ".../v1" and ".../v2" represent revisions of
    # the same underlying work. Removing the version suffix prevents multiple
    # revisions from appearing as separate evidence items in the final report.
    normalised = re.sub(r"/v\d+$", "", normalised)

    return normalised


def _normalise_title(title: str) -> str:
    """
    Normalise titles for fallback duplicate detection.

    Title matching is used only when a DOI is unavailable because titles are
    less reliable identifiers and may vary slightly between metadata sources.
    """

    return " ".join(title.lower().split())


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    """
    Remove duplicate academic records while preserving the first occurrence.

    DOI is used as the primary identifier because it provides stronger
    bibliographic identity than title text. Normalised title matching is used
    only as a fallback when no DOI is available.

    This deterministic approach was chosen so duplicate-removal behaviour is
    transparent, reproducible, and easy to test rather than relying on an LLM
    to decide whether two records represent the same publication.
    """

    unique: list[Paper] = []

    seen_dois: set[str] = set()
    doi_positions: dict[str, int] = {}
    seen_titles: set[str] = set()

    for paper in papers:
        doi = _normalise_doi(paper.doi)
        title = _normalise_title(paper.title)

        if doi:
            # DOI equality is treated as strong evidence that the records refer
            # to the same work, including normalised preprint revisions.
            if doi in seen_dois:
                position = doi_positions[doi]
                first = unique[position]
                # Do not lose a usable abstract supplied by another provider for
                # the exact same DOI. Preserve first-record values and never mix
                # different versioned DOIs that happen to share a normalised key.
                if (first.doi or '').strip().lower() == (paper.doi or '').strip().lower():
                    updates = {field: getattr(paper, field) for field in
                        ("open_access_url", "abstract", "journal", "volume", "issue", "pages", "article_number", "url")
                        if not getattr(first, field) and getattr(paper, field)}
                    if first.authors == paper.authors and not first.author_details:
                        updates["author_details"] = paper.author_details
                    unique[position] = first.model_copy(update=updates)
                continue

            seen_dois.add(doi)
            doi_positions[doi] = len(unique)

        elif title:
            # When DOI metadata is missing, normalised title matching provides
            # a conservative fallback so obvious duplicates are still removed.
            if title in seen_titles:
                continue

        # Titles are tracked even when a DOI exists so later records without a
        # DOI can still be recognised as duplicates of an earlier paper.
        if title:
            seen_titles.add(title)

        unique.append(paper)

    return unique
