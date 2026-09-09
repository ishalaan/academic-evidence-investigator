from package.schemas import ResearchReport
from package.web import create_app


def test_home_page_loads():
    app = create_app()
    app.config["TESTING"] = True

    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Academic Evidence Investigator" in response.data
    assert b"Research Question" in response.data


def test_empty_research_question_shows_error():
    app = create_app()
    app.config["TESTING"] = True

    client = app.test_client()

    response = client.post(
        "/",
        data={
            "research_question": "   ",
        },
    )

    assert response.status_code == 200
    assert b"Please enter a research question." in response.data


def test_valid_research_question_returns_report(monkeypatch):
    class FakeWorkflow:
        def invoke(self, state):
            return {
                "final_report": ResearchReport(
                    research_question=state["research_question"],
                    summary="Test summary",
                    findings=["Test finding"],
                    limitations=["Test limitation"],
                    sources=[],
                ),
                "report_id": 1,
            }

    monkeypatch.setattr(
        "package.web.workflow",
        FakeWorkflow(),
    )

    app = create_app()
    app.config["TESTING"] = True

    client = app.test_client()

    response = client.post(
        "/",
        data={
            "research_question": "Does generative AI improve learning?",
        },
    )

    assert response.status_code == 200
    assert b"Test summary" in response.data
    assert b"Test finding" in response.data
    assert b"Test limitation" in response.data
    assert b"Saved report ID: 1" in response.data