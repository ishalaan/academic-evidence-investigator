import sqlite3

from package.processing.pipeline import process_papers
from package.processing.deduplication import deduplicate_papers
from package.schemas import Paper, ResearchReport
from package.storage import database


def test_ranking_retains_below_threshold_sources_and_more_than_ten():
    papers = [Paper(title=f"Large language models in education study {i}",
                    abstract="Educational tutoring and teaching.", doi=f"10.1234/{i}") for i in range(12)]
    papers += [Paper(title="Ocean currents", abstract="Marine ecosystems"), Paper(title="   ")]
    ranked = []
    retained = process_papers(papers, "Large language models in education", ranked_sources=ranked)
    assert len(retained) == 10 and len(ranked) == 13
    assert [item.relevance_score for item in ranked] == sorted([item.relevance_score for item in ranked], reverse=True)
    assert ranked[-1].paper.title == "Ocean currents" and not ranked[-1].eligible
    for item in ranked:
        if item.selected:
            assert retained[int(item.source_id[1:]) - 1] == item.paper


def test_exact_doi_keeps_abstract_from_second_provider_without_mutation():
    first = Paper(title="Study", doi="10.1234/paper", journal="Original journal")
    second = Paper(title="Study", doi="10.1234/paper", abstract="Useful evidence.", journal="Other journal")
    merged = deduplicate_papers([first, second])[0]
    assert merged.abstract == "Useful evidence."
    assert merged.journal == "Original journal"
    assert first.abstract is None


def test_report_ranking_and_cited_ids_persist_and_legacy_rows_load():
    ranked = []
    papers = process_papers([Paper(title="LLMs in education", abstract="Educational tutoring")],
                             "LLMs in education", ranked_sources=ranked)
    report = ResearchReport(research_question="Q", summary="Answer", sources=papers,
                            ranked_sources=ranked, cited_source_ids=["S1"])
    assert database.load_report(database.save_report(report)) == report
    with sqlite3.connect(database.DATABASE_PATH) as db:
        cursor = db.execute("INSERT INTO reports (research_question, summary, findings, limitations, sources) VALUES (?, ?, ?, ?, ?)",
                            ("Legacy", "Old answer", '{"findings": []}', '{"limitations": []}', '{"sources": []}'))
        legacy_id = cursor.lastrowid
    database.initialise_database()
    old = database.load_report(legacy_id)
    assert old.summary == "Old answer" and old.ranked_sources is None and old.cited_source_ids is None


def test_existing_database_schema_is_upgraded_without_losing_reports(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setattr(database, "DATABASE_PATH", legacy_path)
    with sqlite3.connect(legacy_path) as db:
        db.execute("CREATE TABLE reports (id INTEGER PRIMARY KEY, research_question TEXT, summary TEXT, findings TEXT, limitations TEXT, sources TEXT, created_at TEXT)")
        db.execute("INSERT INTO reports VALUES (1, 'Question', 'Saved answer', ?, ?, ?, '2026-01-01')",
                   ('{"findings": []}', '{"limitations": []}', '{"sources": []}'))
    database.initialise_database()
    database.initialise_database()
    assert database.load_report(1).summary == "Saved answer"
    report_id = database.save_report(ResearchReport(research_question="New", summary="New answer", cited_source_ids=[]))
    assert report_id > 1 and database.load_report(report_id).cited_source_ids == []
