import json
from types import SimpleNamespace
import pytest
from package.agents.reporter import reporter_node
from package.schemas import Paper
from package.storage.database import load_report

@pytest.mark.parametrize('summary',[
 'A systematic review found benefits [S1].',
 'Evidence improves learning S1.',
 'A useful but uncited overview.',
 'Evidence supports learning [S99].',
 'Evidence supports learning (Unknown, 2026).',
])
def test_quality_weakness_completes_and_persists_review_note(monkeypatch,summary):
 calls=[]
 class Client:
  def chat_completion(self,**kw):
   calls.append(kw)
   section=kw['messages'][1]['content'].splitlines()[0].split(': ')[1]
   body={'summary':summary} if section=='summary' else {section:['Participants reported benefits [S1].']}
   return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(body)))])
 monkeypatch.setattr('package.agents.reporter.get_llm_client',lambda:Client())
 p=Paper(title='Survey',authors=['A Smith'],year=2026,abstract='A survey recorded perceived benefits.')
 result=reporter_node({'research_question':'Q','processed_papers':[p]})
 stored=load_report(result['report_id'])
 assert len(calls)==3
 assert stored and any('Reporter review note:' in x for x in stored.limitations)
 assert set(stored.cited_source_ids)<= {'S1'}
 if 'S99' in summary:
  assert 'citation unverified' in stored.summary and 'S99' not in stored.summary
 if ' S1.' in summary:assert '(Smith, 2026)' in stored.summary
