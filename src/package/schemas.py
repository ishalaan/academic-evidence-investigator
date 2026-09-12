from pydantic import BaseModel, Field
from datetime import date
from typing import Literal


class SearchPlan(BaseModel):
    research_goal: str
    queries: list[str]


class AuthorName(BaseModel):
    given: str = ""
    family: str = ""


class Paper(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    url: str | None = None
    year: int | None = None
    source: str | None = None
    author_details: list[AuthorName] = Field(default_factory=list)
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    article_number: str | None = None
    accessed_on: date | None = None
    open_access_url: str | None = None


class CriticDecision(BaseModel):
    sufficient: bool
    reason: str
    suggested_queries: list[str] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    paper_id: str
    source_id: str
    title: str
    doi: str | None = None
    page_number: int | None = None
    chunk_index: int
    text: str
    similarity_score: float = 0.0
    evidence_type: Literal["full_text", "abstract"]
    source_url: str | None = None


class RankedSource(BaseModel):
    paper: Paper
    rank: int
    relevance_score: int
    eligible: bool
    selected: bool
    source_id: str | None = None
    evidence_type: Literal["full_text", "abstract", "metadata_only"] | None = None
    evidence_status: str | None = None


class ResearchReport(BaseModel):
    research_question: str
    summary: str
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    sources: list[Paper] = Field(default_factory=list)
    cited_source_ids: list[str] | None = None
    ranked_sources: list[RankedSource] | None = None
    report_notes: list[str] = Field(default_factory=list)
    evidence_provenance: list[dict] = Field(default_factory=list)
    evidence_coverage: dict = Field(default_factory=dict)
