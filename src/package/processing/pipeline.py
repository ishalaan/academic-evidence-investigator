from package.processing.deduplication import deduplicate_papers
from package.processing.ranking import (
    filter_relevant_papers,
    rank_papers,
)
from package.processing.validation import validate_papers
from package.schemas import Paper


MAX_EVIDENCE_PAPERS = 10


def process_papers(
    papers: list[Paper],
    research_question: str,
    *,
    metrics: dict | None = None,
) -> list[Paper]:
    """
    Clean, deduplicate, filter and rank retrieved evidence.

    Only sufficiently relevant papers are retained, and the final evidence
    set is limited to the ten strongest results.
    """

    validated = validate_papers(papers)

    deduplicated = deduplicate_papers(validated)

    relevant = filter_relevant_papers(
        deduplicated,
        research_question,
        minimum_score=6,
    )

    ranked = rank_papers(
        relevant,
        research_question,
    )

    retained = ranked[:MAX_EVIDENCE_PAPERS]
    if metrics is not None:
        metrics.update(
            valid_papers_retained=len(validated),
            noisy_records_removed=len(papers) - len(validated),
            duplicates_removed=len(validated) - len(deduplicated),
            relevant_papers_retained=len(relevant),
            irrelevant_records_removed=len(deduplicated) - len(relevant),
            evidence_limit_removed=len(ranked) - len(retained),
            final_evidence_count=len(retained),
        )
    return retained
