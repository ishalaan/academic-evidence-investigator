from package.config import MAX_SEARCH_CYCLES
from package.schemas import CriticDecision
from package.workflow.graph import route_after_critic


def test_routes_to_reporter_when_evidence_is_sufficient():
    state = {
        "critic_decision": CriticDecision(
            sufficient=True,
            reason="Evidence is sufficient.",
            suggested_queries=[],
        ),
        "search_cycle": 1,
    }

    result = route_after_critic(state)

    assert result == "reporter"


def test_routes_to_planner_when_evidence_is_insufficient():
    state = {
        "critic_decision": CriticDecision(
            sufficient=False,
            reason="More evidence is required.",
            suggested_queries=["additional search"],
        ),
        "search_cycle": 1,
    }

    result = route_after_critic(state)

    assert result == "planner"


def test_routes_to_reporter_when_max_cycles_reached():
    state = {
        "critic_decision": CriticDecision(
            sufficient=False,
            reason="Evidence is still insufficient.",
            suggested_queries=["additional search"],
        ),
        "search_cycle": MAX_SEARCH_CYCLES,
    }

    result = route_after_critic(state)

    assert result == "reporter"