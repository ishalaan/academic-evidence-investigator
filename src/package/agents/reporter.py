"""Compose a developed report in bounded sections over one shared evidence set."""

import html
import json
import re
import time
from difflib import SequenceMatcher

import httpx
from pydantic import ValidationError

from package.services.presentation import british_prose
from package.schemas import ResearchReport
from package.rag.context import evidence_payload
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
    ("summary", "summary", "Write ONE coherent summary of approximately 450–650 words in 4–6 paragraphs. Plan the entire answer before writing: open with a direct answer, group related evidence into distinct themes, compare studies within those themes, then conclude with practical implications. Each paragraph must add a new point; explain each application once, merging sources that support it. Do not restart the introduction or repeat the catalogue of applications. Use fewer words if the evidence is thin. Findings will provide the study-level detail separately.", 0),
    ("findings", "findings", "Aim for 5–8 distinct, developed findings, each 70–110 words, but use fewer when the abstracts support fewer distinct findings. Explain what the evidence says, how it works or why it matters, and supporting examples. Use different sources where relevant. Do not repeat the same claim as separate findings.", 300),
    ("limitations", "limitations", "Write 3–5 proportionate limitations, each 35–60 words. State what a limitation affects and what further evidence would help. A missing abstract in one record does not invalidate other sources. Avoid repeating the same caveat.", 100),
)


def has_repeated_passages(text):
    """Catch substantial near-identical sentences, not merely shared topic words."""
    plain = re.sub(r"\[S[^\]]*\]|\([^)]*(?:\d{4}|no date)[^)]*\)", "", text)
    sentences = [" ".join(re.findall(r"\w+", sentence.lower()))
                 for sentence in re.split(r"[.!?]+(?:\s+|$)|\n\n", plain)]
    substantive = [sentence for sentence in sentences if len(sentence.split()) >= 12]
    return any(SequenceMatcher(None, sentence, earlier, autojunk=False).ratio() >= 0.9
               for index, sentence in enumerate(substantive) for earlier in substantive[:index])


def parse_section(content, field):
    """Accept lossless formatting variations without repairing incomplete JSON."""
    cleaned = clean_json_response(content)
    decoder = json.JSONDecoder(strict=False)
    try:
        data = decoder.decode(cleaned)
    except ValueError:
        # Some models introduce the JSON with a sentence or a Markdown label.
        start = cleaned.find("{")
        if start < 0:
            raise ValueError("Return a complete JSON object, not plain prose.") from None
        try:
            data, end = decoder.raw_decode(cleaned, start)
        except ValueError:
            raise ValueError("Return complete JSON with escaped quotes and closed brackets.") from None
        if cleaned[end:].strip() not in ("", "```"):
            raise ValueError("Return one JSON object without trailing commentary.")
    if not isinstance(data, dict) or field not in data:
        raise ValueError(f"Return a JSON object containing the exact key '{field}'.")
    value = data[field]
    if field == "summary" and isinstance(value, list) and value and all(isinstance(v, str) and v.strip() for v in value):
        value = "\n\n".join(value)
    if field == "summary":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("The summary must be a non-empty string of paragraphs.")
    elif not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValueError(f"The {field} must be a non-empty array of strings.")
    return value


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
    except ValueError as exc:
        reasons = {
            "Reporter must use source IDs instead of author-year citations.": "author_year_format",
            "Reporter cited an unknown source identifier.": "unknown_source",
            "Reporter omitted a supporting source citation.": "missing_citation",
            "Reporter returned an invalid source citation.": "invalid_syntax",
        }
        error = ReportGenerationError("report_citations_invalid")
        error.validation_reason = reasons.get(str(exc), "invalid_syntax")
        raise error from None
    report.cited_source_ids = [entry["id"] for entry in entries if entry["id"] in used]
    return report


def section_event(state, action, section, **details):
    if state.get("run_id"):
        record_event(state["run_id"], "Reporter", action,
                     {"section": section, **details}, stage="reporter")


def request_section(client, messages, state, section):
    """Transport retries do not consume the section's content-correction budget."""
    for connection_attempt in range(1, 4):
        try:
            return client.chat_completion(messages=messages, temperature=0.2,
                max_tokens=MAX_SECTION_TOKENS,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        except httpx.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            transient = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)) or status in (429, 500, 502, 503, 504)
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                transient = False
            if transient and connection_attempt < 3:
                section_event(state, "retrying", section, attempt=connection_attempt + 1,
                              error_code="report_model_unavailable")
                time.sleep(2 ** connection_attempt)
                continue
            raise ReportGenerationError("report_model_unavailable") from None


def generate_section(client, state, papers, entries, context, descriptor, previous):
    section, field, instruction, minimum_words = descriptor
    available_ids = [entry["id"] for entry in entries]
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
    format_hint = "Return a complete JSON object with the requested section key."
    section_event(state, "section_started", section)
    for attempt in range(1, MAX_REPORT_ATTEMPTS + 1):
        messages = base + ([{"role": "user", "content": correction}] if correction else [])
        response = request_section(client, messages, state, section)
        try:
            if not response.choices or not response.choices[0].message.content:
                raise ReportGenerationError("report_format_invalid")
            if getattr(response.choices[0], "finish_reason", None) == "length":
                raise ReportGenerationError("report_output_truncated")
            try:
                value = parse_section(response.choices[0].message.content, field)
                body = ({"summary": value} if field == "summary" else
                        {"summary": f"Evidence overview [{available_ids[0]}].", field: value})
            except ValueError as format_error:
                format_hint = str(format_error)
                raise ReportGenerationError("report_format_invalid") from None
            validated = validate_report_content(json.dumps(body), papers, entries, state["research_question"])
            raw_text = value if isinstance(value, str) else "\n\n".join(value)
            if has_repeated_passages(raw_text) or (field == "findings" and has_repeated_passages("\n\n".join(previous + [raw_text]))):
                raise ReportGenerationError("report_repetition")
            ids = used_source_ids(raw_text, entries)
            word_count = len(raw_text.split())
            # Accept valid grounded sections regardless of length or number of sources.
            # Cosmetic expansion must not consume credits or replace usable content.
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
            if exc.code == "report_citations_invalid":
                correction += {
                    "missing_citation": " Every non-empty summary paragraph and every finding must contain a supporting [Snumber] token. Remove unsupported claims; do not invent a citation.",
                    "unknown_source": " A cited source ID was not in the supplied list. Use only an existing ID whose abstract supports the claim; remove unsupported claims.",
                    "author_year_format": " Use bracketed source IDs, not author-year citations. The application adds author names and years.",
                    "invalid_syntax": " Write citation tokens exactly as [S1] or [S2], choosing actual supplied IDs.",
                }.get(getattr(exc, "validation_reason", ""), "")
            if exc.code == "report_format_invalid":
                correction += format_hint
            if exc.code == "report_repetition":
                correction += "Repeated passages were detected. Write a fresh coherent section: explain each point once, merging its supporting citations, and give every paragraph a distinct purpose."
            if exc.code == "report_output_truncated":
                correction += "Keep this section shorter so the response completes."
            section_event(state, "retrying", section, attempt=attempt + 1, error_code=exc.code,
                          validation_reason=getattr(exc, "validation_reason", None))


def reporter_node(state: ResearchState) -> dict:
    papers = state.get("processed_papers", [])
    entries = reference_entries(papers)
    if not papers or not (state.get("evidence_chunks") or any(clean_abstract(p.abstract) for p in papers)):
        report = ResearchReport(research_question=state["research_question"],
            summary="The search identified no usable abstracts from which to develop an evidence-based answer. "
                    "The source records remain available for follow-up in Ranked Sources.",
            limitations=["Retrieve abstracts or full texts for the most relevant records before drawing conclusions about their findings."],
            sources=papers, cited_source_ids=[], ranked_sources=state.get("ranked_sources"))
    else:
        client = get_llm_client()
        context = evidence_payload(state["evidence_chunks"]) if "evidence_chunks" in state else evidence_context(papers)
        summary, findings, limitations, previous = "", [], [], []
        used = set()
        for descriptor in SECTIONS:
            value, ids = generate_section(client, state, papers, entries, context, descriptor, previous)
            used.update(ids)
            if descriptor[1] == "summary":
                summary = value
                previous.append(value[:900])
            elif descriptor[1] == "findings":
                findings = value
            else:
                limitations = value
        report = ResearchReport(research_question=state["research_question"], summary=summary,
            findings=findings, limitations=limitations, sources=papers,
            cited_source_ids=[entry["id"] for entry in entries if entry["id"] in used],
            ranked_sources=state.get("ranked_sources"))
    report.summary = british_prose(report.summary)
    report.findings = [british_prose(text) for text in report.findings]
    report.limitations = [british_prose(text) for text in report.limitations]
    report.evidence_provenance = [c.model_dump(exclude={"text"}) for c in state.get("evidence_chunks", [])]
    report.evidence_coverage = state.get("evidence_coverage", {})
    return {"final_report": report, "report_id": save_report(report)}
