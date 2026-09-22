"""All disk artefacts live beneath a dedicated, gitignored runtime root."""
from pathlib import Path
import re
from package.config import PROJECT_ROOT

RUNTIME_ROOT = PROJECT_ROOT / "data" / "tmp"
MODEL_CACHE = PROJECT_ROOT / "data" / "cache" / "sentence_transformers"


def run_directory(run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Invalid runtime identifier")
    root = RUNTIME_ROOT.resolve()
    path = (root / run_id).resolve()
    # Check the resolved path as well as the identifier before creating files;
    # cleanup must remain confined to this run directory.
    if path.parent != root:
        raise ValueError("Runtime path escapes root")
    path.mkdir(parents=True, exist_ok=True)
    return path
