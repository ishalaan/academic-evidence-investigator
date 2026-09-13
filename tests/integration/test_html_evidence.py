import json
import httpx
import numpy as np
import pytest
from package.schemas import Paper, RankedSource, ResearchReport
from package.services import html_loader
from package.services.pdf_loader import PdfFailure
from package.processing.chunking import chunk_html
from package.rag.context import evidence_payload
from package.rag.pipeline import build_evidence
from package.storage.audit import create_run, get_run, record_event
from package.storage.database import save_report, load_report

PAPER = Paper(title='Learning outcomes with artificial intelligence', doi='10.1234/study', url='https://journal.test/article')


def article():
    sections = []
    for i, name in enumerate(['Introduction', 'Methods', 'Results']):
        text = ' '.join(f'{name.lower()}word{n}' for n in range(115))
        sections.append(f'<section id="sec{i}"><h2>{name}</h2><p id="p{i}">{text}</p></section>')
    return '<html><head><meta name="citation_doi" content="10.1234/study"></head><body><nav>MENU JUNK</nav><article>' + ''.join(sections) + '<h2>References</h2><p>REFERENCE JUNK</p></article><footer>FOOTER JUNK</footer></body></html>'


def test_article_extraction_removes_boilerplate_and_preserves_locators():
    paragraphs = html_loader.extract_article(article(), PAPER, PAPER.url)
    assert [p['section_title'] for p in paragraphs] == ['Introduction', 'Methods', 'Results']
    assert [p['paragraph_number'] for p in paragraphs] == [1, 2, 3]
    assert paragraphs[1]['html_anchor'] == 'p1'
    assert 'JUNK' not in str(paragraphs)


def test_correction_notice_is_not_a_research_passage():
    markup = article().replace('<article>', '<article><h2>Correction</h2><p>' + 'Correction notice metadata. ' * 50 + '</p>')
    paragraphs = html_loader.extract_article(markup, PAPER, PAPER.url)
    assert len(paragraphs) == 3 and paragraphs[0]['section_title'] == 'Introduction'


@pytest.mark.parametrize('change,reason', [
    (lambda x: x.replace('10.1234/study', '10.1234/other'), 'html_identity_mismatch'),
    (lambda x: x.replace('<head>', '<head><title>Client Challenge</title>'), 'html_access_blocked'),
    (lambda x: x.replace('<article>', '<main>').replace('</article>', '</main>'), 'html_no_article_body'),
    (lambda x: x.replace('Introduction', 'Abstract').replace('Methods', 'References').replace('Results', 'References'), 'html_insufficient_body'),
    (lambda x: x.replace('<article>', '<article hidden>'), 'html_no_article_body'),
    (lambda x: x.replace('<article>', '<article><input type="password">'), 'html_access_blocked'),
])
def test_unusable_or_wrong_html_is_rejected(change, reason):
    with pytest.raises(PdfFailure, match=reason): html_loader.extract_article(change(article()), PAPER, PAPER.url)


def test_title_match_without_doi_metadata():
    markup = article().replace('<meta name="citation_doi" content="10.1234/study">', '<meta name="citation_title" content="Learning outcomes with artificial intelligence">')
    assert len(html_loader.extract_article(markup, PAPER, PAPER.url)) == 3
    with pytest.raises(PdfFailure, match='html_identity_mismatch'):
        html_loader.extract_article(markup, Paper(title='Unrelated quantum mechanics'), PAPER.url)


def test_html_chunk_and_agent_payload_no_fake_pdf_pages():
    chunks = chunk_html(PAPER, html_loader.extract_article(article(), PAPER, PAPER.url), PAPER.url)
    assert all(c.page_number is None and c.source_format == 'html' for c in chunks)
    payload = json.loads(evidence_payload(chunks))
    assert payload[1]['paragraph_number'] == 2 and payload[1]['section_title'] == 'Methods'
    assert payload[1]['source_url'] == PAPER.url


@pytest.fixture
def http(monkeypatch):
    requests = []
    def install(handler):
        def handle(request):
            requests.append(str(request.url)); return handler(request)
        monkeypatch.setattr(html_loader, 'http_client', lambda: httpx.Client(transport=httpx.MockTransport(handle)))
        monkeypatch.setattr(html_loader, '_https_target', lambda u:u)
        return requests
    return install


def test_html_live_path_with_controlled_http(http):
    calls = http(lambda r: httpx.Response(200, text=article(), headers={'content-type':'text/html'}))
    paragraphs, url = html_loader.load_html_article(PAPER.url, PAPER)
    assert len(paragraphs) == 3 and url == PAPER.url and len(calls) == 1


@pytest.mark.parametrize('status', [401, 403, 429])
def test_html_does_not_retry_access_controls(http, status):
    calls = http(lambda r: httpx.Response(status))
    with pytest.raises(httpx.HTTPStatusError): html_loader.load_html_article(PAPER.url, PAPER)
    assert len(calls) == 1


def test_html_size_bound(http, monkeypatch):
    http(lambda r: httpx.Response(200, text=article(), headers={'content-type':'text/html'}))
    monkeypatch.setattr(html_loader, 'MAX_HTML_BYTES', 10)
    with pytest.raises(PdfFailure, match='html_size_limit'): html_loader.load_html_article(PAPER.url, PAPER)


def test_html_redirect_private_destination_blocked(http, monkeypatch):
    calls = http(lambda r: httpx.Response(302, headers={'location':'https://127.0.0.1/private'}))
    def check(url):
        if '127.0.0.1' in url: raise ValueError('Non-public')
        return url
    monkeypatch.setattr(html_loader, '_https_target', check)
    with pytest.raises(ValueError): html_loader.load_html_article(PAPER.url, PAPER)
    assert len(calls) == 1


def test_html_workflow_persistence_ui_and_replan_cache(monkeypatch, tmp_path):
    from package.rag import runtime
    from package.web import create_app
    monkeypatch.setattr(runtime, 'RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr('package.rag.pipeline.resolve_fulltext', lambda p:None)
    monkeypatch.setattr('package.processing.semantic_retrieval.encode', lambda texts:np.ones((len(texts),2), dtype='float32'))
    calls = []
    def load(url, paper):
        calls.append(url)
        return html_loader.extract_article(article(), paper, url), url
    monkeypatch.setattr('package.rag.pipeline.load_html_article', load)
    rows = [RankedSource(paper=PAPER, rank=1, relevance_score=20, eligible=True, selected=True)]
    run_id = create_run()
    state = {'run_id':run_id, 'research_question':'learning outcomes'}
    result = build_evidence(state, rows)
    assert result['rag_metrics']['html_papers_resolved'] == 1
    assert result['rag_metrics']['pdf_papers_resolved'] == 0
    assert result['evidence_coverage']['html_sources'] == 1
    assert rows[0].source_format == 'html'
    assert all(c.page_number is None for c in result['evidence_chunks'])
    again = build_evidence({**state, 'rag_cache':result['rag_cache'], 'rag_failures':result['rag_failures']}, rows)
    assert len(calls) == 1 and again['rag_metrics']['html_papers_resolved'] == 1
    assert 'html_extracted' in [e['action'] for e in get_run(run_id)['events']]
    report = ResearchReport(research_question='Q', summary='S', sources=result['processed_papers'], ranked_sources=rows,
        evidence_provenance=[c.model_dump(exclude={'text'}) for c in result['evidence_chunks']], evidence_coverage=result['evidence_coverage'])
    report_id = save_report(report)
    loaded = load_report(report_id)
    assert loaded.evidence_provenance[0]['section_title'] and 'text' not in loaded.evidence_provenance[0]
    record_event(run_id,'Reporter','completed',{},stage='completed',status='completed',report_id=report_id)
    response = create_app().test_client().get(f'/runs/{run_id}/report')
    assert 'Full-text evidence (HTML)' in response.text and 'extracted paragraph' in response.text
    assert 'PDF page' not in response.text


def test_html_failure_retains_abstract_fallback(monkeypatch, tmp_path):
    from package.rag import runtime
    monkeypatch.setattr(runtime, 'RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr('package.rag.pipeline.resolve_fulltext', lambda p:None)
    monkeypatch.setattr('package.processing.semantic_retrieval.encode', lambda texts:np.ones((len(texts),2),dtype='float32'))
    rows = [RankedSource(paper=PAPER.model_copy(update={'abstract':'Learning evidence from the abstract.'}), rank=1, relevance_score=20, eligible=True, selected=True)]
    result = build_evidence({'research_question':'learning'}, rows)
    assert result['rag_metrics']['abstract_fallbacks'] == 1 and rows[0].source_format is None


def test_html_recovers_failed_pdf(monkeypatch, tmp_path):
    from package.rag import runtime
    monkeypatch.setattr(runtime, 'RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr('package.rag.pipeline.resolve_fulltext', lambda p:'https://journal.test/broken.pdf')
    def failed_pdf(*args): raise PdfFailure('not_pdf')
    monkeypatch.setattr('package.rag.pipeline.download_pdf', failed_pdf)
    monkeypatch.setattr('package.rag.pipeline.load_html_article', lambda url,p:(html_loader.extract_article(article(),p,url),url))
    monkeypatch.setattr('package.processing.semantic_retrieval.encode', lambda texts:np.ones((len(texts),2),dtype='float32'))
    rows = [RankedSource(paper=PAPER,rank=1,relevance_score=20,eligible=True,selected=True)]
    result = build_evidence({'research_question':'learning'},rows)
    assert result['rag_metrics']['html_papers_resolved'] == 1
    assert result['rag_metrics']['abstract_fallbacks'] == 0
    assert result['rag_metrics']['fulltext_access_failures'] == 1  # failed PDF attempt remains visible


def test_html_failure_without_abstract_is_metadata_only(monkeypatch, tmp_path):
    from package.rag import runtime
    monkeypatch.setattr(runtime, 'RUNTIME_ROOT', tmp_path / 'runtime')
    monkeypatch.setattr('package.rag.pipeline.resolve_fulltext', lambda p:None)
    rows = [RankedSource(paper=PAPER,rank=1,relevance_score=20,eligible=True,selected=True)]
    result = build_evidence({'research_question':'learning'},rows)
    assert result['processed_papers'] == [] and result['evidence_chunks'] == []
    assert rows[0].evidence_type == 'metadata_only' and not rows[0].selected


def test_non_html_response_is_rejected(http):
    http(lambda r:httpx.Response(200,content=b'%PDF-1.7',headers={'content-type':'application/pdf'}))
    with pytest.raises(PdfFailure,match='html_wrong_content_type'): html_loader.load_html_article(PAPER.url,PAPER)


def test_html_redirect_loop_is_bounded(http):
    calls = http(lambda r:httpx.Response(302,headers={'location':'/loop'}))
    with pytest.raises(PdfFailure,match='redirect_limit'): html_loader.load_html_article(PAPER.url,PAPER)
    assert len(calls) == 6
