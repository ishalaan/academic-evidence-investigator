from threading import Event

import pytest

from package.schemas import ResearchReport
from package.storage.audit import create_run, get_run, record_event
from package.storage.database import save_report
from package.web import create_app
from package.workflow.audit import STAGE_MESSAGES


@pytest.mark.parametrize("stage", STAGE_MESSAGES)
def test_status_returns_only_safe_stage_fields(stage):
    run_id = create_run()
    status = stage if stage in ("completed", "failed") else "running"
    record_event(run_id, "Critic", "completed", {"reason": "PRIVATE detail"},
                 stage=stage, status=status, metrics={"private": "hidden"})
    response = create_app().test_client().get(f"/runs/{run_id}/status")
    assert response.status_code == 200
    assert response.json["message"] == STAGE_MESSAGES[stage]
    assert set(response.json) == {"run_id", "stage", "status", "message", "report_url", "events"}
    assert "PRIVATE" not in response.text
    assert "private" not in response.text
    assert response.headers["Cache-Control"] == "no-store"


def test_start_returns_before_workflow_finishes_and_can_be_polled(monkeypatch):
    entered, release, finished = Event(), Event(), Event()

    class FakeWorkflow:
        def invoke(self, state):
            run_id = state["run_id"]
            record_event(run_id, "Planner", "started", {}, stage="planner")
            entered.set()
            try:
                assert release.wait(5)
                report_id = save_report(ResearchReport(research_question=state["research_question"], summary="Persisted briefing"))
                record_event(run_id, "Reporter", "completed", {}, stage="completed", status="completed", report_id=report_id)
            finally:
                finished.set()

    monkeypatch.setattr("package.web.workflow", FakeWorkflow())
    client = create_app().test_client()
    response = client.post("/runs", data={"research_question": "Education"})
    try:
        assert response.status_code == 202
        assert entered.wait(5)
        status_url = response.json["status_url"]
        assert client.get(status_url).json["message"] == "Planning search"
        assert not finished.is_set()
    finally:
        release.set()
        assert finished.wait(5)
    status = client.get(status_url).json
    assert status["status"] == "completed"
    report = client.get(status["report_url"])
    assert b"Persisted briefing" in report.data
    assert b"Investigation and Audit" in report.data


def test_report_tab_shows_persisted_critic_metrics_and_escapes_reason():
    run_id = create_run()
    report_id = save_report(ResearchReport(research_question="Education", summary="Briefing"))
    record_event(run_id, "Critic", "completed", {
        "sufficient": False, "reason": "Limited coverage <script>alert(1)</script>",
        "next_stage": "reporter", "cycle_limit_reached": True,
    }, stage="critic")
    record_event(run_id, "Reporter", "completed", {}, stage="completed", status="completed",
                 report_id=report_id, metrics={"search_cycles": 3, "final_evidence_count": 2})
    # A fresh application still reads the saved audit and report.
    response = create_app().test_client().get(f"/runs/{run_id}/report")
    assert response.status_code == 200
    assert b'role="tab" id="audit-tab"' in response.data
    assert b'role="tabpanel" aria-labelledby="audit-tab"' in response.data
    assert b"Insufficient evidence" in response.data
    assert b"search cycle limit reached" in response.data
    assert b"Search cycles" in response.data
    assert b"Limited coverage &lt;script&gt;" in response.data
    assert b"<script>alert(1)</script>" not in response.data
    assert run_id.encode() in response.data


def test_unknown_pending_and_invalid_requests():
    client = create_app().test_client()
    assert client.get("/runs/missing/status").status_code == 404
    assert client.get("/runs/missing/report").status_code == 404
    assert client.get(f"/runs/{create_run()}/report").status_code == 409
    assert client.post("/runs", data={}).status_code == 400
    assert client.post("/runs", data={"research_question": "   "}).status_code == 400


def test_background_failure_is_safe_and_durable(monkeypatch):
    # Execute the worker synchronously here to make failure assertions deterministic.
    class ImmediateThread:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    class BrokenWorkflow:
        def invoke(self, state):
            raise RuntimeError("SECRET provider credentials")

    monkeypatch.setattr("package.web.Thread", ImmediateThread)
    monkeypatch.setattr("package.web.workflow", BrokenWorkflow())
    client = create_app().test_client()
    for _ in range(3):  # A failed job must release its worker slot.
        response = client.post("/runs", data={"research_question": "Question"})
        assert response.status_code == 202
        status = client.get(response.json["status_url"])
        assert status.json["status"] == "failed"
        assert "SECRET" not in status.text
        assert "SECRET" not in str(get_run(response.json["run_id"]))
    response = client.post("/", data={"research_question": "Question"})
    assert response.status_code == 500
    assert b"SECRET" not in response.data


def test_loading_page_uses_stage_polling_and_accessible_status():
    response = create_app().test_client().get("/")
    assert b'aria-live="polite"' in response.data
    assert b'filename=' not in response.data
    assert b'/static/progress.js' in response.data


def test_worker_capacity_returns_actionable_error(monkeypatch):
    class PendingThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr("package.web.Thread", PendingThread)
    client = create_app().test_client()
    assert client.post("/runs", data={"research_question": "First"}).status_code == 202
    assert client.post("/runs", data={"research_question": "Second"}).status_code == 202
    response = client.post("/runs", data={"research_question": "Third"})
    assert response.status_code == 503
    assert "busy" in response.json["error"]


def test_activity_retains_short_stages_and_replanning_without_private_details():
    run_id = create_run()
    for component, action, details in [
        ("Planner", "started", {"cycle": 1}),
        ("Planner", "completed", {"cycle": 1, "prompt": "PRIVATE"}),
        ("Retrieval", "started", {"cycle": 1}),
        ("Retrieval", "provider_failed", {"provider": "Crossref", "message": "PRIVATE"}),
        ("Retrieval", "completed", {"cycle": 1}),
        ("Processing", "completed", {"cycle": 1}),
        ("Critic", "completed", {"cycle": 1, "next_stage": "planner", "reason": "PRIVATE"}),
        ("Planner", "started", {"cycle": 2}),
    ]:
        record_event(run_id, component, action, details, stage="replanning")
    client = create_app().test_client()
    first = client.get(f"/runs/{run_id}/status")
    events = first.json["events"]
    assert len(events) == 8
    assert events[-1]["message"] == "Replanning if needed"
    assert events[-1]["cycle"] == 2
    assert "Further searching requested" in events[-2]["message"]
    assert "Crossref was unavailable" in events[3]["message"]
    assert "PRIVATE" not in first.text
    assert events == client.get(f"/runs/{run_id}/status").json["events"]
    assert all(set(e) == {"id", "timestamp", "component", "action", "cycle", "message"} for e in events)
