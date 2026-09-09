from pydantic import BaseModel, Field


class SearchPlan(BaseModel):
    research_goal: str
    queries: list[str]


class Paper(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    url: str | None = None
    year: int | None = None
    source: str | None = None


class CriticDecision(BaseModel):
    sufficient: bool
    reason: str
    suggested_queries: list[str] = Field(default_factory=list)


class ResearchReport(BaseModel):
    research_question: str
    summary: str
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    sources: list[Paper] = Field(default_factory=list)