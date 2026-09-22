from package.processing.deduplication import deduplicate_papers
from package.processing.ranking import (
    _relevance_score,
    filter_relevant_papers,
    rank_papers,
)
from package.processing.validation import validate_papers
from package.schemas import Paper, RankedSource


MAX_EVIDENCE_PAPERS = 10


def process_papers(
    papers: list[Paper],
    research_question: str,
    *,
    metrics: dict | None = None,
    ranked_sources: list[RankedSource] | None = None,
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

    # Prefer usable abstracts for synthesis; the complete relevance ranking is
    # retained independently, including metadata-only and below-threshold papers.
    evidence_order = sorted(ranked, key=lambda paper: bool((paper.abstract or '').strip()), reverse=True)
    retained = evidence_order[:MAX_EVIDENCE_PAPERS]
    if ranked_sources is not None:
        for index, paper in enumerate(rank_papers(deduplicated, research_question), 1):
            selected = paper in retained
            ranked_sources.append(RankedSource(paper=paper, rank=index,
                relevance_score=_relevance_score(paper, research_question)[0],
                eligible=paper in relevant, selected=selected,
                source_id=f"S{retained.index(paper) + 1}" if selected else None))
    # Count losses at each boundary so the audit can distinguish poor relevance
    # from duplicates or papers excluded only by the writing limit.
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
