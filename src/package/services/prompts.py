from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(filename: str) -> str:
    """
    Load a prompt template from the package prompts directory.

    Keeping prompt loading in one place avoids duplicating file-path logic
    across multiple agents.
    """

    prompt_path = PROMPTS_DIR / filename

    return prompt_path.read_text(encoding="utf-8")