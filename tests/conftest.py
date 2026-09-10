import pytest

from package.storage import database


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Every test gets its own database; the user's saved reports stay untouched."""
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "academic_evidence.db")
    database.initialise_database()
