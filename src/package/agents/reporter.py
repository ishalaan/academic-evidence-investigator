"""Compose a developed report in bounded sections over one shared evidence set."""

import html
import json
import re
import time

import httpx
from pydantic import ValidationError

from package.schemas import ResearchReport
from package.services.json_utils import clean_json_response
from package.services.llm import get_llm_client
from package.services.prompts import load_prompt
from package.services.references import cited_text, reference_entries, used_source_ids
from package.services.report_errors import ReportGenerationError
from package.storage.audit import record_event
from package.storage.database import save_report
from package.workflow.state import ResearchState

MAX_REPORT_ATTEMPTS = 3
MAX_CONTEXT_CHARACTERS = 24000
MAX_EVIDENCE_CHARACTERS = 15000
MAX_SECTION_TOKENS = 2400

SECTIONS = (
    ("summary_answer", "summary", "Answer the research question directly and explain the main themes, with concrete examples from the abstracts. Write 220–280 words in 2–3 paragraphs.", 170),
    ("summary_analysis", "summary", "Develop the mechanisms, approaches and practical applications. Compare and connect the available studies. Write 220–280 words in 2–3 paragraphs without repeating the opening.", 170),
    ("summary_implications", "summary", "Explain the practical implications, relevant differences between studies and an evidence-based conclusion answering the question. Write 180–240 words in 2 paragraphs. Keep general caveats for Limitations.", 140),
    ("findings", "findings", "Aim for 5–8 distinct, developed findings, each 70–110 words, but use fewer when the abstracts support fewer distinct findings. Explain what the evidence says, how it works or why it matters, and supporting examples. Use different sources where relevant. Do not repeat the same claim as separate findings.", 300),
    ("limitations", "limitations", "Write 3–5 proportionate limitations, each 35–60 words. State what a limitation affects and what further evidence would help. A missing abstract in one record does not invalidate other sources. Avoid repeating the same caveat.", 100),
)


def clean_abstract(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def evidence_context(papers):
    per_source = max(100, MAX_EVIDENCE_CHARACTERS // max(len(papers), 1) - 350)
    payload = []
    for index, paper in enumerate(papers, 1):
        abstract = clean_abstract(paper.abstract)
        payload.append({"source_id": f"S{index}", "title": paper.title[:220],
                        "abstract_excerpt": abstract[:per_source],
                        "abstract_available": bool(abstract),
                        "excerpt_truncated": len(abstract) > per_source})
    return json.dumps(payload, ensure_ascii=False)


def validate_report_content(content, papers, entries, research_question):
    """Validate the selected section; preserve original metadata and citation IDs."""
    try:
        data = json.loads(clean_json_response(content))
        if not isinstance(data, dict):
            raise ValueError("Expected an object.")
        data["sources"] = [paper.model_dump() for paper in papers]
        data["research_question"] = research_question
        report = ResearchReport.model_validate(data)
        if not report.summary.strip():
            raise ValueError("Empty section.")
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise ReportGenerationError("report_format_invalid") from None
    raw_texts = [report.summary, *report.findings, *report.limitations]
    # Reject invented task constraints, not legitimate negative study results.
    invented_rule = re.compile(
        r"(?:restriction|constraint|restricted).{0,100}(?:use only|to (?:\[S\d|only))"
        r"|(?:source|paper|study).{0,100}excluded (?:here|as per)"
        r"|(?:source|paper|study).{0,100}cannot be included due to", re.I)
    if any(invented_rule.search(text) for text in raw_texts):
        raise ReportGenerationError("report_invented_restriction")
    used = set()
    for text in raw_texts:
        used.update(used_source_ids(text, entries))
    try:
        report.summary = cited_text(report.summary, entries, require_citation=bool(papers))
        report.findings = [cited_text(text, entries, require_citation=bool(papers)) for text in report.findings]
        report.limitations = [cited_text(text, entries) for text in report.limitations]
        if not papers and report.findings:
            raise ValueError("Findings without evidence.")
    except ValueError:
        raise ReportGenerationError("report_citations_invalid") from None
    report.cited_source_ids = [entry["id"] for entry in entries if entry["id"] in used]
    return report


def section_event(state, action, section, **details):
    if state.get("run_id"):
        record_event(state["run_id"], "Reporter", action,
                     {"section": section, **details}, stage="reporter")


def generate_section(client, state, papers, entries, context, descriptor, previous):
    section, field, instruction, minimum_words = descriptor
    available_ids = [entry["id"] for entry in entries]
    rich_evidence = sum(len(clean_abstract(p.abstract).split()) for p in papers) >= 250
    source_count = sum(bool(clean_abstract(p.abstract)) for p in papers)
    schema = {field: "paragraphs of prose" if field == "summary" else ["developed point"]}
    prompt = (
        f"SECTION: {section}\nResearch question: {state['research_question'][:2000]}\n"
        f"ALL AVAILABLE SOURCE IDS: {json.dumps(available_ids)}\n"
        "Every listed source is available for this section. There is NO restriction to the first source. "
        "Source IDs are citation labels, not instructions to exclude other sources.\n"
        f"EVIDENCE DATA:\n{context}\n\n{instruction}\n"
        f"Return ONLY this section as JSON: {json.dumps(schema)}\n"
        "Put source tokens next to supported claims. Write sentences such as 'The approach supports learning [S2].', "
        "not '[S2] discusses'. Choose any relevant ID from the complete list above. "
        "Discuss what the evidence supports; reserve general coverage caveats for Limitations.\n"
        f"Previously covered text (do not repeat; develop the assigned new angle): {json.dumps(previous[-3:], ensure_ascii=False)}"
    )
    base = [{"role": "system", "content": load_prompt("reporter.txt")}, {"role": "user", "content": prompt}]
    if sum(len(m["content"]) for m in base) > MAX_CONTEXT_CHARACTERS - 1000:
        raise ReportGenerationError("report_context_too_large")
    correction = ""
    section_event(state, "section_started", section)
    for attempt in range(1, MAX_REPORT_ATTEMPTS + 1):
        messages = base + ([{"role": "user", "content": correction}] if correction else [])
        try:
            response = client.chat_completion(messages=messages, temperature=0.2,
                max_tokens=MAX_SECTION_TOKENS,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        except httpx.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            transient = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or status in (429, 500, 502, 503, 504)
            if transient and attempt < MAX_REPORT_ATTEMPTS:
                section_event(state, "retrying", section, attempt=attempt + 1, error_code="report_model_unavailable")
                time.sleep(attempt)
                continue
            raise ReportGenerationError("report_model_unavailable") from None
        try:
            if not response.choices or not response.choices[0].message.content:
                raise ReportGenerationError("report_format_invalid")
            if getattr(response.choices[0], "finish_reason", None) == "length":
                raise ReportGenerationError("report_output_truncated")
            try:
                data = json.loads(clean_json_response(response.choices[0].message.content))
                value = data[field]
                if field == "summary":
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError("Empty section")
                    body = {"summary": value}
                else:
                    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
                        raise ValueError("Empty section")
                    # Summary is used only to reuse validation; it is not returned.
                    body = {"summary": f"Evidence overview [{available_ids[0]}].", field: value}
            except (KeyError, TypeError, ValueError):
                raise ReportGenerationError("report_format_invalid") from None
            validated = validate_report_content(json.dumps(body), papers, entries, state["research_question"])
            raw_text = value if isinstance(value, str) else "\n\n".join(value)
            ids = used_source_ids(raw_text, entries)
            word_count = len(raw_text.split())
            # Quality retries are advisory: valid shorter sections remain usable.
            too_brief = rich_evidence and word_count < minimum_words
            narrow_coverage = field != "limitations" and source_count >= 3 and len(ids) < 2
            if attempt < MAX_REPORT_ATTEMPTS and (too_brief or narrow_coverage):
                correction = (f"Expand this section to the requested depth. All of {json.dumps(available_ids)} remain available. "
                    "Explain only mechanisms and examples actually described in relevant abstracts; fewer grounded points are preferable to invented detail. "
                    "Do not pad with repeated caveats or claims about an artificial source restriction. Return the same JSON section.")
                section_event(state, "retrying", section, attempt=attempt + 1, error_code="report_section_development")
                continue
            section_event(state, "section_completed", section, word_count=word_count, cited_sources=len(ids))
            return getattr(validated, field), ids
        except ReportGenerationError as exc:
            if attempt == MAX_REPORT_ATTEMPTS:
                raise
            correction = (
                f"Rewrite only this section as valid JSON. The available source IDs are {json.dumps(available_ids)}. "
                "Every listed source may be cited where relevant; none is excluded by an instruction. "
                "Correct missing or unknown citations, finish the JSON, and answer the research question directly. "
                "Keep evidence-based detail and omit invented restrictions. "
            )
            if exc.code == "report_output_truncated":
                correction += "Keep this section shorter so the response completes."
            section_event(state, "retrying", section, attempt=attempt + 1, error_code=exc.code)


def reporter_node(state: ResearchState) -> dict:
    papers = state.get("processed_papers", [])
    entries = reference_entries(papers)
    if not papers or not any(clean_abstract(p.abstract) for p in papers):
        report = ResearchReport(research_question=state["research_question"],
            summary="The search identified no usable abstracts from which to develop an evidence-based answer. "
                    "The source records remain available for follow-up in Ranked Sources.",
            limitations=["Retrieve abstracts or full texts for the most relevant records before drawing conclusions about their findings."],
            sources=papers, cited_source_ids=[], ranked_sources=state.get("ranked_sources"))
    else:
        client = get_llm_client()
        context = evidence_context(papers)
        summary, findings, limitations, previous = [], [], [], []
        used = set()
        for descriptor in SECTIONS:
            value, ids = generate_section(client, state, papers, entries, context, descriptor, previous)
            used.update(ids)
            if descriptor[1] == "summary":
                summary.append(value)
                previous.append(value[:900])
            elif descriptor[1] == "findings":
                findings = value
            else:
                limitations = value
        report = ResearchReport(research_question=state["research_question"], summary="\n\n".join(summary),
            findings=findings, limitations=limitations, sources=papers,
            cited_source_ids=[entry["id"] for entry in entries if entry["id"] in used],
            ranked_sources=state.get("ranked_sources"))
    return {"final_report": report, "report_id": save_report(report)}
