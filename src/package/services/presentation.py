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
    return " ".join(re.sub(r"</?[A-Za-z][A-Za-z0-9:._-]*(?:\s+[^<>]*?)?\s*/?>", " ", html.unescape(value or "")).split())


def british_prose(text):
    replacements = {
        "organize":"organise", "organizes":"organises", "organized":"organised", "organizing":"organising",
        "personalize":"personalise",
        "democratize":"democratise", "democratizes":"democratises", "democratizing":"democratising",
        "recognize":"recognise", "recognized":"recognised", "recognizes":"recognises", "recognizing":"recognising",
        "customization":"customisation", "customized":"customised", "customize":"customise",
        "maximize":"maximise", "maximizes":"maximises", "maximized":"maximised", "maximizing":"maximising",
        "emphasizing":"emphasising", "optimize":"optimise", "optimized":"optimised", "optimizing":"optimising",
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
    # Educational programmes; preserve the computing sense of 'program'.
    text = re.sub(r"\b(training|education|educational|degree|academic) programs\b", r"\1 programmes", text, flags=re.I)
    pattern = r"\b(" + "|".join(replacements) + r")\b"
    def substitute(match):
        word = match.group(0); new = replacements[word.lower()]
        return new.upper() if word.isupper() else new.capitalize() if word[0].isupper() else new
    # Preserve citations and source tokens; never alter source bibliographic metadata.
    parts = re.split(r"(\([^)]*\)|\[[^\]]*\])", text)
    return "".join(part if i % 2 else re.sub(pattern, substitute, part, flags=re.I) for i, part in enumerate(parts))
