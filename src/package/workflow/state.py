from typing import TypedDict

from package.schemas import CriticDecision, Paper, ResearchReport, SearchPlan, RankedSource


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
    rag_cache: dict
    rag_failures: dict
    semantic_policy: dict
