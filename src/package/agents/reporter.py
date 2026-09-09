import json

from package.schemas import ResearchReport
from package.services.json_utils import clean_json_response
from package.services.llm import get_llm_client
from package.services.prompts import load_prompt
from package.storage.database import save_report
from package.workflow.state import ResearchState


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
    papers_payload = [
        {
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "doi": paper.doi,
            "url": paper.url,
            "year": paper.year,
            "source": paper.source,
        }
        for paper in papers
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

The sources field must contain the academic papers supplied above.
""".strip()

    client = get_llm_client()

    response = client.chat_completion(
        messages=[
            {
                "role": "system",
                "content": reporter_prompt,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        # A low temperature is used because the Reporter should favour factual
        # consistency and stable synthesis over creative variation.
        temperature=0.2,
        # Qwen3 may consume part of the output allowance during reasoning, so a
        # larger token budget is reserved for the final structured briefing.
        max_tokens=2000,
    )

    content = response.choices[0].message.content

    # An empty response cannot be safely rendered or persisted, so the workflow
    # fails explicitly rather than saving an incomplete research report.
    if not content:
        raise RuntimeError("Reporter LLM returned an empty response.")

    cleaned_content = clean_json_response(content)
    report_data = json.loads(cleaned_content)

    # Bibliographic metadata is deliberately overwritten with the retrieved
    # Paper objects instead of trusting the LLM-generated sources field.
    # This decision was introduced after testing showed that generative models
    # can invent or alter citation details such as publication years.
    report_data["sources"] = [
        paper.model_dump()
        for paper in papers
    ]

    # Pydantic validation creates a deterministic boundary between generated
    # narrative content and the application layer before anything is stored.
    report = ResearchReport.model_validate(report_data)

    # Persisting the validated report provides an execution record and allows
    # the browser interface to show a saved report identifier.
    report_id = save_report(report)

    return {
        "final_report": report,
        "report_id": report_id,
    }