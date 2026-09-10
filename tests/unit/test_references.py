from datetime import date

import pytest

from package.schemas import Paper, ResearchReport
from package.services.references import author_label, cited_text, reference_entries, source_url
from package.storage.database import save_report, load_report


def test_journal_reference_and_harvard_citation():
    paper = Paper(title="Learning with AI", authors=["Jane Smith", "Joe van der Meer"],
                  author_details=[{"given": "Jane", "family": "Smith"},
                                  {"given": "Joe", "family": "van der Meer"}],
                  year=2025, journal="Journal of Education", volume="12", issue="3",
                  pages="20–30", doi="10.1234/education", accessed_on=date(2026, 9, 10))
    entry = reference_entries([paper])[0]
    assert entry["citation"] == "(Smith and van der Meer, 2025)"
    assert entry["opening"] == "Smith, J. and van der Meer, J. (2025) ‘Learning with AI’"
    assert entry["publication"] == "12(3), pp. 20–30"
    assert entry["url"] == "https://doi.org/10.1234/education"
    assert entry["access_date"] == "10 September 2026"
    assert cited_text("Reported benefits [S1].", [entry], require_citation=True) == "Reported benefits (Smith and van der Meer, 2025)."


@pytest.mark.parametrize("names, expected", [
    (["Smith, Jane"], "Smith"),
    (["Jane Smith", "Joe Jones", "Amy Green"], "Smith, Jones and Green"),
    (["Jane Smith", "Joe Jones", "Amy Green", "Sue White"], "Smith et al."),
])
def test_author_counts(names, expected):
    assert author_label(Paper(title="Study", authors=names)) == expected


def test_missing_metadata_and_unsafe_links_are_not_invented():
    paper = Paper(title="Unnamed study", url="javascript:alert(1)")
    entry = reference_entries([paper])[0]
    assert entry["citation"] == "(Unnamed study, no date)"
    assert entry["opening"] == "‘Unnamed study’ (no date)"
    assert entry["publication"] == ""
    assert entry["access_date"] is None
    assert entry["url"] is None


def test_same_author_year_suffixes_match_reference_order():
    papers = [Paper(title="Zebra", authors=["Jane Smith"], year=2025),
              Paper(title="Apple", authors=["Jane Smith"], year=2025)]
    entries = reference_entries(papers)
    assert [e["citation"] for e in entries] == ["(Smith, 2025b)", "(Smith, 2025a)"]
    assert cited_text("A comparison [S1] [S2].", entries) == "A comparison (Smith, 2025b; Smith, 2025a)."
    assert "2025b" in entries[0]["opening"]


@pytest.mark.parametrize("text", ["Invented [S99].", "Unsupported claim.",
                                      "Claim [S1].\n\nUncited paragraph.",
                                      "Claim [S1, S2].", "Claim (Imaginary, 2025) [S1]."])
def test_invalid_or_missing_citations_rejected(text):
    with pytest.raises(ValueError):
        cited_text(text, reference_entries([Paper(title="Study")]), require_citation=True)


def test_access_dates_and_extra_metadata_survive_database_round_trip():
    report = ResearchReport(research_question="Q", summary="Answer (Smith, 2025).",
                            sources=[Paper(title="Study", authors=["Jane Smith"], year=2025,
                                           journal="Journal", pages="5", accessed_on=date(2024, 1, 2))])
    loaded = load_report(save_report(report))
    assert loaded == report
    assert reference_entries(loaded.sources)[0]["access_date"] == "2 January 2024"


def test_doi_url_normalisation_and_fallback():
    assert source_url(Paper(title="Study", doi="https://doi.org/10.1234/test")) == "https://doi.org/10.1234/test"
    assert source_url(Paper(title="Study", doi="bad", url="https://example.org/article")) == "https://example.org/article"
