from package.services.semantic_scholar import search_semantic_scholar


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "data": [
                {
                    "title": "Generative AI in Higher Education",
                    "authors": [
                        {"name": "Author One"},
                        {"name": "Author Two"},
                    ],
                    "abstract": "Example abstract about generative AI.",
                    "year": 2025,
                    "url": "https://example.com/paper",
                    "externalIds": {
                        "DOI": "10.1000/example",
                    },
                }
            ]
        }


def test_semantic_scholar_response_is_normalised(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "package.services.semantic_scholar.requests.get",
        fake_get,
    )

    monkeypatch.setattr(
        "package.services.semantic_scholar.time.sleep",
        lambda *args, **kwargs: None,
    )

    result = search_semantic_scholar(
        "generative AI higher education",
        limit=1,
    )

    assert len(result) == 1

    paper = result[0]

    assert paper.title == "Generative AI in Higher Education"
    assert paper.authors == ["Author One", "Author Two"]
    assert paper.abstract == "Example abstract about generative AI."
    assert paper.year == 2025
    assert paper.url == "https://example.com/paper"
    assert paper.doi == "10.1000/example"
    assert paper.source == "Semantic Scholar"