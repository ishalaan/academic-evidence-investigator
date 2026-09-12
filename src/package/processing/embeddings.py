"""Local sentence embeddings; model downloads are an explicit setup step."""
from functools import lru_cache
import numpy as np
from package.rag.runtime import MODEL_CACHE

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_model():
    if not MODEL_CACHE.exists():
        raise OSError("Local embedding model is not installed")
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME, cache_folder=str(MODEL_CACHE),
                               local_files_only=True, device="cpu")


def encode(texts):
    model = get_model()
    # MiniLM has a short context: embed subwindows then average, rather than
    # silently truncating each approximately 1,000-token evidence chunk.
    vectors = []
    for text in texts:
        tokens = model.tokenizer.encode(text, add_special_tokens=False)
        windows = [model.tokenizer.decode(tokens[i:i + 200]) for i in range(0, len(tokens), 180)] or [""]
        parts = model.encode(windows, normalize_embeddings=True, show_progress_bar=False)
        vector = np.mean(parts, axis=0)
        vectors.append(vector / max(float(np.linalg.norm(vector)), 1e-12))
    return np.asarray(vectors, dtype="float32")


if __name__ == "__main__":
    # Explicit setup command; downloads model weights only, no research content.
    from package.services.llm import create_http_client
    from huggingface_hub import set_client_factory
    set_client_factory(create_http_client)
    from sentence_transformers import SentenceTransformer
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    SentenceTransformer(MODEL_NAME, cache_folder=str(MODEL_CACHE), device="cpu")
    print("Local embedding model ready in the runtime cache.")
