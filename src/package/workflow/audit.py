"""Observe existing graph nodes without recording prompts or model traces."""

from functools import wraps
from time import perf_counter
import re

from package.storage.audit import create_run, record_event
from package.services.report_errors import failure_details


STAGE_MESSAGES = {
    "queued": "Waiting to start",
    "planner": "Planning search",
    "retrieval": "Retrieving academic sources",
    "processing": "Processing evidence",
    "critic": "Evaluating sufficiency",
    "replanning": "Replanning if needed",
    "reporter": "Generating report",
    "completed": "Investigation complete",
    "failed": "Investigation could not be completed. Please try again.",
}


def public_reason(reason):
    # The structured final reason is a short evidence assessment, never a trace.
    reason = re.sub(r"<think\b[^>]*>.*?(?:</think>|$)", "", reason, flags=re.I | re.S)
    return reason.strip()[:1500]


def observed_node(component, node, route=None):
    @wraps(node)
    def invoke(state):
        # Work on a copy so observation does not mutate the state handed to us
        # by the graph; the wrapper returns its additions with the node result.
        state = dict(state)
        run_id = state.setdefault("run_id", None) or create_run()
        state["run_id"] = run_id
        started = state.setdefault("run_started", perf_counter())
        metrics = dict(state.get("metrics", {}))
        for key in ("search_cycles", "queries_generated", "raw_papers_retrieved",
                    "valid_papers_retained", "relevant_papers_retained", "duplicates_removed",
                    "noisy_records_removed", "irrelevant_records_removed", "evidence_limit_removed",
                    "provider_failures", "final_evidence_count"):
            metrics.setdefault(key, 0)
        stage = "replanning" if component == "planner" and state.get("search_cycle", 0) else component
        record_event(run_id, component.title(), "started",
                     {"cycle": state.get("search_cycle", 0) + (component == "planner")},
                     stage=stage, metrics=metrics)
        node_started = perf_counter()
        try:
            result = node(state)
            details = {"duration_seconds": round(perf_counter() - node_started, 3),
                       "cycle": result.get("search_cycle", state.get("search_cycle", 0))}
            if component == "planner":
                metrics["search_cycles"] = result["search_cycle"]
                metrics["queries_generated"] += len(result["search_plan"].queries)
                details["queries_generated"] = len(result["search_plan"].queries)
            elif component == "retrieval":
                metrics["raw_papers_retrieved"] = len(result["raw_papers"])
                failures = result.get("provider_failures", [])
                policy = result.get("semantic_policy", {})
                metrics["semantic_scholar_requests"] = policy.get("requests", 0)
                metrics["semantic_scholar_disabled"] = policy.get("disabled", False)
                if policy.get("disabled") and not state.get("semantic_policy", {}).get("disabled"):
                    record_event(run_id, "Retrieval", "provider_paused",
                                 {"provider": "Semantic Scholar"}, stage=stage)
                metrics["provider_failures"] += len(failures)
                details.update(raw_papers_retrieved=len(result["raw_papers"]), provider_failures=failures)
                for failure in failures:
                    record_event(run_id, "Retrieval", "provider_failed", failure, stage=stage)
            elif component == "processing":
                # Processing re-examines the accumulated corpus: replace counts,
                # never add them again when the Critic requests another cycle.
                metrics.update(result.get("processing_metrics", {}))
                details.update(result.get("processing_metrics", {}))
            elif component == "critic":
                decision = result["critic_decision"]
                details.update(sufficient=decision.sufficient, reason=public_reason(decision.reason),
                               next_stage=route({**state, **result}))
                details["cycle_limit_reached"] = not decision.sufficient and details["next_stage"] == "reporter"
            elif component == "reporter":
                metrics["final_evidence_count"] = len(result["final_report"].sources)
                used = result["final_report"].cited_source_ids
                if used is not None:
                    metrics["sources_cited"] = len(used)
            metrics["elapsed_seconds"] = round(perf_counter() - started, 3)
            record_event(run_id, component.title(), "completed", details,
                         stage="completed" if component == "reporter" else stage,
                         status="completed" if component == "reporter" else "running",
                         metrics=metrics, report_id=result.get("report_id"))
            return {**result, "run_id": run_id, "run_started": started, "metrics": metrics}
        except Exception as exc:
            metrics["elapsed_seconds"] = round(perf_counter() - started, 3)
            record_event(run_id, component.title(), "failed", failure_details(exc),
                         stage="failed", status="failed", metrics=metrics)
            # Recording a failure must not turn it into a successful node result.
            raise
    return invoke
