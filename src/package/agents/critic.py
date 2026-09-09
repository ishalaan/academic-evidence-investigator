import json

from package.schemas import CriticDecision
from package.services.json_utils import clean_json_response
from package.services.llm import get_llm_client
from package.services.prompts import load_prompt
from package.workflow.state import ResearchState


def critic_node(state: ResearchState) -> dict:
    """
    Assess whether the retrieved evidence is sufficient for reporting.

    The Critic is separated from the Planner and Reporter so evidence quality is
    reviewed before synthesis. This provides an explicit reflection stage in the
    workflow rather than allowing the system to accept the first retrieved
    results automatically.

    The Critic can either approve the current evidence or recommend additional
    search queries. This supports autonomous replanning while keeping the final
    decision represented as structured state that LangGraph can route on.
    """

    research_question = state["research_question"]
    papers = state.get("processed_papers", [])

    # Keeping the Critic instructions in a separate prompt file makes the
    # evaluation criteria easier to review and revise without changing the
    # orchestration logic.
    critic_prompt = load_prompt("critic.txt")

    # Only structured metadata and abstracts are supplied to the Critic.
    # This keeps its judgement grounded in retrieved evidence and avoids giving
    # the model unrelated application state or database information.
    papers_payload = [
        {
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "doi": paper.doi,
            "year": paper.year,
            "source": paper.source,
        }
        for paper in papers
    ]

    # The exact JSON schema is included in the request because the Critic's
    # decision controls workflow routing. A predictable structure is therefore
    # more important than free-form explanatory prose.
    user_content = f"""
Research question:
{research_question}

Retrieved and processed papers:
{json.dumps(papers_payload, ensure_ascii=False)}

Return JSON only in this exact structure:

{{
  "sufficient": true,
  "reason": "string",
  "suggested_queries": ["string", "string"]
}}
""".strip()

    client = get_llm_client()

    response = client.chat_completion(
        messages=[
            {
                "role": "system",
                "content": critic_prompt,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        # A low temperature is used because the Critic should make relatively
        # stable evaluation decisions rather than generate highly variable
        # interpretations of the same evidence set.
        temperature=0.2,
        # Qwen3 may use part of the token budget for reasoning, so sufficient
        # capacity is reserved for both evaluation and final structured output.
        max_tokens=1200,
    )

    content = response.choices[0].message.content

    # An empty Critic decision would make the workflow's next route ambiguous,
    # so the system fails explicitly rather than silently assuming sufficiency.
    if not content:
        raise RuntimeError("Critic LLM returned an empty response.")

    cleaned_content = clean_json_response(content)
    decision_data = json.loads(cleaned_content)

    # Pydantic validation creates a deterministic boundary around the LLM's
    # probabilistic output before the decision is used for graph routing.
    decision = CriticDecision.model_validate(decision_data)

    return {
        "critic_decision": decision,
    }