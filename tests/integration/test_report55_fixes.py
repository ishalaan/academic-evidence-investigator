import json
from types import SimpleNamespace
import httpx
import pytest
from package.schemas import Paper, AuthorName
from package.services.source_locations import html_candidates, stable_url
from package.services.references import reference_entries
from package.services.presentation import british_prose
from package.services.grounding_checks import grounding_issue, repeats_summary
from package.services import bibliographic_metadata as metadata


def test_catalogue_does_not_shadow_doi_or_open_landing():
    p=Paper(title='Study',doi='10.1234/study',url='https://www.semanticscholar.org/paper/id',open_access_url='https://journal.test/article')
    assert html_candidates(p)==['https://doi.org/10.1234/study','https://journal.test/article']


def test_candidate_limit_and_deduplication():
    p=Paper(title='Study',doi='10.1234/study',url='https://journal.test/third',open_access_url='https://journal.test/article')
    assert len(html_candidates(p,'https://journal.test/fourth'))==2
    assert html_candidates(Paper(title='A',url='https://semanticscholar.org/paper/id'))==[]


def test_session_free_url_preserves_document_query():
    assert stable_url('https://repo.test/file.pdf;jsessionid=PRIVATE?sequence=1&sessionid=PRIVATE')=='https://repo.test/file.pdf?sequence=1'


def test_oa_metadata_http_url_is_tried_as_https(monkeypatch):
    from package.services import fulltext_resolver
    seen=[]
    monkeypatch.setattr(fulltext_resolver,'public_https',lambda u:seen.append(u) or u)
    assert fulltext_resolver.resolve_fulltext(Paper(title='A',open_access_url='http://publisher.test/p.pdf'))=='https://publisher.test/p.pdf'
    assert seen==['https://publisher.test/p.pdf']


def test_rsis_body_selector_still_requires_article_identity():
    from package.services.html_loader import extract_article
    paragraphs=''.join('<h3>'+name+'</h3><p>'+('Evidence '+name+' ')*60+'</p>' for name in ['Introduction','Methods','Results'])
    markup='<meta name="citation_doi" content="10.1234/study"><div class="sj-article-detail_content">'+paragraphs+'</div>'
    assert len(extract_article(markup,Paper(title='A',doi='10.1234/study'),'https://publisher.test/a'))==3


def test_honorific_does_not_create_initial():
    p=Paper(title='Study',authors=['Dr Namrata Yadav Das'],year=2025)
    assert reference_entries([p])[0]['opening'].startswith('Das, N.Y.')
    p.author_details=[AuthorName(given='Dr. Namrata Yadav',family='Das')]
    assert reference_entries([p])[0]['opening'].startswith('Das, N.Y.')


def test_explicit_article_number_not_page():
    p=Paper(title='Study',article_number='1070',pages='1070')
    assert reference_entries([p])[0]['publication']=='article 1070'


def test_british_words_preserve_bibliographic_citations():
    assert british_prose('Recognizing customization helps maximize access (Recognizing, 2026).')=='Recognising customisation helps maximise access (Recognizing, 2026).'


@pytest.mark.parametrize('claim,evidence,expected',[
    ('GenAI enhances learning as demonstrated in practical applications [S1].','Expected Learning Benefit: improved learning.','expected_benefit_as_result'),
    ('GenAI may enhance learning; these are expected benefits [S1].','Expected Learning Benefit: improved learning.',None),
    ('GenAI improves grades [S1].','Questionnaire responses correlated with perceived performance.','observational_as_causal'),
    ('Reported grades were associated with GenAI use [S1].','Questionnaire responses correlated with perceived performance.',None),
    ('Gains were contingent on faculty training [S1].','A correlation with satisfaction was found.','unsupported_condition'),
    ('The study recommends faculty training [S1].','The study recommends faculty training.',None),
    ('GenAI improves scores [S1].','A randomised controlled experiment measured improved scores.',None),
])
def test_grounding_checks(claim,evidence,expected):
    assert grounding_issue(claim,json.dumps([{'source_id':'S1','text':evidence}]))==expected


def test_citation_specific_checks_do_not_borrow_uncited_result():
    context=json.dumps([{'source_id':'S1','text':'Expected Learning Benefit: faster improvement.'},
                        {'source_id':'S2','text':'Randomised results showed p < 0.01.'}])
    assert grounding_issue('Learning improves [S1].',context)=='expected_benefit_as_result'


def test_summary_restatement_detected():
    summary='Generative AI supports academic writing and research by providing instant feedback and personalised explanations to university students.'
    assert repeats_summary('University students receive personalised explanations and instant feedback as generative AI supports academic writing and research.',[summary])
    assert not repeats_summary('The questionnaire sampled 350 students and measured self-reported outcomes rather than independently assessed grades.',[summary])


def test_doi_metadata_enrichment_is_identity_checked(monkeypatch):
    record={'DOI':'10.3390/example','title':['Study title'],'publisher':'MDPI AG','container-title':['Information'],'volume':'16','issue':'12','page':'1070',
            'author':[{'given':'Wei‐Han','family':'Rong'}]}
    monkeypatch.setattr(metadata,'http_client',lambda:httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'message':record}))))
    p=Paper(title='Study title',doi='10.3390/example',year=2025)
    enriched,status=metadata.enrich_paper(p)
    assert status=='verified' and enriched.article_number=='1070' and enriched.pages is None
    assert reference_entries([enriched])[0]['opening'].startswith('Rong, W.H.')
    record['DOI']='10.1234/wrong'
    rejected,status=metadata.enrich_paper(p)
    assert status=='identity_mismatch' and rejected==p


def test_malformed_registry_name_does_not_replace_existing_authors(monkeypatch):
    record={'DOI':'10.1234/study','title':['Study'],'author':[{'family':'Omar J. Alkhatib'}]}
    monkeypatch.setattr(metadata,'http_client',lambda:httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'message':record}))))
    p=Paper(title='Study',doi='10.1234/study',authors=['Omar J. Alkhatib'])
    enriched,status=metadata.enrich_paper(p)
    assert reference_entries([enriched])[0]['opening'].startswith('Alkhatib, O.J.')


def test_grounding_failure_regenerates_current_section(monkeypatch):
    from package.agents.reporter import generate_section
    responses=iter(['GenAI improves learning [S1].','GenAI may support learning; these are expected benefits [S1].'])
    calls=[]
    class Client:
        def chat_completion(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps({'summary':next(responses)})))])
    p=Paper(title='Study',authors=['Author'],year=2026,abstract='Expected Learning Benefit: improved learning.')
    value,ids=generate_section(Client(),{'research_question':'Q'},[p],reference_entries([p]),json.dumps([{'source_id':'S1','text':p.abstract}]),('summary','summary','Summarise',0),[])
    assert len(calls)==2 and 'may support' in value and 'grounding check failed' in str(calls[1])
