import pytest

from package.storage import database


@pytest.fixture(autouse=True)
def no_live_html_in_workflow_tests(monkeypatch):
    """Workflow tests use explicit HTML fixtures; live verification is separate."""
    def unavailable(*args, **kwargs):
        raise ValueError('No HTML fixture supplied')
    monkeypatch.setattr('package.rag.pipeline.load_html_article', unavailable)
    monkeypatch.setattr('package.rag.pipeline.enrich_writing_sources', lambda items:[(i.paper,'not_applicable') for i in items])


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Every test gets its own database; the user's saved reports stay untouched."""
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "academic_evidence.db")
    database.initialise_database()
