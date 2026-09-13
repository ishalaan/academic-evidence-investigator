"""Bounded OA PDF retrieval and page-aware extraction; no browser challenges or OCR."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from time import monotonic
import httpx
from package.services.source_locations import stable_url
from package.services.fulltext_resolver import http_client, public_https

MAX_BYTES = 20 * 1024 * 1024
MAX_HTML_BYTES = 512 * 1024
MAX_PAGES = 200
MAX_SECONDS = 30
MAX_REQUESTS = 8


class PdfFailure(ValueError):
    """A safe category, not a remote response body or exception message."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class _PdfMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'meta' and (values.get('name') or '').lower() == 'citation_pdf_url':
            if values.get('content'):
                self.urls.append(values['content'].strip())


def _https_target(url):
    # A DOI may advertise HTTP. Try HTTPS only; never send an HTTP request.
    parsed = urlsplit(url)
    if parsed.scheme == 'http' and not parsed.username and not parsed.password and parsed.port in (None, 80):
        url = urlunsplit(('https', parsed.hostname or '', parsed.path, parsed.query, parsed.fragment))
    public_https(url)
    return url


def failure_details(exc, phase):
    """Only categorised fields may enter the audit log, never remote bodies."""
    details = {'failure_stage': phase}
    if isinstance(exc, PdfFailure):
        reason = exc.reason
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        details['http_status'] = status
        reason = {401: 'access_denied', 403: 'access_denied', 404: 'not_found', 429: 'rate_limited'}.get(status, 'http_error')
    elif isinstance(exc, httpx.TimeoutException):
        reason = 'timeout'
    elif isinstance(exc, httpx.TransportError):
        reason = 'network_error'
    elif phase == 'extraction':
        reason = 'invalid_pdf'
    elif isinstance(exc, ValueError):
        reason = 'unsafe_url'
    else:
        reason = 'access_error'
    details['reason'] = reason
    return details


def download_pdf(url, directory, name, metadata=None):
    """Return a temporary Path; optionally expose the actual PDF URL for provenance."""
    started = monotonic()
    target = directory / (name + '.pdf')
    if target.resolve().parent != directory.resolve():
        raise ValueError('Invalid PDF path')
    html_used, retries = False, 0
    try:
        with http_client() as client:
            for _ in range(MAX_REQUESTS):
                remaining = MAX_SECONDS - (monotonic() - started)
                if remaining <= 0:
                    raise PdfFailure('download_time_limit')
                url = _https_target(url)
                try:
                    with client.stream('GET', url, headers={'Accept': 'application/pdf, text/html;q=0.8'},
                                       timeout=min(10, remaining)) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get('location')
                            if not location:
                                raise PdfFailure('invalid_redirect')
                            url = urljoin(url, location)
                            continue
                        if response.status_code in (502, 503, 504) and retries < 1 and 'retry-after' not in response.headers:
                            retries += 1
                            continue
                        response.raise_for_status()
                        size, body, is_pdf = 0, bytearray(), None
                        with target.open('wb') as out:
                            for part in response.iter_bytes(chunk_size=65536):
                                size += len(part)
                                if monotonic() - started > MAX_SECONDS:
                                    raise PdfFailure('download_time_limit')
                                if is_pdf is None:
                                    is_pdf = part[:1024].lstrip().startswith(b'%PDF-')
                                if size > (MAX_BYTES if is_pdf else MAX_HTML_BYTES):
                                    raise PdfFailure('pdf_size_limit' if is_pdf else 'html_size_limit')
                                if is_pdf:
                                    out.write(part)
                                else:
                                    body.extend(part)
                        if is_pdf:
                            if metadata is not None:
                                metadata.update(source_url=stable_url(url), metadata_resolution=html_used)
                            return target
                        target.unlink(missing_ok=True)
                        if html_used:
                            raise PdfFailure('not_pdf')
                        parser = _PdfMetadata()
                        parser.feed(body.decode('utf-8', errors='replace'))
                        candidates = list(dict.fromkeys(parser.urls))
                        if len(candidates) != 1:
                            raise PdfFailure('no_pdf_metadata')
                        candidate = _https_target(urljoin(url, candidates[0]))
                        if urlsplit(candidate).hostname != urlsplit(url).hostname:
                            raise PdfFailure('cross_host_pdf_metadata')
                        url, html_used = candidate, True
                except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                    target.unlink(missing_ok=True)
                    if retries >= 1:
                        raise
                    retries += 1
            raise PdfFailure('redirect_limit')
    except Exception:
        target.unlink(missing_ok=True)
        raise


def extract_pages(path):
    import pymupdf
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise PdfFailure('password_required')
        if not document.is_pdf:
            raise PdfFailure('invalid_pdf')
        if len(document) > MAX_PAGES:
            raise PdfFailure('page_limit')
        pages = [(i + 1, page.get_text('text', sort=True).strip()) for i, page in enumerate(document)]
        if not any(len(text.split()) >= 10 for _, text in pages):
            raise PdfFailure('no_usable_text')
        return [(number, text[:60000]) for number, text in pages if text.strip()]
