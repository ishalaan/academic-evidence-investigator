def clean_json_response(content: str) -> str:
    """
    Remove common Markdown code fences from an LLM JSON response.

    LLMs may wrap otherwise valid JSON in Markdown fences even when instructed
    to return JSON only, so responses are normalised before parsing.
    """

    cleaned = content.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return cleaned.strip()