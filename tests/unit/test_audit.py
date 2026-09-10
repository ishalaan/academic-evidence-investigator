import sqlite3
from datetime import datetime

import pytest

from package.schemas import ResearchReport
from package.storage import database
from package.storage.audit import create_run, get_run, record_event


def test_audit_persists_events_and_links_earlier_events_to_final_report():
    run_id = create_run()
    record_event(run_id, "Planner", "started", {"cycle": 1}, stage="planner")
    report = ResearchReport(research_question="Question", summary="Summary")
    report_id = database.save_report(report)
    record_event(run_id, "Reporter", "completed", {}, stage="completed", status="completed",
                 report_id=report_id, metrics={"search_cycles": 1, "final_evidence_count": 0})
    # Read from a new connection, as a later request or application would.
    run = get_run(run_id)
    assert run["status"] == "completed"
    assert run["report_id"] == report_id
    assert run["metrics"]["search_cycles"] == 1
    assert [event["component"] for event in run["events"]] == ["Planner", "Reporter"]
    assert all(event["run_id"] == run_id and event["report_id"] == report_id for event in run["events"])
    assert datetime.fromisoformat(run["events"][0]["timestamp"]).tzinfo is not None
    assert database.load_report(report_id) == report


def test_schema_initialisation_preserves_existing_reports_and_is_idempotent():
    report_id = database.save_report(ResearchReport(research_question="Old", summary="Saved"))
    create_run()
    create_run()
    database.initialise_database()
    assert database.load_report(report_id).summary == "Saved"
    assert database.load_report(report_id + 1) is None


def test_unknown_run_does_not_create_orphan_event():
    assert get_run("missing") is None
    with pytest.raises(ValueError):
        record_event("missing", "Planner", "started", {}, stage="planner")
    with sqlite3.connect(database.DATABASE_PATH) as db:
        assert db.execute("SELECT COUNT(*) FROM investigation_events").fetchone()[0] == 0


def test_runs_are_isolated_and_sql_content_is_data():
    first, second = create_run(), create_run()
    reason = "Evidence is insufficient'; DROP TABLE reports; --"
    record_event(first, "Critic", "completed", {"reason": reason}, stage="critic")
    assert get_run(first)["events"][0]["details"]["reason"] == reason
    assert get_run(second)["events"] == []
