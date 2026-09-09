from package.schemas import ResearchReport
from package.storage.database import initialise_database, save_report


def test_report_can_be_saved():
    initialise_database()

    report = ResearchReport(
        research_question="Test research question",
        summary="Test summary",
        findings=["Finding one"],
        limitations=["Limitation one"],
        sources=[],
    )

    report_id = save_report(report)

    assert isinstance(report_id, int)
    assert report_id > 0