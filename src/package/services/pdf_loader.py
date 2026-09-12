"""Bounded PDF download and page-aware extraction; no OCR or authentication."""
from urllib.parse import urljoin
from time import monotonic
from package.services.fulltext_resolver import http_client, public_https

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200


def download_pdf(url, directory, name):
    started = monotonic()
    target = directory / (name + ".pdf")
    if target.resolve().parent != directory.resolve():
        raise ValueError("Invalid PDF path")
    with http_client() as client:
        for _ in range(4):
            public_https(url)
            with client.stream("GET", url, headers={"Accept": "application/pdf"}) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                size = 0
                try:
                    with target.open("wb") as out:
                        for part in response.iter_bytes():
                            size += len(part)
                            if size > MAX_BYTES or monotonic() - started > 30:
                                raise ValueError("PDF exceeds download limit")
                            out.write(part)
                    with target.open("rb") as inp:
                        if not inp.read(1024).lstrip().startswith(b"%PDF-"):
                            raise ValueError("Resource is not a PDF")
                    return target
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
    raise ValueError("Too many redirects")


def extract_pages(path):
    import pymupdf
    with pymupdf.open(path) as document:
        if document.needs_pass or not document.is_pdf:
            raise ValueError("PDF is restricted or invalid")
        if len(document) > MAX_PAGES:
            raise ValueError("PDF exceeds page limit")
        pages = [(i + 1, page.get_text("text", sort=True).strip()) for i, page in enumerate(document)]
        if not any(len(text.split()) >= 10 for _, text in pages):
            raise ValueError("PDF contains no usable text")
        return [(number, text[:60000]) for number, text in pages if text.strip()]
