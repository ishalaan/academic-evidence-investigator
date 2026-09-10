from package.processing.pipeline import process_papers
from package.workflow.state import ResearchState


def processing_node(state: ResearchState) -> dict:
    """
    Clean, deduplicate and rank retrieved academic papers before critique.

    Deterministic processing is kept outside the LLM agents because these
    operations are predictable, testable and do not require generative
    reasoning.
    """

    metrics = {}
    ranked_sources = []
    processed_papers = process_papers(
        papers=state.get("raw_papers", []),
        research_question=state["research_question"],
        metrics=metrics,
        ranked_sources=ranked_sources,
    )

    return {
        "processed_papers": processed_papers,
        "processing_metrics": metrics,
        "ranked_sources": ranked_sources,
    }
