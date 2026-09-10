import re
from datetime import date

from package.schemas import ResearchReport, Paper
from package.storage.audit import create_run, record_event
from package.storage.database import save_report
from package.web import create_app


def test_six_tabs_separate_content_and_references():
    report = ResearchReport(research_question="Education", summary="First paragraph (Smith, 2025).\n\nSecond paragraph.",
                            findings=["Distinct finding"], limitations=["Distinct limitation"],
                            sources=[Paper(title="Study <script>alert(1)</script>", authors=["Jane Smith"],
                                           year=2025, journal="Education Review", volume="2", issue="1",
                                           pages="5–9", url="https://example.org/paper", accessed_on=date(2026, 9, 10))])
    run_id = create_run()
    record_event(run_id, "Planner", "started", {"cycle": 1}, stage="planner")
    record_event(run_id, "Reporter", "completed", {}, stage="completed", status="completed", report_id=save_report(report))
    response = create_app().test_client().get(f"/runs/{run_id}/report")
    assert response.status_code == 200
    html = response.text
    labels = re.findall(r'role="tab"[^>]*>([^<]+)</button>', html)
    assert labels == ["Summary", "Findings", "Limitations", "Sources", "Investigation and Audit", "Activity Log"]
    panels = dict(re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>', html, re.S))
    assert len(panels) == 6
    assert "Distinct finding" in panels["findings-panel"]
    assert "Distinct limitation" in panels["limitations-panel"]
    assert "Distinct finding" not in panels["summary-panel"]
    assert "<p>Second paragraph.</p>" in panels["summary-panel"]
    assert "Smith, J. (2025)" in panels["sources-panel"]
    assert "<em>Education Review</em>" in panels["sources-panel"]
    assert "2(1), pp. 5–9" in panels["sources-panel"]
    assert "Available at:" in panels["sources-panel"]
    assert "(Accessed: 10 September 2026)" in panels["sources-panel"]
    assert "<script>alert(1)</script>" not in html
    assert "Planning search" in panels["activity-panel"]
    assert "Run metrics" in panels["audit-panel"]


def test_older_report_does_not_get_fabricated_access_date():
    report = ResearchReport(research_question="Old question", summary="Original answer",
                            sources=[Paper(title="Old study", url="https://example.org/old")])
    run_id = create_run()
    record_event(run_id, "Reporter", "completed", {}, stage="completed", status="completed", report_id=save_report(report))
    response = create_app().test_client().get(f"/runs/{run_id}/report")
    assert response.status_code == 200
    assert "Access date not recorded" in response.text
    assert "Original answer" in response.text
