from package.services.references import source_url
from package.services.presentation import plain_abstract
"""Hybrid evidence assembly; transient text stays in state, not SQLite."""
from time import perf_counter
from uuid import uuid4
import html
import re
from package.processing.chunking import chunk_pages, chunk_html, paper_key
from package.services.html_loader import load_html_article
from package.services.source_locations import html_candidates, stable_url
from package.services.bibliographic_metadata import enrich_writing_sources
from package.processing.semantic_retrieval import select_chunks
from package.services.fulltext_resolver import resolve_fulltext
from package.services.pdf_loader import download_pdf, extract_pages, failure_details
from package.rag.runtime import run_directory
from package.storage.audit import record_event


def build_evidence(state, ranked):
    run_id = state.get("run_id")
    directory = run_directory(run_id or uuid4().hex)
    metrics = dict(fulltext_papers_resolved=0, abstract_fallbacks=0, metadata_only_papers=0,
                   total_chunks_created=0, chunks_selected=0, pdf_extraction_failures=0,
                   fulltext_access_failures=0, html_papers_resolved=0, pdf_papers_resolved=0,
                   papers_discovered=len(state.get("raw_papers", [])))
    chunks, types, ranks = [], {}, {}
    # Replanning revisits the accumulated corpus. Reuse extraction results and
    # failure categories instead of downloading the same papers every cycle.
    cache = dict(state.get("rag_cache", {}))
    failures = dict(state.get("rag_failures", {}))
    paper_titles = {paper_key(item.paper): item.paper.title for item in ranked}
    paper_urls = {paper_key(item.paper): source_url(item.paper) for item in ranked}
    def event(action, **details):
        if details.get("paper_id") in paper_titles:
            details["paper_url"] = paper_urls.get(details["paper_id"])
            details["paper_title"] = paper_titles[details["paper_id"]][:160]
        if run_id:
            record_event(run_id, "Processing", action, details, stage="processing")
    try:
        for item in ranked:
            paper = item.paper
            key = paper_key(paper)
            ranks[key] = item.rank
            if key in cache:
                paper_chunks, kind = cache[key]
            else:
                paper_chunks, kind, url = [], "metadata_only", None
                phase = "resolution"
                try:
                    url = resolve_fulltext(paper)
                    if url:
                        event("fulltext_located", paper_id=key, doi=paper.doi, source_url=stable_url(url))
                        phase = "download"
                        download_details = {}
                        path = download_pdf(url, directory, key, download_details)
                        url = download_details.get("source_url", url)
                        try:
                            event("pdf_downloaded", paper_id=key, source_url=url,
                                  metadata_resolution=download_details.get("metadata_resolution", False))
                            phase = "extraction"
                            pages = extract_pages(path)
                        finally:
                            path.unlink(missing_ok=True)
                        paper_chunks = chunk_pages(paper, pages, "full_text", url)[:80]
                        kind = "full_text"
                        event("pdf_extracted", paper_id=key, pages=len(pages))
                    else:
                        event("fulltext_unavailable", paper_id=key)
                except Exception as exc:
                    # Access/extraction is optional. Never persist provider bodies.
                    failures[key] = "pdf_extraction_failures" if phase == "extraction" else "fulltext_access_failures"
                    event("pdf_failed" if url else "fulltext_unavailable", paper_id=key,
                          **failure_details(exc, phase))
                # A failed PDF download does not rule out an accessible article
                # body. Try HTML before reducing the evidence to its abstract.
                for html_url in html_candidates(paper, url) if not paper_chunks else []:
                    try:
                        event("html_started", paper_id=key, source_url=stable_url(html_url))
                        paragraphs, html_url = load_html_article(html_url, paper)
                        paper_chunks = chunk_html(paper, paragraphs, html_url)[:80]
                        kind = "full_text"
                        event("html_extracted", paper_id=key, source_url=html_url,
                              paragraphs=len(paragraphs), retained_chunks=len(paper_chunks))
                        break
                    except Exception as exc:
                        event("html_failed", paper_id=key, source_url=stable_url(html_url), **failure_details(exc, "html"))
                        # Count a terminal HTML-only failure once; preserve an earlier PDF failure category.
                        failures.setdefault(key, "fulltext_access_failures")
                if not paper_chunks:
                    abstract = plain_abstract(paper.abstract)
                    if abstract:
                        paper_chunks = chunk_pages(paper, [(None, abstract)], "abstract", stable_url(paper.url))
                        kind = "abstract"
                        event("abstract_fallback", paper_id=key)
                cache[key] = (paper_chunks, kind)
                event("chunks_created", paper_id=key, count=len(paper_chunks), evidence_type=kind)
            if key in failures:
                metrics[failures[key]] += 1
            item.evidence_type = kind
            item.source_format = paper_chunks[0].source_format if paper_chunks and kind == "full_text" else None
            if item.source_format:
                metrics[item.source_format + "_papers_resolved"] += 1
            item.evidence_status = "Text available" if paper_chunks else "No usable text"
            types[key] = kind
            metrics[{"full_text": "fulltext_papers_resolved", "abstract": "abstract_fallbacks", "metadata_only": "metadata_only_papers"}[kind]] += 1
            metrics["total_chunks_created"] += len(paper_chunks)
        # Preserve deterministic relevance and the ten-paper writing limit.
        eligible = [item for item in ranked if item.eligible and cache[paper_key(item.paper)][0]][:10]
        for item, (verified, status) in zip(eligible, enrich_writing_sources(eligible)):
            item.paper = verified
            event("metadata_checked", paper_id=paper_key(verified), status=status)
        papers = [item.paper for item in eligible]
        # Assign citation IDs only after the writing set is final. Reusing the
        # earlier ranking positions would attach passages to the wrong sources.
        for item in ranked:
            item.selected = item in eligible
            item.source_id = f"S{eligible.index(item) + 1}" if item.selected else None
            if item.selected:
                for chunk in cache[paper_key(item.paper)][0]:
                    chunks.append(chunk.model_copy(update={"source_id": item.source_id}))
        start = perf_counter()
        # Bound embedding work to eight lexically promising chunks per paper.
        terms = set(re.findall(r"[a-z0-9]+", state["research_question"].lower()))
        candidates = []
        for paper in papers:
            same = [c for c in chunks if c.paper_id == paper_key(paper)]
            same.sort(key=lambda c: -len(terms & set(re.findall(r"[a-z0-9]+", c.text.lower()))))
            candidates.extend(same[:8])
        selected, mode = select_chunks(state["research_question"], candidates, ranks)
        metrics["semantic_retrieval_seconds"] = round(perf_counter() - start, 3)
        metrics["chunks_selected"] = len(selected)
        metrics["final_evidence_count"] = len(papers)
        coverage = {"writing_sources": len(papers),
                    "full_text_sources": sum(types[paper_key(p)] == "full_text" for p in papers),
                    "html_sources": sum(item.selected and item.source_format == "html" for item in ranked),
                    "pdf_sources": sum(item.selected and item.source_format == "pdf" for item in ranked),
                    "abstract_only_sources": sum(types[paper_key(p)] == "abstract" for p in papers),
                    "selected_chunks": len(selected), "retrieval_mode": mode,
                    "access_failures": metrics["fulltext_access_failures"],
                    "extraction_failures": metrics["pdf_extraction_failures"],
                    "provider_failures": state.get("metrics", {}).get("provider_failures", 0)}
        event("chunks_selected", count=len(selected), provenance=[c.model_dump(exclude={"text"}) for c in selected])
        event("semantic_completed", mode=mode, count=len(selected))
        return {"processed_papers": papers, "evidence_chunks": selected, "evidence_coverage": coverage,
                "rag_cache": cache, "rag_failures": failures, "rag_metrics": metrics}
    finally:
        # Only our own flat PDF artefacts are removed; no recursive deletion.
        for path in directory.glob("*.pdf"):
            path.unlink(missing_ok=True)
        try:
            directory.rmdir()
        except OSError:
            pass
