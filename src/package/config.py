from pathlib import Path
import os

from dotenv import load_dotenv


# Resolve paths from the package so launching from another directory still
# finds the same configuration and saved data.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


HF_TOKEN = os.getenv("HF_TOKEN")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

# Bound the search even when the Critic keeps asking for stronger evidence.
MAX_SEARCH_CYCLES = 3
MAX_RESULTS_PER_QUERY = 10