from package.schemas import Paper, ResearchReport
from package.processing.deduplication import deduplicate_papers
from package.processing.ranking import education_scope_mismatch
from package.processing.chunking import paper_key
from package.workflow.activity import activity_events
from package.services.references import reference_entries
from package.storage.audit import create_run, record_event
from package.storage.database import save_report
from package.web import create_app

def test_osf_versions_deduplicate_without_merging_unrelated_dois():
 papers=[Paper(title='Same',doi='10.31235/osf.io/b3wp5_v2'),Paper(title='Same',doi='10.31235/osf.io/b3wp5_v1'),Paper(title='Same',doi='10.9999/other_v1')]
 assert len(deduplicate_papers(papers))==2
 assert deduplicate_papers(papers)[0].doi.endswith('_v2')

def test_non_education_social_media_record_is_ineligible():
 assert education_scope_mismatch('AI learning in higher education',Paper(title='AI labels on social media',abstract='An Instagram authenticity experiment.'))
 assert not education_scope_mismatch('AI learning in higher education',Paper(title='AI labels',abstract='University students learning outcomes.'))

def test_activity_links_and_title_spacing():
 p=Paper(title='81How Gamified',doi='10.1234/test')
 event={'id':1,'timestamp':'2026-09-14T00:00:00','component':'Processing','action':'chunks_created','details':{'paper_id':paper_key(p),'paper_title':p.title}}
 result=activity_events([event],[p])[0]
 assert '81 How Gamified' in result['message']
 assert result['paper_url']=='https://doi.org/10.1234/test'
 event['details']['paper_url']='javascript:alert(1)'
 assert activity_events([event])[0]['paper_url'] is None

def test_saved_report_separate_log_and_historical_links():
 p=Paper(title='Study',doi='10.1234/test',journal='Research &amp; Learning')
 report=ResearchReport(research_question='Q',summary='Text',sources=[p],cited_source_ids=['S1'])
 run=create_run();record_event(run,'Processing','chunks_created',{'paper_id':paper_key(p),'paper_title':p.title},stage='processing')
 record_event(run,'Reporter','completed',{},stage='completed',status='completed',report_id=save_report(report))
 html=create_app().test_client().get('/runs/'+run+'/report').text
 assert 'id="log-panel"' in html and '>Activity Log</button>' in html
 assert 'href="https://doi.org/10.1234/test" target="_blank" rel="noopener noreferrer">'+paper_key(p) in html
 assert 'Research &amp;amp; Learning' not in html

def test_no_date_suffix_spacing():
 entries=reference_entries([Paper(title='A',authors=['Smith']),Paper(title='B',authors=['Smith'])])
 assert entries[0]['year']=='no date a'
