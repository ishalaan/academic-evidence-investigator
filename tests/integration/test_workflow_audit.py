import pytest

from package.schemas import CriticDecision, Paper, ResearchReport, SearchPlan
from package.storage.audit import get_run
from package.storage.database import save_report
from package.workflow import graph


def configure_nodes(monkeypatch, *, sufficient_after=2):
    question = "Large language models in education"
    paper = Paper(title=question, abstract="Large language models support education and teaching.", doi="10.1/one")

    def planner(state):
        return {"search_plan": SearchPlan(research_goal=question, queries=["education"]),
                "search_cycle": state.get("search_cycle", 0) + 1}

    def critic(state):
        return {"critic_decision": CriticDecision(sufficient=state["search_cycle"] >= sufficient_after,
                reason="<think>PRIVATE TRACE</think>Coverage is limited.")}

    def reporter(state):
        report = ResearchReport(research_question=question, summary="Briefing", sources=state["processed_papers"])
        return {"final_report": report, "report_id": save_report(report)}

    def unavailable(*args, **kwargs):
        raise RuntimeError("SECRET token and provider response")

    # Control agent answers and provider failures but keep the real graph and
    # database, so routing and durable audit records are tested together.
    monkeypatch.setattr(graph, "planner_node", planner)
    monkeypatch.setattr(graph, "critic_node", critic)
    monkeypatch.setattr(graph, "reporter_node", reporter)
    monkeypatch.setattr("package.agents.retrieval.search_semantic_scholar", unavailable)
    monkeypatch.setattr("package.agents.retrieval.search_crossref", lambda *a, **k: [
        paper, paper.model_copy(), Paper(title="   "),
        Paper(title="Unrelated financial forecasting", abstract="Stock markets")])
    return question


def test_real_graph_replanning_metrics_critic_and_persistence(monkeypatch):
    question = configure_nodes(monkeypatch)
    result = graph.build_workflow().invoke({"research_question": question, "search_cycle": 0})
    run = get_run(result["run_id"])
    metrics = run["metrics"]
    assert metrics["search_cycles"] == metrics["queries_generated"] == 2
    assert metrics["raw_papers_retrieved"] == 8
    assert metrics["provider_failures"] == 2
    assert metrics["noisy_records_removed"] == 2
    assert metrics["valid_papers_retained"] == 6
    assert metrics["duplicates_removed"] == 4
    assert metrics["irrelevant_records_removed"] == 1
    assert metrics["relevant_papers_retained"] == metrics["final_evidence_count"] == 1
    assert metrics["elapsed_seconds"] >= 0
    assert metrics["raw_papers_retrieved"] == sum(metrics[key] for key in (
        "noisy_records_removed", "duplicates_removed", "irrelevant_records_removed",
        "evidence_limit_removed", "final_evidence_count"))
    decisions = [e["details"] for e in run["events"] if e["component"] == "Critic" and e["action"] == "completed"]
    assert [d["sufficient"] for d in decisions] == [False, True]
    assert [d["next_stage"] for d in decisions] == ["planner", "reporter"]
    assert all(d["reason"] == "Coverage is limited." for d in decisions)
    assert "PRIVATE TRACE" not in str(run)
    assert "SECRET" not in str(run)
    assert run["report_id"] == result["report_id"]
    assert run["status"] == "completed"
    assert {e["component"] for e in run["events"]} == {"Planner", "Retrieval", "Processing", "Critic", "Reporter"}


def test_cycle_limit_records_insufficient_decision_and_actual_route(monkeypatch):
    question = configure_nodes(monkeypatch, sufficient_after=99)
    result = graph.build_workflow().invoke({"research_question": question})
    run = get_run(result["run_id"])
    decisions = [e["details"] for e in run["events"] if e["component"] == "Critic" and e["action"] == "completed"]
    assert len(decisions) == graph.MAX_SEARCH_CYCLES
    assert decisions[-1]["sufficient"] is False
    assert decisions[-1]["cycle_limit_reached"] is True
    assert decisions[-1]["next_stage"] == "reporter"


def test_node_failure_is_persisted_without_exception_contents(monkeypatch):
    from package.storage.audit import create_run

    def broken(state):
        raise RuntimeError("SECRET prompt")

    monkeypatch.setattr(graph, "planner_node", broken)
    run_id = create_run()
    with pytest.raises(RuntimeError):
        graph.build_workflow().invoke({"research_question": "Q", "run_id": run_id})
    run = get_run(run_id)
    assert run["status"] == "failed"
    assert run["events"][-1]["action"] == "failed"
    assert "SECRET" not in str(run)
