"""Plain-text presentation helpers; stored timestamps and metadata stay intact."""
from datetime import datetime, timezone
import html
import re


def display_timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return "Time unavailable"


def plain_abstract(value):
    return " ".join(re.sub(r"<[^>]*>", " ", html.unescape(value or "")).split())


def british_prose(text):
    replacements = {
        "personalized":"personalised", "personalization":"personalisation",
        "personalizes":"personalises", "personalizing":"personalising",
        "analyze":"analyse", "analyzes":"analyses", "analyzed":"analysed", "analyzing":"analysing",
        "emphasize":"emphasise", "emphasizes":"emphasises", "emphasized":"emphasised",
        "standardized":"standardised", "standardization":"standardisation",
        "generalizability":"generalisability", "generalizable":"generalisable",
        "localized":"localised", "specialized":"specialised", "marginalized":"marginalised",
        "judgment":"judgement", "judgments":"judgements", "rigor":"rigour",
        "prioritizing":"prioritising", "realizing":"realising", "organization":"organisation",
    }
    pattern = r"\b(" + "|".join(replacements) + r")\b"
    def substitute(match):
        word = match.group(0); new = replacements[word.lower()]
        return new.upper() if word.isupper() else new.capitalize() if word[0].isupper() else new
    # Preserve citations and source tokens; never alter source bibliographic metadata.
    parts = re.split(r"(\([^)]*\)|\[[^\]]*\])", text)
    return "".join(part if i % 2 else re.sub(pattern, substitute, part, flags=re.I) for i, part in enumerate(parts))
