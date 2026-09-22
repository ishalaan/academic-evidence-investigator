from typing import TypedDict

from package.schemas import CriticDecision, Paper, ResearchReport, SearchPlan, RankedSource


# Nodes fill this state in stages, so fields cannot all be required at startup.
# Each node returns its changes rather than constructing a complete new run.
class ResearchState(TypedDict, total=False):
    research_question: str
    search_plan: SearchPlan
    raw_papers: list[Paper]
    processed_papers: list[Paper]
    critic_decision: CriticDecision
    search_cycle: int
    final_report: ResearchReport
    report_id: int
    ranked_sources: list[RankedSource]
    run_id: str
    run_started: float
    metrics: dict
    processing_metrics: dict
    provider_failures: list[dict]

    evidence_chunks: list
    evidence_coverage: dict
    # Keep extracted passages and access failures within the run so replanning
    # can reuse work without persisting full article text in the report database.
    rag_cache: dict
    rag_failures: dict
    semantic_policy: dict
