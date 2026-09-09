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

    return ranked[:MAX_EVIDENCE_PAPERS]