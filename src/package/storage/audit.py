"""Durable run snapshots and append-only workflow events."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from package.storage import database


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def connection():
    database.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(database.DATABASE_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS investigation_runs (
                id TEXT PRIMARY KEY, report_id INTEGER REFERENCES reports(id),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                status TEXT NOT NULL, stage TEXT NOT NULL, metrics TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS investigation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES investigation_runs(id),
                timestamp TEXT NOT NULL, component TEXT NOT NULL,
                action TEXT NOT NULL, details TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS events_by_run ON investigation_events(run_id, id)")
            yield db
    finally:
        db.close()


def create_run():
    run_id = uuid4().hex
    now = utc_now()
    with connection() as db:
        db.execute("INSERT INTO investigation_runs VALUES (?, NULL, ?, ?, ?, ?, ?)",
                   (run_id, now, now, "queued", "queued", "{}"))
    return run_id


def record_event(run_id, component, action, details, *, stage, status="running",
                 metrics=None, report_id=None):
    """Commit each event and its progress snapshot together, before polling."""
    now = utc_now()
    with connection() as db:
        cursor = db.execute("""UPDATE investigation_runs SET updated_at=?, stage=?, status=?,
            metrics=COALESCE(?, metrics), report_id=COALESCE(?, report_id) WHERE id=?""",
            (now, stage, status, json.dumps(metrics) if metrics is not None else None,
             report_id, run_id))
        if cursor.rowcount != 1:
            raise ValueError("Unknown investigation run.")
        db.execute("""INSERT INTO investigation_events
            (run_id, timestamp, component, action, details) VALUES (?, ?, ?, ?, ?)""",
            (run_id, now, component, action, json.dumps(details, ensure_ascii=False)))


def get_run(run_id, *, include_events=True):
    with connection() as db:
        row = db.execute("SELECT * FROM investigation_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        run = dict(row)
        run["metrics"] = json.loads(run["metrics"])
        if include_events:
            run["events"] = []
            for row in db.execute("SELECT * FROM investigation_events WHERE run_id=? ORDER BY id", (run_id,)):
                event = dict(row)
                event["details"] = json.loads(event["details"])
                event["report_id"] = run["report_id"]
                run["events"].append(event)
        return run
