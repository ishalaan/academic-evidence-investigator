import requests

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

        for author in item.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            full_name = f"{given} {family}".strip()

            if full_name:
                authors.append(full_name)

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
                url=item.get("URL"),
                year=year,
                source="Crossref",
            )
        )

    return papers