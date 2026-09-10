# Overview reports and ranked evidence

The report has three tabs:

- Overview: developed Summary, Findings, proportionate Limitations, and References
  containing only sources cited in that overview.
- Ranked Sources: all valid, unique records in descending relevance order, including
  records below the evidence filter and outside the writing evidence set. Each row
  shows its score, abstract, link and selection/citation status.
- Agent Activity: investigation metrics, Critic decisions and the complete worklog.

## Report depth and context limits

The Reporter writes one coherent Summary in a single request, then separate
Findings and Limitations. It no longer joins three overlapping summaries.
The Summary targets 450–650 words in 4–6 distinct thematic paragraphs; fewer are
appropriate for thin evidence. Findings provide study-level detail. Substantial
near-identical sentences trigger a bounded rewrite of only the current section.

Each request receives the same complete list of available evidence IDs. An old
retry instruction mentioning only [S1] was removed because it could be mistaken
for a restriction to that source. Retry prompts now enumerate every permitted ID.
Regression checks reject invented claims that the task restricts the report to a
single source. Evidence-supported negative findings are still allowed.

Abstract excerpts use a shared 15,000-character evidence budget. Requests have a
24,000-character input ceiling and a 2,400-token output allowance per section.
Character limits are a conservative engineering budget, not an exact token count.
Previous model conversations are not accumulated; a bounded excerpt of the summary
provides context for subsequent sections. Thinking is disabled for the Reporter. Up to two
correction attempts apply to the current section only. Short but valid sections
remain usable after advisory depth retries; the summary has no minimum-length retry. This takes more model calls than the
old one-shot report, but avoids squeezing the whole answer into one response.

The prose leads with supported applications, mechanisms, examples and comparisons.
General coverage caveats belong mainly in Limitations. A record without an abstract
does not invalidate other usable studies. If no usable abstracts exist at all,
the system does not invent findings from titles; it retains source records for
follow-up and explains the missing evidence briefly.

## Selection and traceability

Existing validation, deduplication and relevance filtering remain deterministic.
The writing set still has a ten-paper cap; among relevant records, papers with
abstracts are preferred and topical rank is preserved within each group. An exact
DOI duplicate can supply an abstract or publication fields missing from the first
record. Different DOI versions are not merged this way.

All valid unique papers retain their original topical ranking independently of the
writing set. A relevance score measures lexical matches, not scientific quality.
Citation IDs map selected records to report sources. Citations are validated and
formatted from retrieved metadata. Only IDs actually used in the report enter its
References; unused selected records remain in Ranked Sources.

Harvard formatting follows the Open University's Cite Them Right guide:
https://university.open.ac.uk/library/referencing-and-plagiarism/quick-guide-to-harvard-referencing-cite-them-right

Reference details are never invented. Available at links prefer DOI URLs; recorded
UTC retrieval dates are shown as Accessed dates, including on DOI entries as requested.
Access dates describe retrieval of metadata/abstracts, not reading the full text.
Complex author names and missing publication metadata may still require checking.

## Persistence and compatibility

SQLite gains an optional report_payload column, preserving old report rows. The
payload stores all ranking records, scores and citation IDs with the report. Older
reports keep their original text. Their complete ranking cannot be reconstructed:
the interface labels their saved evidence list accordingly. Old references are
matched conservatively to saved author-year citation text.

Verification covers section context budgets, explicit availability of all source
IDs, invented restriction rejection, reference filtering, ranking order, selection
status, duplicate metadata preservation, database migration and keyboard tabs.
