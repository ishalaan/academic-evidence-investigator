from langgraph.graph import END, START, StateGraph

from package.agents.critic import critic_node
from package.agents.planner import planner_node
from package.agents.reporter import reporter_node
from package.agents.retrieval import retrieval_node
from package.config import MAX_SEARCH_CYCLES
from package.workflow.nodes import processing_node
from package.workflow.state import ResearchState
from package.workflow.audit import observed_node


def route_after_critic(state: ResearchState) -> str:
    """
    Decide whether to re-plan or continue to reporting.

    The Critic's decision is used as a control signal for the workflow rather
    than merely as descriptive output. This allows the system to behave
    autonomously by revising its search strategy when evidence is judged
    insufficient.

    Replanning is deliberately capped so the agent cannot enter an uncontrolled
    loop when external retrieval remains weak or unavailable.
    """

    decision = state["critic_decision"]
    search_cycle = state.get("search_cycle", 0)

    # If the Critic judges the current evidence sufficient, further searching
    # would add latency and potentially introduce weaker or redundant material,
    # so the workflow proceeds directly to reporting.
    if decision.sufficient:
        return "reporter"

    # A hard cycle limit provides a deterministic safety boundary around the
    # otherwise autonomous feedback loop. Without this safeguard, repeated
    # Critic rejection could cause indefinite replanning.
    if search_cycle >= MAX_SEARCH_CYCLES:
        return "reporter"

    # Insufficient evidence within the permitted cycle limit is routed back to
    # the Planner so Critic feedback can influence a revised search strategy.
    return "planner"


def build_workflow():
    """
    Construct and compile the LangGraph research workflow.

    LangGraph is used because the system requires explicit shared state,
    conditional routing, and a feedback loop between Critic and Planner.
    These behaviours would be less transparent in a simple linear pipeline.
    """

    graph = StateGraph(ResearchState)

    # Each responsibility is represented as a separate node so planning,
    # retrieval, deterministic processing, evaluation and reporting can be
    # tested independently while still cooperating through shared state.
    graph.add_node("planner", observed_node("planner", planner_node))
    graph.add_node("retrieval", observed_node("retrieval", retrieval_node))
    graph.add_node("processing", observed_node("processing", processing_node))
    graph.add_node("critic", observed_node("critic", critic_node, route_after_critic))
    graph.add_node("reporter", observed_node("reporter", reporter_node))

    # The normal execution path follows the evidence-investigation lifecycle:
    # interpret the goal, retrieve evidence, process it, then evaluate quality.
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "retrieval")
    graph.add_edge("retrieval", "processing")
    graph.add_edge("processing", "critic")

    # Conditional routing is the key autonomous control point. The Critic can
    # either approve the evidence for reporting or send the workflow back to
    # the Planner for another search cycle.
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "planner": "planner",
            "reporter": "reporter",
        },
    )

    # Reporting is the terminal stage because the final validated report has
    # already been persisted by the Reporter node before execution ends.
    graph.add_edge("reporter", END)

    return graph.compile()


# Compiling once at module load avoids rebuilding the graph for every web
# request while keeping the workflow reusable by both the Flask application
# and direct integration tests.
workflow = build_workflow()
