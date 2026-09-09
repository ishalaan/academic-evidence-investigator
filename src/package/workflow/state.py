from typing import TypedDict

from package.schemas import CriticDecision, Paper, ResearchReport, SearchPlan


class ResearchState(TypedDict, total=False):
    research_question: str
    search_plan: SearchPlan
    raw_papers: list[Paper]
    processed_papers: list[Paper]
    critic_decision: CriticDecision
    search_cycle: int
    final_report: ResearchReport
    report_id: int