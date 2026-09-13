import httpx
import pymupdf
import pytest
from package.services import pdf_loader as pdf


@pytest.fixture
def mock_http(monkeypatch):
    calls = []
    def install(handler):
        def handle(request):
            calls.append(str(request.url))
            return handler(request)
        monkeypatch.setattr(pdf, 'http_client', lambda: httpx.Client(transport=httpx.MockTransport(handle)))
        monkeypatch.setattr(pdf, 'public_https', lambda url: url)
        return calls
    return install


def test_doi_landing_metadata_resolves_pdf_with_final_provenance(tmp_path, mock_http):
    def handler(request):
        if request.url.host == 'doi.org':
            return httpx.Response(302, headers={'location': 'https://journal.test/article'})
        if request.url.path == '/article':
            return httpx.Response(200, text='<meta content="/download/1?a=1&amp;b=2" name="citation_pdf_url">')
        return httpx.Response(200, content=b'%PDF-1.7\nbody')
    calls = mock_http(handler)
    metadata = {}
    path = pdf.download_pdf('https://doi.org/10.1/a', tmp_path, 'paper', metadata)
    assert path.read_bytes().startswith(b'%PDF-')
    assert metadata == {'source_url': 'https://journal.test/download/1?a=1&b=2', 'metadata_resolution': True}
    assert len(calls) == 3


def test_http_redirect_is_upgraded_without_sending_http(tmp_path, mock_http):
    calls = mock_http(lambda r: httpx.Response(302, headers={'location':'http://journal.test:80/a.pdf'})
                      if r.url.host == 'doi.org' else httpx.Response(200, content=b'%PDF-1.7'))
    pdf.download_pdf('https://doi.org/10.1/a', tmp_path, 'paper')
    assert calls == ['https://doi.org/10.1/a', 'https://journal.test/a.pdf']


@pytest.mark.parametrize('body', [
    '<html>Client Challenge</html>',
    '<a href="/unrelated.pdf">Download</a>',
    '<meta name="citation_pdf_url" content="/a"><meta name="citation_pdf_url" content="/b">',
])
def test_no_guessing_links_or_challenge_bypass(tmp_path, mock_http, body):
    calls = mock_http(lambda r: httpx.Response(200, text=body))
    with pytest.raises(pdf.PdfFailure, match='no_pdf_metadata'):
        pdf.download_pdf('https://journal.test/article', tmp_path, 'paper')
    assert len(calls) == 1 and not list(tmp_path.glob('*.pdf'))


def test_cross_host_metadata_rejected(tmp_path, mock_http):
    calls = mock_http(lambda r: httpx.Response(200, text='<meta name="citation_pdf_url" content="https://other.test/a.pdf">'))
    with pytest.raises(pdf.PdfFailure, match='cross_host_pdf_metadata'):
        pdf.download_pdf('https://journal.test/article', tmp_path, 'paper')
    assert len(calls) == 1


def test_private_metadata_rejected_before_request(tmp_path, mock_http, monkeypatch):
    calls = mock_http(lambda r: httpx.Response(200, text='<meta name="citation_pdf_url" content="https://127.0.0.1/a">'))
    def check(url):
        if '127.0.0.1' in url: raise ValueError('Non-public address')
    monkeypatch.setattr(pdf, 'public_https', check)
    with pytest.raises(ValueError): pdf.download_pdf('https://journal.test/article', tmp_path, 'paper')
    assert len(calls) == 1


@pytest.mark.parametrize('status', [401, 403, 404, 429])
def test_permanent_or_rate_limit_response_not_retried(tmp_path, mock_http, status):
    calls = mock_http(lambda r: httpx.Response(status))
    with pytest.raises(httpx.HTTPStatusError) as error:
        pdf.download_pdf('https://journal.test/a.pdf', tmp_path, 'paper')
    assert len(calls) == 1
    assert pdf.failure_details(error.value, 'download')['http_status'] == status


def test_transient_server_error_recovers_once(tmp_path, mock_http):
    responses = iter([httpx.Response(503), httpx.Response(200, content=b'%PDF-1.7')])
    calls = mock_http(lambda r: next(responses))
    assert pdf.download_pdf('https://journal.test/a.pdf', tmp_path, 'paper').exists()
    assert len(calls) == 2


def test_timeout_retry_is_bounded_and_sanitised(tmp_path, mock_http):
    def timeout(r): raise httpx.ReadTimeout('secret remote response', request=r)
    calls = mock_http(timeout)
    with pytest.raises(httpx.ReadTimeout) as error:
        pdf.download_pdf('https://journal.test/a.pdf', tmp_path, 'paper')
    assert len(calls) == 2 and not list(tmp_path.glob('*.pdf'))
    assert pdf.failure_details(error.value, 'download') == {'failure_stage':'download','reason':'timeout'}


@pytest.mark.parametrize('body,constant,reason', [(b'%PDF-1.7 long', 'MAX_BYTES', 'pdf_size_limit'),
                                               (b'<html>long', 'MAX_HTML_BYTES', 'html_size_limit')])
def test_download_limits_cleanup(tmp_path, mock_http, monkeypatch, body, constant, reason):
    mock_http(lambda r: httpx.Response(200, content=body))
    monkeypatch.setattr(pdf, constant, 5)
    with pytest.raises(pdf.PdfFailure, match=reason): pdf.download_pdf('https://journal.test/a', tmp_path, 'paper')
    assert not list(tmp_path.glob('*.pdf'))


def test_request_limit_stops_redirect_loop(tmp_path, mock_http):
    calls = mock_http(lambda r: httpx.Response(302, headers={'location':'/loop'}))
    with pytest.raises(pdf.PdfFailure, match='redirect_limit'): pdf.download_pdf('https://journal.test/a', tmp_path, 'paper')
    assert len(calls) == pdf.MAX_REQUESTS


def test_blank_pdf_has_specific_extraction_reason(tmp_path):
    path = tmp_path / 'blank.pdf'
    with pymupdf.open() as doc:
        doc.new_page(); doc.save(path)
    with pytest.raises(pdf.PdfFailure) as error: pdf.extract_pages(path)
    assert pdf.failure_details(error.value, 'extraction') == {'failure_stage':'extraction', 'reason':'no_usable_text'}


def test_total_deadline_prevents_more_requests(tmp_path, mock_http, monkeypatch):
    calls = mock_http(lambda r: httpx.Response(302, headers={'location':'/loop'}))
    ticks = iter([0, 0, 31])
    monkeypatch.setattr(pdf, 'monotonic', lambda: next(ticks))
    with pytest.raises(pdf.PdfFailure, match='download_time_limit'):
        pdf.download_pdf('https://journal.test/a', tmp_path, 'paper')
    assert len(calls) == 1


def test_retry_after_is_not_ignored(tmp_path, mock_http):
    calls = mock_http(lambda r: httpx.Response(503, headers={'retry-after':'120'}))
    with pytest.raises(httpx.HTTPStatusError): pdf.download_pdf('https://journal.test/a', tmp_path, 'paper')
    assert len(calls) == 1
