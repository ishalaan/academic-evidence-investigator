# Detailed reports and Harvard referencing

New investigations request a developed summary of 600–900 words and 5–8 findings
where supported by the available evidence. Sparse evidence should produce a
shorter, qualified answer rather than padding. The Reporter output allowance is
6,000 tokens. The model determines the prose; the application determines the
bibliographic formatting.

The six report tabs are Summary, Findings, Limitations, Sources, Investigation
and Audit, and Activity Log. Each has its own panel. The tab controls support
arrow keys, Home and End. All sections remain readable without JavaScript.

## Citation integrity

The Reporter receives stable source IDs (`S1`, `S2`, …) for its supplied evidence.
It places tokens such as `[S1]` at supported claims. The application checks IDs,
requires citations in each summary paragraph and finding, and converts valid
tokens into author-year citations. Adjacent tokens become a semicolon-separated
group. Grouped forms such as `[S1, S2]` and exact known author-year citations are
normalised without guessing sources. Unknown, malformed or missing required
tokens trigger up to two correction attempts before the reporting stage fails.
Malformed, empty and truncated JSON responses also receive correction attempts.
Qwen thinking is explicitly disabled for the Reporter so the output allowance
is available for the final report. The system does not silently attach arbitrary sources to
uncited text. General limitations of the investigation need not be cited.

Correction attempts are recorded in the activity log. Terminal failures store
safe error categories and show an actionable reporting error in the browser;
private model output and provider exception text are not exposed.

Citation validation establishes that referenced sources exist; it does not prove
that a source supports every claim. Human review is still needed. The prompt
requires cautious paraphrases of retrieved abstracts and prohibits invented
results, quotations, page locators and claims of having read full texts.

## Reference formatting

Formatting follows the Open University's Harvard Cite Them Right guidance:
https://university.open.ac.uk/library/referencing-and-plagiarism/quick-guide-to-harvard-referencing-cite-them-right

- Surname and year in text; first author plus et al. for four or more authors.
- Author surname and initials, year, article title, italic journal title, volume,
  issue, page range or article number where provided.
- Alphabetical source list and consistent a/b year suffixes for ambiguous labels.
- Available at links use a DOI URL where available, otherwise a supplied HTTP(S)
  link. An Accessed date is included when recorded, including for DOI links as
  requested. Cite Them Right normally does not require access dates for DOIs.
- Missing authors fall back to the title; missing years use “no date”. Missing
  journal, page, link or access-date information is not fabricated.

Crossref structured given/family names are retained for accurate author formatting.
Where an adapter only supplies display names, surname/initial parsing is a best
effort and complex or organisational names may require manual correction.
References are formatted from available metadata; source types other than journal
articles and incomplete records may require further bibliographic checking.

Access dates are recorded in UTC when provider metadata is retrieved and stored
on the Paper object in the existing SQLite JSON source field. They reflect access
to metadata/abstracts, not proof that linked full texts were read. Reopening a
report does not change them. Existing reports continue to load with their original
text and show “Access date not recorded” when that field was not stored. Start a
new investigation to obtain the expanded answer and in-text citations.
