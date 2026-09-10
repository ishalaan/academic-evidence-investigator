from package.services.crossref import search_crossref


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "message": {
                "items": [
                    {
                        "title": ["Example Crossref Paper"],
                        "author": [
                            {
                                "given": "A.",
                                "family": "Author",
                            },
                            {
                                "given": "B.",
                                "family": "Author",
                            },
                        ],
                        "abstract": "Example abstract.",
                        "container-title": ["Journal of Education"],
                        "volume": "12",
                        "issue": "3",
                        "page": "20-30",
                        "DOI": "10.5678/example",
                        "URL": "https://example.com/crossref-paper",
                        "published-online": {
                            "date-parts": [[2024, 5, 1]]
                        },
                    }
                ]
            }
        }


def test_crossref_response_is_normalised(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "package.services.crossref.requests.get",
        fake_get,
    )

    result = search_crossref(
        "generative AI higher education",
        limit=1,
    )

    assert len(result) == 1

    paper = result[0]

    assert paper.title == "Example Crossref Paper"
    assert paper.authors == ["A. Author", "B. Author"]
    assert paper.abstract == "Example abstract."
    assert paper.year == 2024
    assert paper.doi == "10.5678/example"
    assert paper.source == "Crossref"
    assert paper.author_details[0].family == "Author"
    assert paper.journal == "Journal of Education"
    assert paper.volume == "12" and paper.issue == "3" and paper.pages == "20-30"
    assert paper.accessed_on is not None
