import json

from package.schemas import SearchPlan
from package.services.json_utils import clean_json_response
from package.services.llm import get_llm_client
from package.services.prompts import load_prompt
from package.workflow.state import ResearchState


def planner_node(state: ResearchState) -> dict:
    """
    Build or revise the academic search plan using the configured LLM.

    The Planner is deliberately responsible only for interpreting the research
    goal and generating search queries. Retrieval is kept in a separate agent so
    that planning decisions remain distinct from external API behaviour.

    Critic feedback is incorporated on later cycles so the workflow can revise
    its search strategy rather than repeatedly issuing the same queries.
    Structured output is validated with Pydantic before it is written back to
    shared state, reducing the risk of malformed LLM responses disrupting later
    workflow nodes.
    """

    research_question = state["research_question"]
    current_cycle = state.get("search_cycle", 0)
    critic_decision = state.get("critic_decision")

    # Prompts are stored outside the Python module so agent instructions can be
    # revised independently from orchestration code and reviewed more easily.
    planner_prompt = load_prompt("planner.txt")

    # The Critic's previous reasoning and suggested queries are passed back to
    # the Planner to support a genuine feedback loop between search cycles.
    # This makes replanning responsive to evidence quality rather than relying
    # on a fixed sequence of searches.
    user_content = f"""
Research question:
{research_question}

Previous critic feedback:
{critic_decision.reason if critic_decision else "None"}

Previous suggested queries:
{critic_decision.suggested_queries if critic_decision else []}

Return JSON only in this exact structure:

{{
  "research_goal": "string",
  "queries": ["string", "string"]
}}
""".strip()

    client = get_llm_client()

    response = client.chat_completion(
        messages=[
            {
                "role": "system",
                "content": planner_prompt,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        # A low temperature is used because planning needs consistent,
        # reproducible query generation rather than highly creative output.
        temperature=0.2,
        # Qwen3 may consume part of the token budget on internal reasoning, so
        # the limit is intentionally large enough to leave room for final JSON.
        max_tokens=1200,
    )

    content = response.choices[0].message.content

    # Failing explicitly is preferable to passing an empty plan into the
    # workflow, where the resulting error would be harder to diagnose.
    if not content:
        raise RuntimeError("Planner LLM returned an empty response.")

    # LLMs sometimes wrap JSON in Markdown code fences. Cleaning the response
    # before parsing improves robustness while still requiring valid JSON.
    cleaned_content = clean_json_response(content)
    plan_data = json.loads(cleaned_content)

    # Pydantic validation provides a strict boundary between probabilistic LLM
    # output and the deterministic shared workflow state.
    plan = SearchPlan.model_validate(plan_data)

    return {
        "search_plan": plan,
        # Incrementing the cycle here makes the number of planning attempts
        # explicit in shared state and supports the workflow's maximum-cycle
        # safeguard against uncontrolled replanning loops.
        "search_cycle": current_cycle + 1,
    }