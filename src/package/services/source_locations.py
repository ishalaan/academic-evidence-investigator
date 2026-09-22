"""Publisher-oriented candidates and stable public provenance URLs."""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from package.services.references import source_url


def stable_url(url):
    if not url:
        return url
    parts = urlsplit(url)
    # Provenance should remain reusable after a session expires. Remove known
    # session credentials while retaining query fields that identify the document.
    path = re.sub(r';(?:jsessionid|phpsessid|aspsessionid)=[^/;?]*', '', parts.path, flags=re.I)
    query = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in {'jsessionid','phpsessid','sessionid','session_id','sid','access_token','token'}]
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def html_candidates(paper, resolved=None):
    candidates = []
    # A DOI resolves to the publisher; catalogue pages are not article bodies.
    for url in [source_url(paper) if paper.doi else None, paper.open_access_url, resolved, paper.url]:
        if not url:
            continue
        try:
            host = (urlsplit(url).hostname or '').lower()
            if host == 'semanticscholar.org' or host.endswith('.semanticscholar.org'):
                continue
            url = stable_url(url)
        except ValueError:
            continue
        if url not in candidates:
            candidates.append(url)
    return candidates[:2]
