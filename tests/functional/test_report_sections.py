import re
from datetime import date

from package.schemas import ResearchReport, Paper
from package.storage.audit import create_run, record_event
from package.storage.database import save_report
from package.web import create_app
from package.processing.pipeline import process_papers


def test_three_tabs_combine_overview_and_preserve_cited_references():
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
    assert labels == ["Overview", "Ranked Sources", "Agent Activity"]
    panels = dict(re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>', html, re.S))
    assert len(panels) == 3
    overview = panels["overview-panel"]
    assert "Distinct finding" in overview
    assert "Distinct limitation" in overview
    assert "<p>Second paragraph.</p>" in overview
    assert "Smith, J. (2025)" in overview
    assert "<em>Education Review</em>" in overview
    assert "2(1), pp. 5–9" in overview
    assert "Available at:" in overview
    assert "(Accessed: 10 September 2026)" in overview
    assert "<script>alert(1)</script>" not in html
    assert "Planning search" in panels["activity-panel"]
    assert "Investigation metrics" in panels["activity-panel"]


def test_older_report_does_not_get_fabricated_access_date():
    report = ResearchReport(research_question="Old question", summary="Original answer (Old study, no date).",
                            sources=[Paper(title="Old study", url="https://example.org/old")])
    run_id = create_run()
    record_event(run_id, "Reporter", "completed", {}, stage="completed", status="completed", report_id=save_report(report))
    response = create_app().test_client().get(f"/runs/{run_id}/report")
    assert response.status_code == 200
    assert "Access date not recorded" in response.text
    assert "Original answer" in response.text


def test_ranked_sources_show_all_records_but_references_show_only_cited_sources():
    ranked = []
    sources = process_papers([
        Paper(title="Large language models in education", abstract="Educational tutoring and feedback.",
              authors=["Jane Smith"], year=2025),
        Paper(title="Education", abstract="Educational feedback.", authors=["Joe Jones"], year=2024),
        Paper(title="Ocean currents", abstract="Marine ecosystems")],
        "Large language models in education", ranked_sources=ranked)
    report = ResearchReport(research_question="Q", summary="Tutoring is supported (Smith, 2025).",
        sources=sources, cited_source_ids=["S1"], ranked_sources=ranked)
    run_id = create_run()
    record_event(run_id, "Reporter", "completed", {}, stage="completed", status="completed", report_id=save_report(report))
    html = create_app().test_client().get(f"/runs/{run_id}/report").text
    panels = dict(re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>', html, re.S))
    overview, ranking = panels["overview-panel"], panels["ranked-panel"]
    assert "Jones" not in overview and "Ocean currents" not in overview
    assert "Smith, J." in overview
    assert ranking.index("Large language models in education") < ranking.index("Ocean currents")
    assert "Below the relevance filter" in ranking
    assert "Available to Reporter; not cited" in ranking
    assert "Cited in Overview" in ranking
