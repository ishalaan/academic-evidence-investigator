"""Page-local chunks: 750 words (~1,000 tokens), 110-word overlap (~150 tokens)."""
import hashlib
import re
from package.schemas import EvidenceChunk


def paper_key(paper):
    # A repeatable key lets replanning reuse extracted text for the same paper;
    # the title is the fallback when the provider supplies no DOI.
    identity = (paper.doi or paper.title).strip().lower()
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def chunk_pages(paper, pages, evidence_type, source_url=None, size=750, overlap=110):
    if not 0 <= overlap < size:
        raise ValueError("Overlap must be smaller than chunk size")
    chunks = []
    # Do not cross page boundaries: each selected passage needs a truthful
    # page reference. Overlap keeps nearby context within a page.
    for page, text in pages:
        words = re.findall(r"\S+", text)
        for start in range(0, len(words), size - overlap):
            chunks.append(EvidenceChunk(paper_id=paper_key(paper), source_id="", title=paper.title,
                doi=paper.doi, page_number=page, chunk_index=len(chunks),
                text=" ".join(words[start:start + size]), evidence_type=evidence_type, source_url=source_url,
                source_format="pdf" if evidence_type == "full_text" else None))
            if start + size >= len(words):
                break
    return chunks


def chunk_html(paper, paragraphs, source_url):
    chunks = []
    # Chunk each paragraph separately so its section and anchor remain valid
    # even when a long HTML paragraph needs more than one chunk.
    for paragraph in paragraphs:
        for chunk in chunk_pages(paper, [(None, paragraph['text'])], 'full_text', source_url):
            chunks.append(chunk.model_copy(update={'chunk_index': len(chunks), 'source_format': 'html',
                'section_title': paragraph['section_title'], 'paragraph_number': paragraph['paragraph_number'],
                'html_anchor': paragraph.get('html_anchor')}))
    return chunks
