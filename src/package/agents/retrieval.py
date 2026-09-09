from package.config import MAX_RESULTS_PER_QUERY
from package.schemas import Paper
from package.services.crossref import search_crossref
from package.services.semantic_scholar import search_semantic_scholar
from package.workflow.state import ResearchState


def retrieval_node(state: ResearchState) -> dict:
    """
    Retrieve academic papers for every query in the current search plan.

    Retrieval is separated from planning so the LLM decides what should be
    searched for, while deterministic service functions are responsible for
    communicating with external academic APIs.

    Papers from earlier search cycles are retained so replanning expands the
    evidence base rather than discarding previously retrieved material.

    Each external source is handled independently. This avoids creating a
    single point of failure and allows the workflow to continue when one
    provider is rate-limited, unavailable, or temporarily unreliable.
    """

    search_plan = state["search_plan"]

    # Existing papers are copied from shared state so a Critic-triggered replan
    # adds new evidence to the investigation instead of replacing earlier
    # results. Deduplication is handled later in the deterministic pipeline.
    papers: list[Paper] = list(state.get("raw_papers", []))

    for query in search_plan.queries:
        try:
            semantic_scholar_results = search_semantic_scholar(
                query,
                limit=MAX_RESULTS_PER_QUERY,
            )
            papers.extend(semantic_scholar_results)

        except Exception as exc:
            # Semantic Scholar is treated as an optional retrieval provider.
            # Logging and continuing allows Crossref to act as a fallback and
            # keeps temporary external-service failures from terminating the
            # complete autonomous workflow.
            print(f"Semantic Scholar retrieval failed: {exc}")

        try:
            crossref_results = search_crossref(
                query,
                limit=MAX_RESULTS_PER_QUERY,
            )
            papers.extend(crossref_results)

        except Exception as exc:
            # Crossref failures are isolated for the same reason: retrieval
            # sources should fail independently rather than bringing down the
            # entire agent system.
            print(f"Crossref retrieval failed: {exc}")

    # Raw results are returned without ranking or filtering here because those
    # responsibilities belong to the processing stage. Keeping these concerns
    # separate makes the workflow easier to test, explain, and maintain.
    return {"raw_papers": papers}