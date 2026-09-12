"""Bounded passage payload shared by Critic and Reporter."""
import json


def evidence_payload(chunks, budget=14000):
    if not chunks:
        return "[]"
    allowance = max(100, budget // len(chunks) - 350)
    return json.dumps([{"source_id": c.source_id, "paper_id": c.paper_id,
        "chunk_index": c.chunk_index, "title": c.title[:220], "page_number": c.page_number,
        "evidence_type": c.evidence_type, "text": c.text[:allowance],
        "excerpt_truncated": len(c.text) > allowance} for c in chunks], ensure_ascii=False)
