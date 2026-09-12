"""In-memory FAISS plus topical overlap and paper rank, with per-paper caps."""
from collections import Counter
import re
import numpy as np
from package.processing.embeddings import encode


def select_chunks(question, chunks, ranks, limit=12, per_paper=2, encoder=None):
    if not chunks:
        return [], "no_evidence"
    terms = set(re.findall(r"[a-z0-9]+", question.lower()))
    semantic = np.zeros(len(chunks), dtype="float32")
    mode = "semantic"
    try:
        import faiss
        vectors = (encoder or encode)([question] + [c.text for c in chunks])
        vectors = np.ascontiguousarray(vectors, dtype="float32")
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors[1:])
        scores, positions = index.search(vectors[:1], len(chunks))
        for score, position in zip(scores[0], positions[0]):
            semantic[position] = score
    except (ImportError, OSError, RuntimeError, ValueError):
        mode = "lexical_fallback"
    scored = []
    for i, chunk in enumerate(chunks):
        words = set(re.findall(r"[a-z0-9]+", chunk.text.lower()))
        lexical = len(terms & words) / max(len(terms), 1)
        rank = 1 / max(ranks.get(chunk.paper_id, 1), 1)
        chunk.similarity_score = float(semantic[i])
        score = .65 * float(semantic[i]) + .25 * lexical + .1 * rank
        scored.append((score, i, chunk))
    ordered = sorted(scored, key=lambda item: (-item[0], item[1]))
    selected, counts = [], Counter()
    # First ensure breadth across papers, then allow a second passage per paper.
    for cap in range(1, per_paper + 1):
        for _, _, chunk in ordered:
            if chunk not in selected and counts[chunk.paper_id] < cap and len(selected) < limit:
                selected.append(chunk)
                counts[chunk.paper_id] += 1
    return selected, mode
