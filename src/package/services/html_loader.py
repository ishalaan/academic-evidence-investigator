"""Conservative, bounded extraction of publicly served scholarly HTML bodies."""
import re
from time import monotonic
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from package.services.fulltext_resolver import http_client
from package.services.pdf_loader import _https_target, PdfFailure
from package.services.source_locations import stable_url

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_PARAGRAPHS = 300
SKIP_SECTIONS = re.compile(r'^(abstract|correction|references|bibliography|acknowledg|funding|conflict|competing|author contribution|supplement|supporting information|related|copyright)', re.I)


def _words(value):
    return set(re.findall(r'\w+', value.casefold()))


def extract_article(markup, paper, source_url):
    """Return labelled paragraphs only after identity/body checks; never whole-page text."""
    soup = BeautifulSoup(markup, 'html.parser')
    page_title = soup.title.get_text(' ', strip=True) if soup.title else ''
    if re.search(r'client challenge|just a moment|access denied|attention required|verify.*human', page_title, re.I):
        raise PdfFailure('html_access_blocked')
    if soup.select_one('input[type="password"], #challenge-form, #cf-challenge-running'):
        raise PdfFailure('html_access_blocked')
    # Redirects can end on another article or a catalogue page. Establish the
    # paper identity before treating any of the page as research evidence.
    doi_meta = soup.find('meta', attrs={'name': re.compile(r'^(citation_doi|dc.identifier.doi)$', re.I)})
    doi = (doi_meta.get('content', '') if doi_meta else '').strip().lower()
    doi = re.sub(r'^(https?://(dx\.)?doi.org/|doi:\s*)', '', doi)
    if doi and paper.doi and doi != paper.doi.lower().strip():
        raise PdfFailure('html_identity_mismatch')
    if not (doi and paper.doi):
        title_meta = soup.find('meta', attrs={'name': re.compile(r'^citation_title$', re.I)})
        heading = soup.find('h1')
        title = title_meta.get('content', '') if title_meta else (heading.get_text(' ', strip=True) if heading else page_title)
        expected, observed = _words(paper.title), _words(title)
        if not expected or len(expected & observed) / len(expected) < .8:
            raise PdfFailure('html_identity_mismatch')
    for tag in list(soup.select('script, style, noscript, nav, aside, footer, header, form, button, svg, iframe, table, [hidden], [aria-hidden="true"], .references, .ref-list, .related-articles, .cookie-banner')):
        if tag.attrs is not None:
            tag.decompose()
    for tag in list(soup.find_all(style=True)):
        if tag.attrs and re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', tag.get('style', ''), re.I):
            tag.decompose()
    # Whole-page text includes navigation, related papers and references, which
    # can otherwise be mistaken for findings from this article.
    roots = soup.select('[itemprop="articleBody"], .article-body, .jats-body, .c-article-body, .sj-article-detail_content, #artText, .ltx_document, article')
    if not roots:
        raise PdfFailure('html_no_article_body')
    root = max(roots, key=lambda node: len(node.get_text(' ', strip=True)))
    section, paragraphs, seen, body_headings = 'Article body', [], set(), 0
    for node in root.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'p']):
        text = ' '.join(node.get_text(' ', strip=True).split())
        if node.name != 'p':
            section = text[:200]
            if not SKIP_SECTIONS.match(section):
                body_headings += 1
            continue
        if SKIP_SECTIONS.match(section) or len(text.split()) < 15 or text in seen:
            continue
        # Abstract containers need excluding even when their heading is outside the body root.
        ancestors = [node, *node.parents]
        if any(re.search(r'(^|[\s_-])(abstract|reference|references|ref-list|related)([\s_-]|$)',
                         ' '.join([a.get('id', ''), *a.get('class', [])]), re.I)
               for a in ancestors if hasattr(a, 'get')):
            continue
        seen.add(text)
        anchor = next((a.get('id') for a in ancestors if hasattr(a, 'get') and a.get('id')), None)
        paragraphs.append({'text': text[:60000], 'section_title': section,
                           'paragraph_number': len(paragraphs) + 1, 'html_anchor': (anchor or '')[:200] or None})
        if len(paragraphs) >= MAX_PARAGRAPHS:
            break
    # A landing page can match the title while exposing only a short teaser.
    # Require enough body structure and text before calling it full-text evidence.
    if body_headings < 1 or len(paragraphs) < 3 or sum(len(p['text'].split()) for p in paragraphs) < 300:
        raise PdfFailure('html_insufficient_body')
    return paragraphs


def load_html_article(url, paper):
    """Read public HTML with checked redirects and size/time bounds, without JS or login."""
    started = monotonic()
    with http_client() as client:
        for _ in range(6):
            url = _https_target(url)
            remaining = 30 - (monotonic() - started)
            if remaining <= 0:
                raise PdfFailure('download_time_limit')
            with client.stream('GET', url, headers={'Accept': 'text/html, application/xhtml+xml'}, timeout=min(10, remaining)) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    if not response.headers.get('location'):
                        raise PdfFailure('invalid_redirect')
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                content_type = response.headers.get('content-type', '').split(';')[0].lower()
                if content_type not in ('text/html', 'application/xhtml+xml'):
                    raise PdfFailure('html_wrong_content_type')
                body = bytearray()
                for part in response.iter_bytes():
                    body.extend(part)
                    if len(body) > MAX_HTML_BYTES:
                        raise PdfFailure('html_size_limit')
                    if monotonic() - started > 30:
                        raise PdfFailure('download_time_limit')
                paragraphs = extract_article(bytes(body), paper, url)
                return paragraphs, stable_url(url)
    raise PdfFailure('redirect_limit')
