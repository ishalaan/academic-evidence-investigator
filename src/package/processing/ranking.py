import re

from package.schemas import Paper


# Stop words are removed because they contribute little semantic value when
# comparing a research question with academic titles and abstracts.
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "which",
    "with",
}


# These terms describe the general LLM/AI topic rather than the research
# domain itself. Separating them prevents generic LLM papers from being ranked
# highly when they do not match the user's actual domain of interest.
GENERIC_LLM_TERMS = {
    "large",
    "language",
    "model",
    "models",
    "llm",
    "llms",
    "artificial",
    "intelligence",
    "generative",
    "ai",
    "applications",
    "application",
}


def _tokenise(text: str) -> set[str]:
    """
    Convert text into a compact set of useful lowercase terms.

    A simple deterministic tokenizer is used instead of another LLM call so
    ranking remains transparent, reproducible, inexpensive, and easy to test.
    """

    words = re.findall(r"[a-zA-Z0-9]+", text.lower())

    return {
        word
        for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def _question_terms(
    research_question: str,
) -> tuple[set[str], set[str]]:
    """
    Split the research question into overall and domain-specific terminology.

    This keeps the relevance logic generic. For example, the same algorithm can
    distinguish education, healthcare, finance, law, or another domain without
    hard-coding a particular demonstration question.
    """

    all_terms = _tokenise(research_question)

    # Removing generic AI/LLM terminology leaves the terms that are more likely
    # to express the specific research domain or context selected by the user.
    domain_terms = {
        term
        for term in all_terms
        if term not in GENERIC_LLM_TERMS
    }

    return all_terms, domain_terms


def _relevance_score(
    paper: Paper,
    research_question: str,
) -> tuple[int, int, int]:
    """
    Calculate a deterministic relevance score for a retrieved paper.

    Title matches are weighted more strongly than abstract matches because a
    title is normally a stronger indicator of the publication's central topic.
    Domain-specific matches receive additional weight so broadly related LLM
    papers do not dominate results purely through generic terminology.

    Abstract availability and publication year are used only as secondary
    tie-break signals after topical relevance.
    """

    all_terms, domain_terms = _question_terms(research_question)

    title_terms = _tokenise(paper.title)
    abstract_terms = _tokenise(paper.abstract or "")

    title_matches = len(all_terms & title_terms)
    abstract_matches = len(all_terms & abstract_terms)

    domain_title_matches = len(domain_terms & title_terms)
    domain_abstract_matches = len(domain_terms & abstract_terms)

    # Explicit weighting makes the ranking rule inspectable and reproducible,
    # unlike asking an LLM to make an opaque ranking decision for every paper.
    relevance = (
        (title_matches * 3)
        + abstract_matches
        + (domain_title_matches * 5)
        + (domain_abstract_matches * 2)
    )

    # These values are returned as secondary sort keys so papers with equal
    # relevance favour richer metadata and then newer publication dates.
    has_abstract = 1 if paper.abstract else 0
    year = paper.year or 0

    return relevance, has_abstract, year


def rank_papers(
    papers: list[Paper],
    research_question: str,
) -> list[Paper]:
    """
    Rank papers by deterministic relevance to the research question.

    Deterministic ranking was preferred because it is explainable, testable,
    and avoids unnecessary dependence on the LLM for low-level evidence
    processing.
    """

    return sorted(
        papers,
        key=lambda paper: _relevance_score(
            paper,
            research_question,
        ),
        reverse=True,
    )


def filter_relevant_papers(
    papers: list[Paper],
    research_question: str,
    minimum_score: int = 6,
) -> list[Paper]:
    """
    Retain papers that meet both topical and domain-specific relevance rules.

    The minimum threshold prevents weakly related records from entering the
    evidence set, while the domain-term check prevents generic LLM papers from
    qualifying purely because they contain common AI terminology.
    """

    _, domain_terms = _question_terms(research_question)

    relevant: list[Paper] = []

    for paper in papers:
        score = _relevance_score(
            paper,
            research_question,
        )[0]

        # The threshold provides a transparent minimum quality gate before
        # evidence reaches the Critic and Reporter.
        if score < minimum_score:
            continue

        if domain_terms:
            paper_terms = _tokenise(
                f"{paper.title} {paper.abstract or ''}"
            )

            # Requiring at least one domain-specific match makes the filter
            # responsive to the user's question without hard-coding any
            # particular subject area.
            if not domain_terms.intersection(paper_terms):
                continue

        relevant.append(paper)

    return relevant