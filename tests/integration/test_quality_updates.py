import requests
from package.agents.retrieval import retrieval_node
from package.schemas import SearchPlan
from package.services.presentation import display_timestamp, plain_abstract, british_prose
from package.workflow.activity import activity_events


def state():
    return {'search_plan': SearchPlan(research_goal='Education', queries=['education']*10)}


def test_semantic_failure_limit_persists_across_replans(monkeypatch):
    calls=[]; crossref=[]
    def failed(*args,**kwargs): calls.append(1); raise requests.Timeout('SECRET')
    monkeypatch.setattr('package.agents.retrieval.search_semantic_scholar',failed)
    monkeypatch.setattr('package.agents.retrieval.search_crossref',lambda *a,**k:crossref.append(1) or [])
    first=retrieval_node(state())
    second=retrieval_node({**state(),**first})
    assert len(calls)==2 and len(crossref)==20
    assert second['semantic_policy']['disabled']
    assert 'SECRET' not in str(first)


def test_semantic_successful_requests_are_bounded(monkeypatch):
    calls=[]
    monkeypatch.setattr('package.agents.retrieval.search_semantic_scholar',lambda *a,**k:calls.append(1) or [])
    monkeypatch.setattr('package.agents.retrieval.search_crossref',lambda *a,**k:[])
    first=retrieval_node(state())
    retrieval_node({**state(),**first})
    assert len(calls)==6 and first['semantic_policy']['disabled']


def test_rate_limit_stops_immediately(monkeypatch):
    calls=[]
    def limited(*a,**k):
        calls.append(1); response=requests.Response();response.status_code=429
        raise requests.HTTPError('SECRET',response=response)
    monkeypatch.setattr('package.agents.retrieval.search_semantic_scholar',limited)
    monkeypatch.setattr('package.agents.retrieval.search_crossref',lambda *a,**k:[])
    result=retrieval_node(state())
    assert len(calls)==1 and result['provider_failures'][0]['reason']=='rate_limit'


def test_presentation_helpers():
    assert display_timestamp('2026-09-12T20:53:25.240+00:00')=='2026-09-12 20:53:25'
    assert display_timestamp('2026-09-12T21:53:25+01:00')=='2026-09-12 20:53:25'
    assert plain_abstract('&lt;jats:p&gt;Example &amp; evidence&lt;/jats:p&gt;')=='Example & evidence'
    assert british_prose('Personalized judgment (Judgment, 2025) [S1].')=='Personalised judgement (Judgment, 2025) [S1].'


def test_paper_activity_has_identifier_and_formatted_time():
    events=activity_events([{'id':1,'component':'Processing','action':'pdf_failed','timestamp':'2026-09-12T20:53:25.240+00:00',
        'details':{'paper_id':'a'*20,'paper_title':'Example paper'}}])
    assert 'a'*20 in events[0]['message'] and 'Example paper' in events[0]['message']
    assert events[0]['display_timestamp']=='2026-09-12 20:53:25'
