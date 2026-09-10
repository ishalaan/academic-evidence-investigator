import json
import httpx
from pydantic import ValidationError

from package.schemas import ResearchReport
from package.services.json_utils import clean_json_response
from package.services.llm import get_llm_client
from package.services.prompts import load_prompt
from package.services.references import cited_text, reference_entries
from package.services.report_errors import ReportGenerationError
from package.storage.audit import record_event
from package.storage.database import save_report
from package.workflow.state import ResearchState

MAX_REPORT_ATTEMPTS = 3


def validate_report_content(content, papers, entries, research_question):
    try:
        data = json.loads(clean_json_response(content))
        if not isinstance(data, dict):
            raise ValueError("Expected an object.")
        data["sources"] = [paper.model_dump() for paper in papers]
        data["research_question"] = research_question
        report = ResearchReport.model_validate(data)
        if not report.summary.strip():
            raise ValueError("Empty summary.")
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise ReportGenerationError("report_format_invalid") from None
    try:
        report.summary = cited_text(report.summary, entries, require_citation=bool(papers))
        report.findings = [cited_text(text, entries, require_citation=bool(papers)) for text in report.findings]
        report.limitations = [cited_text(text, entries) for text in report.limitations]
        if not papers and report.findings:
            raise ValueError("Findings without evidence.")
    except ValueError:
        raise ReportGenerationError("report_citations_invalid") from None
    return report


def reporter_node(state: ResearchState) -> dict:
    """
    Produce and persist the final structured research briefing.

    The Reporter is responsible for synthesis rather than retrieval or evidence
    selection. Keeping these responsibilities separate reduces the risk that
    the LLM changes the evidence base while generating the final narrative.

    Only processed papers already accepted by the workflow are supplied to the
    Reporter. Bibliographic metadata is then preserved deterministically from
    those retrieved Paper objects before the report is validated and stored.
    """

    research_question = state["research_question"]
    papers = state.get("processed_papers", [])

    # The reporting instructions are kept in an external prompt file so the
    # synthesis policy can be reviewed and refined independently from the
    # Python implementation.
    reporter_prompt = load_prompt("reporter.txt")

    # Only the evidence required for synthesis is supplied to the model.
    # Retaining titles, abstracts and source metadata supports grounded report
    # generation while preserving traceability back to retrieved records.
    entries = reference_entries(papers)
    papers_payload = [
        {
            "source_id": f"S{index}",
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "doi": paper.doi,
            "url": paper.url,
            "year": paper.year,
            "source": paper.source,
        }
        for index, paper in enumerate(papers, 1)
    ]

    # A strict JSON response is requested because the report is subsequently
    # validated, persisted and rendered by deterministic application code.
    user_content = f"""
Research question:
{research_question}

Accepted academic evidence:
{json.dumps(papers_payload, ensure_ascii=False)}

Return JSON only in this exact structure:

{{
  "research_question": "string",
  "summary": "string",
  "findings": ["string", "string"],
  "limitations": ["string", "string"],
  "sources": []
}}

Use the supplied [S1], [S2], etc. citation tokens in the text.
Return sources as []; the application fills this with the original evidence.
""".strip()

    client = get_llm_client()

    messages = [{"role": "system", "content": reporter_prompt},
                {"role": "user", "content": user_content}]
    for attempt in range(1, MAX_REPORT_ATTEMPTS + 1):
        try:
            response = client.chat_completion(
                messages=messages, temperature=0.2, max_tokens=6000,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except httpx.HTTPError:
            raise ReportGenerationError("report_model_unavailable") from None
        try:
            if not response.choices:
                raise ReportGenerationError("report_format_invalid")
            choice = response.choices[0]
            if getattr(choice, "finish_reason", None) == "length":
                raise ReportGenerationError("report_output_truncated")
            content = choice.message.content
            if not content:
                raise ReportGenerationError("report_format_invalid")
            report = validate_report_content(content, papers, entries, research_question)
            break
        except ReportGenerationError as exc:
            if attempt == MAX_REPORT_ATTEMPTS:
                raise
            if state.get("run_id"):
                record_event(state["run_id"], "Reporter", "retrying",
                             {"attempt": attempt + 1, "error_code": exc.code}, stage="reporter")
            # Retry with explicit constraints; never record or expose the raw output.
            correction = (
                "Generate the entire report again as one complete JSON object. "
                "Use only supplied [S1] source IDs. Every summary paragraph and every "
                "finding needs a supporting source ID; do not invent citations. "
                "Use plain prose without standalone headings. Keep the requested detail "
                "where evidence supports it, and finish all JSON fields. "
            )
            if exc.code == "report_output_truncated":
                correction += "The last response was cut off. Keep this attempt shorter so it fits."
            elif exc.code == "report_citations_invalid":
                correction += "The last response contained missing or invalid citations."
            else:
                correction += "The last response was empty or did not match the JSON schema."
            messages = messages[:2] + [{"role": "user", "content": correction}]

    # Persisting the validated report provides an execution record and allows
    # the browser interface to show a saved report identifier.
    report_id = save_report(report)

    return {
        "final_report": report,
        "report_id": report_id,
    }
