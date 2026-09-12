import time
from datetime import datetime, timezone

import requests

from package.config import SEMANTIC_SCHOLAR_API_KEY
from package.schemas import Paper


BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

# The approved introductory API limit is one request per second.
# A small margin is added so normal execution remains below that threshold.
REQUEST_INTERVAL_SECONDS = 1.1


def search_semantic_scholar(
    query: str,
    limit: int = 10,
) -> list[Paper]:
    """
    Search Semantic Scholar and return normalised academic metadata.

    Semantic Scholar is treated as an optional retrieval provider rather than
    a mandatory dependency. Live testing showed that the service could return
    rate-limit errors, server errors, or timeouts, so this function is kept
    deliberately small and predictable. Any exception is allowed to propagate
    to the Retrieval Agent, where it is handled independently and Crossref can
    continue supplying evidence.

    A short timeout is therefore preferred over repeated retries because the
    overall research workflow should remain responsive even when this external
    service is temporarily unavailable.
    """

    headers = {}

    # Authentication is added only when a key is configured. This keeps the
    # service compatible with both authenticated and unauthenticated use while
    # avoiding hard-coded credentials in source code.
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    # Requesting only the metadata fields required by downstream processing
    # reduces unnecessary response size and keeps the API interaction focused.
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,abstract,year,url,externalIds,journal,openAccessPdf",
    }

    # The assigned Semantic Scholar key permits one request per second. The
    # explicit delay ensures the implementation respects that external service
    # constraint rather than relying on accidental timing between queries.
    time.sleep(REQUEST_INTERVAL_SECONDS)

    response = requests.get(
        BASE_URL,
        headers=headers,
        params=params,
        # A short timeout prevents Semantic Scholar from becoming a bottleneck.
        # The Retrieval Agent can fall back to Crossref if this request fails.
        timeout=5,
    )

    # HTTP errors are not hidden here because the caller needs to know whether
    # the external source failed. The Retrieval Agent decides how to recover.
    response.raise_for_status()

    data = response.json()

    papers: list[Paper] = []

    for item in data.get("data", []):
        authors = [
            author.get("name", "")
            for author in item.get("authors", [])
            if author.get("name")
        ]

        external_ids = item.get("externalIds") or {}
        journal = item.get("journal") or {}

        # External API data is normalised immediately into the shared Paper
        # schema so downstream agents do not need provider-specific logic.
        papers.append(
            Paper(
                title=item.get("title") or "",
                authors=authors,
                abstract=item.get("abstract"),
                doi=external_ids.get("DOI"),
                open_access_url=(item.get("openAccessPdf") or {}).get("url"),
                url=item.get("url"),
                year=item.get("year"),
                source="Semantic Scholar",
                journal=journal.get("name"),
                volume=str(journal["volume"]) if journal.get("volume") else None,
                pages=str(journal["pages"]) if journal.get("pages") else None,
                accessed_on=datetime.now(timezone.utc).date(),
            )
        )

    return papers
