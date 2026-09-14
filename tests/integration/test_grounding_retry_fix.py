import json
from types import SimpleNamespace
import pytest
from package.services.grounding_checks import grounding_issue
from package.agents.reporter import generate_section
from package.services.references import reference_entries
from package.services.report_errors import ReportGenerationError
from package.schemas import Paper

C=json.dumps([{'source_id':'S1','text':'A mixed-method study collected interviews.'},{'source_id':'S2','text':'A survey examined attitudes.'}])

def test_design_with_corroborating_citation():
 assert grounding_issue('A mixed-methods study examined attitudes [S1] [S2].',C) is None
 assert grounding_issue('Both studies used mixed-methods [S1] [S2].',C)=='unsupported_study_design'
 assert grounding_issue('A systematic review examined attitudes [S2].',C)=='unsupported_study_design'

@pytest.mark.parametrize('separator',['-', ' ', '\u2011', '\u2013'])
def test_method_separator_variants(separator):
 assert grounding_issue('A mixed-methods study collected interviews [S1].',json.dumps([{'source_id':'S1','text':'A mixed'+separator+'method study collected interviews.'}])) is None

def test_retry_identifies_claim_and_final_reason(monkeypatch):
 calls=[];events=[]
 import package.agents.reporter as reporter
 monkeypatch.setattr(reporter,'section_event',lambda *a,**kw:events.append((a,kw)))
 class Client:
  def chat_completion(self,**kw):
   calls.append(kw)
   return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps({'summary':'A systematic review examined attitudes [S1].'})))])
 papers=[Paper(title='Study',authors=['Author'],year=2026)]
 with pytest.raises(ReportGenerationError):
  generate_section(Client(),{'research_question':'Q'},papers,reference_entries(papers),C,('summary','summary','Summarise',0),[])
 assert len(calls)==3
 feedback=calls[1]['messages'][-1]['content']
 assert 'A systematic review examined attitudes [S1].' in feedback and 'unsupported_study_design' in feedback
 assert len(feedback)<=1000
 assert any(a[1]=='validation_failed' and k['validation_reason']=='unsupported_study_design' for a,k in events)


# These cases exercise the optional strict evaluation policy.
import pytest
@pytest.fixture(autouse=True)
def strict_quality_policy(monkeypatch):
    monkeypatch.setattr('package.agents.reporter.STRICT_REPORT_QUALITY', True)
