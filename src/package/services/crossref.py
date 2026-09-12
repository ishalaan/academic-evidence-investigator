import requests
from datetime import datetime, timezone

from package.schemas import Paper


BASE_URL = "https://api.crossref.org/works"


def search_crossref(
    query: str,
    limit: int = 10,
) -> list[Paper]:
    """
    Search Crossref and return normalised Paper objects.

    Crossref results are converted into the same internal Paper schema used
    by the rest of the system so downstream processing does not depend on the
    structure of a particular external API.
    """

    params = {
        "query.bibliographic": query,
        "rows": limit,
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()
    items = data.get("message", {}).get("items", [])

    papers: list[Paper] = []

    for item in items:
        titles = item.get("title") or []
        title = titles[0] if titles else ""

        authors = []
        author_details = []

        for author in item.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            full_name = f"{given} {family}".strip()

            if full_name:
                authors.append(full_name)
                author_details.append({"given": given, "family": family})

        published = item.get("published-print") or item.get("published-online") or {}
        date_parts = published.get("date-parts") or []

        year = None

        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        papers.append(
            Paper(
                title=title,
                authors=authors,
                abstract=item.get("abstract"),
                doi=item.get("DOI"),
                open_access_url=next((link.get("URL") for link in item.get("link", [])
                    if link.get("content-type") == "application/pdf" and
                    any("creativecommons.org/licenses/" in licence.get("URL", "") for licence in item.get("license", []))), None),
                url=item.get("URL"),
                year=year,
                source="Crossref",
                author_details=author_details,
                journal=(item.get("container-title") or [None])[0],
                volume=str(item["volume"]) if item.get("volume") else None,
                issue=str(item["issue"]) if item.get("issue") else None,
                pages=str(item["page"]) if item.get("page") else None,
                article_number=str(item["article-number"]) if item.get("article-number") else None,
                accessed_on=datetime.now(timezone.utc).date(),
            )
        )

    return papers
