import json
import pytest
from package.services.grounding_checks import grounding_issue
from package.services.references import cited_text, used_source_ids, reference_entries, author_label
from package.services.presentation import british_prose
from package.schemas import Paper

CONTEXT=json.dumps([{'source_id':'S1','text':'A mixed-method research design used student questionnaires.'},{'source_id':'S2','text':'A survey of 300 students used regression analysis.'}])

@pytest.mark.parametrize('claim,reason',[
 ('A mixed-methods study involving 300 students reported benefits [S1].','unsupported_sample_size'),
 ('A systematic review reported benefits [S1].','unsupported_study_design'),
 ('The study used regression analysis [S1].','unsupported_study_design'),
 ('A survey of 300 students reported benefits. Other evidence was available [S2].','missing_claim_citation'),
 ('A survey of 300 students reported benefits (S1).','unsupported_sample_size'),
])
def test_rejects_cross_source_details(claim,reason):
 assert grounding_issue(claim,CONTEXT)==reason

def test_accepts_correctly_attributed_details():
 assert grounding_issue('A survey of 300 students used regression analysis [S2].',CONTEXT) is None
 assert grounding_issue('A mixed-methods study used questionnaires [S1].',CONTEXT) is None

def test_parenthesised_ids_resolve_and_count():
 entries=reference_entries([Paper(title='First',authors=['Jane Smith'],year=2025),Paper(title='Second',authors=['John Jones'],year=2026)])
 text='Evidence varies (S1, S2).'
 assert used_source_ids(text,entries)=={'S1','S2'}
 assert cited_text(text,entries)=='Evidence varies (Smith, 2025; Jones, 2026).'
 with pytest.raises(ValueError): cited_text('Surveys like S2 report benefits [S1].',entries)
 with pytest.raises(ValueError): cited_text('Evidence (S99).',entries)

def test_initials_ignore_parenthesis_punctuation():
 assert author_label(Paper(title='Study',authors=['Kai (Louis) Hon']),initials=True)=='Hon, K.L.'

def test_educational_british_spelling_preserves_computing():
 assert british_prose('Organize and personalize training programs; computer programs remain.')=='Organise and personalise training programmes; computer programs remain.'


def test_wrong_sample_triggers_targeted_regeneration():
 from types import SimpleNamespace
 from package.agents.reporter import generate_section
 responses=iter(['A study of 300 students reported benefits [S1].', 'A mixed-methods study examined student responses [S1].'])
 calls=[]
 class Client:
  def chat_completion(self, **kwargs):
   calls.append(kwargs)
   return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps({'summary':next(responses)})))])
 papers=[Paper(title='Study',authors=['Author'],year=2026)]
 value, ids=generate_section(Client(),{'research_question':'Q'},papers,reference_entries(papers),CONTEXT,('summary','summary','Summarise',0),[])
 assert len(calls)==2 and '300' not in value and ids=={'S1'}
 assert 'unsupported_sample_size' in calls[1]['messages'][-1]['content']
