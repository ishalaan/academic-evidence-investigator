"""Deterministic Harvard citations from retrieved metadata, never model metadata."""

from collections import defaultdict
import re
from urllib.parse import quote, urlsplit

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def author_parts(paper):
    if paper.author_details and len(paper.author_details) == len(paper.authors):
        return [(a.family or a.given, a.given if a.family else "") for a in paper.author_details]
    parts = []
    for name in paper.authors:
        name = name.strip()
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
        letters = "".join(word[0].upper() + "." for word in re.split(r"[\s.\-]+", given) if word)
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
                entry["year"] += chr(ord("a") + index)
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
        if paper.pages:
            page_label = "pp." if re.search(r"[-–]", paper.pages) else "p."
            publication += (", " if publication else "") + f"{page_label} {paper.pages}"
        elif paper.article_number:
            publication += (", " if publication else "") + f"article {paper.article_number}"
        entry["publication"] = publication
        entry["url"] = source_url(paper)
        entry["access_date"] = (f"{paper.accessed_on.day} {MONTHS[paper.accessed_on.month - 1]} {paper.accessed_on.year}"
                                if paper.accessed_on else None)
    return entries


def cited_text(text, entries, *, require_citation=False):
    """Resolve validated source tokens. Never fabricate a citation for uncited prose."""
    lookup = {entry["id"]: entry["citation"] for entry in entries}
    if re.search(r"\([^)]*(?:\b(?:19|20)\d{2}[a-z]?\b|no date)[^)]*\)", text, flags=re.I):
        raise ValueError("Reporter must use source IDs instead of author-year citations.")
    tokens = re.findall(r"\[(S\d+)\]", text)
    if any(token not in lookup for token in tokens):
        raise ValueError("Reporter cited an unknown source identifier.")
    if require_citation:
        for paragraph in text.split("\n\n"):
            if paragraph.strip() and not re.search(r"\[S\d+\]", paragraph):
                raise ValueError("Reporter omitted a supporting source citation.")
    def citation_group(match):
        ids = list(dict.fromkeys(re.findall(r"\[(S\d+)\]", match.group(0))))
        return "(" + "; ".join(lookup[source_id][1:-1] for source_id in ids) + ")"

    result = re.sub(r"\[S\d+\](?:[ \t]+\[S\d+\])*", citation_group, text)
    if re.search(r"\[S[^\]]*\]", result):
        raise ValueError("Reporter returned an invalid source citation.")
    return result
