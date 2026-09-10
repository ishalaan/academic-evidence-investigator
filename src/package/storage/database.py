import sqlite3
import json

from package.config import PROJECT_ROOT
from package.schemas import ResearchReport


DATABASE_PATH = PROJECT_ROOT / "data" / "academic_evidence.db"


def initialise_database() -> None:
    """
    Create the SQLite database and required tables if they do not already exist.

    SQLite is appropriate for this prototype because it provides persistent
    storage without requiring a separate database server or deployment service.
    This keeps the application easy to reproduce locally while still
    demonstrating that generated reports are saved beyond the current request.

    A larger multi-user deployment could replace this layer with PostgreSQL or
    another managed database without changing the higher-level agent workflow.
    """

    # The data directory is created automatically so a fresh clone can initialise
    # itself without requiring manual folder preparation.
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        # IF NOT EXISTS makes initialisation idempotent, allowing the application
        # to start repeatedly without recreating or destroying existing data.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                research_question TEXT NOT NULL,
                summary TEXT NOT NULL,
                findings TEXT NOT NULL,
                limitations TEXT NOT NULL,
                sources TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.commit()

    finally:
        # Explicitly closing the connection avoids leaving database resources
        # open between application runs or automated tests.
        connection.close()


def save_report(report: ResearchReport) -> int:
    """
    Save a completed research report and return its database ID.

    Only a validated ResearchReport reaches this function, which keeps the
    persistence layer deterministic and prevents partially structured LLM
    output from being written directly to the database.
    """

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        # Parameterised SQL is used instead of string interpolation so report
        # content is stored safely and cannot alter the SQL statement itself.
        cursor = connection.execute(
            """
            INSERT INTO reports (
                research_question,
                summary,
                findings,
                limitations,
                sources
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                report.research_question,
                report.summary,
                # Lists and nested source objects are serialised as JSON because
                # SQLite does not provide a native structured-list type. This
                # preserves the complete report while keeping the schema simple.
                report.model_dump_json(include={"findings"}),
                report.model_dump_json(include={"limitations"}),
                report.model_dump_json(include={"sources"}),
            ),
        )

        connection.commit()

        # Returning the generated identifier provides evidence that persistence
        # succeeded and allows the Flask interface to display the saved report ID.
        report_id = cursor.lastrowid

        if report_id is None:
            # Failing explicitly is safer than pretending persistence succeeded
            # when SQLite does not return an identifier.
            raise RuntimeError("The database did not return a report ID.")

        return report_id

    finally:
        connection.close()


def load_report(report_id: int) -> ResearchReport | None:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None:
            return None
        return ResearchReport(
            research_question=row["research_question"], summary=row["summary"],
            findings=json.loads(row["findings"])["findings"],
            limitations=json.loads(row["limitations"])["limitations"],
            sources=json.loads(row["sources"])["sources"],
        )
    finally:
        connection.close()
