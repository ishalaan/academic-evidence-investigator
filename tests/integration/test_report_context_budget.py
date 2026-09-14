import json
from types import SimpleNamespace
import pytest
from package.rag.budget import fit_evidence, previous_excerpt
from package.rag.context import evidence_payload
from package.schemas import EvidenceChunk, Paper
from package.agents.reporter import generate_section, MAX_CONTEXT_CHARACTERS
from package.services.references import reference_entries


def test_final_json_budget_includes_escaping_and_metadata():
    chunks=[EvidenceChunk(source_id=f'S{i%10+1}',paper_id=str(i),title='Long title '*40,chunk_index=i,
             source_format='html',section_title='Heading '*60,paragraph_number=i+1,html_anchor='anchor'*100,
             source_url='https://publisher.test/'+'path/'*200,evidence_type='full_text',text=('Quoted "evidence"\n\\data '*1000)) for i in range(12)]
    payload=evidence_payload(chunks)
    assert len(payload)<=14000
    records=json.loads(payload)
    assert len(records)==12
    assert {r['source_id'] for r in records}=={f'S{i}' for i in range(1,11)}
    assert all(r['excerpt_truncated'] and r['metadata_truncated'] for r in records)
    assert all(len(r['text'])>=100 for r in records)
    assert len(chunks[0].source_url)>240  # full stored provenance is unchanged


def test_previous_summary_is_explicitly_shortened_without_mutation():
    previous=['"long summary"\n'*2000]
    encoded=previous_excerpt(previous)
    assert len(encoded)<=2500 and json.loads(encoded)['truncated']
    assert len(previous[0])>2500


def test_findings_after_long_summary_and_retry_stay_within_budget():
    papers=[Paper(title=f'Study {i}',authors=[f'Author{i}'],year=2026) for i in range(10)]
    context=json.dumps([{'source_id':f'S{i+1}','text':'Survey evidence. '+('"quoted"\n'*2500)} for i in range(10)])
    previous=[' '.join(f'summaryword{i}' for i in range(1500))]
    calls=[]
    class Client:
        def chat_completion(self,**kwargs):
            calls.append(kwargs)
            text='Respondents reported benefits.' if len(calls)==1 else 'Respondents reported benefits [S1].'
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps({'findings':[text]})))])
    result,ids=generate_section(Client(),{'research_question':'How does generative AI affect student learning outcomes in higher education?'},
        papers,reference_entries(papers),context,('findings','findings','Describe additional evidence.',0),previous)
    assert len(calls)==2 and ids=={'S1'}
    assert all(sum(len(m['content']) for m in call['messages'])<=MAX_CONTEXT_CHARACTERS for call in calls)
    evidence=json.loads(calls[0]['messages'][1]['content'].split('EVIDENCE DATA:\n')[1].split('\n\nDescribe additional evidence.')[0])
    assert len(evidence)==10 and all(r['text'] and r['excerpt_truncated'] for r in evidence)
    assert calls[0]['messages'][1]['content']==calls[1]['messages'][1]['content']


def test_unfit_minimum_evidence_is_not_silently_dropped():
    with pytest.raises(ValueError):fit_evidence(json.dumps([{'source_id':'S1','text':'x'*1000}]),20)


def test_already_short_evidence_is_preserved():
    rows=[{'source_id':'S1','text':'Short evidence.','excerpt_truncated':False}]
    assert json.loads(fit_evidence(json.dumps(rows),1000))==rows


# These cases exercise the optional strict evaluation policy.
import pytest
@pytest.fixture(autouse=True)
def strict_quality_policy(monkeypatch):
    monkeypatch.setattr('package.agents.reporter.STRICT_REPORT_QUALITY', True)
