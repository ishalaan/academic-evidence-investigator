"""Bounded DOI metadata verification for the final writing sources."""
import re
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from package.services.fulltext_resolver import http_client
from package.schemas import AuthorName


def enrich_paper(paper):
    doi = re.sub(r'^https?://(?:dx\.)?doi.org/', '', (paper.doi or '').strip(), flags=re.I)
    if not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
        return paper, 'not_applicable'
    try:
        with http_client() as client:
            response = client.get('https://api.crossref.org/works/' + quote(doi, safe=''), timeout=4)
            response.raise_for_status()
            record = response.json()['message']
        title = (record.get('title') or [''])[0]
        expected = set(re.findall(r'\w+', paper.title.lower()))
        observed = set(re.findall(r'\w+', title.lower()))
        # Check both identifiers and title overlap before accepting enrichment;
        # plausible metadata from a different paper would corrupt attribution.
        if record.get('DOI', '').lower() != doi.lower() or not expected or len(expected & observed)/len(expected) < .8:
            return paper, 'identity_mismatch'
        fields = {'journal': (record.get('container-title') or [None])[0], 'volume':record.get('volume'),
                  'issue':record.get('issue'), 'pages':record.get('page'), 'article_number':record.get('article-number')}
        updates = {k:str(v) for k,v in fields.items() if v is not None and str(v).strip()}
        # MDPI's modern single-number article locators are deposited as page in
        # some DOI records; do not label these as a one-page publication.
        if doi.lower().startswith('10.3390/') and 'mdpi' in record.get('publisher','').lower() and paper.year and paper.year >= 2020 and re.fullmatch(r'\d+', updates.get('pages','')):
            updates['article_number'] = updates.pop('pages')
            updates['pages'] = None
        details = [AuthorName(given=a.get('given',''), family=a.get('family','') or a.get('name','')) for a in record.get('author',[])]
        # Some deposits put a complete personal name in family. Do not replace
        # an existing usable author list with a misleading structured surname.
        if details and all(a.family or a.given for a in details) and not any(not a.given and ' ' in a.family for a in details):
            updates['author_details'] = details
            updates['authors'] = [' '.join(filter(None,[a.given,a.family])) for a in details]
        return paper.model_copy(update=updates), 'verified'
    except Exception:
        return paper, 'unavailable'


def enrich_writing_sources(items):
    # A small worker pool keeps DOI checks from adding ten sequential waits.
    # map preserves input order for pairing each result with its source.
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(enrich_paper, [item.paper for item in items]))
