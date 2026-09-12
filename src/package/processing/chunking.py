"""Page-local chunks: 750 words (~1,000 tokens), 110-word overlap (~150 tokens)."""
import hashlib
import re
from package.schemas import EvidenceChunk


def paper_key(paper):
    identity = (paper.doi or paper.title).strip().lower()
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def chunk_pages(paper, pages, evidence_type, source_url=None, size=750, overlap=110):
    if not 0 <= overlap < size:
        raise ValueError("Overlap must be smaller than chunk size")
    chunks = []
    for page, text in pages:
        words = re.findall(r"\S+", text)
        for start in range(0, len(words), size - overlap):
            chunks.append(EvidenceChunk(paper_id=paper_key(paper), source_id="", title=paper.title,
                doi=paper.doi, page_number=page, chunk_index=len(chunks),
                text=" ".join(words[start:start + size]), evidence_type=evidence_type, source_url=source_url))
            if start + size >= len(words):
                break
    return chunks
