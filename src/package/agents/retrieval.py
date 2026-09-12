import requests

from package.config import MAX_RESULTS_PER_QUERY
from package.schemas import Paper
from package.services.crossref import search_crossref
from package.services.semantic_scholar import search_semantic_scholar
from package.workflow.state import ResearchState


SEMANTIC_MAX_REQUESTS = 6
SEMANTIC_MAX_FAILURES = 2

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
    failures = []
    policy = dict(state.get("semantic_policy", {"requests": 0, "failures": 0, "disabled": False}))

    for query in search_plan.queries:
        try:
            if policy["disabled"] or policy["requests"] >= SEMANTIC_MAX_REQUESTS:
                policy["disabled"] = True
            else:
                policy["requests"] += 1
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
            policy["failures"] += 1
            status = getattr(getattr(exc, "response", None), "status_code", None)
            reason = ("rate_limit" if status == 429 else "authentication" if status in (401, 403)
                      else "timeout" if isinstance(exc, requests.Timeout) else "service_error" if status and status >= 500 else "request_failed")
            policy["disabled"] = policy["failures"] >= SEMANTIC_MAX_FAILURES or status in (401, 403, 429)
            failures.append({"provider": "Semantic Scholar", "message": "Provider request failed.",
                             "reason": reason, "disabled_for_run": policy["disabled"]})

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
            failures.append({"provider": "Crossref", "message": "Provider request failed."})

    # Raw results are returned without ranking or filtering here because those
    # responsibilities belong to the processing stage. Keeping these concerns
    # separate makes the workflow easier to test, explain, and maintain.
    policy["disabled"] = policy["disabled"] or policy["requests"] >= SEMANTIC_MAX_REQUESTS
    return {"raw_papers": papers, "provider_failures": failures, "semantic_policy": policy}
