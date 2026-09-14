import json
import pytest
from package.schemas import Paper
from package.processing.ranking import population_mismatch, filter_relevant_papers
from package.services.presentation import plain_abstract
from package.services.grounding_checks import grounding_issue
from package.agents.reporter import parse_section, clean_abstract

@pytest.mark.parametrize('title',['AI learning in Grade 9 students','AI in secondary school'])
def test_school_population_excluded(title):
 p=Paper(title=title,abstract='AI improves student learning.')
 assert population_mismatch('AI learning in higher education',p)
 assert not filter_relevant_papers([p],'AI learning in higher education',minimum_score=0)
 assert not population_mismatch('AI learning in secondary school',p)

def test_cross_population_and_higher_education_retained():
 assert not population_mismatch('AI in higher education',Paper(title='Comparing university and Grade 9 students'))
 assert not population_mismatch('AI in higher education',Paper(title='University learning'))

@pytest.mark.parametrize('cleaner',[plain_abstract,clean_abstract])
def test_comparisons_survive_markup_cleaning(cleaner):
 assert cleaner('<jats:p>r = .800, p &lt; .001; score &gt; 2.</jats:p>')=='r = .800, p < .001; score > 2.'
 assert cleaner('<p>p < .001 and score > 2</p>')=='p < .001 and score > 2'

@pytest.mark.parametrize('claim,reason',[
 ('A correlation was found (r = .503, p < .001) [S1].','unsupported_statistic'),
 ('The analysis was truncated [S1].','truncation_as_study_limitation'),
 ('Many studies used small samples [S1].','unsupported_sample_limitation'),
 ('Studies reported negative effects [S1].','unsupported_outcome'),
])
def test_unsupported_report57_claims(claim,reason):
 assert grounding_issue(claim,json.dumps([{'source_id':'S1','text':'A survey reported r = .800, p < .001.','excerpt_truncated':True}]))==reason

def test_supported_statistic_and_limitation_accepted():
 c=json.dumps([{'source_id':'S1','text':'r = 0.800, p < 0.001. Small samples limit interpretation.'}])
 assert grounding_issue('Results showed r = .800, p < .001 [S1].',c) is None
 assert grounding_issue('Small samples limit interpretation [S1].',c) is None

def test_findings_split_without_changing_claims_or_citations():
 result=parse_section(json.dumps({'findings':['One result [S1]. Another result [S2].']}),'findings')
 assert result==['One result [S1].','Another result [S2].']
 assert parse_section(json.dumps({'findings':['A context sentence. A supported result [S1].']}),'findings')==['A context sentence. A supported result [S1].']
