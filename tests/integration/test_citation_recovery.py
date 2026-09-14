import pytest
from package.services.references import cited_text, used_source_ids, resolve_known_citations, reference_entries
from package.services.grounding_checks import grounding_issue
from package.schemas import Paper
import json

def entries():
 return reference_entries([Paper(title='One',authors=['A Smith','B Jones'],year=2025),Paper(title='Two',authors=['A Brown'],year=2026)])

def test_grouped_variants_share_tracking_and_rendering():
 e=entries();t='Evidence (Smith & Jones 2025; Brown, 2026).'
 assert resolve_known_citations(t,e)=='Evidence [S1] [S2].'
 assert used_source_ids(t,e)=={'S1','S2'}
 assert cited_text(t,e)=='Evidence (Smith and Jones, 2025; Brown, 2026).'

def test_date_range_is_not_an_author_citation():
 assert cited_text('A review (2018–2024) reports evidence [S1].',entries(),require_citation=True)=='A review (2018–2024) reports evidence (Smith and Jones, 2025).'

@pytest.mark.parametrize('citation',['(Unknown, 2025)','(Brown, 2024)','(Brown, 2026; Unknown, 2025)'])
def test_unknown_citations_rejected(citation):
 with pytest.raises(ValueError):cited_text('Evidence '+citation,entries())

def test_ambiguous_citation_not_guessed():
 e=entries();e.append(dict(e[0],id='S3'))
 with pytest.raises(ValueError):cited_text('Evidence (Smith and Jones, 2025).',e)

def test_normalised_citation_does_not_bypass_grounding():
 t=resolve_known_citations('A systematic review reported benefits (Brown 2026).',entries())
 assert grounding_issue(t,json.dumps([{'source_id':'S2','text':'A survey explored attitudes.'}]))=='unsupported_study_design'
