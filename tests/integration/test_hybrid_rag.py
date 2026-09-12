import json
from types import SimpleNamespace
import numpy as np
import pytest
import pymupdf
from package.schemas import Paper, RankedSource, ResearchReport
from package.processing.chunking import chunk_pages, paper_key
from package.processing.semantic_retrieval import select_chunks
from package.rag.pipeline import build_evidence
from package.services.pdf_loader import extract_pages, download_pdf
from package.storage.audit import create_run, get_run
from package.storage.database import save_report, load_report
from package.rag import runtime


@pytest.fixture
def rag_runtime(tmp_path, monkeypatch):
    root = tmp_path / 'data' / 'tmp'
    monkeypatch.setattr(runtime, 'RUNTIME_ROOT', root)
    monkeypatch.setattr('package.processing.semantic_retrieval.encode', lambda texts: np.array([[1., 0.]] * len(texts), dtype='float32'))
    monkeypatch.setattr('package.rag.pipeline.resolve_fulltext', lambda paper: paper.open_access_url)
    return root


def make_pdf(path):
    with pymupdf.open() as document:
        for words in ['Aviation safety models predict aircraft maintenance failures using operational data and engineering records.',
                      'XGBoost predicts flight delays using weather data and airport traffic measurements from daily operations.']:
            page = document.new_page()
            page.insert_text((40, 60), words)
        document.save(path)
    return path


def ranked(papers):
    return [RankedSource(paper=p, rank=i+1, relevance_score=20-i, eligible=True, selected=True) for i,p in enumerate(papers)]


def test_pdf_extraction_preserves_page_numbers(tmp_path):
    pages = extract_pages(make_pdf(tmp_path / 'study.pdf'))
    assert [p for p,t in pages] == [1,2]
    assert 'XGBoost' in pages[1][1]


def test_malformed_pdf_rejected(tmp_path):
    path=tmp_path/'broken.pdf'; path.write_bytes(b'%PDF- broken')
    with pytest.raises(Exception): extract_pages(path)


def test_chunk_overlap_order_and_provenance():
    paper=Paper(title='Flight study', doi='10.1234/flight')
    words=[f'w{i}' for i in range(1900)]
    chunks=chunk_pages(paper, [(3,' '.join(words)), (4,'page four')], 'full_text', 'https://example.com/p.pdf')
    assert chunks[0].text.split()[-110:] == chunks[1].text.split()[:110]
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].page_number == 3 and chunks[-1].page_number == 4
    assert all(c.doi==paper.doi and c.source_url.endswith('.pdf') for c in chunks)


def test_vector_relevance_and_diversity():
    a=Paper(title='A'); b=Paper(title='B')
    chunks=chunk_pages(a,[(1,'irrelevant'),(2,'flight'),(3,'flight'),(4,'flight')],'full_text')+chunk_pages(b,[(1,'flight')],'full_text')
    def encoder(texts): return np.array([[1,0]]+[[0,1] if t=='irrelevant' else [1,0] for t in texts[1:]],dtype='float32')
    chosen,mode=select_chunks('flight',chunks,{paper_key(a):1,paper_key(b):2},limit=3,encoder=encoder)
    assert mode=='semantic' and chosen[0].text=='flight'
    assert len([c for c in chosen if c.paper_id==paper_key(a)]) <=2
    assert any(c.paper_id==paper_key(b) for c in chosen)


def test_embedding_failure_is_explicit():
    def unavailable(texts): raise OSError('not installed')
    chunks=chunk_pages(Paper(title='A'),[(None,'flight delay evidence')],'abstract')
    chosen,mode=select_chunks('flight',chunks,{},encoder=unavailable)
    assert chosen and mode=='lexical_fallback'


def test_hybrid_types_audit_cleanup_and_metadata_persistence(rag_runtime, monkeypatch):
    def pdf(url,directory,name): return make_pdf(directory/(name+'.pdf'))
    monkeypatch.setattr('package.rag.pipeline.download_pdf',pdf)
    papers=[Paper(title='Full', open_access_url='https://example.com/full.pdf'), Paper(title='Abstract',abstract='Flight evidence.'), Paper(title='Metadata')]
    run_id=create_run(); rows=ranked(papers)
    result=build_evidence({'run_id':run_id,'research_question':'flight','raw_papers':papers},rows)
    assert [r.evidence_type for r in rows]==['full_text','abstract','metadata_only']
    assert len(result['processed_papers'])==2 and not rows[2].selected
    assert result['evidence_coverage']['full_text_sources']==1
    assert result['rag_metrics']['abstract_fallbacks']==1
    assert not list(rag_runtime.rglob('*.pdf'))
    events=get_run(run_id)['events']; actions={e['action'] for e in events}
    assert {'fulltext_located','pdf_extracted','abstract_fallback','chunks_created','chunks_selected','semantic_completed'}<=actions
    assert all('text' not in e['details'] for e in events)
    report=ResearchReport(research_question='Q',summary='S',sources=result['processed_papers'],ranked_sources=rows,
        evidence_provenance=[c.model_dump(exclude={'text'}) for c in result['evidence_chunks']])
    loaded=load_report(save_report(report))
    assert loaded.evidence_provenance and 'text' not in loaded.evidence_provenance[0]


@pytest.mark.parametrize('failure',[FileNotFoundError('missing'),ValueError('malformed'),PermissionError('restricted')])
def test_inaccessible_fulltext_falls_back_without_terminating(rag_runtime,monkeypatch,failure):
    def bad(*args): raise failure
    monkeypatch.setattr('package.rag.pipeline.download_pdf',bad)
    rows=ranked([Paper(title='Flight',abstract='Flight delays evidence.',open_access_url='https://example.com/a.pdf')])
    result=build_evidence({'research_question':'flight'},rows)
    assert result['evidence_chunks'][0].evidence_type=='abstract'
    assert result['rag_metrics']['pdf_extraction_failures']==1


def test_replan_reuses_extraction(rag_runtime,monkeypatch):
    calls=[]
    monkeypatch.setattr('package.rag.pipeline.resolve_fulltext',lambda p: calls.append(p.title))
    rows=ranked([Paper(title='Flight',abstract='Flight evidence.')])
    first=build_evidence({'research_question':'flight'},rows)
    build_evidence({'research_question':'flight','rag_cache':first['rag_cache']},rows)
    assert len(calls)==1


def test_processing_deduplicates_before_chunks(rag_runtime):
    from package.workflow.nodes import processing_node
    p=Paper(title='XGBoost aviation flight delay prediction',abstract='XGBoost predicts aviation flight delays.',doi='10.1234/a')
    result=processing_node({'research_question':'XGBoost aviation flight delay prediction','raw_papers':[p,p]})
    assert len(result['ranked_sources'])==1
    assert len(result['evidence_chunks'])==1


def test_reporter_and_critic_receive_passages(rag_runtime,monkeypatch):
    from package.agents.reporter import reporter_node
    from package.agents.critic import critic_node
    paper=Paper(title='Flight study',abstract='UNSELECTED ABSTRACT')
    chunks=chunk_pages(paper,[(7,'Selected aviation flight delay evidence.')],'full_text')
    chunks[0].source_id='S1'; calls=[]
    class Client:
        def chat_completion(self,**kwargs):
            calls.append(kwargs)
            body={'summary':'Flight evidence [S1].','findings':['Flight delays [S1].'],'limitations':['Only selected passages were reviewed.'],
                  'sufficient':True,'reason':'The passage addresses the question.','suggested_queries':[]}
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(body)))])
    monkeypatch.setattr('package.agents.reporter.get_llm_client',lambda:Client())
    monkeypatch.setattr('package.agents.critic.get_llm_client',lambda:Client())
    state={'research_question':'flight','processed_papers':[paper],'evidence_chunks':chunks,'evidence_coverage':{'full_text_sources':1,'selected_chunks':1}}
    assert critic_node(state)['critic_decision'].sufficient
    report=reporter_node(state)['final_report']
    assert report.evidence_provenance[0]['page_number']==7
    assert all('Selected aviation' in str(c) and 'UNSELECTED ABSTRACT' not in str(c) for c in calls)
    assert 'full_text_sources' in str(calls[0])


def test_legacy_report_defaults():
    report=ResearchReport.model_validate({'research_question':'Q','summary':'Old'})
    assert report.evidence_provenance==[] and report.evidence_coverage=={}


def test_ui_evidence_labels(rag_runtime):
    from package.web import create_app
    from package.storage.audit import record_event
    rows=ranked([Paper(title='Full'),Paper(title='Abstract'),Paper(title='Metadata')])
    for row,kind in zip(rows,['full_text','abstract','metadata_only']): row.evidence_type=kind
    report=ResearchReport(research_question='Q',summary='Answer',ranked_sources=rows)
    report_id=save_report(report); run_id=create_run()
    record_event(run_id,'Reporter','completed',{},stage='completed',status='completed',report_id=report_id)
    response=create_app().test_client().get(f'/runs/{run_id}/report')
    assert all(label in response.text for label in ['Full-text evidence','Abstract-only evidence','Metadata-only'])


def test_runtime_path_cannot_escape(rag_runtime):
    with pytest.raises(ValueError): runtime.run_directory('../outside')
    assert runtime.run_directory('safe-run').parent==rag_runtime


def test_download_checks_pdf_and_stays_in_runtime(rag_runtime,monkeypatch):
    import httpx
    from package.services import pdf_loader
    directory=runtime.run_directory('download')
    with pymupdf.open() as doc:
        doc.new_page(); pdf=doc.tobytes()
    transport=httpx.MockTransport(lambda request:httpx.Response(200,content=pdf))
    monkeypatch.setattr(pdf_loader,'http_client',lambda:httpx.Client(transport=transport))
    monkeypatch.setattr(pdf_loader,'public_https',lambda url:url)
    path=download_pdf('https://example.com/a.pdf',directory,'paper')
    assert path.parent==directory and path.read_bytes().startswith(b'%PDF')


def test_redirect_to_private_host_is_blocked(rag_runtime,monkeypatch):
    import httpx
    from package.services import pdf_loader
    transport=httpx.MockTransport(lambda request:httpx.Response(302,headers={'location':'https://127.0.0.1/secret'}))
    monkeypatch.setattr(pdf_loader,'http_client',lambda:httpx.Client(transport=transport))
    def check(url):
        if '127.0.0.1' in url: raise ValueError('private')
    monkeypatch.setattr(pdf_loader,'public_https',check)
    with pytest.raises(ValueError): download_pdf('https://example.com/a.pdf',runtime.run_directory('redirect'),'paper')


def test_replan_preserves_failure_counts(rag_runtime,monkeypatch):
    def bad(*args): raise ValueError('bad PDF')
    monkeypatch.setattr('package.rag.pipeline.download_pdf',bad)
    rows=ranked([Paper(title='Flight',abstract='Flight evidence.',open_access_url='https://example.com/a.pdf')])
    first=build_evidence({'research_question':'flight'},rows)
    second=build_evidence({'research_question':'flight','rag_cache':first['rag_cache'],'rag_failures':first['rag_failures']},rows)
    assert second['rag_metrics']['pdf_extraction_failures']==1


def test_public_https_rejects_local_addresses(monkeypatch):
    from package.services.fulltext_resolver import public_https
    monkeypatch.setattr('package.services.fulltext_resolver.socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError): public_https('https://example.com/document.pdf')
    with pytest.raises(ValueError): public_https('http://example.com/document.pdf')


def test_open_access_metadata_resolution(monkeypatch):
    from package.services import fulltext_resolver
    monkeypatch.setattr(fulltext_resolver,'public_https',lambda url:url)
    monkeypatch.delenv('UNPAYWALL_EMAIL',raising=False)
    assert fulltext_resolver.resolve_fulltext(Paper(title='A',open_access_url='https://example.com/a.pdf')).endswith('a.pdf')
    assert fulltext_resolver.resolve_fulltext(Paper(title='B',doi='10.1234/b')) is None


def test_download_rejects_non_pdf(rag_runtime,monkeypatch):
    import httpx
    from package.services import pdf_loader
    transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'<html>Login required</html>'))
    monkeypatch.setattr(pdf_loader,'http_client',lambda:httpx.Client(transport=transport))
    monkeypatch.setattr(pdf_loader,'public_https',lambda url:url)
    folder=runtime.run_directory('nonpdf')
    with pytest.raises(ValueError): download_pdf('https://example.com/a',folder,'paper')
    assert list(folder.iterdir())==[]


def test_runtime_paths_are_gitignored():
    import subprocess
    from package.config import PROJECT_ROOT
    if not (PROJECT_ROOT/'.git').exists(): pytest.skip('Only meaningful in the repository')
    paths=['data/tmp/demo/paper.pdf','data/vector_store/demo.faiss','data/chunks/demo.json','data/cache/model.safetensors','.env','data/academic_evidence.db']
    result=subprocess.run(['git','check-ignore',*paths],cwd=PROJECT_ROOT,capture_output=True,text=True,check=True)
    assert set(result.stdout.splitlines())==set(paths)


def test_real_local_embedding_semantics():
    from package.processing.embeddings import encode, MODEL_CACHE
    if not MODEL_CACHE.exists(): pytest.skip('Run explicit local model setup to enable this integration test')
    texts=['Predicting aircraft arrival delays from weather', 'Aviation flight delay prediction using meteorological observations', 'A recipe for chocolate cake and vanilla icing']
    vectors=encode(texts)
    assert float(vectors[0]@vectors[1]) > float(vectors[0]@vectors[2])
