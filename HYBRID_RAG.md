# Hybrid full-text RAG

## Report 55 remediation

HTML candidates now prioritise DOI/publisher resolution and explicit OA locations,
exclude Semantic Scholar catalogue pages, and try at most two distinct candidates.
Each attempt records its URL. The verified RSIS article-body container is supported
without relaxing article identity or minimum-body checks. Explicit HTTP OA metadata
is tried using HTTPS only. Saved provenance removes transient session identifiers.

The final ten writing sources receive bounded Crossref DOI metadata checks (four
workers, four-second request timeouts, no retries). Matching DOI and title are
required. Failed checks retain existing metadata and are visible in the audit.
No year or article title is silently changed. Author honorifics are excluded from
initials; malformed full-name-as-surname deposits do not override usable existing
authors. Modern MDPI numeric article locators are not formatted as one-page ranges.

Reporter checks detect selected classes of unsupported claims: expected benefits
presented as demonstrated results, unqualified causal language over observational
evidence, and specific conditions absent from cited passages. Failed sections use
the existing three-attempt retry bound; persistent failure is visible rather than
silently accepted. These are targeted heuristics, not a complete faithfulness test.
The complete Summary is available for overlap checking against Findings; near
restatements trigger rewriting. Findings are prompted for additional study-level
detail only when supported. British-English normalisation preserves citations and
source metadata. Saved historical reports are not regenerated or rewritten.

The LangGraph nodes and Critic replanning route are unchanged. Processing first
validates, deduplicates and ranks papers using the existing deterministic rules.
It then resolves explicit open-access PDF metadata (Semantic Scholar openAccessPdf,
or Crossref PDF links accompanied by a Creative Commons licence). Optional
Unpaywall resolution is enabled only when UNPAYWALL_EMAIL is configured. When an
OA URL leads to HTML, the downloader can follow one unambiguous citation_pdf_url
meta tag on the same host. It does not guess PDF links or crawl ordinary anchors.
The landing-page response is limited to 512 KiB and is never used as evidence text.

PDF downloads use verified public HTTPS, inspect redirect destinations, and stop
on access errors. HTTP redirect targets are tried using HTTPS only; insecure HTTP
requests are never sent. There are at most eight requests and one transient-error
retry within a 30-second checked budget. HTTP 401/403/404/429 and Retry-After responses
are not retried. Downloads are capped at 20 MiB and 200
pages. Extraction uses PyMuPDF and preserves one-based PDF page positions. There
is no OCR, CAPTCHA handling, login or paywall workaround.
Scanned, malformed, restricted, oversized or unavailable PDFs fall back to the
HTML article body when a scholarly article URL is available, then to the abstract.
Records without usable text stay in Ranked Sources, outside synthesis.

## HTML article evidence (13 September 2026)

When PDF extraction cannot supply text, Processing checks the paper's scholarly
landing URL (or resolved OA URL) for publicly served HTML. No OA PDF is required
for this branch. Unpaywall OA landing-page metadata is also accepted. It never
executes JavaScript, logs in or bypasses access controls. HTML fetches allow at
most six checked public-HTTPS requests, 2 MiB of response data and elapsed-time
checks against 30 seconds. Synchronous network/DNS work can overrun that checked
budget; it is not a hard process deadline.

Beautiful Soup parses recognised article-body containers. The DOI, or a strong
title match where DOI metadata is absent, must identify the requested paper.
Navigation, forms, hidden content, tables, scripts, abstracts, reference lists,
correction-notice metadata and other support sections are excluded. At least
three retained paragraphs, 300 words and a non-abstract heading are required.
These are conservative heuristics, not proof of completeness or study quality.
Unusual layouts, brief papers and JavaScript-only views may still fall back.

HTML paragraphs enter the same overlapping chunking, embedding, FAISS selection,
deterministic relevance controls and two-passages-per-paper cap as PDFs. The
existing 80-chunk limit applies and can omit later paragraphs. HTML remains
evidence_type=full_text, distinguished by source_format=html; PDFs use pdf.
HTML chunks have no PDF page number. Provenance retains the source URL, section
heading, one-based extracted paragraph number and HTML anchor where available.
Paragraph numbers refer to the filtered extraction, not publisher numbering.

Critic and Reporter receive those locators. SQLite persists provenance and
format/coverage metadata without full HTML or chunk text. Ranked Sources displays
HTML versus PDF evidence and their appropriate locators. Audit events show HTML
attempts, successful extraction and specific fallback reasons. Old reports load
with optional-field defaults and are not rewritten.

fulltext_papers_resolved includes PDF and HTML successes; pdf_papers_resolved and
html_papers_resolved separate the formats. Writing coverage reports pdf_sources
and html_sources. Failed PDF attempts stay counted even when HTML succeeds, so
failure counts must not be interpreted as papers ultimately lacking evidence.

Chunks remain within a page: 750 whitespace-delimited words with 110 words of
overlap (approximately 1,000 and 150 tokens). Short pages remain shorter chunks.
These are engineering defaults, not optimality claims or exact token counts.
At most 80 chunks per paper are retained; long documents can therefore have
incomplete coverage. A lexical preselection keeps eight candidates per writing
paper. The existing relevance threshold and ten-paper limit still apply.

Local all-MiniLM-L6-v2 embeddings are computed through sentence-transformers.
Because that model has a short input window, each chunk is embedded in overlapping
200-token subwindows and their vectors are averaged and normalised. An in-memory
FAISS inner-product index ranks cosine similarity. The combined score is 65%
semantic similarity, 25% question-term overlap and 10% reciprocal paper rank.
These explainable heuristic weights are not calibrated measures of evidence quality.
Selection favours paper breadth, has a two-chunk-per-paper cap and retains at most
12 chunks. If local embeddings cannot load, lexical/rank selection continues and
is explicitly recorded as lexical_fallback. It must not be described as semantic.

Setup in the activated project environment:

    python -m pip install -r requirements.txt
    python -m package.processing.embeddings

The second command explicitly downloads model weights into data/cache; it sends
no paper content for inference. Normal investigations load the model locally and
do not download it. Reporter/Planner/Critic hosted inference still has its separate
provider billing requirements. Windows may use copied cache files rather than
symlinks; this affects disk usage, not functionality.

Selected passages go to the Critic and Reporter with paper/source identifiers,
chunk index, evidence type and PDF page position. Prompt text is bounded to around
14,000 characters, so passages can be shortened further (flagged in the payload).
Harvard citations remain at paper level; PDF page provenance is displayed separately
in Ranked Sources and must not be mistaken for verified printed page numbering.
The Critic receives coverage and failure counts without new sufficiency thresholds.

Raw chunks and the per-run extraction cache live only in LangGraph state. PDFs
live in data/tmp/<run_id>/ and are removed after extraction, including failure
cleanup. FAISS indexes and embedding arrays are in memory only. Model weights
remain in gitignored data/cache. SQLite stores decisions, counts and selected
chunk provenance, never full chunk text. Existing abstract fields remain part of
saved paper metadata for compatibility. Existing saved reports retain defaults
for the new optional fields; the existing report_payload migration is unchanged.

Metrics count the current deduplicated corpus, not repeated work across replans.
Failure metadata and extracted chunks are reused within a run. fulltext_papers_resolved
counts successfully extracted papers. From the 13 September 2026 PDF fix,
pdf_extraction_failures counts failures after download, while fulltext_access_failures
counts URL resolution/download failures. Audit events include a safe reason,
failure stage and HTTP status where applicable. The actual downloaded PDF URL is
retained in passage provenance. Earlier saved reports, including Report 54, retain
their original broader extraction-failure counter; these records are not rewritten.
Runtime text is lost on process restart; there is no persistent vector database.

Verification includes generated PDFs, real FAISS with deterministic test embeddings,
a separate real local-embedding relevance test, abstract fallback, provenance,
page boundaries, redirects, non-PDF responses, duplicate handling, cached failures,
report persistence, UI labels and Git ignore checks. The example supplied with
this change uses real extraction/embeddings/FAISS and simulated discovery and LLM
responses, so it is reproducible without paid inference. It is not research evidence.

## Discovery and display refinements

Semantic Scholar is limited to six requests per investigation and stops after two
failures; HTTP 401, 403 or 429 stops it immediately. A later planned query can
recover after one transient failure. The policy persists across replanning; there
is no unbounded retry loop. Crossref remains available. Provider categories and
pause decisions are recorded without exception bodies or credentials.

Displayed timestamps use UTC yyyy-mm-dd hh:mm:ss; original ISO timestamps remain
in storage and machine-readable fields. Paper-specific RAG actions show the stable
paper identifier and, for new events, a short title. Ranked Sources displays the
same identifier, plain-text abstracts and explicit metadata-only exclusions.
Common US spellings in newly generated prose are normalised while preserving
citations and bibliographic metadata. Prompt guidance calls for proportionate
coverage assessments and supported claims, not minimum paper-count rules.
