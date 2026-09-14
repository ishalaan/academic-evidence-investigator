"""Deterministic Harvard citations from retrieved metadata, never model metadata."""

from collections import defaultdict
import re
from urllib.parse import quote, urlsplit

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def without_title(name):
    return re.sub(r'^(?:(?:dr|prof|professor|doctor)\.?\s+)+', '', name.strip(), flags=re.I)


def author_parts(paper):
    if paper.author_details and len(paper.author_details) == len(paper.authors):
        return [(without_title(a.family or a.given), without_title(a.given) if a.family else "") for a in paper.author_details]
    parts = []
    for name in paper.authors:
        name = without_title(name)
        if not name:
            continue
        if "," in name:
            family, given = name.split(",", 1)
        else:
            words = name.split()
            family, given = words[-1], " ".join(words[:-1])
        parts.append((family.strip(), given.strip()))
    return parts


def join_authors(names):
    if len(names) > 3:
        return names[0] + " et al."
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]


def author_label(paper, *, initials=False):
    parts = author_parts(paper)
    if not parts:
        return paper.title
    names = []
    for family, given in parts:
        letters = "".join(word[0].upper() + "." for word in re.findall(r"[^\W\d_]+", given, re.UNICODE))
        names.append(f"{family}, {letters}" if initials and letters else family)
    return join_authors(names)


def source_url(paper):
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", (paper.doi or "").strip(), flags=re.I)
    if re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return "https://doi.org/" + quote(doi, safe="/():;._-")
    url = (paper.url or "").strip()
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
            return url
    except ValueError:
        pass
    return None


def reference_entries(papers):
    entries = []
    groups = defaultdict(list)
    for index, paper in enumerate(papers, 1):
        label = author_label(paper)
        year = str(paper.year) if paper.year is not None else "no date"
        entry = {"id": f"S{index}", "paper": paper, "author": label, "year": year}
        entries.append(entry)
        groups[(label.casefold(), year)].append(entry)
    for group in groups.values():
        if len(group) > 1:
            for index, entry in enumerate(sorted(group, key=lambda e: (e["paper"].title.casefold(), e["id"]))):
                entry["year"] += (" " if entry["year"] == "no date" else "") + chr(ord("a") + index)
    for entry in entries:
        paper = entry["paper"]
        entry["citation"] = f"({entry['author']}, {entry['year']})"
        entry["sort_key"] = f"{entry['author']} {entry['year']} {paper.title}".casefold()
        author = author_label(paper, initials=True)
        entry["opening"] = (f"{author} ({entry['year']}) ‘{paper.title}’" if author_parts(paper)
                            else f"‘{paper.title}’ ({entry['year']})")
        publication = paper.volume or ""
        if paper.issue:
            publication += f"({paper.issue})"
        if paper.article_number:
            publication += (", " if publication else "") + f"article {paper.article_number}"
        elif paper.pages:
            page_label = "pp." if re.search(r"[-–]", paper.pages) else "p."
            publication += (", " if publication else "") + f"{page_label} {paper.pages}"
        entry["publication"] = publication
        entry["url"] = source_url(paper)
        entry["access_date"] = (f"{paper.accessed_on.day} {MONTHS[paper.accessed_on.month - 1]} {paper.accessed_on.year}"
                                if paper.accessed_on else None)
    return entries


def normalise_source_tokens(text):
    text = re.sub(r"\(\s*s\d+(?:\s*[,;]\s*s\d+)*\s*\)",
                  lambda m: " ".join(f"[{token.upper()}]" for token in re.findall(r"s\d+", m.group(0), re.I)),
                  text, flags=re.I)
    return re.sub(r"\[\s*s\d+(?:\s*[,;]\s*s\d+)*\s*\]",
                  lambda m: " ".join(f"[{token.upper()}]" for token in re.findall(r"s\d+", m.group(0), re.I)),
                  text, flags=re.I)



def resolve_known_citations(text, entries):
    """Resolve only unique metadata matches, never infer an author or year."""
    def key(value):
        value = value.casefold().replace('&', ' and ')
        return re.sub(r'[\s,.]+', '', value)
    lookup = defaultdict(list)
    for entry in entries:
        lookup[key(entry['citation'][1:-1])].append(entry['id'])
    def replace(match):
        parts = match.group(1).split(';')
        ids = [lookup.get(key(part), []) for part in parts]
        if ids and all(len(found) == 1 for found in ids):
            return ' '.join('[' + found[0] + ']' for found in ids)
        return match.group(0)
    return re.sub(r'\(([^()]*)\)', replace, normalise_source_tokens(text))

def used_source_ids(text, entries):
    text = resolve_known_citations(text, entries)
    valid = {entry["id"] for entry in entries}
    bracket_text = " ".join(re.findall(r"\[([^\]]+)\]", text))
    used = set(re.findall(r"\bS\d+\b", bracket_text)) & valid
    used.update(entry["id"] for entry in entries if entry["citation"] in text)
    return used


def report_references(report):
    entries = reference_entries(report.sources)
    if report.cited_source_ids is None:
        # Legacy reports did not preserve source IDs; do not invent citation use.
        text = " ".join([report.summary, *report.findings, *report.limitations])
        return [entry for entry in entries if entry["citation"][1:-1] in text]
    return [entry for entry in entries if entry["id"] in report.cited_source_ids]


def cited_text(text, entries, *, require_citation=False):
    """Resolve validated source tokens. Never fabricate a citation for uncited prose."""
    text = resolve_known_citations(text, entries)
    lookup = {entry["id"]: entry["citation"] for entry in entries}
    if re.search(r"(?<!\[)\bS\d+\b(?!\])", text):
        raise ValueError("Reporter returned an invalid source citation.")
    # Accept ordinary model variations without guessing which source was intended.
    text = re.sub(r"\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]",
                  lambda match: " ".join(f"[{source_id}]" for source_id in re.findall(r"S\d+", match.group(0))), text)
    # A numeric date/range alone is not an author-year citation.
    if re.search(r"\([^)]*[^\W\d_][^)]*(?:\b(?:19|20)\d{2}[a-z]?\b|no date)[^)]*\)", text, flags=re.I):
        raise ValueError("Reporter must use source IDs instead of author-year citations.")
    tokens = re.findall(r"\[(S\d+)\]", text)
    if any(token not in lookup for token in tokens):
        raise ValueError("Reporter cited an unknown source identifier.")
    if require_citation:
        for paragraph in text.split("\n\n"):
            if re.fullmatch(r"\s*#{1,6} [^\n]+\s*", paragraph):
                continue
            if paragraph.strip() and not re.search(r"\[S\d+\]", paragraph):
                raise ValueError("Reporter omitted a supporting source citation.")
    def citation_group(match):
        ids = list(dict.fromkeys(re.findall(r"\[(S\d+)\]", match.group(0))))
        return "(" + "; ".join(lookup[source_id][1:-1] for source_id in ids) + ")"

    result = re.sub(r"\[S\d+\](?:[ \t]*\[S\d+\])*", citation_group, text)
    if re.search(r"\[S[^\]]*\]", result):
        raise ValueError("Reporter returned an invalid source citation.")
    return result
